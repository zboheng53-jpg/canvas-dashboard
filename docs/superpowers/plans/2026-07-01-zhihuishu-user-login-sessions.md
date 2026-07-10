# Zhihuishu User Login Sessions Implementation Plan

> Historical planning record. The unchecked checklist is preserved from drafting. Use `deploy/zhihuishu-login-tunnel.md` and `AGENTS.md` for the current deployment and route behavior.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let ordinary site users log in to Zhihuishu themselves without SSH, server terminal access, or a shared server desktop.

**Architecture:** Flask creates short-lived per-user login sessions with high-entropy tokens. A login session starts an isolated Chromium/noVNC container mounted only to that user's `zhihuishu_chromium_profile`; nginx proxies tokenized `/zhs-vnc/<port>/<token>/...` requests to the local container port after asking Flask to authorize the token. The normal worker continues to read each user's saved profile and cache assignments outside request paths.

**Tech Stack:** Flask, Docker, Chromium, Xvfb, x11vnc, noVNC/websockify, nginx `auth_request`, JSON file storage, existing per-user data directories.

---

## File Structure

- Create `zhihuishu_login_sessions.py`: token lifecycle, per-user session metadata, Docker command construction, port allocation, stop/cleanup helpers.
- Modify `app.py`: add login-session API routes and tokenized redirect/auth endpoints.
- Modify `templates/login_zhihuishu.html`: replace admin SSH instructions with a user-facing "open login window" flow.
- Modify `static/style.css`: add compact login-session UI styles.
- Modify `deploy/canvas-dashboard.nginx`: add token-gated noVNC reverse proxy location.
- Create `deploy/zhihuishu-login-browser.Dockerfile`: reproducible browser/noVNC container image.
- Create `deploy/zhihuishu-login-browser-entrypoint.sh`: launches Xvfb, noVNC, and Chromium with the mounted profile.
- Modify `deploy/zhihuishu-login-tunnel.md`: replace SSH/noVNC admin workflow with user-session deployment notes.
- Create `tests/test_zhihuishu_login_sessions.py`: token, TTL, command, and cleanup tests.
- Modify `tests/test_zhihuishu_api.py`: login-session API contract tests.

---

### Task 1: Login Session Store and Docker Command

**Files:**
- Create: `zhihuishu_login_sessions.py`
- Test: `tests/test_zhihuishu_login_sessions.py`

- [ ] **Step 1: Write failing tests**

Cover:

```python
def test_create_session_records_token_and_user(tmp_path, monkeypatch):
    import zhihuishu_login_sessions as sessions
    monkeypatch.setattr(sessions, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sessions, "_run_docker", lambda command: None)
    monkeypatch.setattr(sessions, "_find_free_port", lambda: 6107)
    session = sessions.create_session("alice", now=1000.0)
    assert session["username"] == "alice"
    assert session["port"] == 6107
    assert session["expires_at"] == 1600.0
    assert sessions.validate_session(session["token"], 6107, now=1001.0)
```

- [ ] **Step 2: Implement minimal module**

Implement `create_session`, `load_session`, `validate_session`, `stop_session`, and `build_docker_command`.

- [ ] **Step 3: Verify tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_zhihuishu_login_sessions.py -v`

---

### Task 2: Flask Routes

**Files:**
- Modify: `app.py`
- Test: `tests/test_zhihuishu_api.py`

- [ ] **Step 1: Write failing API tests**

Cover:

```python
def test_create_login_session_returns_user_url(client_with_user, monkeypatch):
    monkeypatch.setattr(dashboard_app.zhihuishu_login_sessions, "create_session", lambda username: {"token": "tok", "port": 6107, "url": "/zhihuishu/session/tok/"})
    resp = client_with_user.post("/api/zhihuishu/login-session")
    assert resp.status_code == 200
    assert resp.get_json()["url"] == "/zhihuishu/session/tok/"

def test_vnc_auth_rejects_invalid_token(client_with_user):
    resp = client_with_user.get("/api/zhihuishu/login-session-auth?token=bad&port=6107")
    assert resp.status_code == 401
```

- [ ] **Step 2: Add routes**

Add:

- `POST /api/zhihuishu/login-session`
- `GET /zhihuishu/session/<token>/`
- `GET /api/zhihuishu/login-session-auth`
- `POST /api/zhihuishu/login-session/<token>/complete`
- `DELETE /api/zhihuishu/login-session/<token>`

- [ ] **Step 3: Verify API tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_zhihuishu_api.py -v`

---

### Task 3: User Login Page

**Files:**
- Modify: `templates/login_zhihuishu.html`
- Modify: `static/style.css`

- [ ] **Step 1: Replace admin instructions**

Show session status, a primary "打开智慧树登录窗口" button, "我已完成登录" button, and error/status text. Do not mention SSH, noVNC, terminal commands, or server ports.

- [ ] **Step 2: Add JavaScript**

Call `POST /api/zhihuishu/login-session`, open returned `url`, then call `POST /api/zhihuishu/login-session/<token>/complete` when the user confirms.

- [ ] **Step 3: Verify script syntax**

Extract script and run `node --check`.

---

### Task 4: Deployment Artifacts

**Files:**
- Create: `deploy/zhihuishu-login-browser.Dockerfile`
- Create: `deploy/zhihuishu-login-browser-entrypoint.sh`
- Modify: `deploy/canvas-dashboard.nginx`
- Modify: `deploy/zhihuishu-login-tunnel.md`

- [ ] **Step 1: Add container image**

Build an image that runs Xvfb, x11vnc, noVNC, and Chromium with `/profile` as `--user-data-dir`.

- [ ] **Step 2: Add nginx token-gated proxy**

Use `auth_request` against Flask before proxying `/zhs-vnc/<port>/<token>/...` to `127.0.0.1:<port>`.

- [ ] **Step 3: Update docs**

Document Docker build, nginx reload, user flow, and admin-only diagnostics.

---

### Task 5: Verification

**Files:**
- No new files unless issues are found.

- [ ] **Step 1: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests -v`

- [ ] **Step 2: Compile Python**

Run: `.venv\Scripts\python.exe -m py_compile app.py auth.py user_paths.py zhihuishu_store.py zhihuishu_browser.py zhihuishu_worker.py zhihuishu_login_sessions.py`

- [ ] **Step 3: API smoke**

Use Flask test client to confirm login-session create requires auth, returns a tokenized URL for authenticated users, and auth-request rejects bad tokens.

- [ ] **Step 4: Manual Ubuntu verification**

Build the Docker image, deploy nginx, start a login session from a normal web account, complete Zhihuishu login in the embedded browser, and confirm the worker later reads the profile/cache.
