# 外部平台作业子任务 Implementation Plan

> Historical proposal, not an implemented contract. There is currently no `external_subtasks.py`, `/api/external-subtasks` route, or editable subtask UI for imported platform assignments. Custom-todo subtasks are the only editable subtasks; dated custom subtasks can be exported to Apple Calendar.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Canvas、好课、智学盟和智慧树导入的作业拥有与自定义待办相同、刷新后可恢复的子任务读写，并保持三角按钮位置不变。

**Architecture:** 新建每用户外部子任务侧存储，以 `source:item_id` 为稳定键；四个平台接口返回作业前合并本地子任务。前端将 custom-only 子任务逻辑泛化到统一列表，并按来源使用原有自定义 PUT 或新的外部 PUT。

**Tech Stack:** Python、Flask、JSON 原子存储、pytest、Playwright、原生 JavaScript/CSS。

---

## 文件结构

- Create: `external_subtasks.py` — 每用户 `external_subtasks.json` 的验证、读写与响应合并。
- Modify: `app.py` — 四平台响应合并和通用 PUT 路由。
- Create: `tests/test_external_subtasks.py` — 存储、API、恢复和输入校验测试。
- Modify: `templates/index.html` — 统一列表的泛化子任务交互。
- Modify: `tests/test_frontend_playwright.py` — 四平台的端到端读写、刷新和布局回归。
- Modify: `AGENTS.md` — 新路由、数据文件和前端契约。

### Task 1: 为外部子任务存储建立失败测试

**Files:**
- Create: `tests/test_external_subtasks.py`
- Create: `external_subtasks.py`

- [ ] **Step 1: 写入存储层失败测试**

创建 `tests/test_external_subtasks.py`：

```python
import pytest
import app as dashboard_app
import external_subtasks


def test_subtasks_are_isolated_by_source_and_item_id(tmp_path, monkeypatch):
    monkeypatch.setattr(external_subtasks, "user_dir", lambda username: tmp_path / username)
    canvas = [{"id": 1, "text": "Canvas", "done": False}]
    haoke = [{"id": 1, "text": "Haoke", "done": True}]
    external_subtasks.save_subtasks("alice", "canvas", 101, canvas)
    external_subtasks.save_subtasks("alice", "haoke", 101, haoke)
    assert external_subtasks.load_subtasks("alice", "canvas", 101) == canvas
    assert external_subtasks.load_subtasks("alice", "haoke", 101) == haoke


def test_attach_subtasks_includes_empty_lists(tmp_path, monkeypatch):
    monkeypatch.setattr(external_subtasks, "user_dir", lambda username: tmp_path / username)
    external_subtasks.save_subtasks("alice", "zhixuemeng", "work-1", [{"id": 1, "text": "step", "done": False}])
    response = external_subtasks.attach_subtasks("alice", "zhixuemeng", {"data": [{"id": "work-1"}, {"id": "work-2"}]})
    assert response["data"][0]["subtasks"] == [{"id": 1, "text": "step", "done": False}]
    assert response["data"][1]["subtasks"] == []


@pytest.mark.parametrize("source,item_id,subtasks", [("unknown", 1, []), ("canvas", "", []), ("canvas", 1, {})])
def test_invalid_external_subtask_input_is_rejected(tmp_path, monkeypatch, source, item_id, subtasks):
    monkeypatch.setattr(external_subtasks, "user_dir", lambda username: tmp_path / username)
    with pytest.raises(ValueError):
        external_subtasks.save_subtasks("alice", source, item_id, subtasks)
```

- [ ] **Step 2: 确认测试是红的**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_external_subtasks.py -q`  
Expected: collection fails with `ModuleNotFoundError: No module named 'external_subtasks'`.

- [ ] **Step 3: 实现最小存储模块**

创建 `external_subtasks.py`，核心实现如下：

```python
"""Persistent per-user subtasks for imported platform assignments."""
from datetime import datetime, timezone
from storage import locked_json_update, read_json_file
from user_paths import user_dir

