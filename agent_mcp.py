#!/usr/bin/env python3
"""Canvas Dashboard - Model Context Protocol (MCP) Server.

Enables AI Agents (Claude Desktop, Cursor, Cline, etc.) to interact with Canvas Dashboard:
- Query today's and specified date course schedules
- View unified pending todos and assignments across platforms
- Add and complete custom todos
- Check long-term projects and platform sync statuses

Zero external dependencies - runs on Python 3 standard library.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_SERVER_URL = os.environ.get("CANVAS_DASHBOARD_URL", "http://127.0.0.1:5000").rstrip("/")
DEFAULT_API_TOKEN = os.environ.get("CANVAS_DASHBOARD_TOKEN", "")

TOOLS = [
    {
        "name": "get_today_schedule",
        "description": "获取用户今日的课表安排、教室地点及今日截止事项（支持查看节次、时间段、教室等）",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_schedule_for_date",
        "description": "获取用户指定日期的课表安排与排程日程",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "查询日期，格式为 YYYY-MM-DD，例如 2026-09-07",
                }
            },
            "required": ["date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_timetable",
        "description": "获取当前学期完整课表和所有课程的基础信息（包含课程名称、教师、上课时间地点、周次等）",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_todos",
        "description": "获取用户的待办事项与作业列表。聚合了 Canvas、好课、智学盟、智慧树、长期项目与自定义待办",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "按来源筛选：all（全部）、canvas（Canvas）、haoke（好课）、zhixuemeng（智学盟）、zhihuishu（智慧树）、project（项目）、custom（自定义）",
                    "enum": ["all", "canvas", "haoke", "zhixuemeng", "zhihuishu", "project", "custom"],
                },
                "status": {
                    "type": "string",
                    "description": "按状态筛选：pending（待完成，默认）、completed（已完成）、all（全部）",
                    "enum": ["pending", "completed", "all"],
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "add_todo",
        "description": "添加一条新的自定义待办事项。注意：标题须遵循高信息密度动宾结构（8~18字，如'提交数模论文终稿'），严禁在标题中混入免责声明、规则解释或冗长背景说明",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "精炼的待办事项标题（动宾结构，8~18字以内，高信息密度，严禁冗长废话与背景说明）",
                },
                "due_date": {
                    "type": "string",
                    "description": "可选截止日期，格式为 YYYY-MM-DD",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "complete_todo",
        "description": "将指定的待办事项标记为已完成",
        "inputSchema": {
            "type": "object",
            "properties": {
                "todo_id": {
                    "type": "string",
                    "description": "待办事项的 ID",
                },
                "source": {
                    "type": "string",
                    "description": "待办所属来源平台，默认为 custom，可选 canvas、haoke、zhixuemeng、zhihuishu、project",
                    "enum": ["custom", "canvas", "haoke", "zhixuemeng", "zhihuishu", "project"],
                },
            },
            "required": ["todo_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_projects",
        "description": "获取长期项目列表、目标规划、截止时间以及当前激活的主项目和下一步行动 (Next Action)",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_sync_status",
        "description": "获取各平台（Canvas、好课、智学盟、智慧树）的连接状态、最后同步时间与日历资格",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


class CanvasDashboardClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = (base_url or "").rstrip("/")
        self.token = (token or "").strip()

    def request(self, endpoint: str, method: str = "GET", data: dict | None = None) -> dict:
        if not self.base_url:
            raise ValueError("Canvas Dashboard URL 未配置，请设置 CANVAS_DASHBOARD_URL 或通过 --url 传入。")
        if not self.token:
            raise ValueError("Canvas Dashboard Token 未配置，请在网页中生成 Token，并设置 CANVAS_DASHBOARD_TOKEN 或通过 --token 传入。")

        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "CanvasDashboard-MCP/1.0",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_text = resp.read().decode("utf-8")
                return json.loads(resp_text)
        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8")
                parsed = json.loads(error_body)
                err_msg = parsed.get("error") or parsed.get("message") or error_body
            except Exception:
                err_msg = str(exc)
            raise RuntimeError(f"API 请求失败 [{exc.code}]: {err_msg}")
        except Exception as exc:
            raise RuntimeError(f"网络连接错误: {exc}")


def handle_tool_call(client: CanvasDashboardClient, name: str, args: dict[str, Any]) -> str:
    if name == "get_today_schedule":
        res = client.request("/api/agent/v1/schedule/today")
        if not res.get("ok"):
            return f"获取今日日程失败: {res.get('error')}"
        timed = res.get("timed", [])
        deadlines = res.get("deadlines", [])
        date_str = res.get("date", "")
        term = res.get("term", "")
        lines = [f"### 📅 {date_str} 日程安排 (学期: {term or '未知'})"]
        if timed:
            lines.append("\n**课程与时间事项：**")
            for item in timed:
                kind = item.get("kind", "")
                title = item.get("title", "")
                loc = f" 📍 {item['location']}" if item.get("location") else ""
                start = item.get("start_time", "")
                end = item.get("end_time", "")
                time_range = f"{start} - {end}" if start and end else start
                lines.append(f"- [{time_range}] {title}{loc} ({kind})")
        else:
            lines.append("\n今日无排定的课程。")

        if deadlines:
            lines.append("\n**今日截止事项：**")
            for item in deadlines:
                course = f" [{item['course']}]" if item.get("course") else ""
                lines.append(f"- ⚠️ {item.get('title')}{course}")
        return "\n".join(lines)

    elif name == "get_schedule_for_date":
        date_query = args.get("date", "")
        res = client.request(f"/api/agent/v1/schedule/timetable?date={urllib.parse.quote(date_query)}")
        if not res.get("ok"):
            return f"获取日期 {date_query} 日程失败: {res.get('error')}"
        timed = res.get("timed", [])
        lines = [f"### 📅 {date_query} 日程安排"]
        if timed:
            for item in timed:
                loc = f" 📍 {item['location']}" if item.get("location") else ""
                start = item.get("start_time", "")
                end = item.get("end_time", "")
                time_range = f"{start} - {end}" if start and end else start
                lines.append(f"- [{time_range}] {item.get('title')}{loc}")
        else:
            lines.append("该日无课程或排程事项。")
        return "\n".join(lines)

    elif name == "get_timetable":
        res = client.request("/api/agent/v1/schedule/timetable")
        if not res.get("ok"):
            return f"获取全学期课表失败: {res.get('error')}"
        courses = res.get("courses", {}).get("courses", [])
        term = res.get("courses", {}).get("term", "")
        lines = [f"### 📚 学期课程列表 ({term})，共 {len(courses)} 门课程:"]
        for c in courses:
            name_str = c.get("name", "未命名课程")
            code = c.get("code") or c.get("id") or ""
            teacher = f" | 教师: {c.get('teacher')}" if c.get("teacher") else ""
            lines.append(f"- **{name_str}** (代码: {code}{teacher})")
            sessions = c.get("sessions", [])
            for s in sessions:
                weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
                w_str = weekday_map.get(s.get("weekday"), "")
                loc = f" @ {s.get('location')}" if s.get("location") else ""
                t_range = f"{s.get('start_time')}-{s.get('end_time')}"
                weeks = f" [第 {','.join(map(str, s.get('weeks', [])))} 周]" if s.get("weeks") else ""
                lines.append(f"  · {w_str} {t_range}{loc}{weeks}")
        return "\n".join(lines)

    elif name == "get_todos":
        source = args.get("source", "all")
        status = args.get("status", "pending")
        query = f"?source={urllib.parse.quote(source)}&status={urllib.parse.quote(status)}"
        res = client.request(f"/api/agent/v1/todos{query}")
        if not res.get("ok"):
            return f"获取待办失败: {res.get('error')}"
        todos = res.get("todos", [])
        lines = [f"### 📋 待办事项清单 (来源: {source}, 状态: {status}), 共 {len(todos)} 项:"]
        if not todos:
            lines.append("暂无相关待办事项。")
            return "\n".join(lines)

        for item in todos:
            done_mark = "✅" if item.get("done") else "⬜"
            title = item.get("title", item.get("text", "未命名待办"))
            src = item.get("source", "Custom")
            due = f" ⏰ 截止: {item['due_date']}" if item.get("due_date") else ""
            course = f" [{item['course']}]" if item.get("course") else ""
            item_id = item.get("id", "")
            lines.append(f"- {done_mark} (ID: `{item_id}` | 来源: {src}){course} {title}{due}")
        return "\n".join(lines)

    elif name == "add_todo":
        text = args.get("text", "").strip()
        due_date = args.get("due_date")
        payload = {"text": text}
        if due_date:
            payload["due_date"] = due_date
        res = client.request("/api/agent/v1/todos", method="POST", data=payload)
        if not res.get("ok"):
            return f"添加待办失败: {res.get('error')}"
        created = res.get("todo", {})
        return f"🎉 成功添加待办 (ID: {created.get('id')}): {created.get('text')}" + (f" (截止: {created.get('due_date')})" if created.get("due_date") else "")

    elif name == "complete_todo":
        todo_id = str(args.get("todo_id", "")).strip()
        source = args.get("source", "custom")
        res = client.request(f"/api/agent/v1/todos/{urllib.parse.quote(todo_id)}/complete", method="POST", data={"source": source})
        if not res.get("ok"):
            return f"标记完成失败: {res.get('error')}"
        return f"✅ 已成功将待办 (ID: {todo_id}, 来源: {source}) 标记为已完成。"

    elif name == "get_projects":
        res = client.request("/api/agent/v1/projects")
        if not res.get("ok"):
            return f"获取项目列表失败: {res.get('error')}"
        projects = res.get("projects", [])
        primary_id = res.get("primary_project_id")
        lines = [f"### 🎯 长期项目概览 (共 {len(projects)} 个项目):"]
        for p in projects:
            is_pri = " 🌟 [主项目]" if p.get("id") == primary_id else ""
            due = f" (截止: {p['due_date']})" if p.get("due_date") else ""
            next_action = f" | 下一步: {p['next_action']['name']}" if p.get("next_action") else ""
            lines.append(f"- **{p.get('name')}**{is_pri}{due}{next_action}")
            if p.get("objective"):
                lines.append(f"  目标: {p['objective']}")
        return "\n".join(lines)

    elif name == "get_sync_status":
        res = client.request("/api/agent/v1/sync/status")
        if not res.get("ok"):
            return f"获取同步状态失败: {res.get('error')}"
        statuses = res.get("statuses", {})
        lines = ["### 🔄 平台同步状态:"]
        for platform, info in statuses.items():
            state = info.get("connection_state", "unknown")
            last_sync = info.get("last_sync_at") or "从未"
            lines.append(f"- **{platform}**: 状态={state}, 上次同步={last_sync}")
        return "\n".join(lines)

    return f"未知工具: {name}"


def run_stdio_server(client: CanvasDashboardClient):
    """Run standard JSON-RPC 2.0 stdio server for MCP."""
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": {
                        "name": "canvas-dashboard-mcp",
                        "version": "1.0.0",
                    },
                },
            }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            # Client notification after initialize
            pass

        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": TOOLS,
                },
            }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                content_text = handle_tool_call(client, tool_name, tool_args)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": content_text}
                        ],
                        "isError": False,
                    },
                }
            except Exception as exc:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": f"执行出错: {exc}"}
                        ],
                        "isError": True,
                    },
                }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        else:
            if req_id is not None:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found",
                    },
                }
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Canvas Dashboard MCP Server")
    parser.add_argument("--url", default=DEFAULT_SERVER_URL, help="Canvas Dashboard base URL")
    parser.add_argument("--token", default=DEFAULT_API_TOKEN, help="Agent API Token")
    args = parser.parse_args()

    client = CanvasDashboardClient(args.url, args.token)
    run_stdio_server(client)


if __name__ == "__main__":
    main()
