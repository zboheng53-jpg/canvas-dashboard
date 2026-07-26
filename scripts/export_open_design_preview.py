"""Export the real dashboard template as a static Open Design preview.

The export is deliberately derived from Flask's renderer: Jinja includes and
template values are resolved here, while the production template remains the
only source of truth.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import app  # noqa: E402  (the project root is added immediately above)


DEFAULT_OUTPUT = PROJECT_ROOT / "frontend" / "open-design-preview" / "index.html"
_STATIC_ASSET_URL = re.compile(r'(?P<prefix>\b(?:href|src)=["\'])/static/')
_CSRF_SCRIPT = re.compile(r'<script>window\.CSRF_TOKEN = ".*?";</script>')


def export_preview(output: Path = DEFAULT_OUTPUT, username: str = "设计预览") -> Path:
    """Render the dashboard with a disposable demo session and write static HTML."""
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["username"] = username
        response = client.get("/")

    if response.status_code != 200:
        raise RuntimeError(f"Dashboard render failed with HTTP {response.status_code}.")

    html = response.get_data(as_text=True)
    html = _CSRF_SCRIPT.sub(
        '<script>window.__OPEN_DESIGN_PREVIEW__ = true; window.CSRF_TOKEN = "open-design-demo";</script>\n  <script src="../assets/js/open-design-mock.js"></script>',
        html,
        count=1,
    )
    html = _STATIC_ASSET_URL.sub(r"\g<prefix>../assets/", html)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a static dashboard page for Open Design.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output HTML file path.")
    parser.add_argument("--username", default="设计预览", help="Demo username shown in the preview.")
    args = parser.parse_args()

    output = export_preview(args.output.resolve(), args.username)
    print(f"Open Design preview exported to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
