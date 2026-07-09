# Haoke Cache-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small cache-first 好课 API path that can serve as the reference pattern for later platform backgrounding.

**Architecture:** Keep the cache file format unchanged and expose small helpers from `haoke_client.py` for cache metadata and refresh scheduling. `app.py` decides whether to serve cache, start refresh, or fall back to the current synchronous fetch path.

**Tech Stack:** Flask, Python threading, existing JSON storage helpers, pytest.

---

### Task 1: Cache Metadata Helpers

**Files:**
- Modify: `haoke_client.py`
- Test: `tests/test_haoke_client.py`

- [ ] Write failing tests for `get_cached_todos()` returning `fetched_at` and `stale`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_haoke_client.py -q` and confirm the new tests fail because the helper is missing.
- [ ] Implement `HAOKE_CACHE_TTL_SECONDS`, `_cache_file()`, and `get_cached_todos()`.
- [ ] Re-run the targeted test and confirm it passes.

### Task 2: Background Refresh Guard

**Files:**
- Modify: `haoke_client.py`
- Test: `tests/test_haoke_client.py`

- [ ] Write a failing test showing `start_background_refresh()` starts once per user while a refresh is active.
- [ ] Run the targeted Haoke client test and confirm the new test fails.
- [ ] Implement a per-user in-memory refresh set guarded by a lock.
- [ ] Re-run the targeted test and confirm it passes.

### Task 3: Flask API Cache-First Path And Error Codes

**Files:**
- Modify: `app.py`
- Test: `tests/test_haoke_api.py`

- [ ] Write failing API tests for cache-first response, stale refresh scheduling, synchronous first load, and Haoke error code fields.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_haoke_api.py -q` and confirm the tests fail because the route still fetches synchronously.
- [ ] Add a small `api_error()` helper and use it on touched Haoke paths.
- [ ] Import and use `get_cached_todos()` and `start_background_refresh()` in `/api/haoke/todos`.
- [ ] Re-run targeted API tests and confirm they pass.

### Task 4: Verification

**Files:**
- Existing tests only.

- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_haoke_client.py tests\test_haoke_api.py -q`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest -q`.
- [ ] Report exact results and any skipped deployment or git limitations.
