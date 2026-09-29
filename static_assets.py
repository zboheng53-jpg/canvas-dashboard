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
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    return manifest


def load_manifest(asset_root: Path) -> dict[str, str]:
    path = Path(asset_root) / 'built' / 'manifest.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    return {source: target for source, target in data.items()
            if target.startswith('built/') and '..' not in Path(target).parts and (Path(asset_root) / target).is_file()}
