# Custom Todo Subtasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapsible checklist of subtasks to manually created custom todos in Canvas Dashboard.

**Architecture:** Reuse the existing custom todo JSON storage and API. Add a `subtasks` array to custom todo objects, let the frontend edit the entire array through the existing `PUT /api/custom/todos/<id>` route, and render a compact collapsible panel only for custom items in the unified todo list.

**Tech Stack:** Python Flask, standard-library `unittest`, vanilla JavaScript, CSS, JSON file storage.

---

## Scope Check

The approved spec covers one bounded feature: subtasks for manual custom todos only. It does not require new persistence files, external-platform subtask support, drag sorting, batch creation, or persistent expansion state. This can be implemented as one plan.

## File Structure

- Modify: `app.py`
  - Keep responsibility unchanged: Flask routes and JSON persistence for custom todos.
  - Add `subtasks` compatibility in `_load_todos()`.
  - Add `subtasks: []` when creating a custom todo.
  - Allow `PUT /api/custom/todos/<id>` to replace a custom todo's full `subtasks` array.
- Create: `tests/test_custom_todo_subtasks.py`
  - Standard-library backend regression tests using a temporary `custom_todos.json` file.
  - Covers old-data compatibility, POST default subtasks, and PUT subtask persistence without parent auto-completion.
- Modify: `templates/index.html`
  - Add in-memory `expandedCustomTodoIds` state.
  - Carry `subtasks` into unified custom items.
  - Render a custom-only subtask toggle and collapsible panel.
  - Add subtask add/check/delete/edit/save functions.
- Modify: `static/style.css`
  - Add styles for the wrapper, toggle, panel, subtask rows, done text, and add input.
  - Preserve current external-platform row styling.

This workspace is not a git repository, so the plan uses explicit local checkpoints instead of `git commit` commands.

---

### Task 1: Add backend tests for custom todo subtasks

**Files:**
- Create: `tests/test_custom_todo_subtasks.py`
- Test: `tests/test_custom_todo_subtasks.py`

- [ ] **Step 1: Create the failing backend regression tests**

Create `tests/test_custom_todo_subtasks.py` with exactly this content:

```python
import json
import tempfile
import unittest
from pathlib import Path

import app as dashboard_app


class CustomTodoSubtasksTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.todos_file = Path(self.tmpdir.name) / "custom_todos.json"
        self.todos_file.write_text("[]", encoding="utf-8")
        self.original_todos_file = dashboard_app.TODOS_FILE
        dashboard_app.TODOS_FILE = self.todos_file
        self.client = dashboard_app.app.test_client()

    def tearDown(self):
        dashboard_app.TODOS_FILE = self.original_todos_file
        self.tmpdir.cleanup()

    def read_stored_todos(self):
        return json.loads(self.todos_file.read_text(encoding="utf-8"))

    def test_load_todos_adds_missing_labels_and_subtasks(self):
        self.todos_file.write_text(json.dumps([
            {
                "id": 1,
                "text": "旧待办",
                "done": False,
                "created_at": "2026-06-03T20:00:00+08:00",
                "due_date": None,
                "highlighted": False,
            }
        ], ensure_ascii=False), encoding="utf-8")

        todos = dashboard_app._load_todos()

        self.assertEqual(todos[0]["labels"], [])
        self.assertEqual(todos[0]["subtasks"], [])

    def test_post_custom_todo_creates_empty_subtasks(self):
        resp = self.client.post("/api/custom/todos", json={
            "text": "高数作业",
            "due_date": "2026-06-05",
            "labels": ["数学"],
        })

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["todo"]["subtasks"], [])

        stored = self.read_stored_todos()
        self.assertEqual(stored[0]["subtasks"], [])

    def test_put_custom_todo_updates_subtasks_without_completing_parent(self):
        self.todos_file.write_text(json.dumps([
            {
                "id": 1,
                "text": "高数作业",
                "done": False,
                "created_at": "2026-06-03T20:00:00+08:00",
                "due_date": "2026-06-05",
                "highlighted": False,
                "labels": ["数学"],
                "subtasks": [],
            }
        ], ensure_ascii=False), encoding="utf-8")
        subtasks = [
            {"id": 1, "text": "看第 3 章", "done": True},
            {"id": 2, "text": "写 1-5 题", "done": True},
        ]

        resp = self.client.put("/api/custom/todos/1", json={"subtasks": subtasks})

        self.assertEqual(resp.status_code, 200)
        stored = self.read_stored_todos()
        self.assertEqual(stored[0]["subtasks"], subtasks)
        self.assertFalse(stored[0]["done"])
```

