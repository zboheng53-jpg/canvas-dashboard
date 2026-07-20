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
        if any(alias in normalized for alias in aliases):
            return index
    return None


def _split_segments(raw_time):
    separator = r"[；;\n]+|[,，](?=\s*(?:(?:周|星期)[一二三四五六日天]|20\d{2}[./-]))"
    return [part.strip() for part in re.split(separator, raw_time or "") if part.strip()]


def _parse_weeks(text):
    weeks = set()
    for match in re.finditer(r"(\[|第)\s*(\d{1,2})\s*[-~至]\s*(\d{1,2})\s*(周)?", text):
        if match.group(1) == "[" or match.group(4) == "周":
            weeks.update(range(int(match.group(2)), int(match.group(3)) + 1))
    for match in re.findall(r"(?:第)?([\d、，,\s]+)周", text):
        weeks.update(int(value) for value in re.findall(r"\d{1,2}", match))
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
    for text in _split_segments(raw_time):
        weekday_match = re.search(r"(?:周|星期)([一二三四五六日天])", text)
        start_period, end_period = _parse_periods(text)
        date_start, date_end = _parse_date_range(text)
        if not weekday_match and not date_start:
            continue
        if start_period is None:
            continue
        weeks, parity = _parse_weeks(text)
        location = re.sub(r".*?(?:第?\s*\d{1,2}\s*(?:[-~至]\s*\d{1,2})?\s*节)", "", text)
        location = re.sub(r"\[[^\]]*\]", "", location)
        location = re.sub(r"(?:第)?[\d、，,\s~-]+周|[单双]周", "", location).strip(" ，,;；")
        result.append({
            "weekday": WEEKDAYS.get(weekday_match.group(1)) if weekday_match else None,
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


def _parse_selected_courses_tables(tables):
    courses = []
    for table_index, table in enumerate(tables):
        if not table:
            continue
        headers = table[0]
        code = _header_index(headers, ("新课程序号", "课程代码", "课程号"))
        name = _header_index(headers, ("课程名称",))
        teacher = _header_index(headers, ("教师", "任课教师"))
        meeting = _header_index(headers, ("上课时间", "时间"))
        location = _header_index(headers, ("地点", "教室"))
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
            places = " · ".join(value for value in (cell(campus), cell(location)) if value)
            sessions = parse_time_segments(raw_time, places)
            if not sessions:
                continue
            course_name = cell(name)
            courses.append({
                "id": f"{cell(code) or course_name}:{len(courses)}",
                "code": cell(code), "name": course_name, "teacher": cell(teacher),
                "raw_time": raw_time, "location": places, "sessions": sessions,
            })
        if courses:
            return courses
    return []


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
                courses = parse_selected_courses_html(page.content())
                if not courses:
                    raise TimetableFetchError("未在课表页面找到已选课程")
                return courses
            finally:
                browser.close()
    except TimetableLoginError:
        raise
    except TimetableFetchError:
        raise
    except Exception as exc:
        raise TimetableFetchError("课表服务暂时无法访问") from exc
