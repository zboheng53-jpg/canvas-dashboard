def test_profile_path_is_per_user(tmp_path, monkeypatch):
    import zhihuishu_store
    from zhihuishu_browser import profile_path

    monkeypatch.setattr(zhihuishu_store, "DATA_DIR", tmp_path)

    assert profile_path("alice") == tmp_path / "users" / "alice" / "zhihuishu_chromium_profile"


def test_context_launch_options_use_configured_chrome_path(monkeypatch):
    from zhihuishu_browser import _context_launch_options

    monkeypatch.setenv("ZHIHUISHU_CHROMIUM_EXECUTABLE", "/usr/bin/google-chrome-stable")

    assert _context_launch_options() == {
        "headless": True,
        "viewport": {"width": 1280, "height": 900},
        "locale": "zh-CN",
        "executable_path": "/usr/bin/google-chrome-stable",
    }


def test_foreign_profile_lock_is_stale():
    from zhihuishu_browser import _profile_lock_is_stale

    assert _profile_lock_is_stale(
        "container-host-19",
        current_host="server-host",
        pid_is_running=lambda pid: True,
    )


def test_live_current_host_profile_lock_is_not_stale():
    from zhihuishu_browser import _profile_lock_is_stale

    assert not _profile_lock_is_stale(
        "server-host-123",
        current_host="server-host",
        pid_is_running=lambda pid: pid == 123,
    )


def test_normalize_assignment_keeps_expected_fields():
    from zhihuishu_browser import normalize_assignment

    item = normalize_assignment({
        "id": 307240,
        "name": "第六章作业",
        "courseName": "普通化学",
        "endTime": "07-05 23:59",
        "endTimeStamp": "2026-07-05T23:59:59+08:00",
        "type": "作业",
        "url": "https://example.test/work",
    })

    assert item == {
        "id": "zhs_307240",
        "title": "第六章作业",
        "course": "普通化学",
        "due_str": "07-05 23:59",
        "due_ts": "2026-07-05T23:59:59+08:00",
        "type": "作业",
        "url": "https://example.test/work",
    }


def test_normalize_assignment_accepts_zhihuishu_task_list_item():
    from zhihuishu_browser import normalize_assignment

    item = normalize_assignment({
        "id": 307240,
        "taskName": "\u7b2c\u516d\u7ae0\u4f5c\u4e1a",
        "courseName": "\u666e\u901a\u5316\u5b662026\u5e74\u6625\u590f\u5b66\u671f",
        "endTime": "2026-07-05 23:59:59",
        "taskType": 1,
    }, url="https://example.test/task")

    assert item == {
        "id": "zhs_307240",
        "title": "\u7b2c\u516d\u7ae0\u4f5c\u4e1a",
        "course": "\u666e\u901a\u5316\u5b662026\u5e74\u6625\u590f\u5b66\u671f",
        "due_str": "2026-07-05 23:59:59",
        "due_ts": "2026-07-05T23:59:59",
        "type": "\u4f5c\u4e1a",
        "url": "https://example.test/task",
    }


def test_smart_course_task_url_rewrites_knowledge_study_link():
    from zhihuishu_browser import smart_course_task_url

    task_url = smart_course_task_url(
        "https://ai-smart-course-student-pro.zhihuishu.com/"
        "singleCourse/knowledgeStudy/2028351615699116032/159874"
        "?mapUid=1813484274284892160"
    )

    assert task_url == (
        "https://ai-smart-course-student-pro.zhihuishu.com/"
        "singleCourse/taskAndExam/2028351615699116032/159874"
        "?mapUid=1813484274284892160"
    )


def test_smart_course_task_url_keeps_existing_task_and_exam_link():
    from zhihuishu_browser import smart_course_task_url

    url = (
        "https://ai-smart-course-student-pro.zhihuishu.com/"
        "singleCourse/taskAndExam/2028351615699116032/159874"
        "?mapUid=1813484274284892160"
    )

    assert smart_course_task_url(url) == url


def test_smart_course_link_candidates_builds_task_entry():
    from zhihuishu_browser import smart_course_link_candidates

    links = smart_course_link_candidates([
        {
            "href": (
                "https://ai-smart-course-student-pro.zhihuishu.com/"
                "singleCourse/knowledgeStudy/2028351615699116032/159874"
                "?mapUid=1813484274284892160"
            ),
            "text": "普通化学2026年春夏学期\n去学习",
        },
        {"href": "https://example.test/other", "text": "not a course"},
    ])

    assert links == [{
        "href": (
            "https://ai-smart-course-student-pro.zhihuishu.com/"
            "singleCourse/knowledgeStudy/2028351615699116032/159874"
            "?mapUid=1813484274284892160"
        ),
        "task_url": (
            "https://ai-smart-course-student-pro.zhihuishu.com/"
            "singleCourse/taskAndExam/2028351615699116032/159874"
            "?mapUid=1813484274284892160"
        ),
        "course": "普通化学2026年春夏学期",
    }]