- [ ] **Step 2: Run the tests and verify they fail for the missing feature**

Run:

```bash
python -m unittest discover -s tests -p "test_custom_todo_subtasks.py" -v
```

Expected result before implementation:

```text
test_load_todos_adds_missing_labels_and_subtasks ... FAIL
test_post_custom_todo_creates_empty_subtasks ... ERROR
test_put_custom_todo_updates_subtasks_without_completing_parent ... FAIL
```

The exact traceback lines may differ, but the failures must be caused by missing `subtasks` support.

- [ ] **Step 3: Local checkpoint**

Record this checkpoint in the task runner notes:

```text
Checkpoint: backend subtask tests added and currently fail because app.py does not persist subtasks yet.
```

---

### Task 2: Implement backend subtask persistence

**Files:**
- Modify: `app.py:69-76`
- Modify: `app.py:397-467`
- Test: `tests/test_custom_todo_subtasks.py`

- [ ] **Step 1: Update `_load_todos()` to backfill `subtasks`**

In `app.py`, replace the current `_load_todos()` function with this version:

```python
def _load_todos():
    with open(TODOS_FILE, "r", encoding="utf-8") as f:
        todos = json.load(f)
        # 确保所有待办事项都有标签和子任务字段（兼容旧数据）
        for todo in todos:
            if "labels" not in todo:
                todo["labels"] = []
            if "subtasks" not in todo:
                todo["subtasks"] = []
        return todos
```

- [ ] **Step 2: Add `subtasks: []` to new custom todos**

In `app.py`, inside `api_custom_todos()`, replace the single-line `todos.append(...)` call with this block:

```python
        todos.append({
            "id": new_id,
            "text": text,
            "done": False,
            "created_at": now,
            "due_date": due_date,
            "highlighted": False,
            "labels": labels,
            "subtasks": [],
        })
```

- [ ] **Step 3: Allow PUT to replace the `subtasks` array**

In `app.py`, inside `api_custom_todo_item(todo_id)`, after the existing `if "labels" in data:` block, add this block before `break`:

```python
                if "subtasks" in data:
                    t["subtasks"] = data["subtasks"]
```

The final inner update block should include `done`, `text`, `due_date`, `highlighted`, `labels`, and `subtasks`, then `break`.

- [ ] **Step 4: Run backend tests and verify they pass**

Run:

```bash
python -m unittest discover -s tests -p "test_custom_todo_subtasks.py" -v
```

Expected result:

```text
test_load_todos_adds_missing_labels_and_subtasks ... ok
test_post_custom_todo_creates_empty_subtasks ... ok
test_put_custom_todo_updates_subtasks_without_completing_parent ... ok

OK
```

- [ ] **Step 5: Local checkpoint**

Record this checkpoint in the task runner notes:

```text
Checkpoint: backend persists custom todo subtasks and regression tests pass.
```

---

### Task 3: Add frontend state, unified data, and custom-only subtask rendering

**Files:**
- Modify: `templates/index.html`
- Test: browser manual verification after Task 5

- [ ] **Step 1: Add non-persistent expansion state**

In `templates/index.html`, near the existing global state declarations where `let customItems = [];` is defined, add:

```javascript
    let expandedCustomTodoIds = [];
```

