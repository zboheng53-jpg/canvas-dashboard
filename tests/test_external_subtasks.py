import copy
import json

import pytest

import external_subtasks


@pytest.fixture
def external_store(tmp_path, monkeypatch):
    def resolve_user_dir(username):
        path = tmp_path / "users" / username
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(external_subtasks, "user_dir", resolve_user_dir)
    return resolve_user_dir


def test_subtasks_are_isolated_by_source_and_item_id(external_store):
    canvas_subtasks = [{"id": "canvas-step", "text": "Canvas step", "done": False}]
    haoke_subtasks = [{"id": "haoke-step", "text": "Haoke step", "done": True}]

    assert external_subtasks.save_subtasks("alice", "canvas", 42, canvas_subtasks) == canvas_subtasks
    assert external_subtasks.save_subtasks("alice", "haoke", "42", haoke_subtasks) == haoke_subtasks

    assert external_subtasks.load_subtasks("alice", "canvas", "42") == canvas_subtasks
    assert external_subtasks.load_subtasks("alice", "haoke", 42) == haoke_subtasks
    assert external_subtasks.load_subtasks("alice", "zhixuemeng", 42) == []

    stored = json.loads((external_store("alice") / "external_subtasks.json").read_text(encoding="utf-8"))
    assert set(stored) == {"canvas:42", "haoke:42"}
    assert stored["canvas:42"]["subtasks"] == canvas_subtasks
    assert stored["canvas:42"]["updated_at"].endswith("+00:00")


def test_subtasks_are_isolated_by_user_for_the_same_source_and_item_id(external_store):
    alice_subtasks = [{"id": "alice-step", "text": "Alice", "done": False}]
    bob_subtasks = [{"id": "bob-step", "text": "Bob", "done": True}]

    external_subtasks.save_subtasks("alice", "canvas", "assignment-1", alice_subtasks)
    external_subtasks.save_subtasks("bob", "canvas", "assignment-1", bob_subtasks)

    assert external_subtasks.load_subtasks("alice", "canvas", "assignment-1") == alice_subtasks
    assert external_subtasks.load_subtasks("bob", "canvas", "assignment-1") == bob_subtasks


def test_attach_subtasks_merges_saved_and_default_subtasks_without_mutating_input(external_store):
    subtasks = [{"id": "1", "text": "Read", "done": False}]
    external_subtasks.save_subtasks("alice", "zhixuemeng", "work-1", subtasks)
    result = {
        "ok": True,
        "data": [
            {"id": "work-1", "title": "Saved"},
            {"id": "work-2", "title": "Unrecorded"},
        ],
    }
    original = copy.deepcopy(result)

    attached = external_subtasks.attach_subtasks("alice", "zhixuemeng", result)

    assert attached["data"][0]["subtasks"] == subtasks
    assert attached["data"][1]["subtasks"] == []
    assert result == original
    assert attached is not result
    assert attached["data"] is not result["data"]
    assert attached["data"][0] is not result["data"][0]


@pytest.mark.parametrize(
    ("operation", "args"),
    [
        ("save", ("alice", "invalid", "item-1", [])),
        ("load", ("alice", "invalid", "item-1")),
        ("attach", ("alice", "invalid", {"data": []})),
        ("save", ("alice", "canvas", None, [])),
        ("save", ("alice", "canvas", "   ", [])),
        ("load", ("alice", "canvas", "")),
        ("save", ("alice", "canvas", "item-1", {"not": "a list"})),
    ],
)
def test_invalid_source_id_or_subtasks_are_rejected(operation, args):
    functions = {
        "save": external_subtasks.save_subtasks,
        "load": external_subtasks.load_subtasks,
        "attach": external_subtasks.attach_subtasks,
    }

    with pytest.raises(ValueError):
        functions[operation](*args)
