"""Playwright operations for the Zhihuishu background worker."""
import argparse
import os
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import zhihuishu_store

LOGIN_URL = "https://passport.zhihuishu.com/login"
KEEPALIVE_URL = "https://onlineweb.zhihuishu.com/onlinestuh5"
ASSIGNMENTS_URL = "https://onlineweb.zhihuishu.com/onlinestuh5"
SMART_COURSE_HOST = "ai-smart-course-student-pro.zhihuishu.com"
TASK_LIST_URL_FRAGMENT = "kg-run-student.zhihuishu.com/student/gateway/t/task/taskList"
SMART_COURSE_LINK_SELECTOR = (
    f'a[href*="{SMART_COURSE_HOST}/singleCourse/"]'
)
TASK_TAB_TEXT = "任务·作业·考试"
UNFINISHED_TAB_TEXT = "未完成"
COMPLETED_TAB_TEXT = "已完成"
TASK_TYPE_NAMES = {
    0: "\u77e5\u8bc6\u70b9\u5b66\u4e60",
    1: "\u4f5c\u4e1a",
    3: "\u8bdd\u9898\u8ba8\u8bba",
}


def profile_path(username: str) -> Path:
    path = zhihuishu_store.DATA_DIR / "users" / username / "zhihuishu_chromium_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _profile_lock_is_stale(lock_target: str, current_host: str | None = None, pid_is_running=None) -> bool:
    current_host = current_host or socket.gethostname()
    pid_is_running = pid_is_running or _pid_is_running
    prefix = f"{current_host}-"
    if not lock_target.startswith(prefix):
        return True

    pid_text = lock_target[len(prefix):]
    if not pid_text.isdigit():
        return True
    return not pid_is_running(int(pid_text))


def _cleanup_stale_profile_lock(path: Path) -> None:
    try:
        lock_target = os.readlink(path / "SingletonLock")
    except OSError:
        return

    if not _profile_lock_is_stale(lock_target):
        return

    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            (path / name).unlink()
        except FileNotFoundError:
            pass


def _format_due_ts(value) -> str | None:
    if not value:
        return None
    text = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            pass
    return text


def smart_course_task_url(href: str) -> str:
    if not href:
        return ""

    parsed = urlparse(href)
    if SMART_COURSE_HOST not in parsed.netloc:
        return ""

    parts = parsed.path.strip("/").split("/")
    if len(parts) < 4 or parts[0] != "singleCourse":
        return ""

    if parts[1] == "taskAndExam":
        return href

    parts[1] = "taskAndExam"
    return urlunparse(parsed._replace(path="/" + "/".join(parts)))


def normalize_assignment(raw: dict, url: str = "") -> dict:
    raw_id = raw.get("id") or raw.get("workId") or raw.get("homeworkId") or raw.get("url") or raw.get("title")
    title = raw.get("title") or raw.get("name") or raw.get("workName") or raw.get("taskName") or "智慧树任务"
    course = raw.get("course") or raw.get("courseName") or raw.get("courseTitle") or ""
    due_str = raw.get("due_str") or raw.get("endTime") or raw.get("deadline") or ""
    due_ts = raw.get("due_ts") or raw.get("endTimeStamp") or raw.get("deadlineTs")
    item_type = raw.get("type") or raw.get("typeName") or TASK_TYPE_NAMES.get(raw.get("taskType")) or "智慧树"
    url = raw.get("url") or raw.get("href") or url
    return {
        "id": str(raw_id) if str(raw_id).startswith("zhs_") else f"zhs_{raw_id}",
        "title": str(title),
        "course": str(course),
        "due_str": str(due_str) if due_str else "",
        "due_ts": str(due_ts) if due_ts else _format_due_ts(due_str),
        "type": str(item_type),
        "url": str(url),
    }


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: python -m pip install -r requirements.txt") from exc
    return sync_playwright()


def _context_launch_options(headless: bool = True) -> dict:
    options = {
        "headless": headless,
        "viewport": {"width": 1280, "height": 900},
        "locale": "zh-CN",
    }
    executable_path = os.environ.get("ZHIHUISHU_CHROMIUM_EXECUTABLE")
    if executable_path:
        options["executable_path"] = executable_path
    return options


def _new_context(playwright, username: str, headless: bool = True):
    user_data_dir = profile_path(username)
    _cleanup_stale_profile_lock(user_data_dir)
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        **_context_launch_options(headless),
    )