SUPPORTED_SOURCES = frozenset({"canvas", "haoke", "zhixuemeng", "zhihuishu"})
DEFAULT_SUBTASKS = {}

def _path(username):
    return user_dir(username) / "external_subtasks.json"

def _key(source, item_id):
    if source not in SUPPORTED_SOURCES:
        raise ValueError("unsupported source")
    item_id = str(item_id).strip()
    if not item_id:
        raise ValueError("item id is required")
    return f"{source}:{item_id}"

def load_subtasks(username, source, item_id):
    return list(read_json_file(_path(username), DEFAULT_SUBTASKS).get(_key(source, item_id), {}).get("subtasks", []))

def save_subtasks(username, source, item_id, subtasks):
    if not isinstance(subtasks, list):
        raise ValueError("subtasks must be a list")
    key = _key(source, item_id)
    def update(records):
        records[key] = {"subtasks": subtasks, "updated_at": datetime.now(timezone.utc).isoformat()}
        return records
    return locked_json_update(_path(username), DEFAULT_SUBTASKS, update)[key]["subtasks"]

def attach_subtasks(username, source, result):
    records = read_json_file(_path(username), DEFAULT_SUBTASKS)
    response = dict(result)
    response["data"] = [{**item, "subtasks": list(records.get(_key(source, item.get("id")), {}).get("subtasks", []))} for item in response.get("data", [])]
    return response
```

Use only the source whitelist and full-array replacement. Do not prune records when a platform does not currently return an assignment.

- [ ] **Step 4: 确认测试转绿**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_external_subtasks.py -q`  
Expected: all storage tests pass.

### Task 2: 为四平台 API 合并和写入接口执行 TDD

**Files:**
- Modify: `tests/test_external_subtasks.py`
- Modify: `app.py`

- [ ] **Step 1: 写出 API 失败测试**

在测试文件添加登录 session fixture 和可复用的四平台 seed helper：

```python
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


def seed_all_platform_routes(monkeypatch, seeds):
    state = {"hidden": [], "highlighted": [], "deleted": []}
    monkeypatch.setattr(dashboard_app, "fetch_canvas_planner", lambda username: {"ok": True, "data": [{"id": seeds["canvas"], "title": "Canvas"}]})
    monkeypatch.setattr(dashboard_app, "load_state", lambda username: state)
    monkeypatch.setattr(dashboard_app, "save_state", lambda username, value: None)
    monkeypatch.setattr(dashboard_app, "has_haoke_credentials", lambda username: False)
    monkeypatch.setattr(dashboard_app, "fetch_haoke_todos", lambda username: {"ok": True, "data": [{"id": seeds["haoke"], "title": "Haoke"}]})
    monkeypatch.setattr(dashboard_app, "load_haoke_state", lambda username: state)
    monkeypatch.setattr(dashboard_app, "save_haoke_state", lambda username, value: None)
    monkeypatch.setattr(dashboard_app, "get_selected_course", lambda username: None)
    monkeypatch.setattr(dashboard_app, "fetch_zxm_assignments", lambda username, course_code: {"ok": True, "items": [{"id": seeds["zhixuemeng"], "title": "Zhixuemeng"}]})
    monkeypatch.setattr(dashboard_app, "load_zxm_state", lambda username: state)
    monkeypatch.setattr(dashboard_app, "save_zxm_state", lambda username, value: None)
    monkeypatch.setattr(dashboard_app.zhihuishu_store, "load_status", lambda username: {"session": "active"})
    monkeypatch.setattr(dashboard_app.zhihuishu_store, "load_state", lambda username: state)
    monkeypatch.setattr(dashboard_app.zhihuishu_store, "load_cache", lambda username: {"items": [{"id": seeds["zhihuishu"], "title": "Zhihuishu"}], "stale": False, "fetched_at": 0})
```

Then add the following tests:

