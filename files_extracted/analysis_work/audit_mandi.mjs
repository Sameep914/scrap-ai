import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI/files_extracted/SBIP_Model_Clean.xlsx";
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const values = workbook.worksheets.getItem("Mandi Master").getRange("A1:N607").values;

const headers = values[0].map(String);
const rows = values.slice(1).map((row) => {
  const out = {};
  headers.forEach((header, i) => { out[header] = row[i]; });
  return out;
});

const num = (value) => value === null || value === "" || value === undefined ? null : Number(value);
const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
const sd = (xs, sample = false) => {
  const m = mean(xs);
  const denom = xs.length - (sample ? 1 : 0);
  return Math.sqrt(xs.reduce((sum, x) => sum + (x - m) ** 2, 0) / denom);
};

const parsed = rows.map((row, index) => {
  const date = new Date(`${row.Date}T00:00:00Z`);
  const plateValues = ["14ANI", "12ANI", "10ANI", "8ANI", "6ANI"].map((h) => num(row[h])).filter((v) => v !== null);
  const meltValues = ["1kgr", "Att", "Melt"].map((h) => num(row[h])).filter((v) => v !== null);
  const eight = num(row["8ANI"]);
  const melt = num(row.Melt);
  return {
    index,
    date,
    eight,
    melt,
    dd: num(row["8ANI d/d"]),
    eightMelt: eight !== null && melt !== null ? eight - melt : null,
    composite: plateValues.length === 5 && meltValues.length === 3 ? mean(plateValues) - mean(meltValues) : null,
  };
});

let lastMelt = null;
let lastOneKgr = null;
let lastAtt = null;
const filled = parsed.map((row) => {
  if (row.melt !== null) lastMelt = row.melt;
  const original = rows[row.index];
  const oneKgr = num(original["1kgr"]);
  const att = num(original.Att);
  if (oneKgr !== null) lastOneKgr = oneKgr;
  if (att !== null) lastAtt = att;
  const melt = row.melt ?? lastMelt;
  const plateValues = ["14ANI", "12ANI", "10ANI", "8ANI", "6ANI"].map((h) => num(original[h]));
  const meltValues = [oneKgr ?? lastOneKgr, att ?? lastAtt, melt];
  return {
    ...row,
    melt,
    eightMelt: row.eight !== null && melt !== null ? row.eight - melt : null,
    composite: plateValues.every((v) => v !== null) && meltValues.every((v) => v !== null)
      ? mean(plateValues) - mean(meltValues)
      : null,
  };
});

const nonMissing = Object.fromEntries(headers.map((header) => [
  header,
  rows.filter((row) => row[header] !== null && row[header] !== "" && row[header] !== undefined).length,
]));

let duplicates = 0;
let nonIncreasing = 0;
let ddMismatches = 0;
let hundredStepViolations = 0;
for (let i = 0; i < parsed.length; i++) {
  if (i > 0) {
    if (parsed[i].date.getTime() === parsed[i - 1].date.getTime()) duplicates++;
    if (parsed[i].date <= parsed[i - 1].date) nonIncreasing++;
    if (parsed[i].eight !== null && parsed[i - 1].eight !== null && parsed[i].dd !== null && parsed[i].dd !== parsed[i].eight - parsed[i - 1].eight) ddMismatches++;
  }
  for (const header of headers.slice(2, 13)) {
    const v = num(rows[i][header]);
    if (v !== null && v % 100 !== 0) hundredStepViolations++;
  }
}

const zeroMoves = parsed.slice(1).filter((r) => r.dd === 0).length;
const datedRows = parsed.filter((r) => !Number.isNaN(r.date.getTime()));

function rollingZ(field, window, sample = false, data = parsed) {
  const result = Array(data.length).fill(null);
  for (let i = window - 1; i < data.length; i++) {
    const xs = data.slice(i - window + 1, i + 1).map((r) => r[field]);
    if (xs.some((x) => x === null)) continue;
    const sigma = sd(xs, sample);
    result[i] = sigma === 0 ? null : (data[i][field] - mean(xs)) / sigma;
  }
  return result;
}

function signalStats(field, horizon, zThreshold = 1, data = parsed) {
  const z = rollingZ(field, 60, false, data);
  const all = [];
  for (let i = 59; i + horizon < data.length; i++) {
    if (z[i] === null || data[i].eight === null || data[i + horizon].eight === null) continue;
    all.push({ i, z: z[i], ret: data[i + horizon].eight / data[i].eight - 1 });
  }
  const rich = all.filter((x) => x.z > zThreshold);
  const cheap = all.filter((x) => x.z < -zThreshold);
  const summarize = (xs, direction) => ({
    nOverlapping: xs.length,
    meanReturn: xs.length ? mean(xs.map((x) => x.ret)) : null,
    directionalHit: xs.length ? xs.filter((x) => direction === "down" ? x.ret < 0 : x.ret > 0).length / xs.length : null,
  });
  const purged = (xs) => {
    const selected = [];
    let last = -Infinity;
    for (const x of xs) {
      if (x.i - last >= horizon) {
        selected.push(x);
        last = x.i;
      }
    }
    return selected;
  };
  return {
    horizon,
    rich: { ...summarize(rich, "down"), purged: summarize(purged(rich), "down") },
    cheap: { ...summarize(cheap, "up"), purged: summarize(purged(cheap), "up") },
  };
}

const zEight = rollingZ("eightMelt", 60, false);
const zComposite = rollingZ("composite", 60, false);
const zEightSample = rollingZ("eightMelt", 60, true);
const zEightFilled = rollingZ("eightMelt", 60, false, filled);
const zEightFilledSample = rollingZ("eightMelt", 60, true, filled);
const zCompositeFilled = rollingZ("composite", 60, false, filled);
const last = parsed.length - 1;

console.log(JSON.stringify({
  rowCount: parsed.length,
  sampleTypes: Object.fromEntries(headers.map((header) => [header, typeof rows[0][header]])),
  firstDate: datedRows[0].date.toISOString().slice(0, 10),
  lastDate: datedRows.at(-1).date.toISOString().slice(0, 10),
  nonMissing,
  duplicates,
  nonIncreasing,
  ddMismatches,
  hundredStepViolations,
  zeroMoves,
  zeroMoveRate: zeroMoves / (parsed.length - 1),
  latest: {
    eight: parsed[last].eight,
    melt: parsed[last].melt,
    eightMeltSpread: parsed[last].eightMelt,
    compositeSpread: parsed[last].composite,
    eightMeltZ60Population: zEight[last],
    eightMeltZ60Sample: zEightSample[last],
    eightMeltZ60PopulationForwardFilled: zEightFilled[last],
    eightMeltZ60SampleForwardFilled: zEightFilledSample[last],
    compositeZ60Population: zComposite[last],
    compositeZ60PopulationForwardFilled: zCompositeFilled[last],
  },
  signalChecks: [20, 30, 40].map((h) => signalStats("eightMelt", h)),
  signalChecksForwardFilled: [20, 30, 40].map((h) => signalStats("eightMelt", h, 1, filled)),
  compositeSignalChecksForwardFilled: [20, 30, 40].map((h) => signalStats("composite", h, 1, filled)),
}, null, 2));
