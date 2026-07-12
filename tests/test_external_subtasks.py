import copy
import json

import pytest

import app as dashboard_app
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


def test_subtasks_use_trimmed_item_ids_for_saving_loading_and_attaching(external_store):
    subtasks = [{"id": "step-1", "text": "Trimmed", "done": False}]
    external_subtasks.save_subtasks("alice", "canvas", " 42 ", subtasks)

    assert external_subtasks.load_subtasks("alice", "canvas", "42") == subtasks
    attached = external_subtasks.attach_subtasks(
        "alice",
        "canvas",
        {"data": [{"id": "42", "title": "Assignment"}]},
    )
    assert attached["data"][0]["subtasks"] == subtasks


def test_load_subtasks_returns_empty_list_before_the_store_exists(external_store):
    assert external_subtasks.load_subtasks("alice", "canvas", "assignment-1") == []


def test_save_rejects_wrong_shaped_store_without_replacing_it(external_store):
    store_file = external_store("alice") / "external_subtasks.json"
    store_file.write_text("[]", encoding="utf-8")

    with pytest.raises(RuntimeError, match="external subtasks"):
        external_subtasks.save_subtasks("alice", "canvas", "assignment-1", [])

    assert store_file.read_text(encoding="utf-8") == "[]"


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


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    def resolve_user_dir(username):
        path = tmp_path / "users" / username
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(external_subtasks, "user_dir", resolve_user_dir)
    dashboard_app.app.config.update(TESTING=True)
    with dashboard_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["_csrf_token"] = "csrf-test-token"
        client.csrf_headers = {"X-CSRF-Token": "csrf-test-token"}
        yield client


def _empty_state():
    return {"hidden": [], "highlighted": [], "deleted": []}


@pytest.mark.parametrize(
    ("source", "path", "item", "configure_route"),
    [
        (
            "canvas",
            "/api/canvas/todos",
            {"id": "shared-item", "title": "Canvas"},
            lambda monkeypatch: (
                monkeypatch.setattr(
                    dashboard_app,
                    "fetch_canvas_planner",
                    lambda username: {"ok": True, "data": [{"id": "shared-item", "title": "Canvas"}]},
                ),
                monkeypatch.setattr(dashboard_app, "load_state", lambda username: _empty_state()),
                monkeypatch.setattr(dashboard_app, "save_state", lambda username, state: None),
            ),
        ),
        (
            "haoke",
            "/api/haoke/todos",
            {"id": "shared-item", "title": "Haoke"},
            lambda monkeypatch: (
                monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: False),
                monkeypatch.setattr(
                    dashboard_app,
                    "fetch_haoke_todos",
                    lambda username: {"ok": True, "data": [{"id": "shared-item", "title": "Haoke"}]},
                ),
                monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: _empty_state()),
                monkeypatch.setattr(dashboard_app, "save_haoke_state", lambda username, state: None),
            ),
        ),
        (
            "zhixuemeng",
            "/api/zhixuemeng/todos",
            {"id": "zxm-1", "title": "Zhixuemeng"},
            lambda monkeypatch: (
                monkeypatch.setattr(dashboard_app, "get_selected_course", lambda username: "course-1"),
                monkeypatch.setattr(
                    dashboard_app,
                    "fetch_zxm_assignments",
                    lambda username, course_code: {"ok": True, "items": [{"id": "zxm-1", "title": "Zhixuemeng"}]},
                ),
                monkeypatch.setattr(dashboard_app, "load_zxm_state", lambda username: _empty_state()),
                monkeypatch.setattr(dashboard_app, "save_zxm_state", lambda username, state: None),
            ),
        ),
        (
            "zhihuishu",
            "/api/zhihuishu/todos",
            {"id": "zhs-1", "title": "Zhihuishu"},
            lambda monkeypatch: (
                monkeypatch.setattr(dashboard_app.zhihuishu_store, "load_status", lambda username: {"session": "ok"}),
                monkeypatch.setattr(
                    dashboard_app.zhihuishu_store,
                    "load_cache",
                    lambda username: {"items": [{"id": "zhs-1", "title": "Zhihuishu"}], "stale": False, "fetched_at": 1},
                ),
                monkeypatch.setattr(dashboard_app.zhihuishu_store, "load_state", lambda username: _empty_state()),
            ),
        ),
    ],
)
def test_put_subtasks_are_returned_by_each_platform_todos_route(
    api_client, monkeypatch, source, path, item, configure_route
):
    subtasks = [{"id": f"{source}-step", "text": "Read", "done": False}]
    saved = api_client.put(
        "/api/external-subtasks",
        json={"source": source, "item_id": item["id"], "subtasks": subtasks},
        headers=api_client.csrf_headers,
    )

    assert saved.status_code == 200
    assert saved.get_json() == {"ok": True, "subtasks": subtasks}

    configure_route(monkeypatch)
    response = api_client.get(path)

    assert response.status_code == 200
    assert response.get_json()["data"] == [{**item, "subtasks": subtasks}]


