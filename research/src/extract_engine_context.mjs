import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI";
const workbookPath = "C:/Users/demos/Downloads/SBIP_Engine_Data_Master.xlsx";
const outputDir = `${root}/research/inputs/engine_context`;
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
await fs.mkdir(outputDir, { recursive: true });

const selections = [
  ["README", "A1:A28"],
  ["ROADMAP", "A1:D26"],
  ["EXPANDED FACTORS", "A1:E16"],
  ["MULTI-FACTOR PROTOCOL", "A1:D17"],
  ["New Factor Data", "A1:C70"],
  ["Data Subscriptions", "A1:E39"],
  ["CRITICAL - LEAKAGE FINDING", "A1:D24"],
  ["DIRECTION MODEL", "A1:E26"],
  ["Search Framework Findings", "A1:E55"],
  ["Model & Forecast", "A1:F11"],
  ["Directional Signal", "A1:E41"],
  ["USD-INR", "A1:C37"],
  ["Turkey HMS 8020", "A1:D93"],
  ["Policy Events", "A1:D28"],
  ["Supply & Substitutes", "A1:E115"],
  ["China HRC FOB", "A1:B164"],
  ["Turkey Rebar (proxy)", "A1:C13"],
];

function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

for (const [sheetName, rangeAddress] of selections) {
  const values = workbook.worksheets.getItem(sheetName).getRange(rangeAddress).values;
  const csv = values.map((row) => row.map(csvCell).join(",")).join("\r\n");
  const path = `${outputDir}/${slug(sheetName)}.csv`;
  await fs.writeFile(path, csv, "utf8");
  console.log(JSON.stringify({ sheetName, rangeAddress, path, rows: values.length, columns: values[0]?.length ?? 0 }));
}
