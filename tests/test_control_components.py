import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
TEMPLATE_ROOT = PROJECT_ROOT / "frontend" / "templates"
JS_ROOT = PROJECT_ROOT / "frontend" / "assets" / "js"
CSS_ROOT = PROJECT_ROOT / "frontend" / "assets" / "css"

BUTTON_EXCEPTIONS = {
    "biz-project-item__next",
    "btn-delete",
    "btn-dismiss",
    "btn-flag",
    "btn-quiet",
    "connection-platform-item",
    "f-chip",
    "icon-btn",
    "login-card",
    "proj-name",
    "project-todo-link",
    "project-browser-item",
    "project-choice-row",
    "project-list-item",
    "side-logout",
    "side-user",
    "sidebar-footer-action",
    "sidebar-collapse-toggle",
    "sidebar-nav-item",
    "sidebar-scrim",
    "sidebar-user",
    "subtask-toggle",
    "sync-status-button",
    "todo-action-button",
    "up-collapse",
}
MIGRATED_VISUAL_CLASSES = set(
    """
    action-button btn-accent btn-auth-secondary btn-cancel
    btn-primary btn-refresh btn-schedule-action btn-schedule-primary
    btn-schedule-secondary btn-secondary btn-sm btn-submit calendar-panel-primary
    calendar-panel-revoke connection-clear-button connection-danger-quiet
    connection-primary-action connection-text-button console-secondary-button
    console-stateful-button last-updated mobile-action-trigger mobile-menu-toggle
    project-button-danger project-button-primary project-button-secondary
    project-due-editable project-empty-create project-group-add-task-btn
    project-modal-close project-next-action-btn-choose
    project-next-action-btn-complete project-overview-add project-overview-all
    project-tab-btn project-task-action-btn project-task-name-btn project-todo-link
    schedule-import-button schedule-modal-close schedule-nav-btn
    schedule-refresh-button schedule-return-default settings-danger-button
    subtask-add-btn subtask-delete
    sync-status-button todo-source-filter date-input logged-in-select
    subtask-add-due-input subtask-add-input subtask-due-input todo-source-select
    connection-field-label settings-field-label setup-hint connection-setup-hint
    connection-data-note form-note schedule-login-note error-banner
    connection-error project-modal-error
    stat-pill stat-count empty-state item-source-badge label-badge subtask-empty
    login-card-status login-session-message sidebar-attention-dot
    rail-empty-state project-main-badge project-next-badge
    project-manager-status project-list-empty project-detail-empty
    project-status-badge project-created-notice project-all-done
    project-task-empty project-overview-empty-line schedule-manager-status
    console-manager-status connections-manager-status status-badge connection-state-connected
    calendar-privacy-badge calendar-subscription-status
    account-delete-warning project-tag-pill
    """.split()
)
VISUAL_DECLARATION = re.compile(
    r"""(?im)(?:^|;)\s*(?:
        appearance|accent-color|color|background(?:-[\w-]+)?|
        border(?:-[\w-]+)?|box-shadow|font(?:-[\w-]+)?|line-height|
        letter-spacing|text-align|text-decoration(?:-[\w-]+)?|cursor|
        transition(?:-[\w-]+)?|outline(?:-[\w-]+)?|opacity|filter|
        height|min-height|max-height|padding(?:-[\w-]+)?
    )\s*:""",
    re.VERBOSE,
)


def _production_sources() -> list[tuple[Path, str]]:
    paths = [
        path
        for path in TEMPLATE_ROOT.rglob("*.html")
        if path.name != "component_lab.html"
    ]
    paths.extend(JS_ROOT.glob("*.js"))
    return [(path, path.read_text(encoding="utf-8")) for path in paths]


def _class_value(tag: str) -> str:
    match = re.search(r"""class=["']([^"']*)["']""", tag)
    return match.group(1) if match else ""


def test_production_buttons_use_component_api_or_documented_pattern():
    uncovered = []
    conflicting = []
    visual_variants = {
        "ui-button--primary",
        "ui-button--secondary",
        "ui-button--outline",
        "ui-button--danger",
        "ui-button--text",
        "ui-button--choice",
    }

    for path, source in _production_sources():
        for tag in re.findall(r"<button\b[^>]*>", source, flags=re.IGNORECASE):
            classes = set(_class_value(tag).split())
            is_documented_pattern = any(
                class_name.startswith(exception)
                for class_name in classes
                for exception in BUTTON_EXCEPTIONS
            )
            if not ({"ui-button", "ui-icon-button"} & classes) and not is_documented_pattern:
                uncovered.append((path.name, tag))
            if len(visual_variants & classes) > 1:
                conflicting.append((path.name, tag))

    assert uncovered == []
    assert conflicting == []


def test_production_form_controls_use_component_api():
    uncovered = []
    for path, source in _production_sources():
        for tag in re.findall(
            r"<(?:input|select|textarea)\b[^>]*>", source, flags=re.IGNORECASE
        ):
            classes = set(_class_value(tag).split())
            type_match = re.search(r"""type=["']([^"']+)["']""", tag)
            input_type = type_match.group(1).lower() if type_match else ""
            if input_type in {"hidden", "radio", "file"}:
                continue
            if input_type == "checkbox":
                covered = "ui-checkbox" in classes
            else:
                covered = "ui-control" in classes
            if not covered:
                uncovered.append((path.name, tag))

    assert uncovered == []


