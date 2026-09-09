#!/usr/bin/env python3
"""Canvas Dashboard Python Client and CLI Tool.

Zero-dependency client for interacting with Canvas Dashboard Agent API.
Can be imported as a library or executed directly from CLI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


def load_config() -> Dict[str, str]:
    """Load configuration from config.json or environment variables."""
    config: Dict[str, str] = {
        "server_url": os.environ.get("CANVAS_DASHBOARD_URL", "").rstrip("/"),
        "token": os.environ.get("CANVAS_DASHBOARD_TOKEN", "").strip(),
    }

    candidates = [
        Path(__file__).parent / "config.json",
        Path.home() / ".agents" / "skills" / "canvas-dashboard" / "config.json",
        Path.home() / ".claude" / "skills" / "canvas-dashboard" / "config.json",
    ]

    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if not config["server_url"] and data.get("server_url"):
                        config["server_url"] = str(data["server_url"]).rstrip("/")
                    if not config["token"] and data.get("token"):
                        config["token"] = str(data["token"]).strip()
            except Exception:
                pass
            if config["server_url"] and config["token"]:
                break

    if not config["server_url"]:
        config["server_url"] = "http://127.0.0.1:5000"

    return config


class CanvasDashboard:
    """Python interface to Canvas Dashboard Agent v1 REST API."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        cfg = load_config()
        self.base_url = (base_url or cfg.get("server_url") or "http://127.0.0.1:5000").rstrip("/")
        self.token = (token or cfg.get("token") or "").strip()

    def _req(self, path: str, method: str = "GET", data: Any = None) -> Any:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "canvas-dashboard-skill/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {"ok": True}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                err_data = json.loads(err_body)
                raise RuntimeError(f"HTTP {exc.code}: {err_data.get('error', err_body)}") from exc
            except Exception:
                raise RuntimeError(f"HTTP {exc.code}: {err_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to connect to Canvas Dashboard ({url}): {exc.reason}") from exc

    def get_today_schedule(self) -> dict:
        return self._req("/api/agent/v1/schedule/today")

    def get_schedule_for_date(self, target_date: str) -> dict:
        return self._req(f"/api/agent/v1/schedule/date?date={urllib.parse.quote(target_date)}")

    def get_timetable(self) -> dict:
        return self._req("/api/agent/v1/schedule/timetable")

    def get_todos(self, source: str = "all", status: str = "pending") -> dict:
        query = urllib.parse.urlencode({"source": source, "status": status})
        return self._req(f"/api/agent/v1/todos?{query}")

    def add_todo(self, text: str, due_date: Optional[str] = None, planned_on: Optional[str] = None, details: Optional[str] = None, **fields) -> dict:
        payload: Dict[str, Any] = {"text": text}
        if due_date:
            payload["due_date"] = due_date
        if planned_on:
            payload["planned_on"] = planned_on
        if details:
            payload["details"] = details
        payload.update(fields)
        return self._req("/api/agent/v1/todos", method="POST", data=payload)

    def complete_todo(self, todo_id: str, source: str = "custom") -> dict:
        return self._req(f"/api/agent/v1/todos/{urllib.parse.quote(str(todo_id))}/complete", method="POST", data={"source": source})

    def get_agenda(self, start: str, end: str) -> dict:
        query = urllib.parse.urlencode({"start": start, "end": end})
        return self._req(f"/api/agent/v1/agenda?{query}")

    def get_action(self, ref: str) -> dict:
        return self._req(f"/api/agent/v1/actions/{urllib.parse.quote(ref, safe='')}")

    def update_action(self, ref: str, **changes) -> dict:
        return self._req(f"/api/agent/v1/actions/{urllib.parse.quote(ref, safe='')}", method="PUT", data=changes)

    def get_projects(self) -> dict:
        return self._req("/api/agent/v1/projects")

    def add_project_task(self, project_id: str, **fields) -> dict:
        return self._req(f"/api/agent/v1/projects/{urllib.parse.quote(project_id)}/tasks", method="POST", data=fields)

    def schedule_action(self, kind: str, **fields) -> dict:
        if kind not in ("one-off", "recurring"):
            raise ValueError(f"Invalid schedule kind: {kind}")
        return self._req(f"/api/agent/v1/schedule/{kind}", method="POST", data=fields)


def main():
    parser = argparse.ArgumentParser(description="Canvas Dashboard Skill API Client")
    parser.add_argument("--server", help="Canvas Dashboard base URL")
    parser.add_argument("--token", help="Canvas Dashboard Agent Token")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # today
    subparsers.add_parser("today", help="Get today's schedule and due items")

    # schedule
    p_sched = subparsers.add_parser("schedule", help="Get schedule for a specific date")
    p_sched.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")

    # timetable
    subparsers.add_parser("timetable", help="Get semester full timetable")

    # todos
    p_todos = subparsers.add_parser("todos", help="Get pending/completed todos")
    p_todos.add_argument("--source", default="all", choices=["all", "canvas", "haoke", "zhixuemeng", "zhihuishu", "project", "custom"])
    p_todos.add_argument("--status", default="pending", choices=["pending", "completed", "all"])

    # add-todo
    p_add = subparsers.add_parser("add-todo", help="Add a new obligation todo")
    p_add.add_argument("text", help="Todo title (8-20 words recommended)")
    p_add.add_argument("--due", help="Due date YYYY-MM-DD")
    p_add.add_argument("--planned", help="Planned date YYYY-MM-DD")
    p_add.add_argument("--details", help="Details, requirements, standards")

    # complete-todo
    p_comp = subparsers.add_parser("complete-todo", help="Mark a todo as completed")
    p_comp.add_argument("todo_id", help="Todo ID")
    p_comp.add_argument("--source", default="custom", help="Platform source")

    # agenda
    p_agenda = subparsers.add_parser("agenda", help="Get agenda for date range")
    p_agenda.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p_agenda.add_argument("--end", required=True, help="End date YYYY-MM-DD")

    # action
    p_act = subparsers.add_parser("action", help="Get action detail by ref")
    p_act.add_argument("ref", help="Action ref (e.g. custom:123)")

    # projects
    subparsers.add_parser("projects", help="Get long-term projects and tasks")

    args = parser.parse_args()
    client = CanvasDashboard(base_url=args.server, token=args.token)

    try:
        if args.command == "today":
            result = client.get_today_schedule()
        elif args.command == "schedule":
            result = client.get_schedule_for_date(args.date)
        elif args.command == "timetable":
            result = client.get_timetable()
        elif args.command == "todos":
            result = client.get_todos(source=args.source, status=args.status)
        elif args.command == "add-todo":
            result = client.add_todo(args.text, due_date=args.due, planned_on=args.planned, details=args.details)
        elif args.command == "complete-todo":
            result = client.complete_todo(args.todo_id, source=args.source)
        elif args.command == "agenda":
            result = client.get_agenda(args.start, args.end)
        elif args.command == "action":
            result = client.get_action(args.ref)
        elif args.command == "projects":
            result = client.get_projects()
        else:
            parser.print_help()
            sys.exit(1)

        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"[Error] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
