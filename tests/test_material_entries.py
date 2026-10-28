"""Native material entries preserve legacy text and use the project storage boundary."""
from concurrent.futures import ThreadPoolExecutor

import pytest

import agent_auth
import app as dashboard
import project_store
from test_action_workspace import create_project, workspace
from test_today_project_rules import project_clock


pytestmark = [pytest.mark.now("2026-10-28T12:00:00+08:00"), pytest.mark.usefixtures("project_clock")]


def _create(client, headers, project, body="记录本次结果", **fields):
    response = client.post(f"/api/projects/{project['id']}/materials", headers=headers,
                           json={"body": body, **fields})
    assert response.status_code in (200, 201), response.get_json()
    return response.get_json()["entry"]


def _project():
    return project_store.load_projects("alice")[0]


def test_log_crud_conflicts_and_nonreused_ids(workspace):
    client, headers = workspace
    project = create_project(client, headers)
    original = "  第一行\r\n第二行  \n"
    entry = _create(client, headers, project, original, request_id="log-1")
    assert entry["date"] == "2026-10-28" and entry["body"] == original
    replay = _create(client, headers, project, original, request_id="log-1")
    assert replay["id"] == entry["id"]
    assert len(_project()["material_entries"]) == 1
    collection = f"/api/projects/{project['id']}/materials"
    assert client.post(collection, headers=headers, json={"body": "不同结果", "request_id": "log-1"}).status_code == 409
    url = f"{collection}/{entry['id']}"
    updated = client.put(url, headers=headers, json={"body": "补充结果\n", "date": "2026-10-27",
                        "expected_updated_at": entry["updated_at"]})
    assert updated.status_code == 200
    current = updated.get_json()["entry"]
    assert current["body"] == "补充结果\n" and current["date"] == "2026-10-27"
    assert client.put(url, headers=headers, json={"body": "过期修改", "expected_updated_at": entry["updated_at"]}).status_code == 409
    assert client.delete(url, headers=headers, json={"expected_updated_at": entry["updated_at"]}).status_code == 409
    assert _project()["material_entries"][0]["body"] == "补充结果\n"
    assert client.delete(url, headers=headers, json={"expected_updated_at": current["updated_at"]}).status_code == 200
    newer = _create(client, headers, project, request_id="log-2")
    assert newer["id"] > entry["id"]
    assert _project()["next_material_entry_id"] > newer["id"]


def test_legacy_edit_is_lossless_and_cannot_replace_native_log(workspace):
    client, headers = workspace
    project = create_project(client, headers)
    original = "  前言\r\n【2026-10-27 实验】\r\n结果\n\n【旧记录】\n无日期\n "
    response = client.put(f"/api/projects/{project['id']}", headers=headers,
                          json={"materials": original, "expected_updated_at": project["updated_at"]})
    assert response.status_code == 200 and response.get_json()["project"]["materials"] == original
    entry = _create(client, headers, project)
    current = _project()
    replacement = original + "\n追加原文说明\n"
    response = client.put(f"/api/projects/{project['id']}", headers=headers,
                          json={"materials": replacement, "expected_updated_at": current["updated_at"]})
    assert response.status_code == 200
    assert _project()["materials"] == replacement
    assert _project()["material_entries"][0]["id"] == entry["id"]
    data = client.get(f"/api/materials?project_id={project['id']}").get_json()
    assert data["projects"][0]["materials"] == replacement
    assert len([item for item in data["entries"] if not item["legacy"]]) == 1
    assert any(item["legacy"] and item["date"] is None for item in data["entries"])
    assert any(item["legacy"] and item["date"] == "2026-10-27" for item in data["entries"])


@pytest.mark.parametrize("changes", [{"body": "x" * 20001}, {"body": ""}, {"date": "2026-02-30"}, {"body": ["text"]}])
def test_invalid_entry_does_not_modify_project(workspace, changes):
    client, headers = workspace
    project = create_project(client, headers)
    before = _project()
    response = client.post(f"/api/projects/{project['id']}/materials", headers=headers,
                           json={"body": "正常记录", **changes})
    assert response.status_code == 400
    assert _project() == before


