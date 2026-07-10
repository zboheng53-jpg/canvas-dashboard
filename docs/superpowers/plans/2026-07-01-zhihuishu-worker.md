# Zhihuishu Worker Implementation Plan

> Historical planning record. The unchecked checklist is preserved from drafting and includes superseded SSH-login assumptions. Use `docs/zhihuishu-reusable-web-patterns.md`, `deploy/zhihuishu-login-tunnel.md`, and `AGENTS.md` for the current login-window and worker behavior.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore Zhihuishu assignments in Canvas Dashboard with a background Ubuntu worker that keeps a persistent browser session alive and writes cached todos for the Flask app.

**Architecture:** Keep the main Flask app request path browser-free. A dedicated worker owns one persistent Playwright Chromium profile per site account, performs periodic keepalive and fetch cycles with backoff, and writes small JSON status/cache files under `data/users/<username>/`. Flask reads those files and exposes normal `/api/zhihuishu/*` endpoints.

**Tech Stack:** Flask, Waitress, Playwright Chromium, systemd service/timer or long-running service, JSON file storage, existing per-user `user_paths.py` layout.

---

## File Structure

- Create `zhihuishu_store.py`: per-user file paths, status/cache/state read/write helpers, stale-cache logic.
- Create `zhihuishu_worker.py`: long-running worker loop, single-instance lock, Playwright browser lifecycle, keepalive/fetch scheduling, backoff.
- Create `zhihuishu_browser.py`: isolated Playwright operations for login-state check, keepalive page visit, and assignment extraction.
- Create `templates/login_zhihuishu.html`: page that shows current worker/session status and Ubuntu login instructions.
- Create `tests/test_zhihuishu_store.py`: unit tests for cache/status/state behavior.
- Create `tests/test_zhihuishu_api.py`: Flask API tests with mocked store/client behavior.
- Modify `requirements.txt`: add `playwright`.
- Modify `app.py`: register `/login/zhihuishu` and `/api/zhihuishu/*`.
- Modify `templates/index.html`: add Zhihuishu card and unified list integration.
- Modify `static/style.css`: add Zhihuishu source badge styling.
- Modify `auth.py`: include legacy `zhihuishu_cache.json`, `zhihuishu_state.json`, and `zhihuishu_cookies.json` in first-account migration.
- Create `deploy/zhihuishu-worker.service`: Ubuntu systemd unit for the background worker.
- Create `deploy/zhihuishu-login-tunnel.md`: exact SSH tunnel/noVNC login procedure.

The current workspace is not a Git repository, so execution should use explicit checkpoints instead of `git commit` unless the repository is initialized before implementation.

---

### Task 1: Store Layer

**Files:**
- Create: `zhihuishu_store.py`
- Test: `tests/test_zhihuishu_store.py`

- [ ] **Step 1: Write failing tests for status/cache/state**

Create tests that monkeypatch `zhihuishu_store.DATA_DIR` to a temporary directory and verify:

```python
def test_status_defaults_to_never_logged_in(tmp_path, monkeypatch):
    import zhihuishu_store
    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    status = zhihuishu_store.load_status("alice")
    assert status["session"] == "not_logged_in"
    assert status["worker"] == "unknown"
    assert status["last_success_at"] is None


def test_cache_round_trip_marks_stale(tmp_path, monkeypatch):
    import time
    import zhihuishu_store
    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    zhihuishu_store.save_cache("alice", [{"id": "zhs_1", "title": "作业"}], fetched_at=time.time() - 7200)
    cache = zhihuishu_store.load_cache("alice", stale_after_seconds=1800)
    assert cache["items"][0]["id"] == "zhs_1"
    assert cache["stale"] is True


def test_state_update_is_string_based(tmp_path, monkeypatch):
    import zhihuishu_store
    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)
    state = zhihuishu_store.update_state("alice", "hide", "zhs_1")
    assert state["hidden"] == ["zhs_1"]
    state = zhihuishu_store.update_state("alice", "delete", "zhs_1")
    assert state["hidden"] == []
    assert state["deleted"] == ["zhs_1"]
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_zhihuishu_store.py -v`

Expected: imports or functions missing.

- [ ] **Step 3: Implement `zhihuishu_store.py`**

Implement helpers:

```python
STATUS_DEFAULT = {
    "session": "not_logged_in",
    "worker": "unknown",
    "last_keepalive_at": None,
    "last_fetch_at": None,
    "last_success_at": None,
    "last_error": "",
}
```

Use `data/users/<username>/zhihuishu_status.json`, `zhihuishu_cache.json`, and `zhihuishu_state.json`. State shape must match other platforms: `{"hidden": [], "highlighted": [], "deleted": []}`.

