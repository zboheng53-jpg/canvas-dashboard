# P1 Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 琛ラ綈 Canvas銆佸ソ璇俱€佹櫤瀛︾洘銆佽璇佽竟鐣屻€佸啓鍏ヤ竴鑷存€у拰鍓嶇鍏抽敭娴佺▼鐨?P1 鍥炲綊娴嬭瘯銆?
**Architecture:** 鍙柊澧炴祴璇曞拰娴嬭瘯杈呭姪浠ｇ爜锛屼紭鍏堢敤 monkeypatch/涓存椂鐩綍闅旂鐪熷疄 `data/`锛屼笉璁块棶鐪熷疄骞冲彴缃戠粶锛屼笉鏀圭敓浜ц涓恒€傚悗绔鎴风娴嬭瘯鐩存帴瑕嗙洊绾嚱鏁板拰缃戠粶杈圭晫锛汚PI 娴嬭瘯浣跨敤 Flask test client锛涘墠绔祴璇曚娇鐢?Playwright 鎵撶湡瀹?Flask 涓存椂鏈嶅姟骞舵嫤鎴笉鐩稿叧骞冲彴璇锋眰銆?
**Tech Stack:** Python 3.11 venv, pytest, unittest 鍏煎鐜版湁娴嬭瘯, Flask test client, Playwright Python sync API.

---

## 鍏抽敭鍋囪

- 褰撳墠浠撳簱鐩綍涓嶆槸 git repository锛屾棤娉曟寜浠诲姟 commit锛涙墽琛屾椂鐢ㄥ皬琛ヤ竵鍜屽垎娈?pytest 浣滀负鍥炴粴杈圭晫銆?- 鐢ㄦ埛瑕佹眰鈥滃厛缁欐柟妗堝啀鎵ц鈥濓紝鍥犳鏈枃浠跺彧瑙勫垝锛屼笉鏂板娴嬭瘯浠ｇ爜銆?- `python -m pytest --collect-only -q` 浼氬洜绯荤粺 Python 缂哄皯 Flask 澶辫触锛涙墽琛屼笌楠岃瘉閮戒娇鐢?`.\.venv\Scripts\python.exe`銆?- 鎵€鏈夋柊澧炴祴璇曞繀椤婚伩鍏嶇湡瀹炶处鍙枫€佺湡瀹?`data/`銆佺湡瀹?Canvas/濂借/鏅哄鐩熺綉缁滆姹傘€?- Playwright 宸插湪 `requirements.txt` 涓瓨鍦紱鑻ユ祻瑙堝櫒浜岃繘鍒剁己澶憋紝鎵ц闃舵鍏堣繍琛?`.\.venv\Scripts\python.exe -m playwright install chromium`銆?
## 鏂囦欢缁撴瀯

- Create: `tests/test_canvas_auth.py`
  - 瑕嗙洊 `canvas_auth._parse_ical()`銆乣_extract_stable_id()`銆乣fetch_canvas_planner()` 缂撳瓨 fallback銆?- Create: `tests/test_haoke_client.py`
  - 瑕嗙洊 `haoke_client._parse_date()`銆乣_normalize_task()`銆乣_get_token()` 鐢ㄦ埛鍒嗘《缂撳瓨銆乣fetch_haoke_todos()` fallback cache銆?- Create: `tests/test_zhixuemeng_client.py`
  - 瑕嗙洊 JWT 鐢ㄦ埛鍚嶈В鏋愩€佽绋嬪幓閲嶆帓搴忋€佽绋嬫壂鎻忕紦瀛?filter銆乴ogout 娓呯悊 token 涓庨€夎銆?- Modify: `tests/test_security_auth.py`
  - 缁х画鏀捐璇佽竟鐣屾祴璇曪紝澶嶇敤宸叉湁 CSRF helper 鍜?client fixture 椋庢牸銆?- Create: `tests/test_concurrent_writes.py`
  - 瑕嗙洊 custom todo API 杩炵画/骞跺彂鍐欏叆銆乣PlatformStateStore` 杩炵画/骞跺彂 state 鏇存柊銆?- Create: `tests/test_frontend_playwright.py`
  - 娴忚鍣ㄧ骇鍥炲綊锛氭柊澧炰换鍔?鏍囩銆佸瓙浠诲姟灞曞紑涓庢柊澧炪€佸钩鍙扮姸鎬佸崱鐗囥€OCR 下线回归銆?- Optional Create: `tests/frontend_server.py`
  - 浠呭綋 `test_frontend_playwright.py` 鍐呴儴 fixture 杩囬暱鏃舵媶鍑?Flask 涓存椂鏈嶅姟 helper锛涗紭鍏堜笉鎷嗐€?