```python
def test_external_subtask_put_restores_subtasks_in_all_platform_responses(client_with_user, monkeypatch):
    seeds = {"canvas": 101, "haoke": 102, "zhixuemeng": "103", "zhihuishu": "104"}
    seed_all_platform_routes(monkeypatch, seeds)
    for source, item_id in seeds.items():
        subtasks = [{"id": 1, "text": source, "done": False, "due_date": None}]
        written = client_with_user.put("/api/external-subtasks", json={"source": source, "item_id": item_id, "subtasks": subtasks}, headers=client_with_user.csrf_headers)
        assert written.status_code == 200
        fetched = client_with_user.get(f"/api/{source}/todos")
        assert fetched.get_json()["data"][0]["subtasks"] == subtasks


def test_external_subtask_put_rejects_invalid_payload(client_with_user):
    response = client_with_user.put("/api/external-subtasks", json={"source": "unknown", "item_id": "1", "subtasks": []}, headers=client_with_user.csrf_headers)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
```

- [ ] **Step 2: 运行并确认失败原因**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_external_subtasks.py -q`  
Expected: API test fails with `404` and/or missing `subtasks`, not fixture errors.

- [ ] **Step 3: 接入路由和响应合并**

在 `app.py` 添加 `from external_subtasks import attach_subtasks, save_subtasks`，并在 Canvas 组前添加：

```python
@app.route("/api/external-subtasks", methods=["PUT"])
def api_external_subtasks():
    username = session["username"]
    data = read_json_request()
    if not isinstance(data, dict):
        return invalid_request_response()
    try:
        subtasks = save_subtasks(username, data.get("source"), data.get("item_id"), data.get("subtasks"))
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    return jsonify({"ok": True, "subtasks": subtasks})
```

Wrap each four existing todo response after `build_platform_todos_response()`:

```python
return jsonify(attach_subtasks(username, "canvas", result))
return jsonify(attach_subtasks(username, "haoke", result))
return jsonify(attach_subtasks(username, "zhixuemeng", result))
return jsonify(attach_subtasks(username, "zhihuishu", result))
```

Also wrap Zhihuishu's early `need_setup` response so its `data` contract is identical. Do not alter the platform state files or platform client modules.

- [ ] **Step 4: 验证 API 恢复行为**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_external_subtasks.py -q`  
Expected: all tests pass; a GET after a prior PUT returns the same source-and-ID keyed record.

### Task 3: 对前端统一子任务面板执行浏览器 TDD

**Files:**
- Modify: `tests/test_frontend_playwright.py`
- Modify: `templates/index.html`

- [ ] **Step 1: 添加四平台失败的 Playwright 测试**

扩展 `live_app` fixture：让好课、智学盟、智慧树也各返回一条稳定作业，保留 Canvas 现有作业。添加下列参数化测试：

```python
@pytest.mark.parametrize("title", ["Canvas seeded", "Haoke seeded", "Zhixuemeng seeded", "Zhihuishu seeded"])
def test_frontend_external_subtasks_persist_after_reload(live_app, browser, title):
    page = browser.new_page()
    register_dashboard_user(page, live_app, f"external-{title}")
    item = page.locator(".unified-item-wrap").filter(has_text=title)
    toggle = item.locator(".subtask-toggle")
    expect(toggle).to_have_text("▷")
    toggle.click()
    page.fill(".subtask-add-input", "Read first")
    page.press(".subtask-add-input", "Enter")
    item.locator(".subtask-text").click()
    page.locator(".subtask-edit-input").fill("Read revised")
    page.press(".subtask-edit-input", "Enter")
    item.locator(".subtask-due-input").fill("2026-07-10")
    item.locator("input[type=checkbox]").check()
    page.reload()
    restored = page.locator(".unified-item-wrap").filter(has_text=title)
    expect(restored.locator(".subtask-toggle")).to_have_text("▷")
    restored.locator(".subtask-toggle").click()
    expect(restored.locator(".subtask-text")).to_have_text("Read revised")
    expect(restored.locator("input[type=checkbox]")).to_be_checked()
    expect(restored.locator(".subtask-due-input")).to_have_value("2026-07-10")
    restored.locator(".subtask-delete").click()
    expect(restored.locator(".subtask-text")).to_have_count(0)
```

