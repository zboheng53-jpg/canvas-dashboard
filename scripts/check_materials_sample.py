"""Validate a local, manually annotated materials fixture without network access."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from material_log import parse_legacy_materials


def validate_fixture(fixture):
    required = {"materials", "project_id", "updated_at", "sha256",
                "expected_start_lines", "expected_dates"}
    if not isinstance(fixture, dict) or not required.issubset(fixture):
        missing = required - set(fixture) if isinstance(fixture, dict) else required
        raise ValueError("缺少样本字段：" + ", ".join(sorted(missing)))
    original = fixture["materials"]
    if not isinstance(original, str) or not original:
        raise ValueError("materials 必须为非空原文")
    if type(fixture["project_id"]) is not int or not isinstance(fixture["updated_at"], str):
        raise ValueError("样本项目标识或版本无效")
    expected_hash = fixture["sha256"]
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise ValueError("sha256 必须为人工核对样本的 64 位小写摘要")
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
    if digest != expected_hash:
        raise ValueError(f"原文 SHA256 不符：实际 {digest}，预期 {expected_hash}")

    expected_lines, expected_dates = fixture["expected_start_lines"], fixture["expected_dates"]
    if (not isinstance(expected_lines, list) or not expected_lines
            or any(type(value) is not int or value < 1 for value in expected_lines)
            or expected_lines[0] != 1 or expected_lines != sorted(set(expected_lines))):
        raise ValueError("expected_start_lines 必须为从第 1 行开始的严格递增人工边界")
    if not isinstance(expected_dates, list) or len(expected_dates) != len(expected_lines):
        raise ValueError("expected_dates 必须与人工段落边界逐项对应")
    for expected in expected_dates:
        if expected is None:
            continue
        try:
            valid = isinstance(expected, str) and date.fromisoformat(expected).isoformat() == expected
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("expected_dates 仅接受完整有效 ISO 日期或 null")

    sections = parse_legacy_materials(original)
    if "".join(section["raw"] for section in sections) != original:
        raise ValueError("原文逐字重建失败")
    cursor = 0
    for section in sections:
        if (section["start"] != cursor or section["end"] <= cursor
                or section["raw"] != original[section["start"]:section["end"]]
                or section["body"] != section["raw"]):
            raise ValueError("原文切片存在缺口、重叠或正文改变")
        cursor = section["end"]
    if cursor != len(original):
        raise ValueError("原文切片未覆盖全文")
    actual_lines = [section["start_line"] for section in sections]
    if actual_lines != expected_lines:
        raise ValueError(f"人工段数或边界不符：实际 {actual_lines}，预期 {expected_lines}")
    actual_dates = [section["date"] for section in sections]
    if actual_dates != expected_dates:
        raise ValueError(f"人工日期期望不符：实际 {actual_dates}，预期 {expected_dates}")
    return {"ok": True, "project_id": fixture["project_id"], "characters": len(original),
            "lines": len(original.splitlines()), "segments": len(sections),
            "dated_segments": sum(value is not None for value in actual_dates),
            "sha256": digest,
            "checks": {"hash": True, "exact_reconstruction": True,
                       "contiguous_slices": True, "manual_boundaries": True,
                       "manual_dates": True}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="带原文摘要和人工边界/日期期望的本地 JSON")
    args = parser.parse_args(argv)
    try:
        result = validate_fixture(json.loads(args.fixture.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
