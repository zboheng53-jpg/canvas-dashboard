import app as dashboard_app
import user_paths


def _client(tmp_path, monkeypatch, username):
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    monkeypatch.setitem(dashboard_app.app.config, "TESTING", True)
    client = dashboard_app.app.test_client()
    with client.session_transaction() as session:
        session["username"] = username
        session["_csrf_token"] = f"csrf-{username}"
    client.csrf_headers = {"X-CSRF-Token": f"csrf-{username}"}
    return client


def test_dashboard_source_preferences_default_persist_and_stay_account_scoped(tmp_path, monkeypatch):
    alice = _client(tmp_path, monkeypatch, "alice")
    default = alice.get("/api/dashboard/preferences")

    assert default.status_code == 200
    assert default.get_json()["visible_todo_sources"] == [
        "canvas",
        "haoke",
        "zhixuemeng",
        "zhihuishu",
        "project",
        "custom",
    ]

    updated = alice.put(
        "/api/dashboard/preferences",
        json={"visible_todo_sources": ["canvas", "custom"]},
        headers=alice.csrf_headers,
    )
    assert updated.status_code == 200
    assert updated.get_json()["visible_todo_sources"] == ["canvas", "custom"]
    assert alice.get("/api/dashboard/preferences").get_json()["visible_todo_sources"] == ["canvas", "custom"]

    bob = _client(tmp_path, monkeypatch, "bob")
    assert bob.get("/api/dashboard/preferences").get_json()["visible_todo_sources"] == [
        "canvas",
        "haoke",
        "zhixuemeng",
        "zhihuishu",
        "project",
        "custom",
    ]


def test_dashboard_source_preferences_reject_invalid_payloads(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "alice")

    for payload in (
        {},
        {"visible_todo_sources": "canvas"},
        {"visible_todo_sources": ["canvas", "canvas"]},
        {"visible_todo_sources": ["canvas", "unknown"]},
        {"visible_todo_sources": ["canvas", {"bad": True}]},
    ):
        response = client.put(
            "/api/dashboard/preferences",
            json=payload,
            headers=client.csrf_headers,
        )
        assert response.status_code == 400
        assert response.get_json()["code"] == "visible_todo_sources_invalid"


def test_dashboard_source_preferences_fail_closed_on_corrupt_json(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "alice")
    preference_path = tmp_path / "users" / "alice" / "dashboard_preferences.json"
    preference_path.parent.mkdir(parents=True, exist_ok=True)
    preference_path.write_text("{broken", encoding="utf-8")

    response = client.get("/api/dashboard/preferences")

    assert response.status_code == 503
    assert response.get_json()["error"] == "stored data is temporarily unavailable"
    assert preference_path.read_text(encoding="utf-8") == "{broken"
    assert list(preference_path.parent.glob("dashboard_preferences.json.corrupt-*"))