def test_agent_and_browser_share_logs_but_never_accounts(workspace):
    client, headers = workspace
    project = create_project(client, headers)
    browser_entry = _create(client, headers, project, "网页记录")
    read_token = agent_auth.create_token("alice", scopes=["read"])
    read_headers = {"Authorization": f"Bearer {read_token}"}
    assert client.get("/api/agent/v1/materials").status_code == 401
    data = client.get("/api/agent/v1/materials", headers=read_headers).get_json()
    assert any(item["id"] == browser_entry["id"] and item["body"] == "网页记录" for item in data["entries"])
    url = f"/api/agent/v1/projects/{project['id']}/materials"
    assert client.post(url, headers=read_headers, json={"body": "不允许"}).status_code == 403
    write_token = agent_auth.create_token("alice", scopes=["read", "write", "delete"])
    bearer = {"Authorization": f"Bearer {write_token}"}
    created = client.post(url, headers=bearer, json={"body": "Agent 记录", "date": "2026-10-26", "request_id": "agent-log"})
    assert created.status_code in (200, 201)
    assert any(item["body"] == "Agent 记录" for item in client.get("/api/materials").get_json()["entries"])
    agent_auth.auth.register("bob", "password1")
    with client.session_transaction() as session:
        session["username"] = "bob"
    response = client.get("/api/materials")
    assert response.status_code == 200 and response.get_json()["entries"] == []
    assert client.post(f"/api/projects/{project['id']}/materials", headers=headers, json={"body": "越界"}).status_code == 404
    assert len(client.get("/api/agent/v1/materials", headers=bearer).get_json()["entries"]) == 2


def test_to_materials_is_atomic_retry_safe_and_advances_current_step(workspace):
    client, headers = workspace
    project = create_project(client, headers)
    project_store.update_project("alice", project["id"], {"materials": "原文保持不变"})
    task = project_store.create_task("alice", project["id"], {
        "name": "完成实验", "details": "完整实验方法\n结论保留", "planned_on": "2026-10-27",
        "due_date": "2026-11-03", "is_next_action": True,
    })
    following = project_store.create_task("alice", project["id"], {"name": "下个步骤", "planned_on": "2026-10-29"})
    current = _project()
    payload = {"expected_updated_at": task["updated_at"], "expected_project_updated_at": "stale"}
    url = f"/api/projects/{project['id']}/tasks/{task['id']}/to-materials"
    assert client.post(url, headers=headers, json=payload).status_code == 409
    assert _project() == current
    payload["expected_project_updated_at"] = current["updated_at"]
    assert client.post(url, headers=headers, json=payload).status_code == 200
    assert client.post(url, headers=headers, json=payload).status_code == 200
    current = _project()
    assert current["materials"] == "原文保持不变"
    assert [item["id"] for item in current["tasks"]] == [following["id"]]
    assert current["tasks"][0]["is_next_action"]
    assert len(current["material_entries"]) == 1
    entry = current["material_entries"][0]
    assert entry["source_ref"] == f"project:{project['id']}:{task['id']}"
    assert all(value in entry["body"] for value in (task["name"], task["details"], "2026-10-27", "2026-11-03"))


def test_concurrent_log_appends_do_not_overwrite_each_other(workspace):
    client, headers = workspace
    project = create_project(client, headers)
    token = agent_auth.create_token("alice", scopes=["read", "write"])
    bearer = {"Authorization": f"Bearer {token}"}

    def append(number):
        with dashboard.app.test_client() as peer:
            response = peer.post(f"/api/agent/v1/projects/{project['id']}/materials", headers=bearer,
                                 json={"body": f"并发记录 {number}", "request_id": f"parallel-{number}"})
            assert response.status_code in (200, 201)
            return response.get_json()["entry"]

    with ThreadPoolExecutor(2) as pool:
        entries = list(pool.map(append, [1, 2]))
    assert len({item["id"] for item in entries}) == 2
    assert {item["body"] for item in _project()["material_entries"]} == {"并发记录 1", "并发记录 2"}
