# JSON Corruption Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve damaged runtime JSON files and stop requests from overwriting them with empty defaults.

**Architecture:** `storage.read_json_file()` becomes fail-closed for malformed or non-UTF-8 JSON: it leaves the original in place, saves a timestamped forensic copy beside it, and raises `JsonFileCorruptionError`. Flask maps that error to a stable 503 response, so routes neither expose internals nor continue with an empty object that might be written back.

**Tech Stack:** Python 3.13, Flask, pytest, standard-library `json`, `shutil`, and `logging`.

---

### Task 1: Preserve and report malformed JSON

**Files:**
- Modify: `storage.py:1-36`
- Modify: `tests/test_p0_safety.py`

- [x] **Step 1: Write failing storage tests**

```python
def test_read_json_file_preserves_corrupt_file_and_raises(tmp_path):
    import storage

    path = tmp_path / "config.json"
    path.write_text('{"broken": ', encoding="utf-8")

    with pytest.raises(storage.JsonFileCorruptionError):
        storage.read_json_file(path, {})

    copies = list(tmp_path.glob("config.json.corrupt-*"))
    assert path.read_text(encoding="utf-8") == '{"broken": '
    assert len(copies) == 1
    assert copies[0].read_text(encoding="utf-8") == '{"broken": '
```

- [x] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_p0_safety.py::test_read_json_file_preserves_corrupt_file_and_raises -q`

Expected: FAIL because `JsonFileCorruptionError` does not exist and malformed input is silently replaced by the default.

- [x] **Step 3: Implement the minimal fail-closed read path**

```python
class JsonFileCorruptionError(RuntimeError):
    pass


def read_json_file(path: Path, default):
    path = Path(path)
    if not path.exists():
        return _copy_default(default)
    with _lock_for(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = path.with_name(f"{path.name}.corrupt-{timestamp}")
            shutil.copy2(path, backup)
            raise JsonFileCorruptionError(path) from error
```

- [x] **Step 4: Run the storage test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_p0_safety.py::test_read_json_file_preserves_corrupt_file_and_raises -q`

Expected: PASS.

### Task 2: Return a stable web error without modifying the damaged file

**Files:**
- Modify: `app.py:18, 221-240`
- Modify: `tests/test_p0_safety.py`

- [x] **Step 1: Write the failing route test**

```python
def test_corrupt_custom_todos_returns_service_unavailable_without_overwrite(client_with_user, tmp_path):
    path = tmp_path / "users" / "alice" / "custom_todos.json"
    path.write_text('[{"id": ', encoding="utf-8")

    response = client_with_user.get("/api/custom/todos")

    assert response.status_code == 503
    assert response.get_json() == {"ok": False, "error": "stored data is temporarily unavailable"}
    assert path.read_text(encoding="utf-8") == '[{"id": '
```

- [x] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_p0_safety.py::test_corrupt_custom_todos_returns_service_unavailable_without_overwrite -q`

Expected: FAIL because Flask returns an unhandled error or the data read falls back to an empty list.

- [x] **Step 3: Implement the Flask error handler**

```python
@app.errorhandler(JsonFileCorruptionError)
def handle_json_file_corruption(error):
    logger.error("Stored JSON is corrupt: %s", error)
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "stored data is temporarily unavailable"}), 503
    return "Stored data is temporarily unavailable.", 503
```

- [x] **Step 4: Run the route test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_p0_safety.py::test_corrupt_custom_todos_returns_service_unavailable_without_overwrite -q`

Expected: PASS.

### Task 3: Verify the safety boundary

**Files:**
- Verify: `storage.py`, `app.py`, `tests/test_p0_safety.py`

- [x] **Step 1: Run focused storage and route tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_p0_safety.py tests\test_concurrent_writes.py -q`

Expected: PASS.

- [x] **Step 2: Run project verification**

Run: `.\scripts\test.ps1; .\.venv\Scripts\python.exe -m compileall -q .; git diff --check`

Expected: all tests pass, compilation succeeds, and `git diff --check` has no output.

- [ ] **Step 3: Commit the focused batch**

```powershell
git add storage.py app.py tests/test_p0_safety.py docs/superpowers/plans/2026-07-10-json-corruption-protection.md
git commit -m "fix: preserve corrupt runtime json files"
```
