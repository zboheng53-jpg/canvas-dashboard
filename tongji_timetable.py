"""Parse Tongji graduate timetable rows and fetch them from Tongji's workbench."""
import html
import json
import re
import time
from datetime import date
from html.parser import HTMLParser
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree

import requests

import settings

TIMETABLE_URL = "https://1.tongji.edu.cn/GraduateStudentTimeTable"
PERIOD_TIMES = {
    1: ("08:00", "08:45"), 2: ("08:50", "09:35"), 3: ("10:00", "10:45"),
    4: ("10:50", "11:35"), 5: ("13:30", "14:15"), 6: ("14:20", "15:05"),
    7: ("15:30", "16:15"), 8: ("16:20", "17:05"), 9: ("18:30", "19:15"),
    10: ("19:20", "20:05"), 11: ("20:10", "20:55"),
}
WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


class TimetableLoginError(RuntimeError):
    """The Tongji unified-login page could not be completed automatically."""


class TimetableFetchError(RuntimeError):
    """The logged-in timetable page did not contain a usable course table."""


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._table, self._row, self._cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def _normalized(value):
    return re.sub(r"\s+", "", html.unescape(value or ""))


def _header_index(headers, aliases):
    for index, header in enumerate(headers):
        normalized = _normalized(header)
        if any(alias == normalized for alias in aliases):
            return index
    for index, header in enumerate(headers):
        normalized = _normalized(header)
        if any(alias in normalized for alias in aliases):
            return index
    return None


def _split_segments(raw_time):
    separator = r"[；;\n]+|[,，](?=\s*(?:(?:周|星期)[一二三四五六日天]|20\d{2}[./-]|\[?\s*\d{1,2}\s*[-~至]\s*\d{1,2}\s*节))"
    return [part.strip() for part in re.split(separator, raw_time or "") if part.strip()]


def _parse_weeks(text):
    weeks = set()
    for match in re.finditer(r"(\[|第)\s*(\d{1,2})\s*[-~至]\s*(\d{1,2})\s*(周)?", text):
        if match.group(1) == "[" or match.group(4) == "周":
            weeks.update(range(int(match.group(2)), int(match.group(3)) + 1))
    for match in re.findall(r"(?:第)?([\d、，,\s]+)周", text):
        weeks.update(int(value) for value in re.findall(r"\d{1,2}", match))
    for bracket in re.findall(r"\[([^\]]*)\]", text):
        if re.fullmatch(r"[\d、，,\s]+", bracket):
            weeks.update(int(value) for value in re.findall(r"\d{1,2}", bracket))
    bracket_parities = "".join(re.findall(r"\[([^\]]*)\]", text))
    parity = "odd" if "单周" in text or "单" in bracket_parities else "even" if "双周" in text or "双" in bracket_parities else None
    return sorted(weeks), parity


def _parse_periods(text):
    match = re.search(r"第?\s*(\d{1,2})\s*(?:[-~至]\s*(\d{1,2}))?\s*节", text)
    if not match:
        return None, None
    start, end = int(match.group(1)), int(match.group(2) or match.group(1))
    if start not in PERIOD_TIMES or end not in PERIOD_TIMES or end < start:
        return None, None
    return start, end


def _parse_date_range(text):
    match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\s*(?:至|~|-)\s*(?:20\d{2}[./-])?(\d{1,2})[./-](\d{1,2})", text)
    if not match:
        return None, None
    year, month, day, end_month, end_day = map(int, match.groups())
    try:
        return date(year, month, day).isoformat(), date(year, end_month, end_day).isoformat()
    except ValueError:
        return None, None


def parse_time_segments(raw_time, fallback_locations=""):
    """Turn a course's original time string into independent meeting segments."""
    result = []
    last_weekday = None
    for text in _split_segments(raw_time):
        weekday_match = re.search(r"(?:周|星期)([一二三四五六日天])", text)
        start_period, end_period = _parse_periods(text)
        date_start, date_end = _parse_date_range(text)
        weekday = WEEKDAYS.get(weekday_match.group(1)) if weekday_match else last_weekday
        if weekday is not None:
            last_weekday = weekday
        if weekday is None and not date_start:
            continue
        if start_period is None:
            continue
        weeks, parity = _parse_weeks(text)
        location = re.sub(r".*?(?:第?\s*\d{1,2}\s*(?:[-~至]\s*\d{1,2})?\s*节)", "", text)
        location = re.sub(r"\[[^\]]*\]", "", location)
        location = re.sub(r"(?:第)?[\d、，,\s~-]+周|[单双]周", "", location).strip(" ，,;；")
        result.append({
            "weekday": weekday,
            "weeks": weeks,
            "parity": parity,
            "start_period": start_period,
            "end_period": end_period,
            "start_time": PERIOD_TIMES[start_period][0],
            "end_time": PERIOD_TIMES[end_period][1],
            "date_start": date_start,
            "date_end": date_end,
            "location": location or fallback_locations,
            "raw_time": text,
        })
    return result