Do not read from or write to `localStorage`; refresh must collapse all subtask panels.

- [ ] **Step 2: Carry `subtasks` into unified custom items**

In `renderUnifiedList()`, inside the `customItems.forEach(item => { ... unified.push({ ... }) })` object, add this property after `manualHighlighted: item.highlighted || false,`:

```javascript
          subtasks: item.subtasks || [],
```

- [ ] **Step 3: Add subtask progress/toggle markup for custom items**

In `renderUnifiedList()`, after `labelsHtml` is computed and before `animAttr` is computed, add:

```javascript
        const subtasks = item.subtasks || [];
        const isSubtaskExpanded = item.source === 'custom' && expandedCustomTodoIds.includes(item.rawId);
        const subtaskToggleHtml = item.source === 'custom'
          ? `<button class="subtask-toggle" onclick="toggleSubtasks(${item.rawId})" title="子任务">${isSubtaskExpanded ? '▾' : '▸'}</button>`
          : '<span class="subtask-toggle subtask-toggle-placeholder" aria-hidden="true">▸</span>';
```

- [ ] **Step 4: Replace the row return block with wrapper-aware rendering**

In `renderUnifiedList()`, replace the current `return \`` block that starts with `<div class="todo-item unified-item...` and ends with `</div>\`;` with this code:

```javascript
        const rowHtml = `
          <div class="todo-item unified-item ${urgencyClass} ${manualFlag ? 'manual-flagged' : ''} ${isDismissed ? 'dismissed' : ''} ${animAttr}">
            <span class="item-source-badge src-${item.source}">${item.type}</span>
            ${titleHtml}
            ${item.course ? `<span class="item-course">${escapeHtml(item.course)}</span>` : ''}
            ${labelsHtml}
            ${dueHtml}
            <span class="item-subtask-slot">${subtaskToggleHtml}</span><span class="item-actions">${actionsHtml}</span>
          </div>
        `;

        if (item.source !== 'custom') {
          return rowHtml;
        }

        const panelHtml = isSubtaskExpanded ? renderSubtaskPanel(item.rawId, subtasks) : '';
        return `
          <div class="unified-item-wrap">
            ${rowHtml}
            ${panelHtml}
          </div>
        `;
```

This keeps Canvas, 好课, 智学盟, and 智慧树 rows non-expandable while still reserving a triangle slot for visual alignment.

- [ ] **Step 5: Add `renderSubtaskPanel()`**

In `templates/index.html`, after `updateStatsBar(unified)` and before `async function toggleHighlight(itemId, current)`, add this function:

```javascript
    function renderSubtaskPanel(todoId, subtasks) {
      const rowsHtml = subtasks.map(subtask => `
        <div class="subtask-row">
          <input type="checkbox" ${subtask.done ? 'checked' : ''} onchange="toggleSubtaskDone(${todoId}, ${subtask.id})">
          <span class="subtask-text ${subtask.done ? 'done' : ''}" onclick="startSubtaskEdit(${todoId}, ${subtask.id}, this)">${escapeHtml(subtask.text)}</span>
          <button class="subtask-delete" onclick="deleteSubtask(${todoId}, ${subtask.id})" title="删除子任务">×</button>
        </div>
      `).join('');

      return `
        <div class="subtask-panel">
          ${rowsHtml || '<div class="subtask-empty">还没有子任务</div>'}
          <input class="subtask-add-input" placeholder="添加子任务..." onkeydown="handleSubtaskAddKey(event, ${todoId})">
        </div>
      `;
    }
```

- [ ] **Step 6: Local checkpoint**

Record this checkpoint in the task runner notes:

```text
Checkpoint: frontend can render custom-only subtask toggles and expanded panels, but subtask actions are not wired yet.
```

---

### Task 4: Add frontend subtask operations

**Files:**
- Modify: `templates/index.html`
- Test: browser manual verification after Task 5

- [ ] **Step 1: Add custom todo lookup helper**

