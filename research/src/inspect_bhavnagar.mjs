import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI/research";
const path = `${root}/inputs/Bhavnagar_TMT_Ingot_Billet_Daily_Jan2022_Aug2026.xlsx`;
const input = await FileBlob.load(path);
const workbook = await SpreadsheetFile.importXlsx(input);

const sheets = await workbook.inspect({ kind: "sheet", include: "id,name,range", maxChars: 20000 });
console.log(sheets.ndjson);

for (const line of sheets.ndjson.split(/\r?\n/).filter(Boolean)) {
  const record = JSON.parse(line);
  if (record.kind !== "sheet") continue;
  const table = await workbook.inspect({
    kind: "table",
    sheetId: record.name,
    range: record.range,
    include: "values,formulas",
    maxChars: 12000,
    tableMaxRows: 20,
    tableMaxCols: 20,
    tableMaxCellChars: 200,
  });
  console.log(`---${record.name}---`);
  console.log(table.ndjson);
  const values = workbook.worksheets.getItem(record.name).getRange(record.range).values;
  const csv = values.map((row) => row.map((value) => {
    if (value === null || value === undefined) return "";
    const text = String(value);
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  }).join(",")).join("\r\n");
  const safe = record.name.replace(/[^a-z0-9_-]+/gi, "_");
  await fs.writeFile(`${root}/inputs/bhavnagar_${safe}.csv`, csv, "utf8");
}