## Task 0: Baseline And Environment

**Files:** none

- [ ] **Step 1: Confirm test collection uses venv**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest --collect-only -q
```

Expected: 62 tests collected.

- [ ] **Step 2: Confirm current backend suite baseline**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: existing tests pass before adding P1 tests. If not, stop and report the existing failure separately.

## Task 1: Canvas Client Tests

**Files:**
- Create: `tests/test_canvas_auth.py`
- Read-only target: `canvas_auth.py`

- [ ] **Step 1: Add iCal parsing tests**

Add tests equivalent to:

```python
def test_parse_ical_extracts_canvas_assignment_id_course_and_cst_due():
    raw = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:uid-123@example
SUMMARY:Control homework
DESCRIPTION:Course: Automation
URL:https://canvas.example/courses/1/assignments/123#assignment_123
DTSTART:20990102T070000Z
END:VEVENT
END:VCALENDAR
"""
    items = canvas_auth._parse_ical(raw)
    assert items == [{
        "id": 123,
        "title": "Control homework",
        "course": "Automation",
        "due_str": "01-02 15:00",
        "due_ts": "2099-01-02T15:00:00+08:00",
        "type": "浣滀笟",
        "type_raw": "assignment",
        "url": "https://canvas.example/courses/1/assignments/123#assignment_123",
    }]
```

Also add:

```python
def test_parse_ical_skips_missing_due_and_expired_events():
    raw = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:no-due
SUMMARY:No due
END:VEVENT
BEGIN:VEVENT
UID:old
SUMMARY:Old assignment
DTSTART:20000102
END:VEVENT
END:VCALENDAR
"""
    assert canvas_auth._parse_ical(raw) == []
```

- [ ] **Step 2: Add stable-id fallback test**

```python
def test_extract_stable_id_uses_fragment_then_hash_fallback():
    assert canvas_auth._extract_stable_id("https://x/#calendar_event_456", "uid") == 456
    hashed = canvas_auth._extract_stable_id("https://x/no-fragment", "uid")
    assert isinstance(hashed, int)
    assert 0 <= hashed < 1000000
```

- [ ] **Step 3: Add network success/cache fallback test**

Use `tmp_path`, monkeypatch `canvas_auth.user_dir`, save a config with `calendar_feed_url`, monkeypatch `canvas_auth.requests.get` to first return `status_code=200` with iCal text, then raise `requests.RequestException`.

Expected assertions:

- first call returns `{"ok": True, "cached": False}` and writes `canvas_cache.json`;
- second call returns `{"ok": True, "cached": True}` with the same data;
- no real HTTP call is made.

- [ ] **Step 4: Verify Canvas tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_canvas_auth.py -q
```

Expected: all new Canvas tests pass.

## Task 2: Haoke Client Tests

**Files:**
- Create: `tests/test_haoke_client.py`
- Read-only target: `haoke_client.py`

- [ ] **Step 1: Add date parsing tests**

Cover all supported forms:

```python
def test_parse_date_accepts_numeric_iso_z_and_common_formats():
    assert haoke_client._parse_date(4102444800000).isoformat() == "2100-01-01T08:00:00+08:00"
    assert haoke_client._parse_date(4102444800).isoformat() == "2100-01-01T08:00:00+08:00"
    assert haoke_client._parse_date("2100-01-01T00:00:00Z").isoformat() == "2100-01-01T08:00:00+08:00"
    assert haoke_client._parse_date("2100-01-01 09:30:00").isoformat() == "2100-01-01T09:30:00+08:00"
    assert haoke_client._parse_date("") is None
    assert haoke_client._parse_date("bad") is None
```

- [ ] **Step 2: Add task normalization tests**

