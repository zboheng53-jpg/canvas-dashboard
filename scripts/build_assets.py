"""Run before preview/release; generated outputs are reproducible and ignored."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from static_assets import build_assets

if __name__ == '__main__':
    manifest = build_assets(ROOT / 'frontend' / 'assets')
    print(f'Built {len(manifest)} fingerprinted CSS/JS assets')
