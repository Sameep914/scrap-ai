import fs from "node:fs/promises";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const root = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI/research";
const outDir = `${root}/deliverables`;
await fs.mkdir(outDir, { recursive: true });

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { value += '"'; i++; }
      else if (ch === '"') quoted = false;
      else value += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') { row.push(value); value = ""; }
    else if (ch === '\n') { row.push(value.replace(/\r$/, "")); rows.push(row); row = []; value = ""; }
    else value += ch;
  }
  if (value.length || row.length) { row.push(value.replace(/\r$/, "")); rows.push(row); }
  return rows;
}

function coerce(value) {
  if (value === "" || value === undefined) return null;
  const trimmed = String(value).trim();
  if (/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(trimmed)) return Number(trimmed);
  if (trimmed === "True") return true;
  if (trimmed === "False") return false;
  return value;
}

async function readCsv(path) {
  const text = await fs.readFile(path, "utf8");
  return parseCsv(text).filter((row) => row.some((cell) => String(cell).length)).map((row) => row.map(coerce));
}

function colName(n) {
  let out = "";
  while (n > 0) { n--; out = String.fromCharCode(65 + (n % 26)) + out; n = Math.floor(n / 26); }
  return out;
}

function writeMatrix(sheet, startRow, startCol, matrix) {
  if (!matrix.length || !matrix[0]?.length) return;
  const endRow = startRow + matrix.length - 1;
  const endCol = startCol + matrix[0].length - 1;
  sheet.getRange(`${colName(startCol)}${startRow}:${colName(endCol)}${endRow}`).values = matrix;
}

function styleTable(sheet, rows, cols, widths = {}) {
  if (!rows || !cols) return;
  const header = sheet.getRange(`A1:${colName(cols)}1`);
  header.format = { fill: "#0F3D56", font: { bold: true, color: "#FFFFFF" }, wrapText: true };
  sheet.getRange(`A1:${colName(cols)}${rows}`).format.verticalAlignment = "center";
  sheet.getRange(`A1:${colName(cols)}${rows}`).format.wrapText = true;
  for (let c = 1; c <= cols; c++) {
    const width = widths[c] ?? (c === 1 ? 22 : 14);
    sheet.getRange(`${colName(c)}:${colName(c)}`).format.columnWidth = width;
  }
  sheet.freezePanes.freezeRows(1);
}

const workbook = Workbook.create();

