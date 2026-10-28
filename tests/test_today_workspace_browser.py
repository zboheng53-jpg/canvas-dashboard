import json
import web_common
from datetime import timedelta
import pytest
from playwright.sync_api import expect
import app as dashboard
import project_store
import schedule_store
from conftest import FIXED_NOW
from test_visual_regression import register_dashboard_user


def test_today_workspace_browser(live_app, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        username = register_dashboard_user(page, live_app, "ws")
        today = dashboard.datetime.now(web_common.CST).date()

        # 1. Model 8-step project
        p = project_store.create_project(username, {
            "name": "毕业设计论文",
            "objective": "完成毕业论文初稿与盲审材料",
            "materials": "导师给出的参考文献与实验要求",
        })

        # Step 1: current action
        s1 = project_store.create_task(username, p["id"], {
            "name": "撰写绪论与研究背景",
            "is_next_action": True,
            "planned_on": today.isoformat(),
            "due_date": (today + timedelta(days=10)).isoformat(),
            "details": "包含国内外现状分析、主要创新点与论文结构安排。",
        })
        # Step 2: missed plan (planned_on < today, not genuinely overdue)
        s2 = project_store.create_task(username, p["id"], {
            "name": "整理前期仿真数据",
            "planned_on": (today - timedelta(days=2)).isoformat(),
            "commitment": "obligation",
        })
        # Step 3-6: future roadmap steps
        s3 = project_store.create_task(username, p["id"], {
            "name": "核心算法实现",
            "planned_on": (today + timedelta(days=1)).isoformat(),
        })
        s4 = project_store.create_task(username, p["id"], {
            "name": "实验对比分析",
            "planned_on": (today + timedelta(days=3)).isoformat(),
        })
        s5 = project_store.create_task(username, p["id"], {
            "name": "撰写结论与展望",
            "planned_on": (today + timedelta(days=7)).isoformat(),
        })
        s6 = project_store.create_task(username, p["id"], {
            "name": "格式排版与查重",
        })
        # Steps 7-8: completed steps
        s7 = project_store.create_task(username, p["id"], {"name": "课题立项评审"})
        project_store.update_task(username, p["id"], s7["id"], {"done": True})
        s8 = project_store.create_task(username, p["id"], {"name": "文献综述撰写"})
        project_store.update_task(username, p["id"], s8["id"], {"done": True})

        # 2. Model scheduled course/event for today
        schedule_store.create_item(username, "one_off", {
            "title": "导师例会交流",
            "date": today.isoformat(),
            "start_time": "14:00",
            "end_time": "15:00",
        })

        # 3. Model ordinary unscheduled due item (due today)
        page.evaluate("""async (todayStr) => {
            await fetch('/api/custom/todos', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN},
                body: JSON.stringify({text: '提交学期选课确认表', due_date: todayStr})
            });
        }""", today.isoformat())

        page.reload()
        page.wait_for_selector(".dashboard-shell")

        # ---- Verification A: Homepage one project row ----
        overview_projects = page.locator("#project-overview-content")
        proj_rows = overview_projects.locator(".proj-summary-row")
        expect(proj_rows).to_have_count(1)
        expect(proj_rows.first).to_contain_text("毕业设计论文")
        expect(proj_rows.first).to_contain_text("撰写绪论与研究背景")
        expect(proj_rows.first).to_contain_text("2/8")

        # ---- Verification B: No steps/materials flood on homepage ----
        # Upcoming steps and materials should not flood the homepage
        expect(page.locator("#project-overview-content").get_by_text("核心算法实现")).to_have_count(0)
        expect(page.locator("#project-overview-content").get_by_text("实验对比分析")).to_have_count(0)
        expect(page.locator("#project-overview-content").get_by_text("导师给出的参考文献与实验要求")).to_have_count(0)

        # ---- Verification C: Deadline visible on homepage ----
        deadlines_card = page.locator("#todo-list [data-group-key=today]")
        expect(deadlines_card).to_be_visible()
        expect(deadlines_card).to_contain_text("提交学期选课确认表")

        # ---- Verification D: Timeline only scheduled items ----
        timeline = page.locator("#today-schedule-content")
        expect(timeline).to_be_visible()
        expect(timeline).to_contain_text("导师例会交流")
        # Unscheduled deadline should NOT be in timeline
        expect(timeline.get_by_text("提交学期选课确认表")).to_have_count(0)
        # Project steps should NOT be in timeline
        expect(timeline.get_by_text("撰写绪论与研究背景")).to_have_count(0)

        # ---- Verification E: Project Detail ----
        # Click project row on homepage to open project detail
        proj_rows.first.click()
        detail = page.locator("#project-detail")
        expect(detail).to_be_visible()
        expect(detail.locator("h2")).to_have_text("毕业设计论文")

        # ONE current step card with full escaped details
        step_card = page.locator(".project-current-step-card")
        expect(step_card).to_be_visible()
        expect(step_card).to_contain_text("撰写绪论与研究背景")
        expect(step_card.locator(".project-current-step-details")).to_contain_text("包含国内外现状分析、主要创新点与论文结构安排。")
        expect(step_card.locator(".project-current-step-controls button").filter(has_text="完成步骤")).to_be_visible()
        expect(step_card.locator(".project-current-step-controls button").filter(has_text="编辑步骤")).to_be_visible()
        expect(step_card.locator(".project-current-step-controls button").filter(has_text="安排日程")).to_be_visible()

        # Chronological roadmap: current step excluded from roadmap
        roadmap = page.locator(".project-roadmap-list")
        expect(roadmap).to_be_visible()
        expect(roadmap.get_by_text("撰写绪论与研究背景")).to_have_count(0)
        expect(roadmap.get_by_text("核心算法实现")).to_be_visible()
        expect(roadmap.get_by_text("实验对比分析")).to_be_visible()

        # Completed tasks all in one collapsed section
        history = page.locator(".project-finished-groups")
        expect(history).to_be_visible()
        assert history.get_attribute("open") is None

        # ---- Verification F: Missed planned step stays in TODAY ----
        page.locator('[data-dashboard-view="todos"]').click()
        todos_panel = page.locator("#dashboard-view-todos")
        expect(todos_panel).to_be_visible()

        # Missed plan stays in today group with "原计划" label
        today_group = todos_panel.locator(".todo-group").filter(has=page.get_by_role("heading", name="今天", exact=True))
        expect(today_group).to_be_visible()
        expect(today_group.get_by_text("整理前期仿真数据")).to_be_visible()
        expect(today_group.locator(".todo-row").filter(has_text="整理前期仿真数据")).to_contain_text("原计划")

        # Completing the current step promotes the earliest missed plan.
        page.locator('[data-dashboard-view="projects"]').click()
        step_card.get_by_role("button", name="完成步骤", exact=True).click()
        expect(step_card).to_contain_text("整理前期仿真数据")
        expect(page.locator(".project-progress-pill")).to_contain_text("3/8")

    finally:
        page.close()
