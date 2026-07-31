# Security and Release Foundation Implementation Plan

> Historical planning record. The domain, ICP filing, HTTPS, secure cookies, pinned SSH host key, encrypted backup drill, and rollback-capable release workflow are now active. Use `docs/operations.md`, `docs/backup-and-restore.md`, and current tests for the production contract.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current HTTP deployment safer to operate and ensure every deployment executes the real regression suite before domain-backed HTTPS is enabled.

**Architecture:** Keep Flask bound to loopback and make Nginx the sole source of the client IP forwarded to Flask. Validate user-supplied Canvas feed URLs before persistence, and make deployment verification call the repository test script rather than a separate, partial test runner. `canvas-dashboard.xyz` is awaiting domain review; HTTPS and secure cookies remain outside this plan until domain review and ICP filing are complete.

**Tech Stack:** Flask, pytest, PowerShell, Nginx.

---

### Task 1: Protect rate-limit identity at the proxy boundary

**Files:**
- Modify: `tests/test_security_auth.py`
- Modify: `tests/test_zhihuishu_login_sessions.py`
- Modify: `app.py`
- Modify: `deploy/canvas-dashboard.nginx`

- [x] Add a failing Flask test that sends both `X-Forwarded-For: forged` and `X-Real-IP: 203.0.113.9`, and asserts `_request_ip()` returns `203.0.113.9`.
- [x] Run `python -m pytest tests/test_security_auth.py -q` and confirm the new test fails because `_request_ip()` currently trusts `X-Forwarded-For`.
- [x] Change `_request_ip()` to use the Nginx-overwritten `X-Real-IP` header and fall back only to `request.remote_addr`.
- [x] Add a failing Nginx text test that requires `proxy_set_header X-Forwarded-For $remote_addr;` for both proxy locations and rejects `$proxy_add_x_forwarded_for`.
- [x] Update both Nginx proxy locations to overwrite `X-Forwarded-For` with `$remote_addr`.
- [ ] Run the two targeted tests and then `scripts/test.ps1`; commit only the changed tests, Flask file, and Nginx file.

### Task 2: Reject unsafe Canvas feed URLs

**Files:**
- Modify: `tests/test_canvas_auth.py`
- Modify: `canvas_auth.py`
- Modify: `app.py`

- [x] Add failing tests for rejecting non-HTTPS URLs, URLs without a hostname, and hostnames resolving to loopback/private/link-local addresses.
- [x] Run `python -m pytest tests/test_canvas_auth.py -q` and confirm the validation tests fail because `save_feed_url()` accepts every string.
- [x] Add one focused URL validator in `canvas_auth.py`; parse with `urllib.parse.urlsplit`, require `https`, require no username/password, resolve the hostname with `socket.getaddrinfo`, and reject every address for which `ipaddress.ip_address(address).is_global` is false.
- [x] Make `save_feed_url()` return `(False, error)` for invalid URLs and `(True, None)` only after persisting a valid URL. Make `/api/config` return the validator error as a 400 response.
- [ ] Re-run the targeted tests and full suite; commit the Canvas validation change separately.

### Task 3: Make deployment run the real test gate

**Files:**
- Modify: `tests/test_scripts.py`
- Modify: `.agents/skills/deploy-canvas-dashboard/scripts/deploy.ps1`

- [x] Add failing tests that require the deploy script to invoke `scripts/test.ps1`, `python -m compileall`, and prohibit `unittest discover`.
- [x] Run `python -m pytest tests/test_scripts.py -q` and confirm the new deploy assertions fail.
- [x] Replace the partial unittest command with the repository test script and add a compile-only check before archive creation; preserve the existing abort-on-nonzero behavior.
- [ ] Do not replace `StrictHostKeyChecking=no` until the production host fingerprint is independently verified and pinned; record this as the next deployment-operator task.
- [ ] Run targeted tests and `scripts/test.ps1`; commit the deployment gate change separately.

### Task 4: Verify the iteration without changing production transport

**Files:**
- Modify: `README.md`

- [x] Add a concise deployment prerequisite stating that production HTTPS and `CANVAS_DASHBOARD_COOKIE_SECURE=1` wait for a validated domain or a tested IP-certificate renewal process.
- [x] Run `scripts/test.ps1` and `python -m compileall -q .`.
- [ ] Before any deployment, create and verify an out-of-server `data/` backup, inspect `nginx -t`, and manually confirm `/healthz` through the existing endpoint.
- [ ] Commit the documentation-only change separately.
