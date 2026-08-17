import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI/files_extracted/SBIP_Model_Clean.xlsx";
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = await workbook.inspect({
  kind: "workbook,sheet,definedName,drawing",
  include: "id,name,range",
  maxChars: 20000,
  options: { maxResults: 500 },
});

console.log(summary.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
  maxChars: 8000,
});

console.log("---FORMULA_ERRORS---");
console.log(errors.ndjson);
