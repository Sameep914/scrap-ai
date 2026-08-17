import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const csvPath = "C:/Users/demos/Downloads/c-u26_price-history-08-12-2026.csv";
const workbookPath = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI/files_extracted/SBIP_Model_Clean.xlsx";

const DAY_MS = 86_400_000;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const horizons = [5, 10, 15, 30, 45, 60, 90];

const toIso = (date) => date.toISOString().slice(0, 10);
const parseDate = (value) => {
  const text = String(value ?? "").trim();
  return ISO_DATE.test(text) ? new Date(`${text}T00:00:00Z`) : null;
};
const numberOrNull = (value) => {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const parsed = Number(String(value).replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
};
const mean = (xs) => xs.length ? xs.reduce((sum, x) => sum + x, 0) / xs.length : null;
const median = (xs) => quantile(xs, 0.5);
function quantile(xs, p) {
  if (!xs.length) return null;
  const sorted = [...xs].sort((a, b) => a - b);
  const h = (sorted.length - 1) * p;
  const lo = Math.floor(h);
  const hi = Math.ceil(h);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (h - lo);
}
function sd(xs, sample = true) {
  if (xs.length < (sample ? 2 : 1)) return null;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((sum, x) => sum + (x - m) ** 2, 0) / (xs.length - (sample ? 1 : 0)));
}
function skewness(xs) {
  if (xs.length < 3) return null;
  const m = mean(xs);
  const s = sd(xs, false);
  return s === 0 ? 0 : mean(xs.map((x) => ((x - m) / s) ** 3));
}
function excessKurtosis(xs) {
  if (xs.length < 4) return null;
  const m = mean(xs);
  const s = sd(xs, false);
  return s === 0 ? 0 : mean(xs.map((x) => ((x - m) / s) ** 4)) - 3;
}
function pearson(xs, ys) {
  if (xs.length !== ys.length || xs.length < 3) return null;
  const mx = mean(xs);
  const my = mean(ys);
  const numerator = xs.reduce((sum, x, i) => sum + (x - mx) * (ys[i] - my), 0);
  const denom = Math.sqrt(
    xs.reduce((sum, x) => sum + (x - mx) ** 2, 0) *
    ys.reduce((sum, y) => sum + (y - my) ** 2, 0),
  );
  return denom === 0 ? null : numerator / denom;
}
function autocorrelation(xs, lag) {
  if (xs.length <= lag + 2) return null;
  return pearson(xs.slice(lag), xs.slice(0, -lag));
}
function pct(value, total) {
  return total ? value / total : null;
}
function dateDiff(a, b) {
  return Math.round((a - b) / DAY_MS);
}
function longestRuns(rows, predicate, labelFn = () => null, limit = 8) {
  const runs = [];
  let start = null;
  for (let i = 0; i <= rows.length; i++) {
    const active = i < rows.length && predicate(rows[i], i);
    if (active && start === null) start = i;
    if (!active && start !== null) {
      const end = i - 1;
      runs.push({
        start: toIso(rows[start].date),
        end: toIso(rows[end].date),
        sessions: end - start + 1,
        calendarDays: dateDiff(rows[end].date, rows[start].date) + 1,
        label: labelFn(rows[start], rows[end]),
      });
      start = null;
    }
  }
  return runs.sort((a, b) => b.sessions - a.sessions || a.start.localeCompare(b.start)).slice(0, limit);
}
function longestEqualValueRuns(rows, valueFn, limit = 8) {
  const runs = [];
  let start = 0;
  for (let i = 1; i <= rows.length; i++) {
    if (i < rows.length && valueFn(rows[i]) === valueFn(rows[i - 1])) continue;
    const end = i - 1;
    if (end > start) {
      runs.push({
        start: toIso(rows[start].date),
        end: toIso(rows[end].date),
        sessions: end - start + 1,
        calendarDays: dateDiff(rows[end].date, rows[start].date) + 1,
        value: valueFn(rows[start]),
      });
    }
    start = i;
  }
  return runs.sort((a, b) => b.sessions - a.sessions || a.start.localeCompare(b.start)).slice(0, limit);
}
function summary(xs) {
  return {
    n: xs.length,
    mean: mean(xs),
    median: median(xs),
    sd: sd(xs),
    min: xs.length ? Math.min(...xs) : null,
    p01: quantile(xs, 0.01),
    p05: quantile(xs, 0.05),
    p25: quantile(xs, 0.25),
    p75: quantile(xs, 0.75),
    p95: quantile(xs, 0.95),
    p99: quantile(xs, 0.99),
    max: xs.length ? Math.max(...xs) : null,
  };
}

