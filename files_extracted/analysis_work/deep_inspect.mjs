import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI/files_extracted/SBIP_Model_Clean.xlsx";
const previewDir = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI/files_extracted/analysis_work/previews";
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const sheetScan = await workbook.inspect({
  kind: "sheet",
  include: "id,name,range",
  maxChars: 30000,
  options: { maxResults: 500 },
});

const sheets = sheetScan.ndjson
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line))
  .filter((record) => record.kind === "sheet");

const keySheets = [
  "VALIDATED SIGNALS",
  "DATA WANTED",
  "THE REAL MODEL",
  "MODEL & FORECAST",
  "DIRECTIONAL SIGNAL",
  "Daily Snapshot Log",
  "DATA INVENTORY",
  "ROADMAP & PROTOCOL",
];

for (const name of keySheets) {
  const sheet = sheets.find((item) => item.name.toUpperCase() === name.toUpperCase());
  if (!sheet) continue;
  const detail = await workbook.inspect({
    kind: "table",
    sheetId: sheet.id,
    range: sheet.range,
    include: "values,formulas",
    maxChars: 24000,
    tableMaxRows: 100,
    tableMaxCols: 20,
    tableMaxCellChars: 500,
  });
  console.log(`---SHEET:${sheet.name}---`);
  console.log(detail.ndjson);
}

for (const range of ["A1:N18", "A590:N607"]) {
  const detail = await workbook.inspect({
    kind: "table",
    sheetId: "Mandi Master",
    range,
    include: "values,formulas",
    maxChars: 18000,
    tableMaxRows: 30,
    tableMaxCols: 20,
    tableMaxCellChars: 200,
  });
  console.log(`---MANDI:${range}---`);
  console.log(detail.ndjson);
}

console.log("---FORMULA_SUMMARY---");
for (const sheet of sheets) {
  const formulaScan = await workbook.inspect({
    kind: "formula",
    sheetId: sheet.id,
    range: sheet.range,
    maxChars: 12000,
    options: { maxResults: 1000 },
  });
  const lines = formulaScan.ndjson.split(/\r?\n/).filter(Boolean);
  const records = [];
  for (const line of lines) {
    try {
      const parsed = JSON.parse(line);
      if (parsed.kind === "formula") records.push(parsed);
    } catch {}
  }
  console.log(JSON.stringify({
    sheet: sheet.name,
    formulaRecords: records.length,
    examples: records.slice(0, 12),
    rawNotice: records.length === 0 ? formulaScan.ndjson : undefined,
  }));
}

await fs.mkdir(previewDir, { recursive: true });
for (const sheet of sheets) {
  const safeName = sheet.name.replace(/[^a-z0-9._-]+/gi, "_");
  const preview = await workbook.render({
    sheetName: sheet.name,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(`${previewDir}/${String(sheet.index).padStart(2, "0")}_${safeName}.png`, new Uint8Array(await preview.arrayBuffer()));
  console.log(`RENDERED:${sheet.name}`);
}
