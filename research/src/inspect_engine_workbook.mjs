import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const path = "C:/Users/demos/Downloads/SBIP_Engine_Data_Master.xlsx";
const input = await FileBlob.load(path);
const workbook = await SpreadsheetFile.importXlsx(input);

const sheets = await workbook.inspect({
  kind: "sheet",
  include: "id,name,range",
  options: { maxResults: 200 },
  maxChars: 20000,
});
console.log(sheets.ndjson);

for (const name of ["RAW DATA", "DATA", "INPUTS", "Mandi Master", "Turkey", "USDINR", "China HRC", "Ingot", "TMT"]) {
  const found = sheets.ndjson.split(/\r?\n/).filter(Boolean).map((x) => JSON.parse(x)).find((x) => x.kind === "sheet" && x.name.toLowerCase() === name.toLowerCase());
  if (!found) continue;
  const table = await workbook.inspect({
    kind: "table",
    sheetId: found.id,
    range: found.range,
    include: "values,formulas",
    tableMaxRows: 25,
    tableMaxCols: 30,
    tableMaxCellChars: 200,
    maxChars: 30000,
  });
  console.log(`---${found.name}---`);
  console.log(table.ndjson);
}

const formulas = await workbook.inspect({
  kind: "formula",
  options: { maxResults: 100 },
  maxChars: 10000,
});
console.log("---FORMULAS---");
console.log(formulas.ndjson);