const csvText = await fs.readFile(csvPath, "utf8");
const csvWorkbook = await Workbook.fromCSV(csvText, { sheetName: "Turkey" });
const csvValues = csvWorkbook.worksheets.getItem("Turkey").getUsedRange().values;
const csvHeaders = csvValues[0].map((value) => String(value));
const rawCsvRows = csvValues.slice(1).map((row) => Object.fromEntries(csvHeaders.map((header, i) => [header, row[i]])));
const footerRows = rawCsvRows.filter((row) => !parseDate(row.Time));

const turkey = rawCsvRows
  .filter((row) => parseDate(row.Time))
  .map((row) => ({
    date: parseDate(row.Time),
    open: numberOrNull(row.Open),
    high: numberOrNull(row.High),
    low: numberOrNull(row.Low),
    close: numberOrNull(row.Latest),
    change: numberOrNull(row.Change),
    percentChange: numberOrNull(String(row["%Change"] ?? "").replace("%", "")),
    volume: numberOrNull(row.Volume),
    openInterest: numberOrNull(row["Open Int"]),
  }))
  .sort((a, b) => a.date - b.date);

for (let i = 0; i < turkey.length; i++) {
  const row = turkey[i];
  row.return = i ? row.close / turkey[i - 1].close - 1 : null;
  row.priceChange = i ? row.close - turkey[i - 1].close : null;
  row.priceUnchanged = i ? row.close === turkey[i - 1].close : null;
  row.zeroRange = row.high === row.low;
  row.oiUnchanged = i ? row.openInterest === turkey[i - 1].openInterest : null;
}

const fieldNames = ["open", "high", "low", "close", "change", "percentChange", "volume", "openInterest"];
const missingness = Object.fromEntries(fieldNames.map((field) => [field, turkey.filter((row) => row[field] === null).length]));
const dateCounts = new Map();
for (const row of turkey) dateCounts.set(toIso(row.date), (dateCounts.get(toIso(row.date)) ?? 0) + 1);
const duplicateDates = [...dateCounts].filter(([, count]) => count > 1).map(([date, count]) => ({ date, count }));

const weekdayDates = [];
for (let date = new Date(turkey[0].date); date <= turkey.at(-1).date; date = new Date(date.getTime() + DAY_MS)) {
  if (date.getUTCDay() >= 1 && date.getUTCDay() <= 5) weekdayDates.push(toIso(date));
}
const actualDateSet = new Set(turkey.map((row) => toIso(row.date)));
const absentWeekdays = weekdayDates.filter((date) => !actualDateSet.has(date));
const calendarGaps = turkey.slice(1).map((row, i) => ({
  prior: toIso(turkey[i].date),
  next: toIso(row.date),
  calendarDays: dateDiff(row.date, turkey[i].date),
})).filter((gap) => gap.calendarDays > 3).sort((a, b) => b.calendarDays - a.calendarDays || a.prior.localeCompare(b.prior));

const ohlcViolations = turkey.filter((row) =>
  row.high < Math.max(row.open, row.close, row.low) ||
  row.low > Math.min(row.open, row.close, row.high),
);
const nonHalfTickValues = turkey.flatMap((row) => [row.open, row.high, row.low, row.close])
  .filter((value) => value !== null && Math.abs(value * 2 - Math.round(value * 2)) > 1e-9);
const changeMismatches = turkey.slice(1).filter((row) => Math.abs(row.change - row.priceChange) > 1e-9);
const percentChangeMismatches = turkey.filter((row) => {
  const prior = row.close - row.change;
  const expected = prior === 0 ? null : 100 * row.change / prior;
  return expected !== null && Math.abs(row.percentChange - expected) > 0.011;
});

const returns = turkey.slice(1).map((row) => row.return);
const positiveVolumeReturns = turkey.slice(1).filter((row) => row.volume > 0).map((row) => row.return);
const zeroVolumeReturns = turkey.slice(1).filter((row) => row.volume === 0).map((row) => row.return);
const largestMoves = turkey.slice(1)
  .map((row) => ({ date: toIso(row.date), close: row.close, change: row.priceChange, return: row.return, volume: row.volume, openInterest: row.openInterest }))
  .sort((a, b) => Math.abs(b.return) - Math.abs(a.return))
  .slice(0, 12);

