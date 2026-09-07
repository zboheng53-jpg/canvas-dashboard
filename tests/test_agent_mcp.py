import json
from unittest.mock import MagicMock

import agent_mcp


def test_mcp_tools_list():
    assert len(agent_mcp.TOOLS) >= 7
    tool_names = {t["name"] for t in agent_mcp.TOOLS}
    expected_tools = {
        "get_today_schedule",
        "get_schedule_for_date",
        "get_timetable",
        "get_todos",
        "add_todo",
        "complete_todo",
        "get_projects",
        "get_sync_status",
    }
    assert expected_tools.issubset(tool_names)


def test_mcp_tool_call_handler():
    mock_client = MagicMock()

    # get_today_schedule
    mock_client.request.return_value = {
        "ok": True,
        "date": "2026-09-07",
        "term": "2026-2027第一学期",
        "timed": [
            {"kind": "course", "title": "高等数学", "location": "教学楼A101", "start_time": "08:00", "end_time": "09:35"}
        ],
        "deadlines": [],
    }
    out = agent_mcp.handle_tool_call(mock_client, "get_today_schedule", {})
    assert "2026-09-07" in out
    assert "高等数学" in out
    assert "教学楼A101" in out

    # add_todo
    mock_client.request.return_value = {
        "ok": True,
        "todo": {"id": 123, "text": "完成实验报告", "due_date": "2026-09-09"},
    }
    out = agent_mcp.handle_tool_call(mock_client, "add_todo", {"text": "完成实验报告", "due_date": "2026-09-09"})
    assert "成功添加待办" in out
    assert "完成实验报告" in out

    # complete_todo
    mock_client.request.return_value = {"ok": True, "completed": True}
    out = agent_mcp.handle_tool_call(mock_client, "complete_todo", {"todo_id": "123", "source": "custom"})
    assert "已成功将待办" in out
