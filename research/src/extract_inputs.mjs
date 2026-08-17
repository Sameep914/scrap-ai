import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI";
const workbookPath = `${root}/files_extracted/SBIP_Model_Clean.xlsx`;
const outputPath = `${root}/research/inputs/mandi_master.csv`;

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const values = workbook.worksheets.getItem("Mandi Master").getRange("A1:N607").values;

function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const csv = values.map((row) => row.map(csvCell).join(",")).join("\r\n");
await fs.writeFile(outputPath, csv, "utf8");
console.log(JSON.stringify({ outputPath, rows: values.length - 1, columns: values[0].length }));