- [ ] **Step 4: Verify tests pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_zhihuishu_store.py -v`

Expected: all tests pass.

- [ ] **Step 5: Checkpoint**

Record changed files and passing test output in the session notes.

---

### Task 2: Flask API Contract

**Files:**
- Modify: `app.py`
- Create: `tests/test_zhihuishu_api.py`

- [ ] **Step 1: Write failing Flask API tests**

Tests should cover:

```python
def test_zhihuishu_todos_requires_setup_when_no_session(client_with_user, monkeypatch):
    resp = client_with_user.get("/api/zhihuishu/todos")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is False
    assert data["need_setup"] is True


def test_zhihuishu_state_rejects_json_null(client_with_user):
    resp = client_with_user.post("/api/zhihuishu/state", data="null", content_type="application/json")
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_login_page_accepts_zhihuishu(client_with_user):
    resp = client_with_user.get("/login/zhihuishu")
    assert resp.status_code == 200
```

Add a local fixture that creates a test client and sets `session["username"] = "alice"`.

- [ ] **Step 2: Run tests and confirm failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_zhihuishu_api.py -v`

Expected: route missing or status mismatch.

- [ ] **Step 3: Add Flask routes**

Add platform to `/login/<platform>` allowlist. Add:

- `GET /api/zhihuishu/config`
- `GET /api/zhihuishu/todos`
- `POST /api/zhihuishu/state`
- `POST /api/zhihuishu/login-required`

`/api/zhihuishu/todos` must read cache/status only. It must not launch a browser.

- [ ] **Step 4: Verify API tests pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_zhihuishu_api.py -v`

Expected: all tests pass.

- [ ] **Step 5: Checkpoint**

Record route list and test output.

---

### Task 3: Worker Skeleton Without Browser Logic

**Files:**
- Create: `zhihuishu_worker.py`
- Test: add tests to `tests/test_zhihuishu_store.py` or create `tests/test_zhihuishu_worker.py`

- [ ] **Step 1: Write tests for scheduling/backoff helpers**

Test pure functions:

```python
def test_backoff_caps_at_one_hour():
    from zhihuishu_worker import next_delay_seconds
    assert next_delay_seconds(0) == 15 * 60
    assert next_delay_seconds(1) == 30 * 60
    assert next_delay_seconds(2) == 60 * 60
    assert next_delay_seconds(5) == 60 * 60
```

- [ ] **Step 2: Implement worker constants and pure helpers**

Set:

```python
KEEPALIVE_INTERVAL_SECONDS = 15 * 60
FETCH_INTERVAL_SECONDS = 45 * 60
MAX_FAILURE_DELAY_SECONDS = 60 * 60
FETCH_TIMEOUT_SECONDS = 180
```

Implement `next_delay_seconds(failure_count)`.

- [ ] **Step 3: Add single-instance lock design**

Use a lock file under `data/zhihuishu_worker.lock`. On Ubuntu, use `fcntl.flock`; on unsupported platforms, fail clearly with a log message rather than running two workers.

- [ ] **Step 4: Add dry-run mode**

`python zhihuishu_worker.py --once --dry-run --username alice` should update status to `worker: "dry_run"` and exit without Playwright.

- [ ] **Step 5: Verify**

Run: `.venv\Scripts\python.exe -m pytest tests/test_zhihuishu_worker.py -v`

Expected: all pure tests pass.

---

### Task 4: Browser Adapter

**Files:**
- Create: `zhihuishu_browser.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add dependency**

Add `playwright>=1.45.0` to `requirements.txt`.

Ubuntu deployment command later:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

- [ ] **Step 2: Implement profile path convention**

For user `alice`, browser profile directory is:

```text
data/users/alice/zhihuishu_chromium_profile/
```

- [ ] **Step 3: Implement browser functions**

Implement:

- `open_login_browser(username: str) -> None`
- `check_session(username: str) -> bool`
- `keepalive(username: str) -> bool`
- `fetch_assignments(username: str) -> list[dict]`

Use Playwright persistent context. Keep extraction minimal: first support currently known assignment URLs and fields from cache shape: `id`, `title`, `course`, `due_str`, `due_ts`, `type`, `url`.

- [ ] **Step 4: Add manual smoke command**

`python zhihuishu_browser.py login --username alice` opens a visible browser on Ubuntu display/noVNC and waits for login.

- [ ] **Step 5: Manual verification**

On Ubuntu, run login command through noVNC/SSH tunnel, complete slider, then run:

```bash
.venv/bin/python zhihuishu_browser.py check --username alice
```

Expected: prints session OK.

---

### Task 5: Worker Browser Integration

**Files:**
- Modify: `zhihuishu_worker.py`
- Modify: `zhihuishu_store.py`

- [ ] **Step 1: Wire keepalive cycle**

Worker loop for each username:

1. Load status.
2. Call `zhihuishu_browser.check_session`.
3. If true, call `keepalive`.
4. Save status `session: "active"` and `last_keepalive_at`.
5. If false, save `session: "need_relogin"` and back off.

- [ ] **Step 2: Wire fetch cycle**

Every 45 minutes, call `fetch_assignments`, save cache, update `last_fetch_at` and `last_success_at`.

- [ ] **Step 3: Add failure behavior**

On exception:

