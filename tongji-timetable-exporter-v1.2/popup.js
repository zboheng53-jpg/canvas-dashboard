import { createXlsx, filenameForToday } from "./table-exporter.mjs";

const button = document.querySelector("#exportButton");
const status = document.querySelector("#status");

function setStatus(message, isError = false) {
  status.textContent = message;
  status.classList.toggle("error", isError);
}

function extractTimetable() {
  try {
  const clean = (value) => String(value ?? "").replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n").replace(/\n[ \t]+/g, "\n").trim();
  const toGrid = (table) => {
    const grid = [];
    const merges = [];
    Array.from(table.rows).forEach((row, rowIndex) => {
      grid[rowIndex] ||= [];
      let column = 0;
      Array.from(row.cells).forEach((cell) => {
        while (grid[rowIndex][column] !== undefined) column += 1;
        const value = clean(cell.innerText);
        const rowSpan = cell.rowSpan || 1;
        const colSpan = cell.colSpan || 1;
        if (rowSpan > 1 || colSpan > 1) merges.push({
          startRow: rowIndex, startCol: column, endRow: rowIndex + rowSpan - 1, endCol: column + colSpan - 1,
        });
        for (let r = 0; r < rowSpan; r += 1) {
          grid[rowIndex + r] ||= [];
          for (let c = 0; c < colSpan; c += 1) grid[rowIndex + r][column + c] = r || c ? "" : value;
        }
        column += colSpan;
      });
    });
    const width = Math.max(...grid.map((row) => row.length));
    return { rows: grid.map((row) => Array.from({ length: width }, (_, index) => row[index] ?? "")), merges };
  };

  const tables = Array.from(document.querySelectorAll("table"));
  const schedule = tables.find((table) => clean(table.innerText).includes("节次/周次"));
  const courseHeaderIndex = tables.findIndex((table) => {
    const text = clean(table.innerText);
    return text.includes("新课程序号") && text.includes("课程名称");
  });
  if (!schedule || courseHeaderIndex < 0) return { ok: false, error: "课表仍在加载。请等待页面出现课表后重试。" };
  const courseTable = tables.slice(courseHeaderIndex + 1).find((table) => table.rows.length > 0);
  if (!courseTable) return { ok: false, error: "未找到已选课程列表。请刷新页面后再试。" };

  const removeLeadingBlank = (row) => row[0] === "" ? row.slice(1) : row;
  const courseHeader = toGrid(tables[courseHeaderIndex]).rows.map(removeLeadingBlank);
  const courses = toGrid(courseTable).rows.map(removeLeadingBlank);
  const scheduleData = toGrid(schedule);
  const rowHeights = scheduleData.rows.map((row, rowIndex) => {
    if (rowIndex === 0) return 26;
    const longest = Math.max(...row.map((cell) => cell.length), 0);
    const span = scheduleData.merges.find((merge) => merge.startRow === rowIndex && merge.startCol > 0);
    const dividedLength = span ? Math.ceil(longest / (span.endRow - span.startRow + 1)) : longest;
    return Math.min(120, Math.max(24, Math.ceil(dividedLength / 18) * 15));
  });
  return { ok: true,
    schedule: { ...scheduleData, rowHeights, columnWidths: [13, 30, 30, 30, 30, 30, 18, 18] },
    courses: { rows: [...courseHeader, ...courses], columnWidths: [14, 22, 10, 13, 10, 8, 18, 30, 22, 45, 14] },
  };
  } catch (error) {
    return { ok: false, error: error?.message || "课表解析失败，请刷新页面后再试。" };
  }
}

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function readTimetable(tabId) {
  let lastError = "课表仍在加载。";
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const injection = await chrome.scripting.executeScript({ target: { tabId }, func: extractTimetable });
    const result = injection.find((item) => item.frameId === 0)?.result;
    if (result?.ok && result.schedule && result.courses) return result;
    lastError = result?.error || lastError;
    if (attempt < 5) await sleep(700);
  }
  throw new Error(`${lastError} 请切换学期后等待几秒，再点击导出。`);
}

button.addEventListener("click", async () => {
  button.disabled = true;
  setStatus("正在读取当前页面…");
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab.url?.startsWith("https://1.tongji.edu.cn/")) {
      throw new Error("请先在同济教学管理系统中打开“个人课表”页面。");
    }
    const result = await readTimetable(tab.id);
    const xlsx = createXlsx([
      { name: "学生课表", ...result.schedule },
      { name: "已选课程", ...result.courses },
    ]);
    const url = URL.createObjectURL(new Blob([xlsx], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
    await chrome.downloads.download({ url, filename: filenameForToday(), saveAs: true });
    setTimeout(() => URL.revokeObjectURL(url), 15_000);
    setStatus("已生成文件，请在浏览器下载列表中查看。");
  } catch (error) {
    setStatus(error.message || "导出失败，请刷新页面后重试。", true);
  } finally {
    button.disabled = false;
  }
});