Assert a future `endTime` becomes a unified item with URL, type map, `due_str`, and course; assert expired and year `9999` sentinel return `None`.

Minimum cases:

- `{"taskId": 7, "taskName": "Quiz", "taskType": 40, "endTime": "2100-01-01 09:30:00", "instanceId": "inst-1"}` returns id `7`, type from `TASK_TYPE_MAP[40]`, URL containing `taskId=7`.
- `{"taskId": 8, "endTime": "2000-01-01 00:00:00"}` returns `None`.
- `{"taskId": 9, "endTime": "9999-12-31 00:00:00"}` returns `None`.

- [ ] **Step 3: Add token cache bucket test**

Monkeypatch `_get_credentials` and `_login`.

Expected sequence:

- first `_get_token("alice")` logs in and caches `token-alice`;
- first `_get_token("bob")` logs in and caches `token-bob`;
- second `_get_token("alice")` reuses cache and does not call `_login` again;
- `save_credentials("alice", ...)` invalidates only `alice` cache, not `bob`.

- [ ] **Step 4: Add fetch fallback cache test**

Create `haoke_cache.json`, monkeypatch:

- `has_credentials(username)` -> `True`;
- `_get_token(username)` -> `"token"`;
- `_fetch_all_todos(token)` -> raises `RuntimeError("network down")`.

Expected:

```python
result["ok"] is True
result["cached"] is True
result["data"] == cached_items
```

- [ ] **Step 5: Verify Haoke tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_haoke_client.py -q
```

Expected: all new Haoke tests pass.

## Task 3: Zhixuemeng Client Tests

**Files:**
- Create: `tests/test_zhixuemeng_client.py`
- Read-only target: `zhixuemeng_client.py`

- [ ] **Step 1: Add JWT helper**

In the test file only:

```python
def fake_jwt(payload):
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{body}.sig"
```

- [ ] **Step 2: Add course fetch test**

Monkeypatch `_get_token` to return `fake_jwt({"username": "zxm-alice"})` and `requests.get` to assert params include `username="zxm-alice"`.

Response records:

```python
[
    {"courseCode": "B002", "courseName": "B", "className": "2", "semester_dictText": "2026"},
    {"courseCode": "A001", "courseName": "A", "className": "1", "semester_dictText": "2026"},
    {"courseCode": "A001", "courseName": "A duplicate", "className": "1", "semester_dictText": "2026"},
]
```

Expected: courses are de-duplicated and sorted as `A001`, `B002`.

- [ ] **Step 3: Add assignment scan/cache/filter test**

Monkeypatch:

- `user_dir` to `tmp_path / username`;
- `_get_token` to `"token"`;
- `_get_zxm_username` to `"zxm-alice"`;
- `requests.get` for `/edu/eduCourseUser/list` to return `A001`, `B002`;
- `_scan_course` to return one item per course;
- `time_module.time` to fixed `1000`.

Expected:

- first call scans both courses, writes `zhixuemeng_cache.json`, returns `cached=False`;
- second call with same user/time uses cache, returns `cached=True`, does not call `_scan_course`;
- call with `course_code="A001"` returns only items whose URL ends with `courseCode=A001`.

- [ ] **Step 4: Add logout token cleanup test**

Set config:

```json
{
  "zhixuemeng_token_encrypted": "cipher",
  "zhixuemeng_selected_course": "A001",
  "calendar_feed_url": "keep"
}
```

Set `_token_cache["alice"]`.

Expected after `logout("alice")`:

- `_token_cache` has no `alice`;
- config no longer has `zhixuemeng_token_encrypted`;
- config no longer has `zhixuemeng_selected_course`;
- unrelated `calendar_feed_url` remains.

- [ ] **Step 5: Verify Zhixuemeng tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_zhixuemeng_client.py -q
```

Expected: all new Zhixuemeng tests pass.

## Task 4: Authentication Boundary Tests

**Files:**
- Modify: `tests/test_security_auth.py`
- Read-only targets: `app.py`, `auth.py`

- [ ] **Step 1: Add isolated auth storage fixture**

Add a fixture that monkeypatches:

- `auth.DATA_DIR`;
- `auth.USERS_FILE`;
- `auth.SECRET_KEY_FILE`;
- `user_paths.DATA_DIR`;
- app testing config and rate-limit buckets.