- Save `last_error`.
- Increment failure count.
- Sleep using `next_delay_seconds`.
- Do not delete cache.

- [ ] **Step 4: Manual verification**

Run:

```bash
.venv/bin/python zhihuishu_worker.py --once --username alice
```

Expected: status JSON updates; cache JSON is written if session is active.

---

### Task 6: Frontend Integration

**Files:**
- Modify: `templates/index.html`
- Create: `templates/login_zhihuishu.html`
- Modify: `static/style.css`

- [ ] **Step 1: Add connection card**

Add a fourth card:

```html
<a href="/login/zhihuishu" class="login-card" data-platform="zhihuishu">
  <span class="login-card-title">智慧树</span>
  <span class="login-card-status" id="card-status-zhihuishu">检查中...</span>
</a>
```

- [ ] **Step 2: Add unified list arrays and fetcher**

Add `zhihuishuItems`, `zhihuishuHiddenIds`, `zhihuishuHighlightedIds`, `zhihuishuDeletedIds`.

Fetch `/api/zhihuishu/todos`, render source `zhihuishu`, and show stale status when returned.

- [ ] **Step 3: Add state actions**

Add `toggleZhihuishuHide`, `toggleZhihuishuHighlight`, `toggleZhihuishuDelete`. Check `resp.ok` before changing local arrays.

- [ ] **Step 4: Add login page**

`login_zhihuishu.html` should show:

- current session state
- last keepalive/fetch time
- last error
- instructions to open SSH tunnel/noVNC
- a refresh button

- [ ] **Step 5: Manual browser verification**

Run app locally or on Ubuntu, load `/`, confirm card appears and no JavaScript console errors.

---

### Task 7: Legacy Data and Multi-User Migration

**Files:**
- Modify: `auth.py`
- Optional migration note: `AGENTS.md`

- [ ] **Step 1: Add legacy file names**

Add to `_LEGACY_FILES`:

```python
"zhihuishu_state.json",
"zhihuishu_cache.json",
"zhihuishu_cookies.json",
```

Do not move `zhihuishu_chrome_profile/` automatically; document that it needs manual archival because it may be large and locked.

- [ ] **Step 2: Add migration test**

Test first registration moves top-level Zhihuishu JSON files into `data/users/<username>/`.

- [ ] **Step 3: Verify existing tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Expected: all tests pass.

---

### Task 8: Ubuntu Deployment

**Files:**
- Create: `deploy/zhihuishu-worker.service`
- Create: `deploy/zhihuishu-login-tunnel.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add systemd service**

Service shape:

```ini
[Unit]
Description=Canvas Dashboard Zhihuishu Worker
After=network.target canvas-dashboard.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/canvas-dashboard
ExecStart=/home/ubuntu/canvas-dashboard/.venv/bin/python zhihuishu_worker.py --all-users
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Add noVNC/SSH tunnel procedure**

Document:

```bash
ssh -L 6080:127.0.0.1:6080 ubuntu@124.222.188.101
```

Then open `http://127.0.0.1:6080` locally, complete Zhihuishu slider, close tunnel after login.

- [ ] **Step 3: Add production install commands**

```bash
cd /home/ubuntu/canvas-dashboard
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
sudo cp deploy/zhihuishu-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zhihuishu-worker.service
```

- [ ] **Step 4: Verify service**

```bash
systemctl status zhihuishu-worker.service
journalctl -u zhihuishu-worker.service -n 100 --no-pager
```

Expected: service running, no rapid restart loop, status/cache files updated.

---

### Task 9: End-to-End Verification

**Files:**
- No new files unless bugs are found.

- [ ] **Step 1: Run unit tests**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

- [ ] **Step 2: Compile Python files**

```powershell
.venv\Scripts\python.exe -m py_compile app.py auth.py user_paths.py zhihuishu_store.py zhihuishu_browser.py zhihuishu_worker.py
```

- [ ] **Step 3: Local API smoke test**

Use Flask test client to confirm unauthenticated `/api/zhihuishu/todos` returns `401`, authenticated returns JSON, and state rejects JSON `null` with `400`.

- [ ] **Step 4: Ubuntu smoke test**

Confirm:

- `/login/zhihuishu` shows worker status.
- Dashboard shows Zhihuishu card.
- Cache survives worker restart.
- Worker failure does not break Canvas/好课/智学盟.

- [ ] **Step 5: Production rollout**

Deploy code excluding `data/` and `.venv/`, install dependency, restart `canvas-dashboard`, start `zhihuishu-worker`, complete one noVNC login, then monitor for at least one keepalive interval and one fetch interval.

---

## Self-Review Notes

- Covers the agreed worker architecture, Ubuntu/noVNC first-login flow, 2c2g-friendly intervals, stale cache, backoff, and multi-user isolation.
- Avoids auto-solving slider; keeps human slider only for initial or forced re-login.
- Avoids browser work inside Flask requests.
- Current workspace is not a Git repository, so execution checkpoints replace commit steps.
