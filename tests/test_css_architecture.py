import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
CSS_ROOT = PROJECT_ROOT / "frontend" / "assets" / "css"
TEMPLATE_ROOT = PROJECT_ROOT / "frontend" / "templates"

ENTRY_FILES = ("app.css", "dashboard.css", "component-lab.css")
NEW_FOUNDATION_FILES = ("tokens.css", "foundation.css", "components.css", "patterns.css", *ENTRY_FILES)
LEGACY_FILES = ("style.css", "dashboard-shell.css", "dashboard-v103.css")
FORBIDDEN_FONT_NAMES = (
    "anthropicSerif",
    "Inter",
    "JetBrains Mono",
    "MiSans",
    "Newsreader",
    "Source Han Serif",
    "Styrene",
    "Tiempos",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_templates_use_one_css_entry_and_one_font_include():
    dashboard = _read(TEMPLATE_ROOT / "index.html")
    assert "css/dashboard.css" in dashboard
    assert "css/style.css" not in dashboard
    assert "css/dashboard-shell.css" not in dashboard
    assert "css/dashboard-v103.css" not in dashboard

    page_templates = (
        "auth_login.html",
        "auth_register.html",
        "auth_reset_password.html",
        "login_canvas.html",
        "login_haoke.html",
        "login_zhixuemeng.html",
        "login_zhihuishu.html",
    )
    for filename in page_templates:
        source = _read(TEMPLATE_ROOT / filename)
        assert '{% include "_font_assets.html" %}' in source
        assert "css/app.css" in source
        assert "css/style.css" not in source

    font_include = _read(TEMPLATE_ROOT / "_font_assets.html")
    assert "Geist:wght@400;500;600;700" in font_include
    assert "Noto+Serif+SC:wght@400;500;600;700" in font_include

    for template in TEMPLATE_ROOT.rglob("*.html"):
        if template.name == "_font_assets.html":
            continue
        assert "fonts.googleapis.com/css2" not in _read(template)


def test_cascade_layers_isolate_legacy_and_fix_source_order():
    layer_order = "@layer legacy, tokens, foundation, components, patterns, pages, utilities;"
    app_entry = _read(CSS_ROOT / "app.css")
    dashboard_entry = _read(CSS_ROOT / "dashboard.css")
    lab_entry = _read(CSS_ROOT / "component-lab.css")

    for source in (app_entry, dashboard_entry, lab_entry):
        assert source.startswith(layer_order)

    assert '@import url("./style.css") layer(legacy);' in app_entry
    assert '@import url("./style.css") layer(legacy);' in dashboard_entry
    assert '@import url("./dashboard-shell.css") layer(legacy);' in dashboard_entry
    assert '@import url("./dashboard-v103.css") layer(legacy);' in dashboard_entry
    assert '@import url("./tokens.css") layer(tokens);' in dashboard_entry
    assert '@import url("./foundation.css") layer(foundation);' in dashboard_entry
    assert '@import url("./components.css") layer(components);' in dashboard_entry
    assert '@import url("./patterns.css") layer(patterns);' in dashboard_entry


def test_global_tokens_have_one_source_and_no_duplicate_names():
    root_sources = []
    for stylesheet in CSS_ROOT.glob("*.css"):
        if re.search(r"(?m)^\s*:root\s*\{", _read(stylesheet)):
            root_sources.append(stylesheet.name)
    assert root_sources == ["tokens.css"]

    token_source = _read(CSS_ROOT / "tokens.css")
    names = re.findall(r"(?m)^\s*(--[\w-]+)\s*:", token_source)
    duplicates = {name for name in names if names.count(name) > 1}
    assert duplicates == set()

    for filename in LEGACY_FILES:
        source = _read(CSS_ROOT / filename)
        assert "--font-serif:" not in source
        assert "--shell-surface:" not in source


def test_new_foundation_has_no_important_or_unloaded_font_names():
    for filename in NEW_FOUNDATION_FILES:
        source = _read(CSS_ROOT / filename)
        assert "!important" not in source

    css_source = "\n".join(
        line
        for path in CSS_ROOT.glob("*.css")
        for line in _read(path).splitlines()
        if "font-family" in line
    )
    for font_name in FORBIDDEN_FONT_NAMES:
        assert font_name not in css_source


def test_component_lab_records_confirmed_candidate_and_serif_titles():
    template = _read(TEMPLATE_ROOT / "component_lab.html")
    lab_css = _read(CSS_ROOT / "component-lab.css")

    assert 'data-candidate="action-a" data-selected="true"' in template
    assert 'value="a" aria-label="候选 A：静默描边" checked' in template
    assert 'id="confirmed-controls" data-control-api="a"' in template
    assert "ui-button ui-button--primary" in template
    assert "ui-input-shell is-loading" in template
    assert ".lab-section-heading h2" in lab_css
    assert ".lab-specimen-heading h3" in lab_css
    assert "font-family: var(--lab-font-serif);" in lab_css
