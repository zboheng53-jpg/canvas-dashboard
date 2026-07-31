const encoder = new TextEncoder();

function escapeXml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function columnName(index) {
  let output = "";
  for (let value = index + 1; value > 0; value = Math.floor((value - 1) / 26)) {
    output = String.fromCharCode(65 + ((value - 1) % 26)) + output;
  }
  return output;
}

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function writeUInt16(target, value, offset) {
  target[offset] = value & 0xff;
  target[offset + 1] = (value >>> 8) & 0xff;
}

function writeUInt32(target, value, offset) {
  target[offset] = value & 0xff;
  target[offset + 1] = (value >>> 8) & 0xff;
  target[offset + 2] = (value >>> 16) & 0xff;
  target[offset + 3] = (value >>> 24) & 0xff;
}

function dosDateTime(date) {
  const year = Math.max(date.getFullYear(), 1980);
  return {
    date: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate(),
    time: (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2),
  };
}

function zip(files) {
  const timestamp = dosDateTime(new Date());
  const localParts = [];
  const centralParts = [];
  let localOffset = 0;
  for (const file of files) {
    const name = encoder.encode(file.name);
    const data = encoder.encode(file.content);
    const crc = crc32(data);
    const local = new Uint8Array(30 + name.length + data.length);
    writeUInt32(local, 0x04034b50, 0);
    writeUInt16(local, 20, 4);
    writeUInt16(local, 0x0800, 6);
    writeUInt16(local, 0, 8);
    writeUInt16(local, timestamp.time, 10);
    writeUInt16(local, timestamp.date, 12);
    writeUInt32(local, crc, 14);
    writeUInt32(local, data.length, 18);
    writeUInt32(local, data.length, 22);
    writeUInt16(local, name.length, 26);
    name.forEach((value, index) => { local[30 + index] = value; });
    local.set(data, 30 + name.length);
    localParts.push(local);

    const central = new Uint8Array(46 + name.length);
    writeUInt32(central, 0x02014b50, 0);
    writeUInt16(central, 20, 4);
    writeUInt16(central, 20, 6);
    writeUInt16(central, 0x0800, 8);
    writeUInt16(central, 0, 10);
    writeUInt16(central, timestamp.time, 12);
    writeUInt16(central, timestamp.date, 14);
    writeUInt32(central, crc, 16);
    writeUInt32(central, data.length, 20);
    writeUInt32(central, data.length, 24);
    writeUInt16(central, name.length, 28);
    writeUInt32(central, localOffset, 42);
    central.set(name, 46);
    centralParts.push(central);
    localOffset += local.length;
  }
  const centralSize = centralParts.reduce((size, part) => size + part.length, 0);
  const end = new Uint8Array(22);
  writeUInt32(end, 0x06054b50, 0);
  writeUInt16(end, files.length, 8);
  writeUInt16(end, files.length, 10);
  writeUInt32(end, centralSize, 12);
  writeUInt32(end, localOffset, 16);
  const output = new Uint8Array(localOffset + centralSize + end.length);
  let offset = 0;
  for (const part of [...localParts, ...centralParts, end]) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
}

function sheetXml(sheet) {
  const { rows, merges = [], columnWidths = [] } = sheet;
  const mergeReferences = merges.map((merge) => `${columnName(merge.startCol)}${merge.startRow + 1}:${columnName(merge.endCol)}${merge.endRow + 1}`);
  const columns = columnWidths.length ? `<cols>${columnWidths.map((width, index) =>
    `<col min="${index + 1}" max="${index + 1}" width="${width}" customWidth="1"/>`).join("")}</cols>` : "";
  const body = rows.map((row, rowIndex) => {
    const cells = row.map((value, columnIndex) => value === "" ? "" :
      `<c r="${columnName(columnIndex)}${rowIndex + 1}" s="${rowIndex === 0 ? 2 : 1}" t="inlineStr"><is><t xml:space="preserve">${escapeXml(value)}</t></is></c>`).join("");
    const rowHeight = sheet.rowHeights?.[rowIndex];
    return `<row r="${rowIndex + 1}"${rowHeight ? ` ht="${rowHeight}" customHeight="1"` : ""}>${cells}</row>`;
  }).join("");
  const mergeCells = mergeReferences.length ? `<mergeCells count="${mergeReferences.length}">${mergeReferences.map((reference) => `<mergeCell ref="${reference}"/>`).join("")}</mergeCells>` : "";
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">${columns}<sheetData>${body}</sheetData>${mergeCells}</worksheet>`;
}

export function createXlsx(sheets) {
  const workbookSheets = sheets.map((sheet, index) => `<sheet name="${escapeXml(sheet.name)}" sheetId="${index + 1}" r:id="rId${index + 1}"/>`).join("");
  const workbookRels = sheets.map((_, index) => `<Relationship Id="rId${index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${index + 1}.xml"/>`).join("");
  const contentOverrides = sheets.map((_, index) => `<Override PartName="/xl/worksheets/sheet${index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("");
  return zip([
    { name: "[Content_Types].xml", content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${contentOverrides}</Types>` },
    { name: "_rels/.rels", content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>` },
    { name: "xl/workbook.xml", content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${workbookSheets}</sheets></workbook>` },
    { name: "xl/_rels/workbook.xml.rels", content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${workbookRels}<Relationship Id="rId${sheets.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>` },
    { name: "xl/styles.xml", content: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="10"/><name val="Microsoft YaHei"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Microsoft YaHei"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0B3A70"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="2"><border/><border><left style="thin"><color rgb="FFD0D7E2"/></left><right style="thin"><color rgb="FFD0D7E2"/></right><top style="thin"><color rgb="FFD0D7E2"/></top><bottom style="thin"><color rgb="FFD0D7E2"/></bottom></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="1" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf></cellXfs></styleSheet>` },
    ...sheets.map((sheet, index) => ({ name: `xl/worksheets/sheet${index + 1}.xml`, content: sheetXml(sheet) })),
  ]);
}

export function filenameForToday(date = new Date()) {
  return `同济大学课程表_${date.toISOString().slice(0, 10)}.xlsx`;
}