Extend the current desktop/mobile alignment tests to assert each external button has a bounding box inside `.item-subtask-slot`, lies to the right of labels, and retains the existing 36px mobile hit area.

- [ ] **Step 2: 运行并确认占位符导致失败**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py -q`  
Expected: new test fails because external triangles are non-clickable placeholder spans and no subtask panel is rendered.

- [ ] **Step 3: 泛化前端逻辑，保持布局不变**

在 `templates/index.html` 完成以下修改：

1. Replace `expandedCustomTodoIds` with `expandedTodoKeys`; add:

```javascript
function todoKey(source, todoId) { return `${source}:${todoId}`; }
```

2. Add `subtasks: item.subtasks || []` to the Canvas, Haoke, Zhixuemeng, and Zhihuishu unified objects.

3. Render every `item-subtask-slot` as the existing `.subtask-toggle` button. Use safe inline arguments and the same position:

```javascript
const itemKey = todoKey(item.source, item.rawId);
const isSubtaskExpanded = expandedTodoKeys.includes(itemKey);
const sourceArg = JSON.stringify(item.source);
const rawIdArg = JSON.stringify(String(item.rawId));
const subtaskToggleHtml = `<button class="subtask-toggle" onclick="toggleSubtasks(${sourceArg}, ${rawIdArg})" title="${subtaskToggleLabel}" aria-label="${subtaskToggleLabel}">${subtaskToggleIcon}</button>`;
```

4. Return `.unified-item-wrap` for all sources with unchanged `rowHtml` and optional `renderSubtaskPanel(item.source, item.rawId, subtasks)` below it. Do not alter `item-subtask-slot`, dates, actions, or subtask CSS dimensions.

5. Replace `findCustomTodo(todoId)` with `findTodo(source, todoId)`, selecting the corresponding source array and comparing IDs as strings. Add `source` as the first argument to all subtask handler and rendering functions.

6. Replace `saveCustomSubtasks` with `saveSubtasks(source, todoId, subtasks)`. Keep the custom branch exactly on `/api/custom/todos/${todoId}` with `updated_at`; use this external branch:

```javascript
const resp = await fetch('/api/external-subtasks', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ source, item_id: todoId, subtasks }),
});
```

On successful writes update the in-memory item and render. On failure retain the current alert, then call `fetchCustomTodos()` for custom or the matching existing platform fetcher for an external source.

- [ ] **Step 4: 验证端到端读写和位置**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py -q`  
Expected: all existing tests and four external source cases pass, proving add/edit/check/date/delete persistence and unchanged button geometry.

### Task 4: 更新项目契约并进行完整验证

**Files:**
- Modify: `AGENTS.md`
- Test: `tests/test_external_subtasks.py`
- Test: `tests/test_frontend_playwright.py`

- [ ] **Step 1: 记录新的 API 和数据文件契约**

In `AGENTS.md`, add `/api/external-subtasks` (PUT) to the route table; add per-user `external_subtasks.json` keyed by platform source and assignment ID to the data table; note that all unified external rows share the custom subtask UI while expansion state remains browser-only. If `CLAUDE.md` is not still linked to `AGENTS.md`, stop and report rather than overwriting it.

- [ ] **Step 2: 运行目标测试集**

Run: `\.venv\Scripts\python.exe -m pytest tests\test_external_subtasks.py tests\test_custom_todo_subtasks.py tests\test_frontend_playwright.py -q`  
Expected: exit code 0.

- [ ] **Step 3: 运行完整回归并检查改动范围**

Run: `.\scripts\test.ps1`  
Expected: exit code 0.

Then run: `git diff --check; git status --short`  
Expected: no whitespace errors; no changes under `data/`; only files listed in this plan are changed.
