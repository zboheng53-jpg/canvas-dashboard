from datetime import date, timedelta
import pytest
import recurring_todo_store
import user_paths
from action_contract import ActionValidationError


@pytest.fixture
def store_env(tmp_path, monkeypatch):
    monkeypatch.setattr(user_paths, "DATA_DIR", tmp_path)
    return "testuser"


def test_create_series_validation(store_env):
    # 成功创建每周系列
    series = recurring_todo_store.create_series(store_env, {
        "title": "每周力学大作业",
        "first_due_date": "2026-09-23",
        "interval_weeks": 1,
        "details": "第1-16周每周三提交"
    })
    assert series["id"] == 1
    assert series["title"] == "每周力学大作业"
    assert series["interval_weeks"] == 1
    assert series["first_due_date"] == "2026-09-23"

    # 非法间隔
    with pytest.raises(ActionValidationError, match="重复间隔"):
        recurring_todo_store.create_series(store_env, {
            "title": "测试",
            "first_due_date": "2026-09-23",
            "interval_weeks": 3
        })

    # 结束日期早于首次截止
    with pytest.raises(ActionValidationError, match="结束日期不能早于首次截止日期"):
        recurring_todo_store.create_series(store_env, {
            "title": "测试",
            "first_due_date": "2026-09-23",
            "end_date": "2026-09-20"
        })


def test_request_id_replay_idempotency(store_env):
    payload = {
        "title": "概率论作业",
        "first_due_date": "2026-09-24",
        "interval_weeks": 2,
        "request_id": "req-prob-001"
    }
    s1 = recurring_todo_store.create_series(store_env, payload)
    s2 = recurring_todo_store.create_series(store_env, payload)
    assert s1["id"] == s2["id"]


def test_homepage_single_item_and_earliest_pending(store_env):
    # 首次截止为 2026-09-23（周三），每周重复
    recurring_todo_store.create_series(store_env, {
        "title": "计算机系统作业",
        "first_due_date": "2026-09-23",
        "interval_weeks": 1
    })

    # 1. 2026-09-10（距离首次截止 13 天）：超过 7 天窗口且未逾期，首页不展示
    day_far = date(2026, 9, 10)
    items = recurring_todo_store.get_homepage_items(store_env, today=day_far)
    assert len(items) == 0

    # 2. 2026-09-18（距离首次截止 5 天）：进入 7 天窗口，首页展示 2026-09-23 这一期
    day_in_window = date(2026, 9, 18)
    items = recurring_todo_store.get_homepage_items(store_env, today=day_in_window)
    assert len(items) == 1
    assert items[0]["due_date"] == "2026-09-23"
    assert items[0]["original_due_date"] == "2026-09-23"
    assert items[0]["status"] == "pending"

    # 3. 2026-09-28（9-23 已逾期，9-30 也在 7 天窗口内）：
    # 验证旧次阻塞！首页必须持续显示 9-23 这一期逾期作业，不能并排显示 9-30，每个系列最多 1 条！
    day_overdue = date(2026, 9, 28)
    items = recurring_todo_store.get_homepage_items(store_env, today=day_overdue)
    assert len(items) == 1
    assert items[0]["due_date"] == "2026-09-23"

    # 4. 完成 9-23 这一期后，首页自动顺延切换到 9-30 这一期！
    recurring_todo_store.complete_occurrence(store_env, 1, "2026-09-23", done=True)
    items_after = recurring_todo_store.get_homepage_items(store_env, today=day_overdue)
    assert len(items_after) == 1
    assert items_after[0]["due_date"] == "2026-09-30"
    assert items_after[0]["original_due_date"] == "2026-09-30"


def test_skip_occurrence_and_switch(store_env):
    recurring_todo_store.create_series(store_env, {
        "title": "隔周实验报告",
        "first_due_date": "2026-09-21",
        "interval_weeks": 2
    })
    today = date(2026, 9, 21)
    items = recurring_todo_store.get_homepage_items(store_env, today=today)
    assert len(items) == 1
    assert items[0]["due_date"] == "2026-09-21"

    # 跳过 9-21 这一期
    recurring_todo_store.skip_occurrence(store_env, 1, "2026-09-21", skip=True)

    # 验证自动切换到隔周后的下一期：2026-10-05（+14天）
    # 但 9-21 距离 10-05 有 14 天（超过 7 天），所以首页此时暂不展示
    items_next = recurring_todo_store.get_homepage_items(store_env, today=today)
    assert len(items_next) == 0

    # 当到了 2026-09-29（距离 10-05 剩 6 天），进入首页
    items_in_6d = recurring_todo_store.get_homepage_items(store_env, today=date(2026, 9, 29))
    assert len(items_in_6d) == 1
    assert items_in_6d[0]["due_date"] == "2026-10-05"


def test_single_occurrence_delay(store_env):
    recurring_todo_store.create_series(store_env, {
        "title": "毛概读书笔记",
        "first_due_date": "2026-09-25",
        "interval_weeks": 1
    })

    # 单期延期到 2026-09-26，修改标题
    recurring_todo_store.update_occurrence(store_env, 1, "2026-09-25", {
        "due_date": "2026-09-26",
        "title": "毛概读书笔记（延期一天）"
    })

    today = date(2026, 9, 24)
    items = recurring_todo_store.get_homepage_items(store_env, today=today)
    assert len(items) == 1
    assert items[0]["original_due_date"] == "2026-09-25"
    assert items[0]["due_date"] == "2026-09-26"
    assert items[0]["title"] == "毛概读书笔记（延期一天）"
    # action_ref 仍指向原截止日期
    assert items[0]["action_ref"] == "recurring:1:2026-09-25"


def test_stop_series(store_env):
    recurring_todo_store.create_series(store_env, {
        "title": "高等数学双周练习",
        "first_due_date": "2026-09-20",
        "interval_weeks": 1
    })

    # 停止在 2026-09-27 之后
    recurring_todo_store.stop_series(store_env, 1, stop_date="2026-09-27")

    # 展开检查：只应该包含 9-20 和 9-27，不应包含 10-04
    occs = recurring_todo_store.expand_occurrences(
        recurring_todo_store.get_series(store_env, 1),
        date(2026, 9, 20),
        date(2026, 10, 31)
    )
    due_dates = [o["due_date"] for o in occs]
    assert due_dates == ["2026-09-20", "2026-09-27"]


def test_range_occurrences_for_agenda(store_env):
    recurring_todo_store.create_series(store_env, {
        "title": "周程测试",
        "first_due_date": "2026-09-01",
        "interval_weeks": 1,
        "end_date": "2026-09-30"
    })
    # 在议程查询范围（2026-09-01 至 2026-09-15）内展开
    range_items = recurring_todo_store.get_range_occurrences(
        store_env,
        date(2026, 9, 1),
        date(2026, 9, 15)
    )
    # 应包含 9-01, 9-08, 9-15
    assert [o["due_date"] for o in range_items] == ["2026-09-01", "2026-09-08", "2026-09-15"]
