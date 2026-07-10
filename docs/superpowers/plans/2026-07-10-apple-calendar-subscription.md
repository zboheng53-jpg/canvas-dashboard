# Apple Calendar Subscription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a private, revocable ICS calendar for each account without publishing any subscription URL until HTTPS is live.

**Architecture:** A new `apple_calendar.py` owns token persistence and RFC 5545 serialization. `app.py` supplies only already-normalized unfinished tasks and exposes authenticated token-management routes plus one token-only ICS route. The public ICS route will exist locally and in tests, but production deployment remains blocked on `canvas-dashboard.xyz`, ICP, and HTTPS.

**Tech Stack:** Flask, Python standard library (`secrets`, `hashlib`, `datetime`), pytest.

---

### Task 1: Isolated token lifecycle

**Files:**
- Create: `apple_calendar.py`
- Create: `tests/test_apple_calendar.py`

- [x] Write failing tests for generating a URL-safe 32-byte token per account, persisting only its SHA-256 hash, and revoking it without affecting another account.
- [x] Run the focused test and confirm it fails because the module does not exist.
- [x] Implement `create_token(username)`, `revoke_token(username)`, and `username_for_token(token)` using `data/users/<username>/apple_calendar.json` and `secrets.token_urlsafe(32)`.
- [x] Re-run the focused test and confirm it passes.

### Task 2: Deterministic private ICS output

**Files:**
- Modify: `apple_calendar.py`
- Modify: `tests/test_apple_calendar.py`

- [x] Write failing tests that create an item with a due timestamp and assert `BEGIN:VCALENDAR`, a stable UID derived from source and ID, escaped summary text, Asia/Shanghai date-time output, and no completed or undated items.
- [x] Run the focused test and confirm it fails because no serializer exists.
- [x] Implement `build_calendar(username, items, now)` with CRLF-delimited RFC 5545 text, `VEVENT` entries only for active items with valid `due_ts`, and a stable source-and-ID UID.
- [x] Re-run the focused test and confirm it passes.

### Task 3: App routes and task aggregation

**Files:**
- Modify: `app.py`
- Modify: `tests/test_apple_calendar_api.py`

- [x] Write failing tests for authenticated token creation/revocation and unauthenticated ICS retrieval by a valid token; assert an invalid or revoked token returns 404.
- [x] Run the focused tests and confirm they fail because the routes do not exist.
- [x] Add `POST /api/apple-calendar/subscription`, `DELETE /api/apple-calendar/subscription`, and `GET /calendar/<token>.ics`; aggregate only unfinished, non-hidden, non-deleted, dated tasks from the existing platform data shapes.
- [x] Re-run the focused tests and full suite; do not deploy or expose the URL in production.

### Task 4: Verification and handoff

**Files:**
- Modify: `README.md`
- Verify: `tests/test_apple_calendar.py`, `tests/test_apple_calendar_api.py`

- [x] Document that subscription endpoints are implemented locally but production activation waits for domain review, ICP filing, HTTPS, and an iPhone subscription test.
- [x] Run `.\scripts\test.ps1`, `.\.venv\Scripts\python.exe -m compileall -q .`, and `git diff --check`.
- [ ] Commit only after the existing uncommitted security/data batch has been reviewed as one coherent change set.

### Deferred before production activation

- [ ] Add the subscription event ledger, `SEQUENCE`, cancellation window, and conditional HTTP cache validators required for reliable update/removal behavior in Apple Calendar clients.
- [ ] Add the settings-card UI only after the HTTPS endpoint and real-iPhone subscription flow are verified.
- [ ] Real-iPhone test is paused: the local Cloudflare Quick Tunnel returns Error 1033 on the current network. Resume only with a compatible network or production HTTPS; do not retry the current tunnel path.
