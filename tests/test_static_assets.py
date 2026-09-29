import hashlib
from pathlib import Path

from static_assets import build_assets, load_manifest


def test_bundle_retains_layer_order_and_changes_when_import_changes(tmp_path):
    css = tmp_path / 'css'
    css.mkdir()
    (tmp_path / 'js').mkdir()
    (css / 'entry.css').write_text('@layer base, page;\n@import url("./base.css") layer(base);\n@import url("./page.css") layer(page);', encoding='utf-8')
    (css / 'base.css').write_text(':root { --tone: blue; }', encoding='utf-8')
    (css / 'page.css').write_text('body { color: var(--tone); }', encoding='utf-8')
    first = build_assets(tmp_path)
    bundled = (tmp_path / first['css/entry.css']).read_text(encoding='utf-8')
    assert '@import' not in bundled
    assert bundled.index('@layer base, page;') < bundled.index('@layer base {') < bundled.index('@layer page {')
    (css / 'base.css').write_text(':root { --tone: green; }', encoding='utf-8')
    second = build_assets(tmp_path)
    assert first['css/entry.css'] != second['css/entry.css']
    assert load_manifest(tmp_path) == second
    assert build_assets(tmp_path) == second


def test_current_css_bundle_contains_all_sources_without_import_waterfall(tmp_path):
    import shutil
    source = Path(__file__).parents[1] / 'frontend/assets'
    shutil.copytree(source / 'css', tmp_path / 'css')
    shutil.copytree(source / 'js', tmp_path / 'js')
    manifest = build_assets(tmp_path)
    bundle = (tmp_path / manifest['css/dashboard.css']).read_text(encoding='utf-8')
    assert '@import' not in bundle
    for name in ('tokens.css', 'business.css', 'guide.css', 'appearance.css'):
        original = (source / 'css' / name).read_text(encoding='utf-8')
        assert all(line.rstrip() in bundle for line in original.splitlines() if line.strip())
    for logical, physical in manifest.items():
        assert hashlib.sha256((tmp_path / physical).read_bytes()).hexdigest()[:20] in physical
