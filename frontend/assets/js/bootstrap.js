/* Dashboard: bootstrap.js; loaded in index.html order. */
    // ---- Init ----
    // Demo mode: prevent fetches from clearing the static sample data
    const isDemoMode = !window.__OPEN_DESIGN_PREVIEW__ && (window.location.protocol === 'file:' || window.location.hostname === '');

    updateGreeting(new Date());
    if (!isDemoMode) {
      initClock();
      loadTodaySchedule();
    }
    tickClock();
    initializeWeatherCampus();

    if (!isDemoMode) {
      loadTodoSourcePreferences();
      fetchWeather();
      fetchTerm();
      fetchCanvasTodos();
      fetchCustomTodos();
      fetchHaokeTodos();
      fetchZhixuemengTodos();
      fetchZhihuishuTodos();
      fetchKetangpaiTodos();
      fetchTongjiojTodos();
      refreshSessionActivity();
    } else {
      window.customToday = '2026-07-25';
      const dueInput = document.getElementById('new-todo-due');
      if (dueInput && !dueInput.value) dueInput.value = window.customToday;
      const updatedEl = document.getElementById('list-updated');
      if (updatedEl) updatedEl.textContent = '';

      canvasItems = [
        { id: 1, title: '《自动控制原理》第七章课后练习提交', course: '自动控制原理', type: '作业', due_str: '2026-07-25', due_ts: '2026-07-25T23:59:00', url: '' },
        { id: 2, title: '《自动控制原理》课件整理与重排版', course: '自动控制原理', type: '课件', due_str: '—', due_ts: null, url: '' },
      ];
      highlightedIds = [];
      hiddenIds = [];
      canvasDeletedIds = [];

      haokeItems = [
        { id: 1, title: '线性代数 第六次直播课签到与随堂练习', course: '线性代数', type: '直播', due_str: '2026-07-23', due_ts: '2026-07-23T20:00:00', url: '' },
      ];
      haokeHighlightedIds = [1];
      haokeHiddenIds = [];
      haokeDeletedIds = [];

      zhixuemengItems = [
        { id: 1, title: '《工程伦理》阶段测试（客观题 40 道）', course: '工程伦理', type: '测验', due_str: '2026-07-27', due_ts: '2026-07-27T23:59:00', url: '' },
      ];
      zhixuemengHighlightedIds = [];
      zhixuemengHiddenIds = [];
      zhixuemengDeletedIds = [];

      zhihuishuItems = [
        { id: 1, title: '《大学物理》第三章作业（光学部分）', course: '大学物理', type: '作业', due_str: '2026-07-26', due_ts: '2026-07-26T23:59:00', url: '' },
      ];
      zhihuishuHighlightedIds = [];
      zhihuishuHiddenIds = [];
      zhihuishuDeletedIds = [];

      ketangpaiItems = [
        { id: 1, title: '1.力的基本概念，力系简化（1）', course: '力学原理A', type: '作业', due_str: '2026-09-22', due_ts: '2026-09-22T23:59:00', url: '' },
      ];
      ketangpaiHighlightedIds = [];
      ketangpaiHiddenIds = [];
      ketangpaiDeletedIds = [];

      tongjiojItems = [
        { id: 'tjoj_590', title: 'HW1线性表', course: '2026秋数据结构与算法设计（刘春梅）', type: '编程作业', due_str: '2026-10-08 23:59', due_ts: '2026-10-08T23:59:59+08:00', url: 'https://oj.tongji.edu.cn/index.php/assignments#1' },
      ];
      tongjiojHighlightedIds = [];
      tongjiojHiddenIds = [];
      tongjiojDeletedIds = [];

      projectItems = [
        { id: 101, project_id: 1, task_id: 11, kind: 'task', title: '全国大学生数学建模竞赛 · 选题与组内分工', project_name: '数学建模竞赛', due_date: '2026-07-27', flagged: false },
      ];

      customItems = [
        { id: 2001, text: '实验室周报提交', due_date: '2026-07-25', labels: ['实验室'], highlighted: false, done: false, subtasks: [] },
        { id: 2002, text: '整理自动化专业笔记归档', due_date: null, labels: ['学习笔记', '归档'], highlighted: false, done: false, subtasks: [] },
      ];

      // Pin the demo clock so tickClock() does not retry /api/clock every second
      serverTime = new Date('2026-07-25T15:19:42').getTime();
      clockStart = Date.now();

      renderUnifiedList();
    }

    const scheduledBackgroundTasks = [];
    function scheduleVisibilityTask(name, fn, intervalMs) {
      scheduledBackgroundTasks.push({
        name,
        fn,
        intervalMs,
        lastRunAt: Date.now(),
      });
    }

    function checkAndRunScheduledTasks() {
      if (document.visibilityState === 'hidden') return;
      const now = Date.now();
      for (const task of scheduledBackgroundTasks) {
        if (now - task.lastRunAt >= task.intervalMs) {
          task.lastRunAt = now;
          try { task.fn(); } catch (_) {}
        }
      }
    }

    if (!isDemoMode) {
      scheduleVisibilityTask('canvas', () => { if (typeof isPlatformConfigured !== 'function' || isPlatformConfigured('canvas')) fetchCanvasTodos(); }, 30 * 60 * 1000);
      scheduleVisibilityTask('haoke', () => { if (typeof isPlatformConfigured !== 'function' || isPlatformConfigured('haoke')) fetchHaokeTodos(); }, 30 * 60 * 1000);
      scheduleVisibilityTask('zhixuemeng', () => { if (typeof isPlatformConfigured !== 'function' || isPlatformConfigured('zhixuemeng')) fetchZhixuemengTodos(); }, 30 * 60 * 1000);
      scheduleVisibilityTask('zhihuishu', () => { if (typeof isPlatformConfigured !== 'function' || isPlatformConfigured('zhihuishu')) fetchZhihuishuTodos(); }, 30 * 60 * 1000);
      scheduleVisibilityTask('ketangpai', () => { if (typeof isPlatformConfigured !== 'function' || isPlatformConfigured('ketangpai')) fetchKetangpaiTodos(); }, 30 * 60 * 1000);
      scheduleVisibilityTask('tongjioj', () => { if (typeof isPlatformConfigured !== 'function' || isPlatformConfigured('tongjioj')) fetchTongjiojTodos(); }, 30 * 60 * 1000);
      scheduleVisibilityTask('term', fetchTerm, 60 * 1000);
      scheduleVisibilityTask('weather', fetchWeather, 60 * 60 * 1000);

      // Periodically check scheduled tasks every 10s (only runs work when tab is visible)
      setInterval(checkAndRunScheduledTasks, 10000);
    }


    // LINK-09: Cross-tab sync and cross-midnight date change detection
    let syncChannel = null;
    try {
      if (typeof BroadcastChannel !== 'undefined') {
        syncChannel = new BroadcastChannel('canvas_dashboard_sync');
        syncChannel.onmessage = (event) => {
          if (event?.data?.type === 'data_changed') {
            debounceRefreshAll();
          }
        };
      }
    } catch (_) {}

    function notifyCrossTabChange(source = 'general') {
      try {
        if (syncChannel) {
          syncChannel.postMessage({ type: 'data_changed', source, timestamp: Date.now() });
        }
        localStorage.setItem('cda_sync_signal', `${Date.now()}_${source}`);
      } catch (_) {}
    }
    window.notifyCrossTabChange = notifyCrossTabChange;

    window.addEventListener('storage', (e) => {
      if (e.key === 'cda_sync_signal' && e.newValue) {
        debounceRefreshAll();
      }
    });

    let debounceTimer = null;
    function debounceRefreshAll() {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        if (typeof refreshWorkspaceSurfaces === 'function') {
          refreshWorkspaceSurfaces();
        } else {
          fetchCustomTodos();
          if (typeof fetchProjectTodos === 'function') fetchProjectTodos();
          if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
        }
      }, 300);
    }

    let lastKnownShanghaiDay = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());

    function checkDateRollOver() {
      const currentShanghaiDay = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
      if (currentShanghaiDay !== lastKnownShanghaiDay) {
        lastKnownShanghaiDay = currentShanghaiDay;
        window.customToday = currentShanghaiDay;
        if (typeof refreshWorkspaceSurfaces === 'function') {
          refreshWorkspaceSurfaces();
        }
      }
    }

    function handleVisibilityResume() {
      checkDateRollOver();
      checkAndRunScheduledTasks();
    }

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        handleVisibilityResume();
      }
    });
    window.addEventListener('focus', handleVisibilityResume);