// Executive dashboard with formula-linked live decisions.
const summary = workbook.worksheets.add("Executive Summary");
summary.getRange("A1:I1").merge();
summary.getRange("A1").values = [["ALANG 8ANI FORECAST AUDIT — 12 AUG 2026"]];
summary.getRange("A1:I1").format = { fill: "#0B2B3C", font: { bold: true, color: "#FFFFFF", size: 16 }, horizontalAlignment: "center" };
summary.getRange("A3:B8").values = [
  ["Forecast origin", "2026-08-11"],
  ["Current 8ANI", 38500],
  ["Primary decision", "NO CALL at every horizon"],
  ["Risk lean", "30–60d downside / sell strength, not a validated trade"],
  ["Closest edge", "Plate–melt relative value at 30–45 calendar days"],
  ["Main blocker", "Independent long-horizon sample size and unstable complex-model skill"],
];
summary.getRange("A3:A8").format = { fill: "#DCEAF1", font: { bold: true, color: "#0B2B3C" } };
summary.getRange("B4").format.numberFormat = "#,##0";
summary.getRange("A10:I10").values = [["Horizon", "Point move", "Point price", "80% low", "80% high", "Down prob", "Independent N", "Carry hurdle", "Decision"]];
for (let row = 11; row <= 17; row++) {
  const sourceRow = row - 9;
  summary.getRange(`A${row}:I${row}`).formulas = [[
    `='Horizon Decisions'!B${sourceRow}`,
    `='Horizon Decisions'!I${sourceRow}`,
    `=ROUND('Horizon Decisions'!J${sourceRow},0)`,
    `=ROUND('Horizon Decisions'!K${sourceRow},0)`,
    `=ROUND('Horizon Decisions'!L${sourceRow},0)`,
    `='Horizon Decisions'!M${sourceRow}`,
    `='Horizon Decisions'!U${sourceRow}`,
    `='Horizon Decisions'!F${sourceRow}`,
    `='Horizon Decisions'!AI${sourceRow}`,
  ]];
}
summary.getRange("A10:I10").format = { fill: "#0F3D56", font: { bold: true, color: "#FFFFFF" } };
summary.getRange("B11:B17").format.numberFormat = "0.00%";
summary.getRange("C11:E17").format.numberFormat = "#,##0";
summary.getRange("F11:F17").format.numberFormat = "0.0%";
summary.getRange("H11:H17").format.numberFormat = "#,##0";
summary.getRange("B11:B17").format.columnWidth = 14;
summary.getRange("C11:E17").format.columnWidth = 18;
summary.getRange("F11:F17").format.columnWidth = 14;
summary.getRange("G11:G17").format.columnWidth = 16;
summary.getRange("H11:H17").format.columnWidth = 16;
summary.getRange("I11:I17").format.columnWidth = 16;
summary.getRange("I11:I17").format = { fill: "#FFF2CC", font: { bold: true, color: "#7F6000" } };
summary.getRange("A19:I22").values = [
  ["Interpretation", null, null, null, null, null, null, null, null],
  ["The combined point forecasts tilt down at 30–90d, but every interval crosses an actionable threshold and the independent samples fall to 9/7/4/3.", null, null, null, null, null, null, null, null],
  ["The 30d plate–melt rule has 19 independent episodes, adjusted p=0.0227, and a positive block interval. It is one episode short of the stated N≥20 gate.", null, null, null, null, null, null, null, null],
  ["SRIA reference terms imply ₹30/MT/day carry; a 30d hold must earn at least ₹900/MT before other risk and costs.", null, null, null, null, null, null, null, null],
];
for (let row = 19; row <= 22; row++) summary.getRange(`A${row}:I${row}`).merge();
summary.getRange("A19:I19").format = { fill: "#2F75B5", font: { bold: true, color: "#FFFFFF" } };
summary.getRange("A20:I22").format = { fill: "#EAF2F8", wrapText: true };
summary.getRange("A:A").format.columnWidth = 22;
summary.freezePanes.freezeRows(1);

const specs = [
  ["Horizon Decisions", `${root}/outputs/v2/horizon_decisions_v2.csv`],
  ["Model Backtests", `${root}/outputs/v2/backtest_summary_v2.csv`],
  ["Rule Backtests", `${root}/outputs/rule_backtest_summary.csv`],
  ["Pairwise Tests", `${root}/outputs/v2/same_origin_pairwise_v2.csv`],
  ["Multiple Testing", `${root}/outputs/v2/multiple_testing_v2.csv`],
  ["Live Rule Signals", `${root}/outputs/live_rule_signals.csv`],
  ["Supply Context", `${root}/outputs/monthly_supply_context_results.csv`],
  ["Live Vessel Supply", `${root}/outputs/live_supply_release_scenarios.csv`],
  ["Regional Snapshot", `${root}/inputs/external/ayronmart_regional_snapshot_2026-08-11.csv`],
  ["Mandi Raw", `${root}/inputs/mandi_master.csv`],
  ["Turkey Nearby Raw", `${root}/inputs/turkey_scrap_daily_nearby.csv`],
];

for (const [name, path] of specs) {
  const matrix = await readCsv(path);
  const sheet = workbook.worksheets.add(name);
  writeMatrix(sheet, 1, 1, matrix);
  const widths = {};
  if (name === "Horizon Decisions") { widths[1] = 14; widths[2] = 10; widths[35] = 15; widths[36] = 55; }
  if (name === "Rule Backtests") { widths[1] = 24; }
  if (name.includes("Raw")) { widths[1] = 16; widths[2] = 14; }
  styleTable(sheet, matrix.length, Math.max(...matrix.map((r) => r.length)), widths);
}

