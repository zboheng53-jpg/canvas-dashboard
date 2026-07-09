# Platform State and Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce backend duplication for platform item state and todo responses without changing route behavior.

**Architecture:** Add a small `platform_state.py` helper for `hidden`/`highlighted`/`deleted` state operations and platform todo response normalization. Add `settings.py` for values currently hardcoded in route/runtime modules. Keep route paths and JSON fields stable.

**Tech Stack:** Flask, Python stdlib, pytest/unittest, existing JSON storage helpers.

---

### Task 1: Shared Platform State

**Files:**
- Create: `platform_state.py`
- Modify: `canvas_auth.py`
- Modify: `haoke_client.py`
- Modify: `zhixuemeng_client.py`
- Modify: `zhihuishu_store.py`
- Test: `tests/test_platform_state.py`

- [ ] **Step 1: Write tests for int and string ID state behavior**

Add tests that create temporary state files, update `hide`/`highlight`/`delete`/`undelete`, and assert int IDs stay ints while string IDs stay strings.

- [ ] **Step 2: Run tests to verify the helper does not exist yet**

Run: `python -m pytest tests/test_platform_state.py -q`

Expected: import failure for `platform_state`.

- [ ] **Step 3: Implement shared state helpers**

Create `PlatformStateStore` with `load`, `save`, and `update`; support `id_type=int` and `id_type=str`; normalize all three state keys; delete removes the ID from hidden/highlighted.

- [ ] **Step 4: Wire existing platform modules to the helper**

Replace duplicated state code in `canvas_auth.py`, `haoke_client.py`, `zhixuemeng_client.py`, and `zhihuishu_store.py` with module-local stores using the same file names and ID conversion strategies.

- [ ] **Step 5: Run focused state tests**

Run: `python -m pytest tests/test_platform_state.py tests/test_zhihuishu_store.py tests/test_zhihuishu_api.py -q`

Expected: all selected tests pass.

### Task 2: Shared Todo Response Shape

**Files:**
- Modify: `platform_state.py`
- Modify: `app.py`
- Test: `tests/test_platform_state.py`

- [ ] **Step 1: Add tests for todo response normalization**

Cover `data` source keys, `items` source keys, deleted filtering, state fields, and expired hidden auto-delete.

- [ ] **Step 2: Run tests before implementation**

Run: `python -m pytest tests/test_platform_state.py -q`

Expected: new helper tests fail.

- [ ] **Step 3: Implement `build_platform_todos_response`**

Move the common route logic into a helper that accepts `result`, `state`, `save_state`, `now`, and `items_key`; returns a JSON-ready dict with `ok/data/hidden/highlighted/deleted` plus existing extra fields.

- [ ] **Step 4: Replace duplicated route code**

Use the helper in `/api/canvas/todos`, `/api/haoke/todos`, `/api/zhixuemeng/todos`, and `/api/zhihuishu/todos` while preserving existing extra fields like `cached`, `need_setup`, `stale`, `fetched_at`, and `status`.

- [ ] **Step 5: Run focused route tests**

Run: `python -m pytest tests/test_platform_state.py tests/test_zhihuishu_api.py -q`

Expected: all selected tests pass.

### Task 3: Central Settings

**Files:**
- Create: `settings.py`
- Modify: `app.py`
- Modify: `serve.py`
- Modify: `haoke_client.py`
- Modify: `zhixuemeng_client.py`
- Modify: `zhihuishu_login_sessions.py`
- Modify: `zhihuishu_worker.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Add tests for environment overrides**

Assert integer, float, string, and boolean environment values override defaults, and invalid numeric overrides fall back to defaults.

- [ ] **Step 2: Implement settings helpers and constants**

Create `env_str`, `env_int`, `env_float`, and `env_bool`; define app host/port, CDP proxy URL, cache TTLs, platform URLs, tenant ID, Docker image, port range, and worker intervals.

- [ ] **Step 3: Replace hardcoded values without changing defaults**

Import settings constants into the touched modules and keep existing behavior when no environment variables are set.

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest -q`

Expected: all tests pass.

### Deferred Follow-Ups

- Blueprint split: split `app.py` into route modules after backend helpers are stable.
- Frontend module split: extract `templates/index.html` JavaScript into static files after route JSON behavior is covered.
- DOM builder/event delegation: migrate the unified list rendering in a separate frontend-only patch with browser screenshot checks.