def test_same_item_id_is_isolated_between_platform_sources(api_client, monkeypatch):
    canvas_subtasks = [{"id": "canvas-step", "text": "Canvas", "done": False}]
    haoke_subtasks = [{"id": "haoke-step", "text": "Haoke", "done": True}]
    for source, subtasks in (("canvas", canvas_subtasks), ("haoke", haoke_subtasks)):
        response = api_client.put(
            "/api/external-subtasks",
            json={"source": source, "item_id": "shared-item", "subtasks": subtasks},
            headers=api_client.csrf_headers,
        )
        assert response.status_code == 200

    monkeypatch.setattr(
        dashboard_app,
        "fetch_canvas_planner",
        lambda username: {"ok": True, "data": [{"id": "shared-item", "title": "Canvas"}]},
    )
    monkeypatch.setattr(dashboard_app, "load_state", lambda username: _empty_state())
    monkeypatch.setattr(dashboard_app, "save_state", lambda username, state: None)
    monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: False)
    monkeypatch.setattr(
        dashboard_app,
        "fetch_haoke_todos",
        lambda username: {"ok": True, "data": [{"id": "shared-item", "title": "Haoke"}]},
    )
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: _empty_state())
    monkeypatch.setattr(dashboard_app, "save_haoke_state", lambda username, state: None)

    assert api_client.get("/api/canvas/todos").get_json()["data"][0]["subtasks"] == canvas_subtasks
    assert api_client.get("/api/haoke/todos").get_json()["data"][0]["subtasks"] == haoke_subtasks


def test_platform_todos_add_empty_subtasks_when_no_record_exists(api_client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "fetch_canvas_planner",
        lambda username: {"ok": True, "data": [{"id": "unrecorded", "title": "Canvas"}]},
    )
    monkeypatch.setattr(dashboard_app, "load_state", lambda username: _empty_state())
    monkeypatch.setattr(dashboard_app, "save_state", lambda username, state: None)

    response = api_client.get("/api/canvas/todos")

    assert response.status_code == 200
    assert response.get_json()["data"][0]["subtasks"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"source": "invalid", "item_id": "item-1", "subtasks": []},
        {"source": "canvas", "item_id": "   ", "subtasks": []},
        {"source": "canvas", "item_id": "item-1", "subtasks": {}},
        None,
    ],
)
def test_external_subtasks_put_rejects_invalid_payload(api_client, payload):
    if payload is None:
        response = api_client.put(
            "/api/external-subtasks",
            data="null",
            content_type="application/json",
            headers=api_client.csrf_headers,
        )
    else:
        response = api_client.put(
            "/api/external-subtasks",
            json=payload,
            headers=api_client.csrf_headers,
        )

    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_zhihuishu_need_setup_uses_subtask_attachment(api_client, monkeypatch):
    attached = []

    def capture_attachment(username, source, result):
        attached.append((username, source, result))
        return result

    monkeypatch.setattr(dashboard_app, "attach_subtasks", capture_attachment)
    monkeypatch.setattr(
        dashboard_app.zhihuishu_store,
        "load_status",
        lambda username: {"session": "not_logged_in"},
    )
    monkeypatch.setattr(
        dashboard_app.zhihuishu_store,
        "load_cache",
        lambda username: {"items": [], "stale": False, "fetched_at": None},
    )
    monkeypatch.setattr(dashboard_app.zhihuishu_store, "load_state", lambda username: _empty_state())

    response = api_client.get("/api/zhihuishu/todos")

    assert response.status_code == 200
    assert response.get_json()["data"] == []
    assert attached == [("alice", "zhihuishu", {
        "ok": False,
        "need_setup": True,
        "status": {"session": "not_logged_in"},
        "data": [],
        "hidden": [],
        "highlighted": [],
        "deleted": [],
    })]
