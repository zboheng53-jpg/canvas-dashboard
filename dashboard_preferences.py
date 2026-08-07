"""Per-user display preferences for the dashboard overview."""

from storage import locked_json_update, read_json_file
from user_paths import user_dir


TODO_SOURCES = (
    "canvas",
    "haoke",
    "zhixuemeng",
    "zhihuishu",
    "project",
    "custom",
)
_DEFAULTS = {
    "version": 1,
    "visible_todo_sources": list(TODO_SOURCES),
}


def _path(username: str):
    return user_dir(username) / "dashboard_preferences.json"


def _normalized(data) -> dict:
    if not isinstance(data, dict):
        return dict(_DEFAULTS, visible_todo_sources=list(TODO_SOURCES))
    visible = data.get("visible_todo_sources")
    if not isinstance(visible, list):
        visible = list(TODO_SOURCES)
    else:
        visible_set = {source for source in visible if source in TODO_SOURCES}
        visible = [source for source in TODO_SOURCES if source in visible_set]
    return {
        **data,
        "version": 1,
        "visible_todo_sources": visible,
    }


def load(username: str) -> dict:
    return _normalized(read_json_file(_path(username), _DEFAULTS))


def save_visible_todo_sources(username: str, visible_sources: list[str]) -> dict:
    visible_set = set(visible_sources)

    def update(current):
        preferences = _normalized(current)
        preferences["visible_todo_sources"] = [
            source for source in TODO_SOURCES if source in visible_set
        ]
        return preferences

    return _normalized(locked_json_update(_path(username), _DEFAULTS, update))
