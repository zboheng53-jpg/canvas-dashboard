import pytest

from services import academic as academic_service
from storage import write_json_file


@pytest.mark.parametrize("holidays", [[], [{"name": "国庆", "begin_day": "2026-10-01", "end_day": "2026-10-07"}]])
def test_holidays_read_local_cache_without_network_or_browser(tmp_path, monkeypatch, holidays):
    path = tmp_path / "holiday_cache.json"
    monkeypatch.setattr(academic_service, "_HOLIDAY_CACHE_FILE", path)
    monkeypatch.setattr(academic_service, "_fetch_holidays", lambda: pytest.fail("ordinary read opened CDP"))
    write_json_file(path, {"holidays": holidays, "fetched_at": "2000-01-01T00:00:00+08:00"})
    assert academic_service._get_holidays() == holidays


def test_missing_holiday_cache_is_immediate_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(academic_service, "_HOLIDAY_CACHE_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(academic_service, "_fetch_holidays", lambda: pytest.fail("ordinary read opened CDP"))
    assert academic_service._get_holidays() == []
