/* Static API fixture used only by scripts/export_open_design_preview.py. */
(() => {
  if (!window.__OPEN_DESIGN_PREVIEW__) return;
  window.__OPEN_DESIGN_MOCK_READY__ = true;

  const project = {
    id: 1, name: "自动化课程设计", objective: "完成控制系统设计、仿真验证与答辩材料。",
    due_date: "2026-08-02", due_state: "upcoming", due_days: 8, status: "active", sort_order: 0,
    completed_count: 1, pending_count: 2,
    groups: [{ id: 1, name: "设计与验证", sort_order: 0 }],
    tasks: [
      { id: 11, name: "完成状态空间模型", group_id: 1, due_date: "2026-07-28", done: false, highlighted: true, is_next_action: true, sort_order: 0 },
      { id: 12, name: "整理仿真结果与图表", group_id: 1, due_date: "2026-07-31", done: false, highlighted: false, is_next_action: false, sort_order: 1 },
      { id: 13, name: "明确课题分工", group_id: null, due_date: "2026-07-24", done: true, highlighted: false, is_next_action: false, sort_order: 0 },
    ],
  };
  const today = "2026-07-25";
  const platformResponse = (data) => ({ ok: true, cached: true, data, hidden: [], highlighted: [], deleted: [] });
  const projectTodo = { id: 101, project_id: 1, task_id: 11, kind: "task", title: "完成状态空间模型", project_name: project.name, due_date: "2026-07-28", flagged: true };
  const payloads = {
    "/api/clock": { ok: true, iso: "2026-07-25T15:19:42+08:00", time: "15:19:42", date: "2026年7月25日", weekday: "星期五" },
    "/api/weather": { ok: true, weather_desc: "晴", weather_emoji: "☀️", temperature: 29, humidity: 62, wind_speed: 3 },
    "/api/term": { ok: true, term: "2025-2026 学年春季学期", week: 18, is_holiday: false },
    "/api/canvas/todos": platformResponse([{ id: 1, title: "《自动控制原理》第七章课后练习提交", course: "自动控制原理", type: "作业", due_str: "2026-07-25", due_ts: "2026-07-25T23:59:00", url: "" }]),
    "/api/haoke/todos": platformResponse([{ id: 1, title: "线性代数 第六次直播课签到与随堂练习", course: "线性代数", type: "直播", due_str: "2026-07-26", due_ts: "2026-07-26T20:00:00", url: "" }]),
    "/api/zhixuemeng/todos": platformResponse([{ id: 1, title: "《工程伦理》阶段测试", course: "工程伦理", type: "测验", due_str: "2026-07-27", due_ts: "2026-07-27T23:59:00", url: "" }]),
    "/api/zhihuishu/todos": platformResponse([{ id: 1, title: "《大学物理》第三章作业（光学部分）", course: "大学物理", type: "作业", due_str: "2026-07-26", due_ts: "2026-07-26T23:59:00", url: "" }]),
    "/api/custom/todos": { ok: true, today, data: [
      { id: 2001, text: "实验室周报提交", due_date: today, labels: ["实验室"], highlighted: false, done: false, subtasks: [] },
      { id: 2002, text: "整理自动化专业笔记归档", due_date: null, labels: ["学习笔记"], highlighted: false, done: false, subtasks: [] },
      {
        id: 2003,
        text: "整理自动控制原理课程设计中的系统辨识、控制器参数整定与实验数据分析，并补充最终报告中的误差讨论",
        due_date: today,
        labels: ["课程设计长标签验证"],
        highlighted: true,
        done: false,
        subtasks: [
          { id: 1, text: "核对一段足够长的子任务文字在窄屏下是否自然换行且不会挤压日期和删除操作", due_date: today, done: false },
          { id: 2, text: "已完成的子任务", due_date: today, done: true },
        ],
      },
      ...Array.from({ length: 12 }, (_, index) => ({
        id: 2100 + index,
        text: `批量数据回归事项 ${String(index + 1).padStart(2, "0")}`,
        due_date: index % 3 === 0 ? today : null,
        labels: index % 2 === 0 ? ["批量验证"] : [],
        highlighted: false,
        done: false,
        subtasks: [],
      })),
    ] },
    "/api/projects": { ok: true, projects: [project], main_project_id: 1, last_viewed_project_id: 1 },
    "/api/projects/overview": { ok: true, active_project_count: 1, main_project: { ...project, upcoming_tasks: [project.tasks[1]], hidden_task_count: 0 } },
    "/api/projects/todos": { ok: true, items: [projectTodo] },
    "/api/schedule": { ok: true, courses: { term: "2025-2026 学年春季学期", semester_start: "2026-02-23", updated_at: "2026-07-24T09:00:00", courses: [{ name: "自动控制原理", location: "中法中心 C405", sessions: [{ weekday: 4, start_time: "10:00", end_time: "11:35", location: "中法中心 C405", weeks: [] }] }] }, items: { recurring: [{ id: 1, title: "课题组周会", weekday: 4, start_time: "14:00", end_time: "15:00", location: "嘉定校区", enabled: true, skipped_dates: [] }], one_off: [] } },
    "/api/schedule/today": { ok: true, date: today, timed: [{ kind: "course", title: "自动控制原理", location: "中法中心 C405", start_time: "10:00", end_time: "11:35" }, { kind: "recurring", title: "课题组周会", location: "嘉定校区", start_time: "14:00", end_time: "15:00" }], deadlines: [{ title: "《自动控制原理》第七章课后练习提交", course: "自动控制原理" }] },
  };

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, window.location.href);
    // file:///C:/... previews resolve /api/... as /C:/api/..., unlike HTTP previews.
    const apiOffset = url.pathname.indexOf("/api/");
    if (apiOffset === -1) return originalFetch(input, options);
    const apiPath = url.pathname.slice(apiOffset);
    const data = payloads[apiPath] || { ok: true, project };
    return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  };
})();
