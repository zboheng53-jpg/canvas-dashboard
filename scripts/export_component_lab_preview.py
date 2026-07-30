"""Export the component laboratory as a standalone static preview."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import app  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "frontend" / "open-design-preview" / "component-lab.html"
_STATIC_ASSET_URL = re.compile(r'(?P<prefix>\b(?:href|src)=["\'])/static/')


def export_component_lab_preview(output: Path = DEFAULT_OUTPUT) -> Path:
    """Render the authenticated lab route and rewrite static assets relatively."""
    previous_testing = app.config["TESTING"]
    app.config.update(TESTING=True)
    try:
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["username"] = "组件实验室"
            response = client.get("/component-lab")
    finally:
        app.config.update(TESTING=previous_testing)

    if response.status_code != 200:
        raise RuntimeError(f"Component lab render failed with HTTP {response.status_code}.")

    html = _STATIC_ASSET_URL.sub(r"\g<prefix>../assets/", response.get_data(as_text=True))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the Canvas Dashboard component lab.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output HTML file path.")
    args = parser.parse_args()
    output = export_component_lab_preview(args.output.resolve())
    print(f"Component lab preview exported to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