In `templates/index.html`, near the existing custom todo functions under `// ---- Custom Todos CRUD ----`, add:

```javascript
    function findCustomTodo(todoId) {
      return customItems.find(item => item.id === todoId);
    }
```

- [ ] **Step 2: Add expand/collapse and add-input handlers**

Below `findCustomTodo(todoId)`, add:

```javascript
    function toggleSubtasks(todoId) {
      if (expandedCustomTodoIds.includes(todoId)) {
        expandedCustomTodoIds = expandedCustomTodoIds.filter(id => id !== todoId);
      } else {
        expandedCustomTodoIds.push(todoId);
      }
      renderUnifiedList();
    }

    function handleSubtaskAddKey(event, todoId) {
      if (event.key === 'Enter') {
        addSubtask(todoId, event.target.value);
      } else if (event.key === 'Escape') {
        event.target.value = '';
        event.target.blur();
      }
    }
```

- [ ] **Step 3: Add subtask save function with reload-on-failure behavior**

Below `handleSubtaskAddKey(event, todoId)`, add:

```javascript
    async function saveCustomSubtasks(todoId, subtasks) {
      try {
        const resp = await fetch(`/api/custom/todos/${todoId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ subtasks }),
        });
        if (!resp.ok) throw new Error('save failed');

        const todo = findCustomTodo(todoId);
        if (todo) todo.subtasks = subtasks;
        renderUnifiedList();
      } catch (e) {
        alert('保存失败');
        fetchCustomTodos();
      }
    }
```

- [ ] **Step 4: Add subtask create, check, and delete functions**

Below `saveCustomSubtasks(todoId, subtasks)`, add:

```javascript
    async function addSubtask(todoId, text) {
      const trimmed = text.trim();
      if (!trimmed) return;

      const todo = findCustomTodo(todoId);
      if (!todo) return;

      const currentSubtasks = todo.subtasks || [];
      const newId = Math.max(0, ...currentSubtasks.map(subtask => subtask.id || 0)) + 1;
      const subtasks = [
        ...currentSubtasks,
        { id: newId, text: trimmed, done: false },
      ];
      await saveCustomSubtasks(todoId, subtasks);
    }

    async function toggleSubtaskDone(todoId, subtaskId) {
      const todo = findCustomTodo(todoId);
      if (!todo) return;

      const subtasks = (todo.subtasks || []).map(subtask => (
        subtask.id === subtaskId ? { ...subtask, done: !subtask.done } : subtask
      ));
      await saveCustomSubtasks(todoId, subtasks);
    }

    async function deleteSubtask(todoId, subtaskId) {
      const todo = findCustomTodo(todoId);
      if (!todo) return;

      const subtasks = (todo.subtasks || []).filter(subtask => subtask.id !== subtaskId);
      await saveCustomSubtasks(todoId, subtasks);
    }
```

- [ ] **Step 5: Add inline edit for subtask text**

Below `deleteSubtask(todoId, subtaskId)`, add:

```javascript
    function startSubtaskEdit(todoId, subtaskId, spanEl) {
      const todo = findCustomTodo(todoId);
      if (!todo) return;

      const subtask = (todo.subtasks || []).find(item => item.id === subtaskId);
      if (!subtask) return;

      const originalText = subtask.text;
      const input = document.createElement('input');
      input.type = 'text';
      input.className = 'subtask-edit-input';
      input.value = originalText;
      spanEl.replaceWith(input);
      input.focus();
      input.select();

      async function finish(save) {
        const nextText = input.value.trim();
        if (!save || !nextText || nextText === originalText) {
          renderUnifiedList();
          return;
        }

        const subtasks = (todo.subtasks || []).map(item => (
          item.id === subtaskId ? { ...item, text: nextText } : item
        ));
        await saveCustomSubtasks(todoId, subtasks);
      }

      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') finish(true);
        if (event.key === 'Escape') finish(false);
      });
      input.addEventListener('blur', () => finish(true));
    }
