"""Read the source actually composed by a dashboard template."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'frontend/templates'


def template_source(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    return re.sub(r'{%\s*include\s+"([^"]+)"\s*%}',
                  lambda m: template_source(TEMPLATES / m[1]), text)


def dashboard_source():
    text = template_source(TEMPLATES / 'index.html')
    scripts = re.findall(r"filename='(js/[^']+)'", text)
    return text + '\n' + '\n'.join((ROOT / 'frontend/assets' / p).read_text(encoding='utf-8') for p in scripts)