def parse_selected_courses_html(markup):
    """Find the selected-course table by header names, never fixed column positions."""
    parser = _TableParser()
    parser.feed(markup or "")
    return _parse_selected_courses_tables(parser.tables)


_VISIBLE_TABLES_SCRIPT = r"""
tables => tables.map(table => {
  const clean = value => String(value ?? "")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n[ \t]+/g, "\n")
    .trim();
  const grid = [];
  Array.from(table.rows).forEach((row, rowIndex) => {
    grid[rowIndex] ||= [];
    let column = 0;
    Array.from(row.cells).forEach(cell => {
      while (grid[rowIndex][column] !== undefined) column += 1;
      const rowSpan = cell.rowSpan || 1;
      const colSpan = cell.colSpan || 1;
      for (let rowOffset = 0; rowOffset < rowSpan; rowOffset += 1) {
        grid[rowIndex + rowOffset] ||= [];
        for (let colOffset = 0; colOffset < colSpan; colOffset += 1) {
          grid[rowIndex + rowOffset][column + colOffset] = rowOffset || colOffset
            ? ""
            : clean(cell.innerText || cell.textContent);
        }
      }
      column += colSpan;
    });
  });
  const width = Math.max(0, ...grid.map(row => row.length));
  return grid.map(row => Array.from({length: width}, (_, index) => row[index] ?? ""));
})
"""


def _visible_timetable_tables(page):
    """Return only rendered timetable tables, with rowspan/colspan expanded."""
    return page.locator("table:visible").evaluate_all(_VISIBLE_TABLES_SCRIPT)


def _parse_grid_table(grid_table):
    """Extract course identifiers and detailed sessions from the visual grid table."""
    if not grid_table:
        return set(), {}

    header = grid_table[0]
    day_cols = {}
    for col_idx, col_name in enumerate(header):
        col_clean = re.sub(r"\s+", "", col_name)
        for w_name, w_val in WEEKDAYS.items():
            if w_name in col_clean:
                day_cols[col_idx] = w_val
                break

    grid_course_identifiers = set()
    grid_courses_by_key = {}
    w_names = ["一", "二", "三", "四", "五", "六", "日"]

    for row in grid_table[1:]:
        if not row:
            continue
        row_label = row[0] if row else ""
        p_match = re.search(r"第?\s*(\d{1,2})\s*节", row_label)
        default_period = int(p_match.group(1)) if p_match else None

        for col_idx, weekday in day_cols.items():
            if col_idx >= len(row):
                continue
            cell_text = row[col_idx].strip()
            if not cell_text:
                continue

            for c_code in re.findall(r"\(([A-Za-z0-9_-]{5,12})\)", cell_text):
                grid_course_identifiers.add(c_code)

            for raw_line in cell_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                code_match = re.search(r"\(([A-Za-z0-9_-]{5,12})\)", line)
                if not code_match:
                    continue
                c_code = code_match.group(1)

                sp, ep = None, None
                p_match_line = re.search(r"\[?\s*(\d{1,2})\s*(?:[-~至]\s*(\d{1,2}))?\s*节\s*\]?", line)
                if p_match_line and p_match_line.start() < code_match.start():
                    sp = int(p_match_line.group(1))
                    ep = int(p_match_line.group(2) or p_match_line.group(1))
                elif default_period is not None:
                    sp, ep = default_period, default_period
                else:
                    continue

                if sp not in PERIOD_TIMES or ep not in PERIOD_TIMES or ep < sp:
                    continue

                weeks = []
                parity = None
                for wm in re.finditer(r"\[([^\]]+)\]", line):
                    w_cand = wm.group(1)
                    if "节" in w_cand:
                        continue
                    w_parsed, p_parsed = _parse_weeks("[" + w_cand + "]")
                    if w_parsed:
                        weeks = w_parsed
                        parity = p_parsed
                        break

                prefix = line[:code_match.start()].strip()
                prefix = re.sub(r"\[?\s*\d{1,2}\s*(?:[-~至]\s*\d{1,2})?\s*节\s*\]?", "", prefix).strip()
                prefix = re.sub(r"\[[^\]]+\]", "", prefix).strip()
                parts = prefix.split()
                if len(parts) >= 2:
                    teacher_pre = parts[0]
                    c_name = " ".join(parts[1:])
                else:
                    teacher_pre = ""
                    c_name = prefix

                suffix = line[code_match.end():].strip()
                suffix = re.sub(r"\[[^\]]+\]", "", suffix).strip()
                suffix_parts = suffix.split()
                teacher_post = ""
                loc = ""
                if len(suffix_parts) >= 2:
                    teacher_post = " ".join(suffix_parts[:-1])
                    loc = suffix_parts[-1]
                elif len(suffix_parts) == 1:
                    loc = suffix_parts[0]

                teacher = teacher_post or teacher_pre
                session_item = {
                    "weekday": weekday,
                    "weeks": weeks,
                    "parity": parity,
                    "start_period": sp,
                    "end_period": ep,
                    "start_time": PERIOD_TIMES[sp][0],
                    "end_time": PERIOD_TIMES[ep][1],
                    "date_start": None,
                    "date_end": None,
                    "location": loc,
                    "teacher": teacher,
                    "raw_time": f"周{w_names[weekday]} 第{sp}-{ep}节",
                }

                c_key = c_code or c_name
                if c_key not in grid_courses_by_key:
                    grid_courses_by_key[c_key] = {
                        "code": c_code,
                        "name": c_name,
                        "teachers": [teacher] if teacher else [],
                        "locations": [loc] if loc else [],
                        "sessions": [session_item],
                    }
                else:
                    entry = grid_courses_by_key[c_key]
                    if teacher and teacher not in entry["teachers"]:
                        entry["teachers"].append(teacher)
                    if loc and loc not in entry["locations"]:
                        entry["locations"].append(loc)
                    sig = (weekday, sp, ep, tuple(weeks))
                    if not any((s["weekday"], s["start_period"], s["end_period"], tuple(s["weeks"])) == sig for s in entry["sessions"]):
                        entry["sessions"].append(session_item)

    return grid_course_identifiers, grid_courses_by_key