This keeps registration tests away from real `data/users.json`.

- [ ] **Step 2: Add non-JSON auth request tests**

Add:

```python
def test_auth_register_rejects_non_json_request(anonymous_client):
    headers = _set_csrf(anonymous_client)
    resp = anonymous_client.post("/api/auth/register", data="x", content_type="text/plain", headers=headers)
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False

def test_auth_login_rejects_json_null(anonymous_client):
    headers = _set_csrf(anonymous_client)
    resp = anonymous_client.post("/api/auth/login", data="null", content_type="application/json", headers=headers)
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
```

- [ ] **Step 3: Add weak password and duplicate registration tests**

Use real `auth.register` against temp files through `/api/auth/register`.

Expected:

- password `"12345"` returns 400 and does not create user;
- first registration of `"alice"` succeeds;
- second registration of `"alice"` returns 400.

- [ ] **Step 4: Add unauthenticated boundary tests**

Expected:

- `GET /api/clock` without session returns `401` JSON `{ok: False, ...}`;
- `GET /` without session redirects `302` to `/login`.

- [ ] **Step 5: Add logout and session cookie behavior tests**

Expected:

- `POST /api/auth/logout` with valid CSRF returns `{ok: True}`;
- after logout, `GET /api/clock` returns 401;
- successful login/register response emits `Set-Cookie` containing a persistent `Expires=` attribute because `session.permanent = True`.

- [ ] **Step 6: Verify auth tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_security_auth.py -q
```

Expected: all security/auth tests pass.

## Task 5: Consecutive And Concurrent Write Tests

**Files:**
- Create: `tests/test_concurrent_writes.py`
- Read-only targets: `app.py`, `platform_state.py`, `storage.py`

- [ ] **Step 1: Add custom todo consecutive field-preservation test**

Use Flask test client with temp user dir and CSRF.

Flow:

1. POST `/api/custom/todos` with text, due date, labels.
2. PUT `/api/custom/todos/1` with `{"subtasks": [{"id": 1, "text": "read", "done": false}]}`.
3. PUT `/api/custom/todos/1` with `{"highlighted": true}`.
4. Read `custom_todos.json`.

Expected: one todo still has original text, due date, labels, subtasks, and `highlighted=True`.

- [ ] **Step 2: Add custom todo real concurrent POST test**

Use `ThreadPoolExecutor(max_workers=8)`. Each worker creates its own `app.test_client()`, sets session username and CSRF token, then posts one unique todo.

Expected file state:

- exactly 20 todos;
- ids are unique;
- all 20 submitted text values are present.

- [ ] **Step 3: Add platform state consecutive update test**

Use `PlatformStateStore(lambda username: tmp_path / f"{username}.json", int)`.

Flow:

```python
store.update("alice", "hide", 1)
store.update("alice", "highlight", 2)
store.update("alice", "hide", 3)
```

Expected: hidden `[1, 3]`, highlighted `[2]`, deleted `[]`.

- [ ] **Step 4: Add platform state real concurrent update test**

Use `ThreadPoolExecutor(max_workers=8)` to update disjoint ids:

- hide ids `1..20`;
- highlight ids `101..120`.

Expected after load:

- hidden contains all `1..20`;
- highlighted contains all `101..120`;
- deleted remains empty.

- [ ] **Step 5: Verify write tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_concurrent_writes.py -q
```

Expected: all write consistency tests pass.

## Task 6: Frontend Playwright Regression Tests

**Files:**
- Create: `tests/test_frontend_playwright.py`
- Read-only targets: `templates/index.html`, `static/csrf.js`, `app.py`

- [ ] **Step 1: Add Flask server fixture**

Fixture behavior:

