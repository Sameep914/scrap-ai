import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI/files_extracted/SBIP_Model_Clean.xlsx";
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const targets = [
  ["EXTERNAL FACTORS SCOREBOARD", "A1:E27"],
  ["LEAD TIMES", "A1:F26"],
  ["GRADE CURVE ANALYSIS", "A1:E49"],
  ["ALANG SUPPLY SIDE", "A1:D44"],
  ["FUNDAMENTALS LAYER", "A1:E48"],
  ["COMPLEX MODELS", "A1:D20"],
  ["CHAIN STRUCTURE", "A1:F40"],
  ["ADVANCED TESTS", "A1:A24"],
  ["FINAL VERDICT", "A1:A36"],
];

for (const [sheetName, range] of targets) {
  const detail = await workbook.inspect({
    kind: "table",
    sheetId: sheetName,
    range,
    include: "values,formulas",
    maxChars: 40000,
    tableMaxRows: 100,
    tableMaxCols: 20,
    tableMaxCellChars: 800,
  });
  console.log(`---SHEET:${sheetName}---`);
  console.log(detail.ndjson);
}