def _parse_selected_courses_tables(tables):
    courses_by_key = {}
    last_course_key = None

    for table_index, table in enumerate(tables):
        if not table:
            continue
        headers = table[0]
        code = _header_index(headers, ("新课程序号", "新课程", "课程代码", "课程号"))
        name = _header_index(headers, ("课程名称", "课程"))
        teacher = _header_index(headers, ("教师", "任课教师"))
        meeting = _header_index(headers, ("上课时间", "时间"))
        location = _header_index(headers, ("上课地点", "地点", "教室"))
        campus = _header_index(headers, ("校区",))
        if name is None or meeting is None:
            continue
        rows = table[1:]
        if not rows:
            rows = next((candidate for candidate in tables[table_index + 1:] if candidate), [])
        for row in rows:
            def cell(index):
                return row[index].strip() if index is not None and index < len(row) else ""
            raw_time = cell(meeting)
            c_code = cell(code)
            c_name = cell(name)
            c_teacher = cell(teacher)
            places = " · ".join(value for value in (cell(campus), cell(location)) if value)

            # Handle continuation row (rowspan)
            if not c_code and not c_name and last_course_key and raw_time:
                c_key = last_course_key
            elif c_code or c_name:
                c_key = c_code or c_name
            else:
                continue

            sessions = parse_time_segments(raw_time, places)
            if not sessions:
                continue

            if c_key not in courses_by_key:
                courses_by_key[c_key] = {
                    "id": f"{c_code or c_name}:{len(courses_by_key)}",
                    "code": c_code,
                    "name": c_name,
                    "teacher": c_teacher,
                    "raw_time": raw_time,
                    "location": places,
                    "sessions": sessions,
                }
                last_course_key = c_key
            else:
                existing = courses_by_key[c_key]
                if not existing["code"] and c_code:
                    existing["code"] = c_code
                if not existing["name"] and c_name:
                    existing["name"] = c_name
                if c_teacher:
                    teachers = [t.strip() for t in re.split(r"[,，、;；\s]+", existing["teacher"]) if t.strip()]
                    for nt in re.split(r"[,，、;；\s]+", c_teacher):
                        nt = nt.strip()
                        if nt and nt not in teachers:
                            teachers.append(nt)
                    existing["teacher"] = "、".join(teachers)
                if places:
                    locs = [l.strip() for l in existing["location"].split(" · ") if l.strip()]
                    if places not in locs:
                        locs.append(places)
                    existing["location"] = " · ".join(locs)
                if raw_time and raw_time not in existing["raw_time"]:
                    existing["raw_time"] = f"{existing['raw_time']}, {raw_time}" if existing["raw_time"] else raw_time
                for s in sessions:
                    sig = (s.get("weekday"), s.get("start_period"), s.get("end_period"), tuple(s.get("weeks") or []))
                    if not any((es.get("weekday"), es.get("start_period"), es.get("end_period"), tuple(es.get("weeks") or [])) == sig for es in existing["sessions"]):
                        existing["sessions"].append(s)

        if courses_by_key:
            break

    list_courses = list(courses_by_key.values())

    # Look for visual weekly timetable grid ('学生课表')
    grid_table = None
    for table in tables:
        if not table:
            continue
        header_str = " ".join(table[0])
        if "节次" in header_str and any(w in header_str for w in ("周一", "星期一")):
            grid_table = table
            break

    if not grid_table:
        return list_courses

    grid_course_identifiers, grid_courses_by_key = _parse_grid_table(grid_table)

    if not grid_course_identifiers:
        return list_courses

    if not list_courses and grid_courses_by_key:
        for idx, (k, g) in enumerate(grid_courses_by_key.items()):
            list_courses.append({
                "id": f"{g['code'] or g['name']}:{idx}",
                "code": g["code"],
                "name": g["name"],
                "teacher": "、".join(g["teachers"]),
                "location": " · ".join(g["locations"]),
                "raw_time": "; ".join(s["raw_time"] for s in g["sessions"]),
                "sessions": g["sessions"],
            })
        return list_courses

    filtered_courses = []
    for c in list_courses:
        c_code = c.get("code", "")
        c_name = c.get("name", "")

        matched_key = None
        if c_code and c_code in grid_course_identifiers:
            matched_key = c_code
        elif any(ident in c_name or c_name in ident for ident in grid_course_identifiers):
            matched_key = c_code or c_name

        if matched_key:
            grid_entry = grid_courses_by_key.get(matched_key) or grid_courses_by_key.get(c_code) or grid_courses_by_key.get(c_name)
            if grid_entry and grid_entry.get("sessions"):
                list_has_weeks = any(s.get("weeks") for s in c.get("sessions", []))
                grid_has_weeks = any(s.get("weeks") for s in grid_entry["sessions"])
                if not list_has_weeks and grid_has_weeks:
                    c["sessions"] = grid_entry["sessions"]
                    if grid_entry.get("teachers") and not c.get("teacher"):
                        c["teacher"] = "、".join(grid_entry["teachers"])
                    if grid_entry.get("locations") and not c.get("location"):
                        c["location"] = " · ".join(grid_entry["locations"])
            filtered_courses.append(c)

    return filtered_courses if filtered_courses else list_courses