def test_control_visuals_have_one_new_source_and_no_important():
    components = (CSS_ROOT / "components.css").read_text(encoding="utf-8")
    patterns = (CSS_ROOT / "patterns.css").read_text(encoding="utf-8")

    assert "!important" not in components
    assert "!important" not in patterns
    assert re.search(r"\.ui-button\s*\{", components)
    assert re.search(r"\.ui-control\s*\{", components)
    assert re.search(r"\.ui-checkbox\s*\{", components)
    assert not re.search(
        r"\b(?:color|background|border|border-radius|box-shadow|font(?:-family|-size)?)\s*:",
        patterns,
    )


def test_migrated_business_classes_and_ids_have_no_legacy_visual_declarations():
    migrated_ids = set()
    for _path, source in _production_sources():
        for tag in re.findall(
            r"<(?:button|input|select|textarea)\b[^>]*>", source, flags=re.IGNORECASE
        ):
            classes = set(_class_value(tag).split())
            if not any(name.startswith("ui-") for name in classes):
                continue
            id_match = re.search(r"""(?<![-\w])id=["']([^"'${}]+)["']""", tag)
            if id_match:
                migrated_ids.add(id_match.group(1))

    legacy_sources = [
        CSS_ROOT / "style.css",
        CSS_ROOT / "dashboard-shell.css",
        CSS_ROOT / "dashboard-v103.css",
        TEMPLATE_ROOT / "dashboard" / "_placeholder_views.html",
    ]
    violations = []
    for path in legacy_sources:
        source = path.read_text(encoding="utf-8")
        for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", source, flags=re.DOTALL):
            selector, declarations = rule.groups()
            uses_migrated_class = any(
                re.search(rf"(?<![\w-])\.{re.escape(name)}(?![\w-])", selector)
                for name in MIGRATED_VISUAL_CLASSES
            )
            uses_migrated_id = any(
                re.search(rf"(?<![\w-])#{re.escape(name)}(?![\w-])", selector)
                for name in migrated_ids
            )
            if (uses_migrated_class or uses_migrated_id) and VISUAL_DECLARATION.search(
                declarations
            ):
                violations.append((path.name, " ".join(selector.split())))

    assert violations == []


def test_touch_targets_and_confirmed_a_tokens_are_locked():
    components = (CSS_ROOT / "components.css").read_text(encoding="utf-8")
    tokens = (CSS_ROOT / "tokens.css").read_text(encoding="utf-8")

    assert "--control-height-md: 36px;" in tokens
    assert "--control-height-lg: 44px;" in tokens
    assert "--radius-control: 6px;" in tokens
    assert "--button-primary-bg: #fbfdff;" in tokens
    assert "--button-primary-border: #c9dbfa;" in tokens
    assert "--control-focus-shadow: 0 0 0 3px" in tokens
    assert "@media (max-width: 768px), (pointer: coarse)" in components
    assert "min-height: var(--control-height-lg);" in components


def test_information_components_have_one_semantic_api():
    components = (CSS_ROOT / "components.css").read_text(encoding="utf-8")
    tokens = (CSS_ROOT / "tokens.css").read_text(encoding="utf-8")
    legacy = "\n".join(
        (CSS_ROOT / name).read_text(encoding="utf-8")
        for name in ("style.css", "dashboard-shell.css", "dashboard-v103.css")
    )

    required_selectors = [
        ".ui-badge",
        ".ui-badge--source",
        ".ui-tag",
        ".ui-count-pill",
        ".ui-status",
        ".ui-status-dot",
        ".ui-feedback",
        ".ui-alert",
        ".ui-loading",
        ".ui-skeleton",
        ".ui-empty",
        ".ui-disabled",
    ]
    for selector in required_selectors:
        assert selector in components

    for source in ("canvas", "haoke", "zhixuemeng", "zhihuishu", "project", "custom"):
        assert f"--color-source-{source}:" in tokens
        assert f".ui-source--{source}" in components

    assert '[class*="status-"]' not in legacy
    assert '[class*="tag-"]' not in legacy
    assert "!important" not in components


def test_sidebar_icons_and_todo_row_actions_keep_their_compact_patterns():
    shell = (CSS_ROOT / "dashboard-shell.css").read_text(encoding="utf-8")
    style = (CSS_ROOT / "style.css").read_text(encoding="utf-8")
    sidebar = (TEMPLATE_ROOT / "dashboard" / "_academic_sidebar.html").read_text(
        encoding="utf-8"
    )
    dashboard = (TEMPLATE_ROOT / "index.html").read_text(encoding="utf-8")

    assert re.search(
        r"\.sidebar-nav-item svg,[^{]+?\{[^}]*height:\s*20px;[^}]*fill:\s*none;"
        r"[^}]*stroke:\s*currentColor;",
        shell,
        flags=re.DOTALL,
    )
    assert 'class="ui-icon-button sidebar-collapse-toggle"' not in sidebar
    assert not re.search(
        r'class="[^"]*\bui-icon-button\b[^"]*\b(?:btn-flag|btn-dismiss|btn-delete|subtask-toggle)\b',
        dashboard,
    )
    action_rule = re.search(
        r"\.btn-flag,\s*\.btn-dismiss,\s*\.btn-delete\s*\{([^}]*)\}",
        style,
        flags=re.DOTALL,
    )
    assert action_rule
    assert re.search(r"font-size:\s*17px;", action_rule.group(1))
    assert re.search(r"padding:\s*5px 7px;", action_rule.group(1))


def test_platform_source_dots_use_distinct_confirmed_colors():
    tokens = (CSS_ROOT / "tokens.css").read_text(encoding="utf-8")
    expected = {
        "canvas": "#c45b55",
        "haoke": "#2f8a64",
        "zhixuemeng": "#4078c8",
        "zhihuishu": "#c48a2c",
        "project": "#8068c5",
        "custom": "#697586",
    }
    for source, color in expected.items():
        assert f"--color-source-{source}: {color};" in tokens
