import json
import tempfile
import unittest
from pathlib import Path

import app as dashboard_app


class CustomTodoSubtasksTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.user_dir = Path(self.tmpdir.name) / "users" / "alice"
        self.user_dir.mkdir(parents=True)
        self.todos_file = self.user_dir / "custom_todos.json"
        self.todos_file.write_text("[]", encoding="utf-8")
        self.original_user_dir = dashboard_app.user_dir
        dashboard_app.user_dir = lambda username: self.user_dir
        self.client = dashboard_app.app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "alice"
            sess["_csrf_token"] = "csrf-test-token"
        self.csrf_headers = {"X-CSRF-Token": "csrf-test-token"}

    def tearDown(self):
        dashboard_app.user_dir = self.original_user_dir
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

        todos = dashboard_app._load_todos("alice")

        self.assertEqual(todos[0]["labels"], [])
        self.assertEqual(todos[0]["subtasks"], [])

    def test_post_custom_todo_creates_empty_subtasks(self):
        resp = self.client.post("/api/custom/todos", json={
            "text": "高数作业",
            "due_date": "2026-06-05",
            "labels": ["数学"],
        }, headers=self.csrf_headers)

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["todo"]["subtasks"], [])

        stored = self.read_stored_todos()
        self.assertEqual(stored[0]["subtasks"], [])
        self.assertEqual(stored[0]["labels"], payload["todo"]["labels"])
        self.assertIn("updated_at", stored[0])

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

        resp = self.client.put("/api/custom/todos/1", json={"subtasks": subtasks}, headers=self.csrf_headers)

        self.assertEqual(resp.status_code, 200)
        stored = self.read_stored_todos()
        self.assertEqual(stored[0]["subtasks"], subtasks)
        self.assertFalse(stored[0]["done"])

    def test_put_custom_todo_rejects_stale_subtask_version(self):
        self.todos_file.write_text(json.dumps([
            {
                "id": 1,
                "text": "Task",
                "done": False,
                "created_at": "2026-06-03T20:00:00+08:00",
                "updated_at": "2026-07-09T08:00:00+08:00",
                "due_date": "2026-06-05",
                "highlighted": False,
                "labels": ["math"],
                "subtasks": [{"id": 1, "text": "old", "done": False}],
            }
        ], ensure_ascii=False), encoding="utf-8")
        subtasks = [{"id": 1, "text": "new", "done": True}]

        resp = self.client.put(
            "/api/custom/todos/1",
            json={"subtasks": subtasks, "updated_at": "2026-07-09T07:00:00+08:00"},
            headers=self.csrf_headers,
        )

        self.assertEqual(resp.status_code, 409)
        payload = resp.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "custom_todo_conflict")
        stored = self.read_stored_todos()
        self.assertEqual(stored[0]["subtasks"], [{"id": 1, "text": "old", "done": False}])

    def test_put_custom_todo_accepts_matching_subtask_version_and_returns_updated_todo(self):
        self.todos_file.write_text(json.dumps([
            {
                "id": 1,
                "text": "Task",
                "done": False,
                "created_at": "2026-06-03T20:00:00+08:00",
                "updated_at": "2026-07-09T08:00:00+08:00",
                "due_date": "2026-06-05",
                "highlighted": False,
                "labels": ["math"],
                "subtasks": [],
            }
        ], ensure_ascii=False), encoding="utf-8")
        subtasks = [{"id": 1, "text": "new", "done": True}]

        resp = self.client.put(
            "/api/custom/todos/1",
            json={"subtasks": subtasks, "updated_at": "2026-07-09T08:00:00+08:00"},
            headers=self.csrf_headers,
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["todo"]["subtasks"], subtasks)
        self.assertNotEqual(payload["todo"]["updated_at"], "2026-07-09T08:00:00+08:00")