```

This saves non-empty edits on Enter or blur, cancels on Escape, and keeps the old text if the edit is blank.

- [ ] **Step 6: Local checkpoint**

Record this checkpoint in the task runner notes:

```text
Checkpoint: subtask add, check, delete, edit, and save functions are wired to the existing custom todo API.
```

---

### Task 5: Add subtask styling

**Files:**
- Modify: `static/style.css`
- Test: browser manual verification in Task 6

- [ ] **Step 1: Add subtask styles after the existing inline edit styles**

In `static/style.css`, after the `.inline-edit-date-input::-webkit-calendar-picker-indicator` rule block, add:

```css
/* ---- Custom Todo Subtasks ---- */
.unified-item-wrap {
  border-top: 1px solid var(--border-light);
}

.unified-item-wrap .unified-item {
  border-top: none;
}

.subtask-toggle {
  flex-shrink: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 12px;
  font-family: inherit;
  padding: 3px 8px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.subtask-toggle:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-subtle);
}

.subtask-panel {
  margin: -4px 20px 12px 61px;
  padding: 8px 12px 10px;
  border-left: 2px solid var(--border);
  background: #fafaf8;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

.subtask-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.subtask-row input[type="checkbox"] {
  flex-shrink: 0;
}

.subtask-text {
  flex: 1;
  min-width: 0;
  line-height: 1.5;
  cursor: text;
  overflow-wrap: anywhere;
}

.subtask-text.done {
  color: var(--text-muted);
  text-decoration: line-through;
}

.subtask-delete {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 16px;
  line-height: 1;
  padding: 2px 6px;
  border-radius: 3px;
  cursor: pointer;
}

.subtask-delete:hover {
  color: var(--danger-hover);
  background: var(--danger-bg);
}

.subtask-empty {
  padding: 4px 0 8px;
  color: var(--text-muted);
  font-size: 13px;
}

.subtask-add-input,
.subtask-edit-input {
  width: 100%;
  box-sizing: border-box;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  padding: 5px 8px;
  border-radius: 3px;
  outline: none;
}

.subtask-add-input:focus,
.subtask-edit-input:focus {
  border-color: var(--accent);
}
```

- [ ] **Step 2: Add mobile subtask styles inside the existing media query**

In `static/style.css`, inside `@media (max-width: 768px) { ... }`, after the existing `.unified-item.approaching` rule, add:

```css
  .subtask-panel {
    margin-left: 34px;
    margin-right: 0;
  }

  .subtask-toggle {
    padding: 3px 6px;
  }
```

- [ ] **Step 3: Local checkpoint**

Record this checkpoint in the task runner notes:

```text
Checkpoint: subtask UI has compact dashboard-matching styles and mobile margins.
```

---

### Task 6: Verify backend and browser behavior

**Files:**
- Test: `tests/test_custom_todo_subtasks.py`
- Test manually in browser at `http://127.0.0.1:5000`

- [ ] **Step 1: Run backend regression tests**

Run:

```bash
python -m unittest discover -s tests -p "test_custom_todo_subtasks.py" -v
```

Expected result:

```text
test_load_todos_adds_missing_labels_and_subtasks ... ok
test_post_custom_todo_creates_empty_subtasks ... ok
test_put_custom_todo_updates_subtasks_without_completing_parent ... ok

OK
```

- [ ] **Step 2: Start the Flask app**

Run:

```bash
python app.py
```

Expected terminal output includes:

```text
Canvas Dashboard
浏览器打开 → http://127.0.0.1:5000
```

Keep the server running while completing the browser checks.

- [ ] **Step 3: Verify old data compatibility**

Temporarily edit one object in `data/custom_todos.json` so it has no `subtasks` field, then refresh the page.

Expected result:

```text
The page loads normally, and that custom todo shows a `▸` triangle toggle instead of crashing or disappearing.
```

After this check, call `GET /api/custom/todos` by refreshing the dashboard or using the browser devtools Network tab. The response object for that todo must include:

```json
"subtasks": []
```

- [ ] **Step 4: Verify new custom todos get empty subtasks**

In the dashboard, add a new custom todo named:

```text
高数作业 #数学
```

Use due date:

```text
2026-06-05
```

Expected result in `data/custom_todos.json` for the new object:

```json
"subtasks": []
```

- [ ] **Step 5: Verify add and refresh behavior**

Click the new custom todo's triangle toggle. In the subtask input, add these two subtasks by pressing Enter after each line:

```text
看第 3 章
写 1-5 题
```

Expected result before refresh:

```text
The two subtasks appear under the parent todo in creation order, and the toggle remains a compact triangle.
```

Refresh the page.

Expected result after refresh:

```text
The parent todo is collapsed. Its toggle shows `▸`. Expanding it shows both subtasks.
```

- [ ] **Step 6: Verify checking a subtask updates progress and does not complete the parent**

Check `看第 3 章`.

Expected result:

```text
The checked subtask state updates. The parent todo is not marked done and remains in the unfinished section.
```

Refresh the page.

Expected result:

```text
The parent todo is collapsed with the `▸` triangle. Expanding it shows “看第 3 章” checked.
```

- [ ] **Step 7: Verify inline edit**

Expand the todo. Click `写 1-5 题`, change it to:

```text
写 1-6 题
```

Press Enter.

Expected result:

```text
The subtask text changes to “写 1-6 题”. Refreshing the page preserves the edited text.
```

- [ ] **Step 8: Verify delete**

Expand the todo. Delete `写 1-6 题`.

Expected result:

```text
Only “看第 3 章” remains. The toggle text becomes “1/1”. Refreshing the page preserves the deletion.
```

- [ ] **Step 9: Verify all subtasks complete does not complete the parent**

Make sure the remaining subtask is checked.

Expected result:

```text
The toggle text shows “1/1”. The parent custom todo still requires its original complete button to be clicked before it becomes done.
```

- [ ] **Step 10: Verify existing custom parent behavior still works**

On the same custom todo:

1. Click the parent title and change it to `高数作业修改 #数学 #作业`.
2. Click the due date and change it to `2026-06-06`.
3. Click the flag button.
4. Click the parent complete button, then click it again to undo completion.

Expected result:

```text
The title, labels, due date, flag state, and parent done state all save normally. Existing parent behavior is unchanged by subtasks.
```

- [ ] **Step 11: Verify external platform rows are unchanged**

Inspect at least one Canvas, 好课, 智学盟, or 智慧树 row if available.

Expected result:

```text
External platform rows show a non-clickable triangle placeholder for alignment but no subtask panel. Their flag, hide, and delete buttons still work as before.
```

- [ ] **Step 12: Final local checkpoint**

Record this checkpoint in the task runner notes:

```text
Checkpoint: backend tests pass and manual browser verification covers the approved custom todo subtask checklist behavior.
```

---

## Self-Review

- Spec coverage:
  - Custom-only subtasks: Tasks 3 and 6.
  - Add/check/delete/edit subtasks: Task 4 and Task 6.
  - Compact triangle expand/collapse control: Task 3 and Task 6.
  - Parent completion independent from subtasks: Task 1, Task 2, and Task 6.
  - Old data compatibility: Task 1, Task 2, and Task 6.
  - No persistent expansion state: Task 3.
  - Existing external-platform behavior unchanged: Task 3 and Task 6.
- Placeholder scan:
  - This plan contains concrete paths, code snippets, commands, and expected results.
  - It does not require new nested routes, a new database, drag sorting, or batch subtask creation.
- Type consistency:
  - Backend uses `subtasks` as a list of objects with `id`, `text`, and `done`.
  - Frontend uses numeric `todoId` and per-parent numeric `subtaskId`.
  - `saveCustomSubtasks(todoId, subtasks)` always sends `{ subtasks }` to the existing custom todo PUT route.
