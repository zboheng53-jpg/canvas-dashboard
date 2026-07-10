from pathlib import Path

import settings


def test_index_template_has_valid_visible_chinese_and_no_leaked_tags():
    text = (Path(__file__).parents[1] / "templates" / "index.html").read_text(encoding="utf-8")

    assert "&#24453;&#21150;&#28165;&#21333;" in text
    assert "&#31995;&#32479;&#30331;&#24405;" in text
    assert "&#36864;&#20986;&#30331;&#24405;</a>" in text
    assert "&#26234;&#24935;&#26641;</span>" in text
    assert "${data.week}" in text
    assert "\\u00b0C" in text

    bad_fragments = [
        "?/span>",
        "?/a>",
        "\u7ed7?{data.week}",
        "\u9a9e?",
        "\u9354\u72ba\u6d47",
        "\u5bf0\u546d",
        "\u95ab\u20ac",
        "\u63b3",
        "\u8133",
        "\u9983",
    ]
    for fragment in bad_fragments:
        assert fragment not in text


def test_default_term_label_is_readable_chinese():
    assert settings.TERM_LABEL == "2025-2026\u5b66\u5e74 \u7b2c\u4e8c\u5b66\u671f"
