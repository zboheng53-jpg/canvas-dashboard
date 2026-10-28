"""Lossless sections and a fail-closed check of a manually annotated sample."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from material_log import parse_legacy_materials
from scripts.check_materials_sample import validate_fixture


def assert_lossless(text, sections):
    assert "".join(section["raw"] for section in sections) == text
    offset = 0
    for section in sections:
        assert section["start"] == offset
        assert section["id"] == f"legacy-{offset}"
        assert section["raw"] == text[section["start"]:section["end"]]
        assert section["body"] == section["raw"]
        assert section["start_line"] == len(text[:offset].splitlines()) + 1
        offset = section["end"]
    assert offset == len(text)


@pytest.mark.parametrize("text", ["", "正文没有标题\n保留空格  \r\n", " \r\n\t\n"])
def test_empty_or_unheaded_materials_remain_exact(text):
    sections = parse_legacy_materials(text)
    assert len(sections) == (1 if text else 0)
    assert_lossless(text, sections)
    if sections:
        assert sections[0]["date"] is None


def test_preamble_adjacent_headings_duplicate_dates_and_whitespace():
    text = ("  前言\r\n\r\n【2026-10-28 第一次】  \r\n"
            "【2026年10月28日 第二次】\r\n正文  \n\n## 方法说明 ##\n末尾\t")
    sections = parse_legacy_materials(text)
    assert [section["start_line"] for section in sections] == [1, 3, 4, 7]
    assert [section["date"] for section in sections] == [None, "2026-10-28", "2026-10-28", None]
    assert [section["title"] for section in sections] == ["历史资料", "2026-10-28 第一次", "2026年10月28日 第二次", "方法说明"]
    assert sections == parse_legacy_materials(text)
    assert_lossless(text, sections)


@pytest.mark.parametrize("heading, expected", [
    ("【2024-02-29 结果】", "2024-02-29"),
    ("# 2026 年 1 月 2 日 结果", "2026-01-02"),
    ("## 2026-02-29 结果", None),
    ("【10月28日 结果】", None),
    ("【2026-1-2 结果】", None),
    ("# 2026年13月1日", None),
    ("【12026-10-28 / 2026-10-281】", None),
    ("###### 2026-10-28 与 2026-10-29", "2026-10-28"),
])
def test_only_complete_valid_heading_dates_are_used(heading, expected):
    text = heading + "\n正文另有 2026-11-01，不能替代标题日期"
    sections = parse_legacy_materials(text)
    assert len(sections) == 1
    assert sections[0]["date"] == expected
    assert_lossless(text, sections)


def test_body_dates_indented_code_and_inline_headings_do_not_split():
    text = ("【方法】\n正文 2026-10-28\n前缀【2026-10-28】\n"
            "【2026-10-28】后缀\n    # 2026-10-28\n\t【2026-10-28】\n"
            "  \t# 2026-10-28\n#无空格 2026-10-28\n####### 2026-10-28\n"
            "   ### 2026-10-29 真实标题\n结果\n")
    sections = parse_legacy_materials(text)
    assert [section["date"] for section in sections] == [None, "2026-10-29"]
    assert [section["start_line"] for section in sections] == [1, 10]
    assert_lossless(text, sections)


@pytest.mark.parametrize("marker", ["```", "~~~~"])
def test_fenced_code_ignores_pseudo_headings_and_requires_matching_close(marker):
    other = "~~~" if marker[0] == "`" else "```"
    text = (f"【方法】\n  {marker}python\n# 2026-10-20 代码\n{other}\n"
            f"【2026-10-21 代码】\n{marker[:-1]}\n# 2026-10-22 代码\n"
            f"{marker} trailing\n# 2026-10-23 代码\n {marker}{marker[0]}\n"
            "## 2026-10-28 真实标题\n结果")
    sections = parse_legacy_materials(text)
    assert [section["date"] for section in sections] == [None, "2026-10-28"]
    assert [section["start_line"] for section in sections] == [1, 11]
    assert_lossless(text, sections)


def test_unclosed_fence_preserves_remaining_content_without_false_segments():
    text = "前言\n```\n【2026-10-28】\n# 2026-10-29\n"
    sections = parse_legacy_materials(text)
    assert len(sections) == 1 and sections[0]["date"] is None
    assert_lossless(text, sections)


def sample_fixture():
    text = "前言\r\n【2026-10-28 记录】\n正文\n# 方法\n末尾"
    return {"project_id": 14, "updated_at": "2026-10-28T00:00:00+00:00", "materials": text,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "expected_start_lines": [1, 2, 4], "expected_dates": [None, "2026-10-28", None]}


def test_sample_validation_checks_manual_boundaries_dates_and_full_original():
    result = validate_fixture(sample_fixture())
    assert result["ok"] and result["segments"] == 3 and result["dated_segments"] == 1
    assert all(result["checks"].values())


@pytest.mark.parametrize("change", [
    {"sha256": "0" * 64},
    {"expected_start_lines": [1, 3, 4]},
    {"expected_start_lines": [1, 2]},
    {"expected_dates": [None, "2026-10-29", None]},
    {"expected_dates": [None, "2026-02-30", None]},
])
def test_sample_validation_rejects_wrong_hash_count_boundaries_or_dates(change):
    with pytest.raises(ValueError):
        validate_fixture({**sample_fixture(), **change})


def test_sample_validation_requires_manual_expectations():
    fixture = sample_fixture()
    del fixture["expected_dates"]
    with pytest.raises(ValueError, match="expected_dates"):
        validate_fixture(fixture)


def test_sample_validation_detects_reconstruction_failure(monkeypatch):
    from scripts import check_materials_sample
    monkeypatch.setattr(check_materials_sample, "parse_legacy_materials", lambda _: [])
    with pytest.raises(ValueError, match="逐字重建失败"):
        validate_fixture(sample_fixture())


def test_cli_requires_existing_fixture_and_reports_results(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_materials_sample.py"
    path = tmp_path / "sample.json"
    path.write_text(json.dumps(sample_fixture(), ensure_ascii=False), encoding="utf-8")
    success = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True, encoding="utf-8")
    assert success.returncode == 0
    assert json.loads(success.stdout)["segments"] == 3
    absent = subprocess.run([sys.executable, str(script), str(tmp_path / "absent.json")], capture_output=True)
    assert absent.returncode != 0
    required = subprocess.run([sys.executable, str(script)], capture_output=True)
    assert required.returncode != 0
