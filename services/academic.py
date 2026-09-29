"""Academic term and holiday data."""
import json
import logging
import requests
import settings
import threading
from datetime import date, datetime, timedelta
from storage import read_json_file, write_json_file
from user_paths import DATA_DIR
from web_common import CST

logger = logging.getLogger(__name__)


TERM_START = datetime.combine(settings.TERM_START_DATE, datetime.min.time(), tzinfo=CST)


TERM_LABEL = settings.TERM_LABEL


_TERM_CONFIG_FILE = DATA_DIR / "term_config.json"


def _compute_week_num(target_date, semester_start_date):
    """Compute current week number given a semester start date.
    Week 1 starts on the Monday containing or following the semester start date.
    """
    days_until_monday = (7 - semester_start_date.weekday()) % 7
    start_monday = semester_start_date + timedelta(days=days_until_monday)
    days_from_start_monday = (target_date - start_monday).days
    return max(0, days_from_start_monday // 7 + 1)


def _load_term_config(target_date=None):
    """Load term config and compute (term_label, week_num, semester_start_str) for target_date."""
    if target_date is None:
        target_date = datetime.now(CST).date()

    data = read_json_file(_TERM_CONFIG_FILE, {})
    semesters = data.get("semesters")

    if isinstance(semesters, list) and len(semesters) > 0:
        parsed_semesters = []
        for s in semesters:
            if not isinstance(s, dict):
                continue
            raw_start = s.get("start_date") or s.get("term_start")
            label = s.get("term_label") or s.get("term")
            weeks = s.get("weeks", 20)
            if raw_start and label:
                try:
                    dt_start = date.fromisoformat(raw_start)
                    days_until_monday = (7 - dt_start.weekday()) % 7
                    start_monday = dt_start + timedelta(days=days_until_monday)
                    parsed_semesters.append({
                        "label": label,
                        "start_monday": start_monday,
                        "weeks": weeks,
                    })
                except (TypeError, ValueError):
                    pass

        if parsed_semesters:
            parsed_semesters.sort(key=lambda item: item["start_monday"])
            
            # Check if target_date falls within any configured semester
            for i, sem in enumerate(parsed_semesters):
                end_sunday = sem["start_monday"] + timedelta(weeks=sem["weeks"]) - timedelta(days=1)
                if sem["start_monday"] <= target_date <= end_sunday:
                    week_num = (target_date - sem["start_monday"]).days // 7 + 1
                    return sem["label"], week_num, sem["start_monday"].strftime("%Y-%m-%d")

            # Dates before the first configured semester belong to its
            # preparation period (第 0 周).
            if target_date < parsed_semesters[0]["start_monday"]:
                first = parsed_semesters[0]
                return first["label"], 0, first["start_monday"].strftime("%Y-%m-%d")

            # A break immediately before a configured semester is its
            # preparation period (第 0 周), following Tongji's calendar wording.
            for i in range(len(parsed_semesters) - 1):
                prev_sem = parsed_semesters[i]
                next_sem = parsed_semesters[i + 1]
                prev_end = prev_sem["start_monday"] + timedelta(weeks=prev_sem["weeks"]) - timedelta(days=1)
                if prev_end < target_date < next_sem["start_monday"]:
                    return next_sem["label"], 0, next_sem["start_monday"].strftime("%Y-%m-%d")

            # If after last semester
            last = parsed_semesters[-1]
            week_num = (target_date - last["start_monday"]).days // 7 + 1
            return last["label"], week_num, last["start_monday"].strftime("%Y-%m-%d")

    # Fallback to single term_config or settings default
    label = data.get("term_label") or data.get("term") or TERM_LABEL
    start_raw = data.get("term_start") or data.get("semester_start")
    if start_raw:
        try:
            start_date = date.fromisoformat(start_raw)
            return label, _compute_week_num(target_date, start_date), start_date.strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            logger.warning("Invalid term config start date: %r", start_raw)

    return TERM_LABEL, _compute_week_num(target_date, TERM_START.date()), TERM_START.date().strftime("%Y-%m-%d")


def get_term_info(now=None):
    """Return (term_label, week_num, semester_start_str).
    Uses offline calendar configuration to compute active term and week number.
    """
    if now is None:
        now = datetime.now(CST)
    return _load_term_config(now.date())


_HOLIDAY_CACHE_FILE = DATA_DIR / "holiday_cache.json"


_HOLIDAY_CACHE_TTL = settings.HOLIDAY_CACHE_TTL_SECONDS


_HOLIDAY_FETCH_RETRY_INTERVAL = settings.HOLIDAY_FETCH_RETRY_INTERVAL_SECONDS


_holiday_fetch_lock = threading.Lock()


_holiday_fetch_failed_at = None


def _load_holiday_cache():
    """Load holiday data from disk cache. Returns list of holiday dicts or None."""
    if _HOLIDAY_CACHE_FILE.exists():
        try:
            data = json.loads(_HOLIDAY_CACHE_FILE.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(data["fetched_at"])
            age = (datetime.now(CST) - fetched_at).total_seconds()
            if age < _HOLIDAY_CACHE_TTL:
                return data.get("holidays")
        except Exception:
            pass
    return None


def _save_holiday_cache(holidays):
    """Save holiday data to disk cache."""
    _HOLIDAY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(_HOLIDAY_CACHE_FILE, {
        "holidays": holidays,
        "fetched_at": datetime.now(CST).isoformat(),
    })


def _fetch_holidays():
    """Fetch holiday data for current year from 1.tongji.edu.cn workbench API via CDP proxy.
    Returns list of dicts with keys: name, begin_day, end_day (as datetime.date).
    """
    try:
        year = datetime.now(CST).year
        # Open a tab on workbench to get authenticated session
        r = requests.get(
            f"{settings.CDP_PROXY_BASE_URL}/new",
            params={"url": "https://1.tongji.edu.cn/workbench"},
            timeout=15,
        )
        target_id = r.json()["targetId"]

        import time
        time.sleep(2)

        # Call the holiday API endpoint via the browser (uses auth cookies)
        r = requests.post(
            f"{settings.CDP_PROXY_BASE_URL}/eval",
            params={"target": target_id},
            data=(
                "new Promise(function(resolve){"
                "var x=new XMLHttpRequest();"
                "x.open('GET','/api/baseresservice/holiday/queryHolidayByYear?year=" + str(year) + "');"
                "x.onload=function(){resolve(x.responseText)};"
                "x.onerror=function(){resolve('XHR error')};"
                "x.send()"
                "})"
            ),
            timeout=15,
        )
        resp_text = r.json()["value"]
        api_resp = json.loads(resp_text)

        # Close tab
        requests.get(
            f"{settings.CDP_PROXY_BASE_URL}/close",
            params={"target": target_id},
            timeout=5,
        )

        if api_resp.get("code") != 200:
            logger.warning(f"Holiday API returned error: {api_resp}")
            return None

        holidays = []
        for h in api_resp.get("data", []):
            begin_dt = datetime.fromtimestamp(h["beginDay"] / 1000, tz=CST)
            end_dt = datetime.fromtimestamp(h["endDay"] / 1000, tz=CST)
            holidays.append({
                "name": h.get("remark", h.get("holidayName", "")),
                "begin_day": begin_dt.date().isoformat(),
                "end_day": end_dt.date().isoformat(),
            })
        return holidays
    except Exception as e:
        logger.warning(f"Holiday fetch via CDP failed: {e}")
    return None


def _get_holidays():
    """Get holiday list with cache. Returns list or empty list."""
    global _holiday_fetch_failed_at

    cached = _load_holiday_cache()
    if cached is not None:
        return cached

    now = datetime.now(CST)
    if (_holiday_fetch_failed_at and
            (now - _holiday_fetch_failed_at).total_seconds() < _HOLIDAY_FETCH_RETRY_INTERVAL):
        return []

    if not _holiday_fetch_lock.acquire(blocking=False):
        return []

    try:
        cached = _load_holiday_cache()
        if cached is not None:
            return cached

        fresh = _fetch_holidays()
        if fresh is not None:
            _holiday_fetch_failed_at = None
            _save_holiday_cache(fresh)
            return fresh

        _holiday_fetch_failed_at = datetime.now(CST)
        return []
    finally:
        _holiday_fetch_lock.release()


def _check_today_holiday(now):
    """Check if today is a holiday. Returns (is_holiday, holiday_name)."""
    today = now.date()
    holidays = _get_holidays()
    for h in holidays:
        begin = date.fromisoformat(h["begin_day"])
        end = date.fromisoformat(h["end_day"])
        if begin <= today <= end:
            return True, h["name"]
    return False, ""

