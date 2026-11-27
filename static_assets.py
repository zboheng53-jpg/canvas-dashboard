"""Build content-addressed assets without changing authoring files or script order."""
import hashlib
import json
from pathlib import Path
import re

IMPORT = re.compile(r'@import url\("\./([^"/]+)"\) layer\(([\w-]+)\);')


def build_assets(asset_root: Path) -> dict[str, str]:
    asset_root = Path(asset_root)
    output = asset_root / 'built'
    manifest = {}
    for directory in ('css', 'js'):
        for source in sorted((asset_root / directory).rglob('*')):
            if not source.is_file() or source.suffix not in ('.css', '.js'):
                continue
            relative = source.relative_to(asset_root)
            content = source.read_text(encoding='utf-8')
            if source.suffix == '.css':
                content = IMPORT.sub(lambda match: '@layer ' + match[2] + ' {\n' + (source.parent / match[1]).read_text(encoding='utf-8') + '\n}', content)
                # Keep quoted strings and CSS token boundaries intact. HTTP
                # compression is handled by Nginx, not a regex minifier.
                content = '\n'.join(line.rstrip() for line in content.splitlines() if line.strip()) + '\n'
            data = content.encode('utf-8')
            digest = hashlib.sha256(data).hexdigest()[:20]
            built = Path('built') / relative.parent / f'{source.stem}.{digest}{source.suffix}'
            target = asset_root / built
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest[relative.as_posix()] = built.as_posix()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    _prune_unreferenced(asset_root, set(manifest.values()), manifest_path)
    return manifest


def _prune_unreferenced(asset_root: Path, referenced: set[str], manifest_path: Path) -> None:
    """Delete hashed files that no current source maps to; they accumulate on every build."""
    for path in sorted(manifest_path.parent.rglob('*')):
        if not path.is_file() or path == manifest_path:
            continue
        relative = path.relative_to(asset_root).as_posix()
        if relative not in referenced:
            path.unlink()


def load_manifest(asset_root: Path) -> dict[str, str]:
    path = Path(asset_root) / 'built' / 'manifest.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    return {source: target for source, target in data.items()
            if target.startswith('built/') and '..' not in Path(target).parts and (Path(asset_root) / target).is_file()}