def _xlsx_column_index(reference):
    letters = "".join(character for character in reference if character.isalpha())
    value = 0
    for character in letters:
        value = value * 26 + ord(character.upper()) - ord("A") + 1
    return value - 1


def _xlsx_text(element, shared_strings):
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    cell_type = element.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in element.findall(f".//{namespace}t"))
    value = element.findtext(f"{namespace}v", default="")
    if cell_type == "s" and value.isdigit() and int(value) < len(shared_strings):
        return shared_strings[int(value)]
    return value


def _xlsx_rows(markup, shared_strings):
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    root = ElementTree.fromstring(markup)
    rows = []
    for row in root.findall(f".//{namespace}row"):
        values = []
        for cell in row.findall(f"{namespace}c"):
            column = _xlsx_column_index(cell.get("r", "A1"))
            values.extend("" for _ in range(max(0, column - len(values))))
            values.append(_xlsx_text(cell, shared_strings))
        rows.append(values)
    return rows


def parse_exported_timetable_xlsx(content):
    """Read the selected-course sheet emitted by the local Tongji exporter extension."""
    try:
        with ZipFile(BytesIO(content)) as archive:
            if len(archive.infolist()) > 50 or sum(item.file_size for item in archive.infolist()) > settings.MAX_CONTENT_LENGTH_BYTES * 4:
                raise ValueError("课表文件内容异常，请重新从插件导出")
            if "xl/workbook.xml" not in archive.namelist():
                raise ValueError("文件不是有效的 Excel 课表")
            shared_strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                shared_strings = ["".join(node.text or "" for node in item.findall(f".//{namespace}t")) for item in root]
            sheets = [
                _xlsx_rows(archive.read(name), shared_strings)
                for name in archive.namelist()
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            ]
    except (BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise ValueError("文件不是有效的 Excel 课表") from error
    courses = _parse_selected_courses_tables(sheets)
    if not courses:
        raise ValueError("未找到插件导出的“已选课程”数据，请确认上传的是课表插件导出的 .xlsx 文件")
    return courses


def fetch_selected_courses():
    """Read the authenticated timetable page through CDP without persisting browser secrets."""
    target_id = None
    try:
        opened = requests.get(f"{settings.CDP_PROXY_BASE_URL}/new", params={"url": TIMETABLE_URL}, timeout=15)
        target_id = opened.json()["targetId"]
        time.sleep(2)
        script = "document.documentElement.innerHTML"
        response = requests.post(f"{settings.CDP_PROXY_BASE_URL}/eval", params={"target": target_id}, data=script, timeout=15)
        markup = response.json().get("value", "")
        courses = parse_selected_courses_html(markup)
        return courses if courses else None
    except (requests.RequestException, KeyError, ValueError, json.JSONDecodeError):
        return None
    finally:
        if target_id:
            try:
                requests.get(f"{settings.CDP_PROXY_BASE_URL}/close", params={"target": target_id}, timeout=5)
            except requests.RequestException:
                pass


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise TimetableFetchError("服务器未安装浏览器运行环境") from exc
    return sync_playwright()


def _first_visible(locator):
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible():
            return candidate
    return None


def _login(page, username, password):
    username_input = _first_visible(page.locator(
        '#j_username, input[name="username"], input#username, input[name="userName"], input#userName, input[autocomplete="username"]'
    ))
    password_input = _first_visible(page.locator('#j_password, input[type="password"]'))
    if not username_input or not password_input:
        raise TimetableLoginError("未找到统一身份认证登录表单")

    username_input.fill(username)
    password_input.fill(password)
    username_input.blur()
    page.wait_for_timeout(500)
    if _first_visible(page.locator('#j_checkcode')):
        raise TimetableLoginError("该账号需要验证码，暂时无法自动登录")
    submit = _first_visible(page.locator(
        '#loginButton, button[type="submit"], input[type="submit"], #loginBtn, #login, .login-btn'
    ))
    if not submit:
        raise TimetableLoginError("未找到统一身份认证登录按钮")
    submit.click()

    try:
        page.wait_for_function("() => !document.querySelector('input[type=password]')", timeout=20_000)
    except Exception as exc:
        raise TimetableLoginError("登录未完成，请检查账号密码或在一网通办完成验证") from exc


def fetch_selected_courses_with_credentials(username, password):
    """Log in in an ephemeral browser and return the current user's courses.

    The browser context is never persisted, so neither passwords nor login cookies
    are written to disk.  This is intentionally separate from the local CDP flow.
    """
    try:
        with _playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="zh-CN")
                page = context.new_page()
                page.goto(TIMETABLE_URL, wait_until="domcontentloaded", timeout=60_000)
                _login(page, username, password)
                page.goto(TIMETABLE_URL, wait_until="networkidle", timeout=60_000)
                try:
                    page.wait_for_selector("table", timeout=20_000)
                except Exception as exc:
                    raise TimetableFetchError("已登录，但课表页面未加载完成") from exc
                return _wait_for_selected_courses(page)
            finally:
                browser.close()
    except TimetableLoginError:
        raise
    except TimetableFetchError:
        raise
    except Exception as exc:
        raise TimetableFetchError("课表服务暂时无法访问") from exc