function rowSummary(rows) {
  const validReturns = rows.map((row) => row.return).filter((value) => value !== null);
  return {
    n: rows.length,
    start: rows.length ? toIso(rows[0].date) : null,
    end: rows.length ? toIso(rows.at(-1).date) : null,
    positiveVolumeDays: rows.filter((row) => row.volume > 0).length,
    positiveVolumeRate: pct(rows.filter((row) => row.volume > 0).length, rows.length),
    totalVolume: rows.reduce((sum, row) => sum + row.volume, 0),
    medianVolume: median(rows.map((row) => row.volume)),
    p90Volume: quantile(rows.map((row) => row.volume), 0.9),
    medianOpenInterest: median(rows.map((row) => row.openInterest)),
    maxOpenInterest: rows.length ? Math.max(...rows.map((row) => row.openInterest)) : null,
    unchangedCloseRate: pct(rows.filter((row) => row.priceUnchanged === true).length, validReturns.length),
    zeroRangeRate: pct(rows.filter((row) => row.zeroRange).length, rows.length),
    meanAbsoluteReturn: validReturns.length ? mean(validReturns.map(Math.abs)) : null,
    returnVolatility: sd(validReturns),
  };
}

const oiRegimes = [
  ["OI=0", (row) => row.openInterest === 0],
  ["OI 1-9", (row) => row.openInterest >= 1 && row.openInterest <= 9],
  ["OI 10-99", (row) => row.openInterest >= 10 && row.openInterest <= 99],
  ["OI 100-499", (row) => row.openInterest >= 100 && row.openInterest <= 499],
  ["OI 500-999", (row) => row.openInterest >= 500 && row.openInterest <= 999],
  ["OI 1000+", (row) => row.openInterest >= 1000],
].map(([name, filter]) => ({ name, ...rowSummary(turkey.filter(filter)) }));

const firstDateWhere = (predicate) => {
  const row = turkey.find(predicate);
  return row ? toIso(row.date) : null;
};
function earliestTrailingEligibility({ window = 20, positiveVolumeRate, medianOpenInterest }) {
  for (let i = window - 1; i < turkey.length; i++) {
    const trailing = turkey.slice(i - window + 1, i + 1);
    const ratio = trailing.filter((row) => row.volume > 0).length / window;
    const medOi = median(trailing.map((row) => row.openInterest));
    if (ratio >= positiveVolumeRate && medOi >= medianOpenInterest) {
      return {
        eligibleDate: toIso(turkey[i].date),
        trailingWindowStart: toIso(trailing[0].date),
        positiveVolumeRate: ratio,
        medianOpenInterest: medOi,
      };
    }
  }
  return null;
}

const monthlyRegimes = [];
for (const key of [...new Set(turkey.map((row) => toIso(row.date).slice(0, 7)))]) {
  const rows = turkey.filter((row) => toIso(row.date).startsWith(key));
  monthlyRegimes.push({ month: key, ...rowSummary(rows) });
}

const input = await FileBlob.load(workbookPath);
const modelWorkbook = await SpreadsheetFile.importXlsx(input);
const mandiValues = modelWorkbook.worksheets.getItem("Mandi Master").getRange("A1:N607").values;
const mandiHeaders = mandiValues[0].map(String);
const mandi = mandiValues.slice(1).map((values) => {
  const row = Object.fromEntries(mandiHeaders.map((header, i) => [header, values[i]]));
  return { date: parseDate(row.Date), eightAni: numberOrNull(row["8ANI"]), dd: numberOrNull(row["8ANI d/d"]) };
}).filter((row) => row.date).sort((a, b) => a.date - b.date);

const coverageStart = turkey[0].date;
const coverageEnd = turkey.at(-1).date;
const mandiInCoverage = mandi.filter((row) => row.date >= coverageStart && row.date <= coverageEnd);
const exactMatches = mandiInCoverage.filter((row) => actualDateSet.has(toIso(row.date)));