- monkeypatch `dashboard_app.DATA_DIR`, ``user_paths.DATA_DIR`, `auth.DATA_DIR`, `auth.USERS_FILE`;
- monkeypatch network-heavy app functions:
  - `fetch_canvas_planner` returns one Canvas item and platform state arrays;
  - `fetch_haoke_todos` returns one Haoke item and platform state arrays;
  - `fetch_zxm_assignments` returns one Zhixuemeng item and platform state arrays;
  - `zhihuishu_store.load_cache` or route dependencies return setup/no items consistently;
  - `requests.get` for clock/weather/term only if needed, otherwise allow local endpoints that do not hit network through monkeypatching app route helpers.
- start `dashboard_app.app.run(port=<free_port>, debug=False, use_reloader=False)` in a daemon thread.

- [ ] **Step 2: Add browser registration helper**

In Playwright:

1. `page.goto(f"{base_url}/register")`.
2. Fill `#register-username` with `alice`.
3. Fill `#register-password` with `password1`.
4. Submit `#register-form`.
5. Wait for URL to become `/`.

Expected: page reaches dashboard and session cookie exists.

- [ ] **Step 3: Add custom todo + labels test**

Flow:

1. Fill `#new-todo-input` with `鎺у埗浣滀笟 #鑷姩鍖?#澶嶄範`.
2. Fill `#new-todo-due` with a future date.
3. Submit form.
4. Wait for `.todo-item` containing `鎺у埗浣滀笟`.

Expected:

- `.item-title` contains `鎺у埗浣滀笟`;
- `.label-badge` texts include `鑷姩鍖朻, `澶嶄範`;
- no literal `#鑷姩鍖朻 remains in the title.

- [ ] **Step 4: Add subtask expand/add test**

Flow after custom todo exists:

1. Click first custom `.subtask-toggle`.
2. Fill `.subtask-add-input` with `鐪嬬 3 绔燻.
3. Press Enter.

Expected:

- `.subtask-panel` is visible;
- `.subtask-text` contains `鐪嬬 3 绔燻;
- after page reload and expand, subtask still appears.

- [ ] **Step 5: Add platform card/status and item state test**

Flow:

1. Click `.login-trigger`.
2. Assert `#login-cards` is visible.
3. Wait for `#card-status-canvas`, `#card-status-haoke`, `#card-status-zhixuemeng` to no longer contain initial checking text.
4. Click a platform flag button in a Canvas or Haoke row.

Expected:

- platform row remains rendered;
- clicked row gets manual flagged class or corresponding button active state after render;
- no uncaught page error is recorded.

- [ ] **Step 6: Add OCR offline regression test**

Flow:

1. Open the dashboard after registration.
2. Assert `.ocr-trigger-arrow-btn` is absent.
3. Assert `#ocr-text-input` is absent.

Expected:

- OCR controls are not rendered on the dashboard;
- custom todo, labels, subtasks, and platform card checks still pass.

- [ ] **Step 7: Verify frontend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_frontend_playwright.py -q
```

Expected: Playwright tests pass locally. If Chromium is missing, install once:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Task 7: Full Verification

**Files:** all touched test files

- [ ] **Step 1: Run targeted backend suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_canvas_auth.py tests/test_haoke_client.py tests/test_zhixuemeng_client.py tests/test_security_auth.py tests/test_concurrent_writes.py -q
```

Expected: all targeted backend tests pass.

- [ ] **Step 2: Run full suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass. Report total count.

- [ ] **Step 3: Report residual risk**

Report:

- whether Playwright ran or was skipped due missing browser/runtime;
- whether any tests required monkeypatching implementation seams;
- that no production data under `data/` was touched.

## Self Review

- Spec coverage:
  - Canvas iCal parsing: Task 1.
  - 濂借鏃ユ湡瑙ｆ瀽/缂撳瓨/token: Task 2.
  - 鏅哄鐩熻绋嬫壂鎻?token/logout: Task 3.
  - 闈?JSON銆佸急瀵嗙爜銆侀噸澶嶆敞鍐屻€佹湭鐧诲綍 API銆乴ogout銆乻ession cookie: Task 4.
  - custom todos 鍜?state 杩炵画/骞跺彂鍐欏叆: Task 5.
  - Playwright 鏂板浠诲姟銆佹爣绛俱€佸瓙浠诲姟銆佸钩鍙板崱鐗囥€OCR 下线回归: Task 6.
- Placeholder scan: no TBD/TODO/later placeholders; each test has concrete flow and assertions.
- Type consistency:
  - Canvas/Haoke state ids are `int`.
  - Zhixuemeng state ids are `str` with `zxm_` item ids where route response expects them.
  - Custom todo ids are `int` and files live under per-user temp directories.

