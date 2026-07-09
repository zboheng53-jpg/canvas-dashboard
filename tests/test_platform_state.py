from datetime import datetime, timedelta, timezone

from platform_state import (
    PlatformStateStore,
    build_platform_todos_response,
    normalize_state,
)


CST = timezone(timedelta(hours=8))


def test_state_store_preserves_int_ids(tmp_path):
    store = PlatformStateStore(lambda username: tmp_path / username / "canvas_state.json", int)

    state = store.update("alice", "hide", "42")
    assert state["hidden"] == [42]

    state = store.update("alice", "highlight", 42)
    assert state["highlighted"] == [42]

    state = store.update("alice", "delete", "42")
    assert state["hidden"] == []
    assert state["highlighted"] == []
    assert state["deleted"] == [42]


def test_state_store_preserves_string_ids(tmp_path):
    store = PlatformStateStore(lambda username: tmp_path / username / "zhihuishu_state.json", str)

    state = store.update("alice", "hide", 42)
    assert state["hidden"] == ["42"]

    state = store.update("alice", "delete", 42)
    assert state["hidden"] == []
    assert state["deleted"] == ["42"]


def test_normalize_state_adds_missing_keys_and_casts_ids():
    state = normalize_state({"hidden": ["1"], "highlighted": [2]}, int)

    assert state == {"hidden": [1], "highlighted": [2], "deleted": []}


def test_build_platform_todos_response_filters_deleted_and_adds_state():
    state = {"hidden": [1], "highlighted": [2], "deleted": [3]}
    result = {
        "ok": True,
        "data": [
            {"id": 1, "title": "hidden"},
            {"id": 2, "title": "highlighted"},
            {"id": 3, "title": "deleted"},
        ],
        "cached": False,
    }

    response = build_platform_todos_response(result, state)

    assert [item["id"] for item in response["data"]] == [1, 2]
    assert response["hidden"] == [1]
    assert response["highlighted"] == [2]
    assert response["deleted"] == [3]
    assert response["cached"] is False


def test_build_platform_todos_response_supports_items_key():
    state = {"hidden": ["zxm_1"], "highlighted": [], "deleted": []}
    result = {"ok": True, "items": [{"id": "zxm_1"}, {"id": "zxm_2"}], "cached": True}

    response = build_platform_todos_response(result, state, items_key="items")

    assert response["items"] == result["items"]
    assert response["data"] == result["items"]
    assert response["cached"] is True


def test_build_platform_todos_response_auto_deletes_expired_hidden_item():
    now = datetime(2026, 7, 9, 12, 0, tzinfo=CST)
    state = {"hidden": [1], "highlighted": [], "deleted": []}
    saved = []
    result = {
        "ok": True,
        "data": [
            {"id": 1, "due_ts": (now - timedelta(hours=1)).isoformat()},
            {"id": 2, "due_ts": (now + timedelta(hours=1)).isoformat()},
        ],
    }

    response = build_platform_todos_response(
        result,
        state,
        save_state=lambda changed_state: saved.append(changed_state.copy()),
        now=now,
    )

    assert response["data"] == [{"id": 2, "due_ts": (now + timedelta(hours=1)).isoformat()}]
    assert response["hidden"] == []
    assert response["deleted"] == [1]
    assert saved == [{"hidden": [], "highlighted": [], "deleted": [1]}]