function priorTurkeyRow(date) {
  let lo = 0;
  let hi = turkey.length - 1;
  let result = null;
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (turkey[mid].date < date) {
      result = turkey[mid];
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return result;
}
const causalAlignments = mandiInCoverage.map((row) => {
  const prior = priorTurkeyRow(row.date);
  return {
    mandiDate: row.date,
    turkeyDate: prior?.date ?? null,
    ageCalendarDays: prior ? dateDiff(row.date, prior.date) : null,
  };
});
const alignmentAges = causalAlignments.map((row) => row.ageCalendarDays).filter((value) => value !== null);

const curveOnlyStart = firstDateWhere((row) => row.openInterest >= 100);
const researchEligibility = earliestTrailingEligibility({ positiveVolumeRate: 0.5, medianOpenInterest: 500 });
const strictEligibility = earliestTrailingEligibility({ positiveVolumeRate: 0.75, medianOpenInterest: 1000 });

function targetCounts(startIso) {
  const start = startIso ? parseDate(startIso) : coverageStart;
  const eligible = mandi.filter((row) => row.date >= start && row.date <= coverageEnd && priorTurkeyRow(row.date));
  return horizons.map((horizon) => {
    const anchors = [];
    for (const anchor of eligible) {
      const wanted = new Date(anchor.date.getTime() + horizon * DAY_MS);
      const target = mandi.find((row) => row.date >= wanted);
      if (!target) continue;
      const actualDays = dateDiff(target.date, anchor.date);
      if (actualDays <= horizon + 3) anchors.push({ anchor: anchor.date, target: target.date });
    }
    const purged = [];
    for (const item of anchors) {
      if (!purged.length || item.anchor >= purged.at(-1).target) purged.push(item);
    }
    return { horizonCalendarDays: horizon, overlappingAnchors: anchors.length, purgedNonOverlappingAnchors: purged.length };
  });
}

const report = {
  identity: {
    file: csvPath,
    inferredInstrument: "Barchart C-U26: LME Steel Scrap CFR Turkey (Platts), September 2026 contract",
    sourceRows: rawCsvRows.length,
    validDatedRows: turkey.length,
    nonDataFooterRows: footerRows.map((row) => row.Time),
  },
  coverageAndIntegrity: {
    start: toIso(coverageStart),
    end: toIso(coverageEnd),
    calendarSpanDays: dateDiff(coverageEnd, coverageStart) + 1,
    missingness,
    duplicateDates,
    expectedMondayToFridayDates: weekdayDates.length,
    absentWeekdaysCount: absentWeekdays.length,
    absentWeekdays,
    largestCalendarGaps: calendarGaps.slice(0, 12),
    ohlcViolations: ohlcViolations.length,
    halfDollarTickViolations: nonHalfTickValues.length,
    changeMismatches: changeMismatches.length,
    percentChangeMismatches: percentChangeMismatches.length,
  },
  priceBehavior: {
    startClose: turkey[0].close,
    endClose: turkey.at(-1).close,
    minClose: Math.min(...turkey.map((row) => row.close)),
    minCloseDate: toIso(turkey.reduce((best, row) => row.close < best.close ? row : best).date),
    maxClose: Math.max(...turkey.map((row) => row.close)),
    maxCloseDate: toIso(turkey.reduce((best, row) => row.close > best.close ? row : best).date),
    closeReturnTotal: turkey.at(-1).close / turkey[0].close - 1,
    dailyReturns: {
      ...summary(returns),
      annualizedVolatility: sd(returns) * Math.sqrt(252),
      positiveRate: pct(returns.filter((value) => value > 0).length, returns.length),
      negativeRate: pct(returns.filter((value) => value < 0).length, returns.length),
      zeroRate: pct(returns.filter((value) => value === 0).length, returns.length),
      skewness: skewness(returns),
      excessKurtosis: excessKurtosis(returns),
      autocorrelation1: autocorrelation(returns, 1),
      autocorrelation5: autocorrelation(returns, 5),
      autocorrelation10: autocorrelation(returns, 10),
    },
    positiveVolumeDayReturns: { ...summary(positiveVolumeReturns), zeroRate: pct(positiveVolumeReturns.filter((value) => value === 0).length, positiveVolumeReturns.length) },
    zeroVolumeDayReturns: { ...summary(zeroVolumeReturns), zeroRate: pct(zeroVolumeReturns.filter((value) => value === 0).length, zeroVolumeReturns.length) },
    largestAbsoluteDailyMoves: largestMoves,
    zeroRangeDays: turkey.filter((row) => row.zeroRange).length,
    zeroRangeRate: pct(turkey.filter((row) => row.zeroRange).length, turkey.length),
    unchangedCloseTransitions: turkey.slice(1).filter((row) => row.priceUnchanged).length,
    unchangedCloseRate: pct(turkey.slice(1).filter((row) => row.priceUnchanged).length, turkey.length - 1),
    longestUnchangedCloseRuns: longestEqualValueRuns(turkey, (row) => row.close),
  },
  liquidity: {
    fullSample: rowSummary(turkey),
    firstPositiveOpenInterest: firstDateWhere((row) => row.openInterest > 0),
    firstOpenInterest100: firstDateWhere((row) => row.openInterest >= 100),
    firstOpenInterest500: firstDateWhere((row) => row.openInterest >= 500),
    firstOpenInterest1000: firstDateWhere((row) => row.openInterest >= 1000),
    firstPositiveVolume: firstDateWhere((row) => row.volume > 0),
    firstVolumeAtLeast5Lots: firstDateWhere((row) => row.volume >= 5),
    firstVolumeAtLeast50Lots: firstDateWhere((row) => row.volume >= 50),
    zeroVolumeDays: turkey.filter((row) => row.volume === 0).length,
    zeroVolumeRate: pct(turkey.filter((row) => row.volume === 0).length, turkey.length),
    zeroVolumeAndZeroRangeDays: turkey.filter((row) => row.volume === 0 && row.zeroRange).length,
    positiveVolumeButZeroRangeDays: turkey.filter((row) => row.volume > 0 && row.zeroRange).length,
    changedCloseDespiteZeroVolumeDays: turkey.slice(1).filter((row) => row.volume === 0 && !row.priceUnchanged).length,
    openInterestUnchangedTransitions: turkey.slice(1).filter((row) => row.oiUnchanged).length,
    openInterestUnchangedRate: pct(turkey.slice(1).filter((row) => row.oiUnchanged).length, turkey.length - 1),
    longestZeroVolumeRuns: longestRuns(turkey, (row) => row.volume === 0, () => "volume=0"),
    longestZeroRangeRuns: longestRuns(turkey, (row) => row.zeroRange, () => "high=low"),
    longestUnchangedOpenInterestRuns: longestEqualValueRuns(turkey, (row) => row.openInterest),
    oiRegimes,
    causalTrailingEligibility: {
      research50pctVolumeAndOi500: researchEligibility,
      strict75pctVolumeAndOi1000: strictEligibility,
    },
    monthlyRegimes,
  },
  mandiOverlap: {
    mandiFullStart: toIso(mandi[0].date),
    mandiFullEnd: toIso(mandi.at(-1).date),
    mandiFullRows: mandi.length,
    mandiRowsWithinTurkeyCoverage: mandiInCoverage.length,
    shareOfMandiRowsWithinTurkeyCoverage: mandiInCoverage.length / mandi.length,
    exactSameDateMatches: exactMatches.length,
    exactMatchRateWithinCoverage: exactMatches.length / mandiInCoverage.length,
    causalPriorCloseAlignedRows: alignmentAges.length,
    causalAlignmentAgeCalendarDays: summary(alignmentAges),
    causalAgeCounts: Object.fromEntries([...new Set(alignmentAges)].sort((a, b) => a - b).map((age) => [age, alignmentAges.filter((value) => value === age).length])),
    causalAlignedWithin3CalendarDays: alignmentAges.filter((age) => age <= 3).length,
    causalAlignedWithin4CalendarDays: alignmentAges.filter((age) => age <= 4).length,
    usableTierRows: {
      curveOnlyFromOi100: mandi.filter((row) => row.date >= parseDate(curveOnlyStart) && row.date <= coverageEnd).length,
      researchFromTrailingLiquidity: researchEligibility ? mandi.filter((row) => row.date >= parseDate(researchEligibility.eligibleDate) && row.date <= coverageEnd).length : 0,
      strictFromTrailingLiquidity: strictEligibility ? mandi.filter((row) => row.date >= parseDate(strictEligibility.eligibleDate) && row.date <= coverageEnd).length : 0,
    },
    horizonAvailabilityByTier: {
      fullTurkeyCoverage: targetCounts(toIso(coverageStart)),
      curveOnlyFromOi100: targetCounts(curveOnlyStart),
      researchFromTrailingLiquidity: targetCounts(researchEligibility?.eligibleDate),
      strictFromTrailingLiquidity: targetCounts(strictEligibility?.eligibleDate),
    },
  },
};

console.log(JSON.stringify(report, null, 2));
