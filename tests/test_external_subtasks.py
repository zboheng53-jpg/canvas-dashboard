"""Unit tests for external platform subtasks storage and API."""
import pytest
import external_subtasks
import app as dashboard_app


def test_subtasks_are_isolated_by_source_and_item_id(tmp_path, monkeypatch):
    monkeypatch.setattr(external_subtasks, "user_dir", lambda username: tmp_path / username)
    canvas = [{"id": 1, "text": "Canvas task", "done": False, "due_date": None}]
    haoke = [{"id": 1, "text": "Haoke task", "done": True, "due_date": "2026-09-30"}]
    ketangpai = [{"id": 1, "text": "Ktp task", "done": False, "due_date": None}]

    external_subtasks.save_subtasks("alice", "canvas", 101, canvas)
    external_subtasks.save_subtasks("alice", "haoke", 101, haoke)
    external_subtasks.save_subtasks("alice", "ketangpai", 101, ketangpai)

    assert external_subtasks.load_subtasks("alice", "canvas", 101) == canvas
    assert external_subtasks.load_subtasks("alice", "haoke", 101) == haoke
    assert external_subtasks.load_subtasks("alice", "ketangpai", 101) == ketangpai


def test_attach_subtasks_includes_empty_lists(tmp_path, monkeypatch):
    monkeypatch.setattr(external_subtasks, "user_dir", lambda username: tmp_path / username)
    external_subtasks.save_subtasks("alice", "zhixuemeng", "work-1", [{"id": 1, "text": "step", "done": False}])
    response = external_subtasks.attach_subtasks("alice", "zhixuemeng", {"data": [{"id": "work-1"}, {"id": "work-2"}]})
    assert response["data"][0]["subtasks"] == [{"id": 1, "text": "step", "done": False, "due_date": None}]
    assert response["data"][1]["subtasks"] == []


@pytest.mark.parametrize("source,item_id,subtasks", [
    ("unknown", 1, []),
    ("canvas", "", []),
    ("canvas", 1, {}),
])
def test_invalid_external_subtask_input_is_rejected(tmp_path, monkeypatch, source, item_id, subtasks):
    monkeypatch.setattr(external_subtasks, "user_dir", lambda username: tmp_path / username)
    with pytest.raises(ValueError):
        external_subtasks.save_subtasks("alice", source, item_id, subtasks)


@pytest.fixture
def client_with_user(tmp_path, monkeypatch):
    user_root = tmp_path / "users"
    def resolve_user_dir(username):
        path = user_root / username
        path.mkdir(parents=True, exist_ok=True)
        return path
    monkeypatch.setattr(dashboard_app, "user_dir", resolve_user_dir)
    monkeypatch.setattr(external_subtasks, "user_dir", resolve_user_dir)
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["_csrf_token"] = "csrf-test-token"
        client.csrf_headers = {"X-CSRF-Token": "csrf-test-token"}
        yield client


def test_api_external_subtasks_put_and_load(client_with_user):
    subtasks = [
        {"id": 1, "text": "先读题", "done": False, "due_date": "2026-09-28"},
        {"id": 2, "text": "写代码", "done": True, "due_date": None},
    ]
    res = client_with_user.put(
        "/api/external-subtasks",
        json={"source": "canvas", "item_id": 999, "subtasks": subtasks},
        headers=client_with_user.csrf_headers,
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True
    assert res.get_json()["subtasks"] == subtasks

    # Verify invalid source rejected with 400
    res_bad = client_with_user.put(
        "/api/external-subtasks",
        json={"source": "invalid_source", "item_id": 999, "subtasks": []},
        headers=client_with_user.csrf_headers,
    )
    assert res_bad.status_code == 400
