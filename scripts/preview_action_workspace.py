"""Run the real application on localhost with isolated, disposable acceptance data."""
import sys
import argparse
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import auth
import user_paths

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--data-dir", type=Path, help="Reuse an existing isolated acceptance directory")
args = parser.parse_args()
if args.data_dir:
    PREVIEW_DATA = args.data_dir.resolve(strict=True)
    if PREVIEW_DATA.parent != Path(tempfile.gettempdir()).resolve() or not PREVIEW_DATA.name.startswith("canvas-workspace-preview-"):
        parser.error("Only an existing canvas-workspace-preview-* temporary directory can be reused")
else:
    PREVIEW_DATA = Path(tempfile.mkdtemp(prefix="canvas-workspace-preview-"))
seed_preview = not (PREVIEW_DATA / "users.json").exists()
auth.DATA_DIR = user_paths.DATA_DIR = PREVIEW_DATA
auth.USERS_FILE = PREVIEW_DATA / "users.json"
auth.SECRET_KEY_FILE = PREVIEW_DATA / ".flask_secret_key"
auth.DELETION_LEDGER_FILE = PREVIEW_DATA / ".account_deletion_ledger.json"
auth.ADMIN_AUDIT_FILE = PREVIEW_DATA / "account_admin_audit.json"

import app as dashboard
import project_store
import schedule_store
from flask import redirect, session, jsonify

dashboard.DATA_DIR = PREVIEW_DATA
dashboard._TERM_CONFIG_FILE = PREVIEW_DATA / "term_config.json"
dashboard._HOLIDAY_CACHE_FILE = PREVIEW_DATA / "holiday_cache.json"
dashboard.app.config["SESSION_COOKIE_SECURE"] = False
dashboard.app.jinja_env.auto_reload = True
# Deliberate fixture values: this preview does not fetch live weather.
dashboard.app.view_functions["api_weather"] = lambda: jsonify(ok=True, temperature=26.3, humidity=62, weather_desc="晴间多云（示例）", weather_emoji="☀️", weather_code=2)
if seed_preview:
    auth.register("preview", "local-preview-only-2026")
    today = datetime.now(timezone(timedelta(hours=8))).date()
    day = lambda offset: (today + timedelta(days=offset)).isoformat()

    english = project_store.create_project("preview", {"name": "英语｜六级学习与持续提升", "objective": "稳定练习，记录听辨和词汇的进步", "materials": "项目资料示例：复用真题音频与错题记录。\n雅思暂缓；确认具体需求后再制定计划。"})
    listening = project_store.create_task("preview", english["id"], {"name": "完成听力诊断与核心词复习", "details": "1. 用一段真题完成听力并对照原文。\n2. 区分词汇不认识与听音辨认困难。\n3. 学习 5–8 个核心词，遮住释义回忆。\n完成标准：留下主要障碍与待复习词。", "commitment": "growth", "planned_on": day(1), "estimate_minutes": 25, "is_next_action": True})
    project_store.create_task("preview", english["id"], {"name": "核实六级报名资格与校内窗口", "details": "这是演示事项，未设置未经核实的截止日期。", "commitment": "obligation"})
    gym = project_store.create_project("preview", {"name": "健身｜稳定训练与引体进步", "objective": "建立可持续的训练节奏"})
    project_store.create_task("preview", gym["id"], {"name": "完成一次基础力量训练", "details": "按熟悉动作练习，记录感受和完成情况。", "commitment": "growth", "planned_on": day(2), "estimate_minutes": 45, "is_next_action": True})
    project_store.create_project("preview", {"name": "科研｜导师沟通到真实项目", "objective": "等待资料，收到后整理问题"})
    project_store.create_project("preview", {"name": "竞赛｜TU 主线与技术积累", "objective": "逐步沉淀技术笔记"})
    project_store.set_main_project("preview", english["id"])
    homework = dashboard._create_custom_action("preview", {"text": "提交自动控制实验报告", "details": "示例责任事项：核对实验图表并提交报告。\n请勿将此数据视为真实课程要求。", "due_date": day(2), "request_id": "preview-homework"})
    dashboard._create_custom_action("preview", {"text": "确认项目组会材料", "due_date": day(5), "request_id": "preview-meeting"})
    schedule_store.create_item("preview", "one_off", {"title": "提交自动控制实验报告", "action_ref": homework["ref"], "date": day(0), "start_time": "16:00", "end_time": "16:45", "location": "图书馆"})
    schedule_store.create_item("preview", "one_off", {"title": listening["name"], "action_ref": f"project:{english['id']}:{listening['id']}", "date": day(1), "start_time": "19:00", "end_time": "19:25", "location": ""})
    schedule_store.create_item("preview", "recurring", {"title": "每周英语练习", "action_ref": f"project:{english['id']}:{listening['id']}", "weekday": (today.weekday()+3)%7, "start_date": day(0), "end_date": day(20), "start_time": "19:00", "end_time": "19:25", "enabled": True})
    schedule_store.save_courses("preview", "本地验收 · 示例课表", day(-today.weekday()), [{"name": "自动控制原理（示例）", "teacher": "示例教师", "sessions": [{"weekday": today.weekday(), "weeks": [], "start_time": "09:50", "end_time": "11:25", "location": "北楼 229"}]}], datetime.now(timezone.utc).isoformat())

dashboard._LOGIN_EXEMPT_ENDPOINTS.add("workspace_preview_login")


@dashboard.app.route("/preview-login")
def workspace_preview_login():
    account_id, version = auth.session_identity("preview")
    session.clear()
    session.update(username="preview", account_id=account_id, session_version=version)
    dashboard._refresh_session_activity(force=True)
    return redirect("/")


@dashboard.app.after_request
def label_preview(response):
    if response.mimetype == "text/html":
        text = response.get_data(as_text=True)
        text = text.replace('添加新待办…', '本地验收示例：添加新待办…')
        response.set_data(text)
    return response


if __name__ == "__main__":
    print(f"Isolated acceptance data: {PREVIEW_DATA}", flush=True)
    dashboard.app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