const methods = workbook.worksheets.add("Methods & Caveats");
const methodRows = [
  ["Topic", "Implementation / finding"],
  ["Target", "True calendar H-day outcome: first quote on/after H, no more than H+4 days."],
  ["Purging", "Every training target endpoint must be strictly before the OOS forecast origin."],
  ["External timing", "Turkey and Bhavnagar use strict prior-date as-of joins because the 10:30 Alang sale cutoff precedes same-day updates."],
  ["Turkey rolls", "Barchart Change equals the cross-contract gap at all 42 switches. Roll-day returns are missing; momentum/volatility remain within Symbol."],
  ["Turkey quality", "873 rows; 89.35% zero volume; 88.32% zero range; curve/assessment control, not an executable spot series."],
  ["Mandi gaps", "606 rows with 87-day and 96-day gaps; rolling state resets after gaps over 14 days."],
  ["Magnitude baseline", "Zero log return / random walk. Expanding trailing median is secondary."],
  ["Direction baseline", "Expanding down/flat/up frequencies and majority class. Flat is retained."],
  ["Dependence", "Greedy non-overlap counts, all phase-offset cohorts, time thirds and moving-block bootstrap."],
  ["Multiple testing", "35 complex-model/horizon candidates and 49 pre-specified rule/horizon candidates receive max-null adjustment."],
  ["Decision gates", "Independent OOS N≥20, positive CI lower bound, adjusted p gate, stable phases/time thirds, quality and economic hurdle."],
  ["SRIA economics", "Reference terms: next-day payment, ₹50/MT loading, ₹30/MT/day credit; confirm before production use."],
  ["Supply context", "AlangToday historic monthly values are current-vintage with unknown original release timestamps; contextual only."],
  ["Grade convention", "Confirm whether operational 8ANI means the yard's 8ANE convention; BigMint publicly maps 8ANE to roughly 12–14mm."],
  ["Primary verdict", "No fully validated horizon. 30–45d downside is a near-edge; live combined system abstains everywhere."],
];
writeMatrix(methods, 1, 1, methodRows);
styleTable(methods, methodRows.length, 2, { 1: 24, 2: 100 });

const sources = workbook.worksheets.add("Sources");
const sourceRows = [
  ["Source", "URL / local artifact", "Use"],
  ["User Mandi workbook", "files_extracted/SBIP_Model_Clean.xlsx", "606 Alang grade quotes"],
  ["Barchart Turkey nearby", "research/inputs/turkey_scrap_daily_nearby.csv", "Global scrap curve control; authenticated download"],
  ["Barchart C-U26", "research/inputs/turkey_scrap_C_U26.csv", "Fixed Sep-2026 contract audit"],
  ["Ayron Mart", "https://ayronmart.com/", "Bhavnagar daily history and 11-Aug regional snapshot"],
  ["LME methodology", "https://www.lme.com/-/media/Files/About/Regulation/Key-compliance-notices/CashSettled-Futures-Daily-Settlement-Prices-Methodology.pdf", "Settlement timing and waterfall"],
  ["LME historical data", "https://www.lme.com/en/market-data/reports-and-data/historical-data-for-cash-settled-futures", "Recommended full curve/OI source"],
  ["AlangToday demolition", "https://www.alangtoday.com/all-demolition.aspx", "70-vessel current snapshot"],
  ["AlangToday analysis", "https://www.alangtoday.com/alang-analysis.aspx", "2016–2026 current-vintage monthly ships/LDT"],
  ["Government shipbreaking guideline", "https://environmentclearance.nic.in/writereaddata/Form-1A/HomeLinks/TGM_Ship%20Breaking%20Yards_010910_NK.pdf", "Type-specific plate-yield priors"],
  ["National Maritime Foundation", "https://maritimeindia.org/sustainable-ship-recycling-in-india-legal-economic-and-political-analysis/", "Dismantling duration and end-use transition"],
  ["BigMint grade table", "https://www.bigmint.co/scrapmetallics?tab=tenders", "Grade-definition caveat"],
];
writeMatrix(sources, 1, 1, sourceRows);
styleTable(sources, sourceRows.length, 3, { 1: 30, 2: 100, 3: 45 });

const errorScan = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!",
  options: { useRegex: true, maxResults: 200 },
  maxChars: 10000,
});
console.log("ERROR_SCAN");
console.log(errorScan.ndjson);

const preview = await workbook.render({ sheetName: "Executive Summary", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outDir}/alang_8ani_audit_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outDir}/Alang_8ANI_Forecast_Audit_2026-08-12.xlsx`);
console.log(JSON.stringify({ output: `${outDir}/Alang_8ANI_Forecast_Audit_2026-08-12.xlsx`, preview: `${outDir}/alang_8ani_audit_preview.png` }));