def _wait_for_spa(page, timeout: int = 20_000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def _course_title(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    title = lines[0]
    for suffix in ("去学习", "继续学习", "开始学习"):
        title = title.replace(suffix, "").strip()
    return title


def smart_course_link_candidates(raw_links: list[dict]) -> list[dict]:
    by_task_url = {}
    for link in raw_links:
        href = str(link.get("href") or "")
        task_url = smart_course_task_url(href)
        if not task_url:
            continue

        title = _course_title(str(link.get("text") or ""))
        existing = by_task_url.get(task_url)
        if not existing or (title and not existing.get("course")):
            by_task_url[task_url] = {
                "href": href,
                "task_url": task_url,
                "course": title,
            }
    return list(by_task_url.values())


def _collect_smart_course_links(page) -> list[dict]:
    links = page.evaluate(
        """
        (selector) => Array.from(document.querySelectorAll(selector))
          .map((el) => ({
            href: el.href,
            text: (el.innerText || el.textContent || '').trim()
          }))
          .filter((item) => item.href)
        """,
        SMART_COURSE_LINK_SELECTOR,
    )

    return smart_course_link_candidates(links)


def _click_course_link(page, href: str):
    before_pages = set(page.context.pages)
    clicked = page.evaluate(
        """
        (href) => {
          const el = Array.from(document.querySelectorAll('a')).find((item) => item.href === href);
          if (!el) return false;
          el.click();
          return true;
        }
        """,
        href,
    )
    if not clicked:
        page.goto(href, wait_until="domcontentloaded", timeout=90_000)
        return page

    time.sleep(2)
    new_pages = [candidate for candidate in page.context.pages if candidate not in before_pages]
    return new_pages[-1] if new_pages else page


def _click_text(page, text: str, timeout: int = 3_000) -> bool:
    try:
        page.get_by_text(text, exact=True).first.click(timeout=timeout)
        return True
    except Exception:
        pass

    return bool(page.evaluate(
        """
        (label) => {
          const candidates = Array.from(document.querySelectorAll('a, button, div, span, li'));
          const el = candidates.find((item) => {
            const text = (item.innerText || item.textContent || '').trim();
            return text === label;
          });
          if (!el) return false;
          el.click();
          return true;
        }
        """,
        text,
    ))


def _click_task_tab_by_keywords(page) -> bool:
    return bool(page.evaluate(
        """
        () => {
          const keywords = ['任务', '作业', '考试'];
          const candidates = Array.from(document.querySelectorAll('a, button, div, span, li'));
          const el = candidates.find((item) => {
            const text = (item.innerText || item.textContent || '').trim();
            return text.length <= 30 && keywords.every((keyword) => text.includes(keyword));
          });
          if (!el) return false;
          el.click();
          return true;
        }
        """
    ))


def _open_task_tab(page, fallback_url: str = "") -> bool:
    if "/singleCourse/taskAndExam/" in page.url:
        return True

    try:
        page.locator('a[href*="/singleCourse/taskAndExam/"]').first.click(timeout=5_000)
        _wait_for_spa(page)
        if "/singleCourse/taskAndExam/" in page.url:
            return True
    except Exception:
        pass

    if _click_text(page, TASK_TAB_TEXT, timeout=5_000) or _click_task_tab_by_keywords(page):
        _wait_for_spa(page)
        time.sleep(1)
        if "/singleCourse/taskAndExam/" in page.url:
            return True

    task_url = smart_course_task_url(page.url) or fallback_url
    if task_url:
        page.goto(task_url, wait_until="domcontentloaded", timeout=90_000)
        _wait_for_spa(page)
        return "/singleCourse/taskAndExam/" in page.url and "passport" not in page.url.lower()

    return False


def _click_homework_task_type(page) -> None:
    try:
        page.evaluate(
            """
            () => {
              const candidates = Array.from(document.querySelectorAll(
                '.task-type-item, [class*="task-type"], div, span'
              ));
              const el = candidates.find((item) => {
                const text = (item.innerText || item.textContent || '').trim();
                return text.startsWith('作业') && text.includes('待完成') && text.length <= 80;
              });
              if (el) el.click();
            }
            """
        )
    except Exception:
        pass


def _task_list_response_items(response) -> list[dict]:
    try:
        payload = response.json()
    except Exception:
        return []
    data = payload.get("data")
    return data if isinstance(data, list) else []


def _fetch_unfinished_homework_items(page) -> list[dict] | None:
    _click_homework_task_type(page)
    time.sleep(1)

    if _click_text(page, COMPLETED_TAB_TEXT, timeout=2_000):
        try:
            page.wait_for_response(lambda response: TASK_LIST_URL_FRAGMENT in response.url, timeout=5_000)
        except Exception:
            pass
        time.sleep(0.5)

    try:
        with page.expect_response(
            lambda response: TASK_LIST_URL_FRAGMENT in response.url,
            timeout=15_000,
        ) as response_info:
            if not _click_text(page, UNFINISHED_TAB_TEXT, timeout=5_000):
                raise RuntimeError("unfinished tab not found")
        return _task_list_response_items(response_info.value)
    except Exception:
        return None


def open_login_browser(username: str) -> None:
    with _playwright() as p:
        context = _new_context(p, username, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
        print("Complete Zhihuishu login in the opened browser, then press Enter here.")
        input()
        context.close()


def check_session(username: str) -> bool:
    with _playwright() as p:
        context = _new_context(p, username)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(KEEPALIVE_URL, wait_until="domcontentloaded", timeout=60_000)
        time.sleep(2)
        url = page.url.lower()
        text = page.locator("body").inner_text(timeout=5_000).lower()
        cookies = context.cookies()
        context.close()

    if "login" in url or "passport" in url:
        return False
    if "登录" in text or "login" in text:
        return False
    return bool(cookies)


def keepalive(username: str) -> bool:
    with _playwright() as p:
        context = _new_context(p, username)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(KEEPALIVE_URL, wait_until="networkidle", timeout=60_000)
        context.close()
    return True


def fetch_assignments(username: str) -> list[dict]:
    raw_items = []
    reached_task_page = False

    with _playwright() as p:
        context = _new_context(p, username)
        page = context.pages[0] if context.pages else context.new_page()

        page.goto(ASSIGNMENTS_URL, wait_until="domcontentloaded", timeout=120_000)
        _wait_for_spa(page)
        time.sleep(2)
        course_links = _collect_smart_course_links(page)

        for course in course_links:
            course_page = _click_course_link(page, course["href"])
            _wait_for_spa(course_page)
            time.sleep(2)
            if "passport" not in course_page.url.lower():
                if _open_task_tab(course_page, course.get("task_url", "")):
                    reached_task_page = True
                    _wait_for_spa(course_page)
                    time.sleep(2)
                    unfinished_items = _fetch_unfinished_homework_items(course_page)
                    if unfinished_items is not None:
                        for raw in unfinished_items:
                            item = dict(raw)
                            if course.get("course") and not item.get("courseName"):
                                item["courseName"] = course["course"]
                            raw_items.append((item, course.get("task_url") or course.get("href", "")))

            if course_page is not page:
                course_page.close()
            page.goto(ASSIGNMENTS_URL, wait_until="domcontentloaded", timeout=120_000)
            _wait_for_spa(page)
            time.sleep(1)

        if not raw_items and not reached_task_page:
            raw_items = [(raw, "") for raw in page.evaluate(
            """
            () => Array.from(document.querySelectorAll('a, [data-id], .work, .homework, .task'))
              .map((el) => {
                const text = (el.innerText || el.textContent || '').trim();
                if (!text || !/(作业|考试|测试|任务)/.test(text)) return null;
                const href = el.href || el.querySelector('a')?.href || location.href;
                const lines = text.split(/\\n+/).map((line) => line.trim()).filter(Boolean);
                return {
                  id: el.dataset.id || el.dataset.workId || href,
                  title: lines[0],
                  course: lines[1] || '',
                  endTime: lines.find((line) => /(截止|到期|\\d{1,2}[-/]\\d{1,2})/.test(line)) || '',
                  type: text.includes('考试') ? '考试' : text.includes('测试') ? '测试' : '作业',
                  url: href,
                };
              })
              .filter(Boolean)
            """
            )]
        context.close()

    seen = set()
    items = []
    for raw, item_url in raw_items:
        item = normalize_assignment(raw, url=item_url)
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append(item)
    return items


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("login", "check", "keepalive", "fetch"))
    parser.add_argument("--username", required=True)
    args = parser.parse_args(argv)

    if args.command == "login":
        open_login_browser(args.username)
    elif args.command == "check":
        print("session OK" if check_session(args.username) else "session missing")
    elif args.command == "keepalive":
        print("keepalive OK" if keepalive(args.username) else "keepalive failed")
    elif args.command == "fetch":
        items = fetch_assignments(args.username)
        print(f"fetched {len(items)} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