def _wait_for_selected_courses(page, timeout_ms=60_000):
    deadline = time.monotonic() + timeout_ms / 1_000
    while True:
        courses = _parse_selected_courses_tables(_visible_timetable_tables(page))
        if courses:
            return courses
        remaining_ms = int((deadline - time.monotonic()) * 1_000)
        if remaining_ms <= 0:
            raise TimetableFetchError("个人课表已经打开，但课程数据仍未加载完成；请稍后重试")
        page.wait_for_timeout(min(1_000, remaining_ms))


def fetch_selected_courses_from_cdp(cdp_endpoint):
    """Read the timetable from the authenticated temporary noVNC browser."""
    try:
        with _playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(cdp_endpoint)
            pages = [page for context in browser.contexts for page in context.pages]
            if not pages:
                raise TimetableFetchError("认证浏览器中没有可用页面")
            page = next((candidate for candidate in pages if "tongji.edu.cn" in candidate.url), pages[0])
            if "GraduateStudentTimeTable" not in page.url:
                view_timetable = _first_visible(page.get_by_text("查看课表", exact=True))
                if view_timetable:
                    view_timetable.click()
                    page.wait_for_timeout(1_000)
                else:
                    page.goto(TIMETABLE_URL, wait_until="networkidle", timeout=60_000)
            return _wait_for_selected_courses(page)
    except TimetableFetchError:
        raise
    except Exception as exc:
        raise TimetableFetchError("无法读取认证后的课表") from exc
