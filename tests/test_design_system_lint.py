"""Static analysis and lint suite for design system compliance.

Prevents hardcoded colors, !important leaks, and ID selectors in core design system layers.
"""
import re
from pathlib import Path
import pytest

CSS_DIR = Path("frontend/assets/css")
MODERN_CSS_FILES = [
    CSS_DIR / "tokens.css",
    CSS_DIR / "foundation.css",
    CSS_DIR / "components.css",
    CSS_DIR / "patterns.css",
    CSS_DIR / "business.css",
]


def test_no_important_in_modern_css_layers():
    """Ensure modern design system layers contain ZERO !important declarations."""
    for css_file in MODERN_CSS_FILES:
        assert css_file.exists(), f"Missing CSS file: {css_file}"
        content = css_file.read_text(encoding="utf-8")
        matches = re.findall(r'[^;{\}\n]+!important', content)
        assert len(matches) == 0, f"Found !important in {css_file.name}: {matches}"


def test_no_hardcoded_colors_in_components_and_business_css():
    """Ensure components.css and business.css use ONLY CSS variables for colors, no raw hex/rgb."""
    color_pattern = re.compile(r'(#(?:[0-9a-fA-F]{3,8})\b|rgba?\([^\)]+\)|hsla?\([^\)]+\))')
    
    for css_file in [CSS_DIR / "components.css", CSS_DIR / "business.css"]:
        content = css_file.read_text(encoding="utf-8")
        clean = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        matches = []
        for line_no, line in enumerate(clean.splitlines(), 1):
            if 'data:image' in line or 'url(' in line:
                continue
            # Remove var(...) calls before matching
            line_no_vars = re.sub(r'var\([^)]+\)', '', line)
            found = color_pattern.findall(line_no_vars)
            if found:
                matches.append((line_no, line.strip(), found))
                
        assert len(matches) == 0, f"Found hardcoded colors in {css_file.name}:\n" + "\n".join(f"  L{l}: {txt}" for l, txt, _ in matches[:10])


def test_no_id_selectors_in_base_components_and_business_css():
    """Ensure components.css and business.css contain ZERO ID selectors for styling."""
    id_selector_pattern = re.compile(r'^\s*#[a-zA-Z0-9_-]+\b\s*\{', re.MULTILINE)
    
    for css_file in [CSS_DIR / "components.css", CSS_DIR / "business.css"]:
        content = css_file.read_text(encoding="utf-8")
        clean = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        matches = id_selector_pattern.findall(clean)
        assert len(matches) == 0, f"Found ID selector in {css_file.name}: {matches}"


def test_css_layer_declaration_integrity():
    """Ensure dashboard.css and app.css declare proper @layer ordering."""
    dashboard_css = CSS_DIR / "dashboard.css"
    app_css = CSS_DIR / "app.css"
    
    expected_layer = "@layer legacy, tokens, foundation, components, patterns, pages, utilities;"
    
    for css_file in [dashboard_css, app_css]:
        content = css_file.read_text(encoding="utf-8")
        assert expected_layer in content, f"Missing or corrupted @layer statement in {css_file.name}"


def test_token_scale_consistency():
    """Ensure tokens.css defines complete scale tokens for colors, spacing, radius, and fonts."""
    tokens_css = CSS_DIR / "tokens.css"
    content = tokens_css.read_text(encoding="utf-8")
    
    required_tokens = [
        "--font-body",
        "--font-title",
        "--font-number",
        "--color-action",
        "--color-surface",
        "--color-text-primary",
        "--radius-control",
        "--radius-card",
        "--space-1",
        "--space-2",
        "--space-3",
        "--space-4",
    ]
    
    for token in required_tokens:
        assert token in content, f"Missing required design system token {token} in tokens.css"
