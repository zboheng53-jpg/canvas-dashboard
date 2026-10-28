"""Read legacy project materials as lossless, dated sections without migrating them."""
import re
from datetime import date


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_BRACKET_HEADING = re.compile(r"^ {0,3}【(.*)】[ \t]*$")
_MARKDOWN_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(.*)|[ \t]*)$")
_HEADING_DATE = re.compile(
    r"(?<![0-9])(?P<iso>[0-9]{4}-[0-9]{2}-[0-9]{2})(?![0-9])"
    r"|(?<![0-9])(?P<year>[0-9]{4})[ \t]*年[ \t]*"
    r"(?P<month>[0-9]{1,2})[ \t]*月[ \t]*(?P<day>[0-9]{1,2})[ \t]*日"
)


def _heading_date(title):
    for match in _HEADING_DATE.finditer(title):
        try:
            if match.group("iso"):
                return date.fromisoformat(match.group("iso")).isoformat()
            return date(int(match.group("year")), int(match.group("month")),
                        int(match.group("day"))).isoformat()
        except ValueError:
            continue
    return None


def parse_legacy_materials(text):
    """Return contiguous original slices; dates come only from explicit headings.

    ATX Markdown headings and standalone 【headings】 start sections. Fenced code
    and lines indented by four spaces or a tab do not. The first valid full date
    in a heading is used; missing years and invalid dates remain undated.
    """
    if not isinstance(text, str):
        raise TypeError("materials must be a string")
    if not text:
        return []

    headings = []
    offset = 0
    fence_character = None
    fence_length = 0
    for line_number, line in enumerate(text.splitlines(keepends=True), 1):
        content = line.rstrip("\r\n")
        fence = _FENCE.match(content)
        if fence_character is not None:
            if (fence and fence.group(1)[0] == fence_character
                    and len(fence.group(1)) >= fence_length
                    and not fence.group(2).strip()):
                fence_character = None
            offset += len(line)
            continue
        if fence and (fence.group(1)[0] == "~" or "`" not in fence.group(2)):
            fence_character = fence.group(1)[0]
            fence_length = len(fence.group(1))
            offset += len(line)
            continue

        bracket = _BRACKET_HEADING.match(content)
        markdown = _MARKDOWN_HEADING.match(content)
        if bracket:
            title = bracket.group(1).strip()
        elif markdown:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", markdown.group(1) or "").strip()
        else:
            offset += len(line)
            continue
        headings.append((offset, line_number, title or "无标题资料", _heading_date(title)))
        offset += len(line)

    if not headings or headings[0][0] != 0:
        headings.insert(0, (0, 1, "历史资料", None))
    sections = []
    for index, (start, start_line, title, section_date) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        raw = text[start:end]
        sections.append({"id": f"legacy-{start}", "date": section_date,
                         "title": title, "body": raw, "raw": raw,
                         "start": start, "end": end, "start_line": start_line})
    return sections
