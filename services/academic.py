"""Academic term and holiday data."""
import json
import logging
import settings
from datetime import date, datetime, timedelta
from storage import read_json_file
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


def _get_holidays():
    """Only read local holiday data; ordinary pages never create CDP browser tabs."""
    data = read_json_file(_HOLIDAY_CACHE_FILE, {})
    return data.get("holidays", []) if isinstance(data, dict) else []


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

