from datetime import datetime, timezone, timedelta

import canvas_auth
import external_subtasks
from platform_state import PlatformStateStore, build_platform_todos_response
from storage import read_json_file, write_json_file
from user_paths import user_dir


def test_platform_get_keeps_latest_user_state_and_never_auto_deletes(tmp_path):
    store = PlatformStateStore(lambda name: tmp_path / name / "state.json")
    store.update("alice", "hide", "old")
    snapshot = store.load("alice")
    store.update_override("alice", "old", {"due_ts": "2099-12-31"})
    store.update("alice", "complete", "another")
    before = store.load("alice")
    calls = []
    result = build_platform_todos_response(
        {"ok": True, "data": [{"id": "old", "due_ts": "2000-01-01"}]}, snapshot,
        now=datetime.now(timezone(timedelta(hours=8))), expire_hidden=calls.append,
    )
    assert result["hidden"] == ["old"]
    assert result["deleted"] == []
    assert not calls
    assert store.load("alice") == before


def test_canvas_offline_migration_is_stable_and_old_client_writes_follow_alias():
    name = "canvas_alias_regression"
    directory = user_dir(name)
    write_json_file(directory / "canvas_cache.json", [{"id": 42, "url": "https://canvas.example/courses/1/assignments/42#assignment_42", "title": "work"}])
    write_json_file(directory / "canvas_state.json", {"completed": [42], "overrides": {"42": {"title": "local"}}})
    external_subtasks.save_subtasks(name, "canvas", 42, [{"id": 1, "text": "step"}])
    write_json_file(directory / "schedule_items.json", {"one_off": [{"id": 1, "action_ref": "canvas:42"}], "recurring": []})
    first = canvas_auth._fallback_cache(name)
    canonical = "canvas:assignment:42"
    assert first["data"][0]["id"] == canonical
    timestamp = (directory / "canvas_cache.json").stat().st_mtime_ns
    second = canvas_auth._fallback_cache(name)
    assert second == first
    assert (directory / "canvas_cache.json").stat().st_mtime_ns == timestamp
    assert canonical in canvas_auth.load_state(name)["completed"]
    assert external_subtasks.load_subtasks(name, "canvas", 42)[0]["text"] == "step"
    assert read_json_file(directory / "schedule_items.json", {})["one_off"][0]["action_ref"] == f"canvas:{canonical}"
    canvas_auth.update_state(name, "uncomplete", 42)
    assert canonical not in canvas_auth.load_state(name)["completed"]
    external_subtasks.save_subtasks(name, "canvas", 42, [{"text": "updated"}])
    assert external_subtasks.load_subtasks(name, "canvas", canonical)[0]["text"] == "updated"


def test_canvas_colliding_legacy_ids_stay_distinct_and_do_not_guess_state_owner():
    name = "canvas_collision_regression"
    directory = user_dir(name)
    write_json_file(directory / "canvas_cache.json", [
        {"id": 42, "url": "https://canvas.example/#assignment_42"},
        {"id": 42, "url": "https://canvas.example/#calendar_event_42"},
    ])
    write_json_file(directory / "canvas_state.json", {"completed": [42], "overrides": {"42": {"title": "old"}}})
    external_subtasks.save_subtasks(name, "canvas", 42, [{"text": "preserve"}])
    result = canvas_auth._fallback_cache(name)
    assert {item["id"] for item in result["data"]} == {"canvas:assignment:42", "canvas:calendar_event:42"}
    assert result["migration_ambiguous_ids"] == ["42"]
    assert canvas_auth.load_state(name)["completed"] == ["42"]
    assert external_subtasks.load_subtasks(name, "canvas", 42)[0]["text"] == "preserve"


def test_canvas_uidless_legacy_cache_does_not_hash_its_own_id_on_every_read():
    name = "canvas_uidless_regression"
    directory = user_dir(name)
    write_json_file(directory / "canvas_cache.json", [{"id": 91, "title": "legacy event"}])
    first = canvas_auth._fallback_cache(name)
    assert first["data"][0]["id"] == "canvas:legacy:91"
    assert canvas_auth._fallback_cache(name) == first
