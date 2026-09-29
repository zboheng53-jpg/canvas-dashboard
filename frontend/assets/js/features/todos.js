/* Dashboard: features/todos.js; loaded in index.html order. */
    // ---- Unified Todo Data ----
    let canvasItems = [];
    let customItems = [];
    let customDataRevision = 0;
    let customFetchRequest = 0;
    let projectItems = [];
    let expandedTodoKeys = [];
    let expandedCustomTodoIds = expandedTodoKeys;
    function todoKey(source, todoId) {
      return `${source}:${todoId}`;
    }
    let openMobileActionItemId = null;
    let hiddenIds = [];
    let highlightedIds = [];

    let haokeItems = [];
    let haokeHiddenIds = [];
    let haokeHighlightedIds = [];

    let zhixuemengItems = [];
    let zhixuemengHiddenIds = [];
    let zhixuemengHighlightedIds = [];
    let zhihuishuItems = [];
    let zhihuishuHiddenIds = [];
    let zhihuishuHighlightedIds = [];
    let ketangpaiItems = [];
    let ketangpaiHiddenIds = [];
    let ketangpaiHighlightedIds = [];
    let tongjiojItems = [];
    let tongjiojHiddenIds = [];
    let tongjiojHighlightedIds = [];
    let canvasDeletedIds = [];
    let haokeDeletedIds = [];
    let zhixuemengDeletedIds = [];
    let zhihuishuDeletedIds = [];
    let ketangpaiDeletedIds = [];
    let tongjiojDeletedIds = [];


    function getTodayDateString() {
      if (window.customToday) return window.customToday;
      const d = new Date();
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    }

    function sortSubtasks(subtasks) {
      return [...subtasks].sort((a, b) => {
        if (a.done === b.done) return 0;
        return a.done ? 1 : -1;
      });
    }

    function setNewTodoDueDefault(today) {
      const dueInput = document.getElementById('new-todo-due');
      if (dueInput && !dueInput.value) dueInput.value = today;
    }

    function toggleMobileActions(itemId) {
      openMobileActionItemId = openMobileActionItemId === itemId ? null : itemId;
      renderUnifiedList();
    }

    async function fetchCustomTodos() {
      const revision = customDataRevision;
      const requestId = ++customFetchRequest;
      try {
        const resp = await fetch('/api/custom/todos');
        const result = await resp.json();
        if (revision !== customDataRevision || requestId !== customFetchRequest) return;
        customItems = result.data || [];
        customItems.forEach(todo => {
          if (todo.subtasks) {
            todo.subtasks.forEach((subtask, idx) => {
              if (subtask.id == null) {
                subtask.id = idx + 1;
              }
            });
            todo.subtasks = sortSubtasks(todo.subtasks);
          }
        });
        window.customToday = result.today || new Date().toISOString().split('T')[0];
        setNewTodoDueDefault(window.customToday);
        renderUnifiedList();
      } catch (e) {
        console.error('Failed to fetch custom todos:', e);
        window.customToday = window.customToday || new Date().toISOString().split('T')[0];
        setNewTodoDueDefault(window.customToday);
      }
    }

    const TODO_SOURCE_ORDER = ['canvas', 'haoke', 'zhixuemeng', 'zhihuishu', 'ketangpai', 'tongjioj', 'project', 'custom'];
    const TODO_PLATFORM_SOURCES = new Set(['canvas', 'haoke', 'zhixuemeng', 'zhihuishu', 'ketangpai', 'tongjioj']);
    let visibleTodoSources = new Set(TODO_SOURCE_ORDER);
    let todoSourcePreferenceRevision = 0;
    let todoSourcePreferenceSaveTimer = null;
    let todoSourceFilter = 'all';

    function todoSourceIsAvailable(source, counts) {
      if (!TODO_PLATFORM_SOURCES.has(source)) return true;
      const sync = platformSyncs[source];
      return (counts[source] || 0) > 0 || Boolean(sync && sync.connection_state !== 'unconfigured');
    }

    async function loadTodoSourcePreferences() {
      const status = document.getElementById('todo-source-manager-status');
      try {
        const response = await fetch('/api/dashboard/preferences');
        const result = await response.json();
        if (!response.ok || !result.ok || !Array.isArray(result.visible_todo_sources)) {
          throw new Error(result.error || '读取失败');
        }
        visibleTodoSources = new Set(
          result.visible_todo_sources.filter((source) => TODO_SOURCE_ORDER.includes(source))
        );
        if (status) status.textContent = '设置会保存到你的账户；可选平台随连接状态自动更新。';
        renderUnifiedList();
        renderDashboardSyncStatus();
        updateAttentionStatus();
      } catch (error) {
        if (status) status.textContent = '暂时无法读取设置，当前使用默认标签。';
      }
    }

    function setTodoSourceVisibility(source, visible) {
      if (!TODO_SOURCE_ORDER.includes(source)) return;
      if (visible) visibleTodoSources.add(source);
      else visibleTodoSources.delete(source);
      if (!visible && todoSourceFilter === source) todoSourceFilter = 'all';
      renderUnifiedList();
      renderDashboardSyncStatus();
      updateAttentionStatus();

      const revision = ++todoSourcePreferenceRevision;
      const status = document.getElementById('todo-source-manager-status');
      if (status) status.textContent = '正在保存…';
      clearTimeout(todoSourcePreferenceSaveTimer);
      todoSourcePreferenceSaveTimer = setTimeout(async () => {
        const requestedSources = TODO_SOURCE_ORDER.filter((item) => visibleTodoSources.has(item));
        try {
          const response = await fetch('/api/dashboard/preferences', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({visible_todo_sources: requestedSources}),
          });
          const result = await response.json();
          if (!response.ok || !result.ok) throw new Error(result.error || '保存失败');
          if (revision !== todoSourcePreferenceRevision) return;
          visibleTodoSources = new Set(result.visible_todo_sources || requestedSources);
          if (status) status.textContent = '已保存；可选平台随连接状态自动更新。';
          renderUnifiedList();
          renderDashboardSyncStatus();
          updateAttentionStatus();
        } catch (error) {
          if (revision !== todoSourcePreferenceRevision) return;
          if (status) status.textContent = '保存失败，请稍后重试。';
        }
      }, 250);
    }

    function setTodoSourceFilter(source) {
      todoSourceFilter = source;
      const selectEl = document.getElementById('todo-source-select');
      if (selectEl && selectEl.value !== source) {
        selectEl.value = source;
      }
      document.querySelectorAll('[data-todo-source]').forEach((element) => {
        const sourceVal = element.dataset.todoSource || element.value;
        const isActive = sourceVal === source;
        element.classList.toggle('is-active', isActive);
        if (element.tagName === 'BUTTON') {
          element.setAttribute('aria-pressed', String(isActive));
        }
      });
      renderUnifiedList();
    }

    let collapsedTodoGroups = new Set(['previous']);
    function toggleTodoGroup(key) {
      if (collapsedTodoGroups.has(key)) {
        collapsedTodoGroups.delete(key);
      } else {
        collapsedTodoGroups.add(key);
      }
      renderUnifiedList();
    }

    let deletingCustomIds = new Set();

    function renderTodoSourceFilters(items) {
      const labels = {
        all: '全部',
        canvas: 'Canvas',
        haoke: '好课',
        zhixuemeng: '智学盟',
        zhihuishu: '智慧树',
        ketangpai: '课堂派',
        tongjioj: '同济OJ',
        project: '项目',
        custom: '自定义',
      };
      const counts = { all: items.filter(it => !it.is_previous).length, canvas: 0, haoke: 0, zhixuemeng: 0, zhihuishu: 0, ketangpai: 0, tongjioj: 0, project: 0, custom: 0 };
      items.forEach((item) => {
        if (item.is_previous) return;
        if (counts[item.source] !== undefined) counts[item.source] += 1;
      });
      const displayedSources = new Set(
        TODO_SOURCE_ORDER.filter((source) => todoSourceIsAvailable(source, counts) && visibleTodoSources.has(source))
      );
      if (todoSourceFilter !== 'all' && !displayedSources.has(todoSourceFilter)) todoSourceFilter = 'all';

      const selectEl = document.getElementById('todo-source-select');
      if (selectEl) {
        selectEl.value = todoSourceFilter;
        Array.from(selectEl.options).forEach((opt) => {
          const source = opt.value || opt.dataset.todoSource;
          if (labels[source]) {
            opt.textContent = `${labels[source]} (${counts[source] || 0})`;
            const isDisplayed = source === 'all' || displayedSources.has(source);
            opt.hidden = !isDisplayed;
            opt.disabled = !isDisplayed;
          }
        });
      }

      document.querySelectorAll('button[data-todo-source]').forEach((button) => {
        const source = button.dataset.todoSource;
        button.classList.toggle('hidden', source !== 'all' && !displayedSources.has(source));
        const countSpan = button.querySelector('.n') || document.getElementById('src-count-' + source);
        if (countSpan) {
          countSpan.textContent = String(counts[source] || 0);
        } else {
          button.textContent = `${labels[source]} (${counts[source] || 0})`;
        }
        const isActive = source === todoSourceFilter;
        button.classList.toggle('is-on', isActive);
        button.classList.toggle('is-active', isActive);
        button.setAttribute('aria-pressed', String(isActive));
      });

      document.querySelectorAll('[data-todo-source-option]').forEach((option) => {
        const source = option.dataset.todoSourceOption;
        const available = todoSourceIsAvailable(source, counts);
        option.classList.toggle('hidden', !available);
        const input = option.querySelector('[data-todo-source-visibility]');
        if (input) {
          input.disabled = !available;
          input.checked = visibleTodoSources.has(source);
        }
      });
    }

    function timeGroupForTodo(item) {
      const today = window.customToday || new Date().toISOString().slice(0, 10);
      const weekEnd = new Date(`${today}T00:00:00Z`);
      weekEnd.setUTCDate(weekEnd.getUTCDate() + 6);
      const dueDate = item.due_ts ? item.due_ts.slice(0, 10) : '';
      if (item.done) return 'today';
      if (dueDate && dueDate <= today) return 'today';
      if (dueDate && dueDate <= weekEnd.toISOString().slice(0, 10)) return 'week';
      return 'later';
    }

    function buildTodoGroups(items) {
      // 设计稿分组：已逾期 / 今天 / 此前未完成 / 明天 / 本周内 / 更晚 / 无日期 / 已完成
      const labels = { overdue: '已逾期', today: '今天', previous: '此前未完成', tomorrow: '明天', week: '本周内', later: '更晚', nodate: '无日期', completed: '已完成' };
      const groups = { overdue: [], today: [], previous: [], tomorrow: [], week: [], later: [], nodate: [], completed: [] };
      const todayStr = window.customToday || new Date().toISOString().slice(0, 10);
      const today = new Date(todayStr + 'T00:00:00');
      const tomorrow = new Date(today.getTime() + 86400000);
      const weekEnd = new Date(today.getTime() + 7 * 86400000);
      const dueKey = (item) => item.due_ts || '9999-12-31T23:59:59';
      items.forEach((item) => {
        if (item.done) { groups.completed.push(item); return; }
        if (item.isTodayAction && (!item.due_ts || item.due_ts.slice(0, 10) >= todayStr)) { groups.today.push(item); return; }
        if (item.is_previous) { groups.previous.push(item); return; }
        if (!item.due_ts) { groups.nodate.push(item); return; }
        const dueDate = new Date(item.due_ts.slice(0, 10) + 'T00:00:00');
        if (dueDate < today) { groups.overdue.push(item); return; }
        if (dueDate.getTime() === today.getTime()) { groups.today.push(item); return; }
        if (dueDate.getTime() === tomorrow.getTime()) { groups.tomorrow.push(item); return; }
        if (dueDate <= weekEnd) { groups.week.push(item); return; }
        groups.later.push(item);
      });
      const sortGroup = (arr) => arr.sort((a, b) =>
        (a.done ? 1 : 0) - (b.done ? 1 : 0) ||
        (b.manualHighlighted ? 1 : 0) - (a.manualHighlighted ? 1 : 0) ||
        dueKey(a).localeCompare(dueKey(b)) || a._stableIndex - b._stableIndex
      );
      Object.values(groups).forEach(sortGroup);
      const order = ['overdue', 'today', 'previous', 'tomorrow', 'week', 'later', 'nodate', 'completed'];
      return order
        .filter((k) => groups[k].length)
        .map((k) => ({ key: k, title: labels[k], items: groups[k] }));
    }

    function compactTodoDateLabel(item, today) {
      const hasDeadline = Boolean(item.due_ts || (item.due_str && !['—', '--'].includes(item.due_str.trim())));
      let day = (hasDeadline ? item.due_str : item.plannedOn) || '';
      let time = '';
      if (hasDeadline && item.due_ts) {
        const timestamp = new Date(item.due_ts);
        if (!Number.isNaN(timestamp.getTime())) {
          day = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(timestamp);
          if (!['custom', 'project'].includes(item.source) && /\d{2}:\d{2}/.test(item.due_str || '')) {
            time = new Intl.DateTimeFormat('en-GB', {timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}).format(timestamp);
          }
        }
      } else if (!hasDeadline && item.occurrences?.length) {
        time = item.occurrences[0].start_time || '';
      }
      if (!day) return '未设截止';
      const match = day.match(/^(\d{4})-(\d{2})-(\d{2})/);
      if (match) {
        const iso = match[0];
        const offset = Math.round((Date.parse(iso) - Date.parse(today)) / 86400000);
        day = offset === 0 ? '今天' : offset === 1 ? '明天' : offset === -1 ? '昨天'
          : `${match[1] === today.slice(0, 4) ? '' : match[1] + '/'}${Number(match[2])}/${Number(match[3])}`;
      }
      return `${hasDeadline ? '截止' : '计划'} ${day}${time ? ' ' + time : ''}`;
    }

    function renderUnifiedList() {
      const container = document.getElementById('todo-list');
      // Keep the live editor (and its handlers) until the user commits or cancels.
      // Each editor renders again on exit, using the latest fetched data.
      if (container.querySelector('.inline-edit-input, .inline-edit-date-input')) return;
      const savedScrollTop = container.scrollTop;
      // Background refreshes must not erase a subtask the user is still typing.
      const subtaskDrafts = Array.from(container.querySelectorAll('.subtask-add-row input')).map(input => ({
        id: input.id, value: input.value, focused: input === document.activeElement,
        start: input.selectionStart, end: input.selectionEnd,
      }));

      // Build unified items
      let unified = [];

      // LINK-05: collect today scheduled action references
      const today = window.customToday || new Date().toISOString().split('T')[0];
      const todayScheduledRefs = new Set();
      if (window.workspaceTodayData?.days?.[0]?.timed) {
        for (const e of window.workspaceTodayData.days[0].timed) {
          if (e.action_ref && !e.occurrence_done && !e.done) {
            todayScheduledRefs.add(e.action_ref);
          }
        }
      }

      canvasItems.forEach(item => {
        if (canvasDeletedIds.includes(item.id)) return;
        const isHidden = hiddenIds.includes(item.id);
        const isHighlighted = highlightedIds.includes(item.id);
        unified.push({
          id: `c${item.id}`,
          source: 'canvas',
          title: item.title,
          course: item.course,
          due_str: item.due_str,
          due_ts: item.due_ts,
          type: item.type,
          url: item.url,
          done: Boolean(item.done) || isHidden,
          hidden: isHidden,
          highlighted: isHighlighted,
          rawId: item.id,
          manualHighlighted: isHighlighted,
          subtasks: item.subtasks || [],
          disconnected: platformSyncs.canvas?.connection_state === 'disconnected',
          isTodayAction: todayScheduledRefs.has(`canvas:${item.id}`),
        });
      });

      haokeItems.forEach(item => {
        if (haokeDeletedIds.includes(item.id)) return;
        const isHidden = haokeHiddenIds.includes(item.id);
        const isHighlighted = haokeHighlightedIds.includes(item.id);
        unified.push({
          id: `h${item.id}`,
          source: 'haoke',
          title: item.title,
          course: item.course,
          due_str: item.due_str,
          due_ts: item.due_ts,
          type: item.type,
          url: item.url,
          done: Boolean(item.done) || isHidden,
          hidden: isHidden,
          highlighted: isHighlighted,
          rawId: item.id,
          manualHighlighted: isHighlighted,
          subtasks: item.subtasks || [],
          disconnected: platformSyncs.haoke?.connection_state === 'disconnected',
          isTodayAction: todayScheduledRefs.has(`haoke:${item.id}`),
        });
      });

      zhixuemengItems.forEach(item => {
        if (zhixuemengDeletedIds.includes(item.id)) return;
        const isHidden = zhixuemengHiddenIds.includes(item.id);
        const isHighlighted = zhixuemengHighlightedIds.includes(item.id);
        unified.push({
          id: `z${item.id}`,
          source: 'zhixuemeng',
          title: item.title,
          course: item.course,
          due_str: item.due_str,
          due_ts: item.due_ts,
          type: item.type,
          url: item.url,
          done: Boolean(item.done) || isHidden,
          hidden: isHidden,
          highlighted: isHighlighted,
          rawId: item.id,
          manualHighlighted: isHighlighted,
          subtasks: item.subtasks || [],
          disconnected: platformSyncs.zhixuemeng?.connection_state === 'disconnected',
          isTodayAction: todayScheduledRefs.has(`zhixuemeng:${item.id}`),
        });
      });

      zhihuishuItems.forEach(item => {
        if (zhihuishuDeletedIds.includes(item.id)) return;
        const isHidden = zhihuishuHiddenIds.includes(item.id);
        const isHighlighted = zhihuishuHighlightedIds.includes(item.id);
        unified.push({
          id: `s${item.id}`,
          source: 'zhihuishu',
          title: item.title,
          course: item.course,
          due_str: item.due_str,
          due_ts: item.due_ts,
          type: item.type || 'zhihuishu',
          url: item.url,
          done: Boolean(item.done) || isHidden,
          hidden: isHidden,
          highlighted: isHighlighted,
          rawId: item.id,
          manualHighlighted: isHighlighted,
          subtasks: item.subtasks || [],
          disconnected: platformSyncs.zhihuishu?.connection_state === 'disconnected',
          isTodayAction: todayScheduledRefs.has(`zhihuishu:${item.id}`),
        });
      });

      ketangpaiItems.forEach(item => {
        if (ketangpaiDeletedIds.includes(item.id)) return;
        const isHidden = ketangpaiHiddenIds.includes(item.id);
        const isHighlighted = ketangpaiHighlightedIds.includes(item.id);
        unified.push({
          id: `k${item.id}`,
          source: 'ketangpai',
          title: item.title,
          course: item.course,
          due_str: item.due_str,
          due_ts: item.due_ts,
          type: item.type || 'ketangpai',
          url: item.url,
          done: Boolean(item.done) || isHidden,
          hidden: isHidden,
          highlighted: isHighlighted,
          rawId: item.id,
          manualHighlighted: isHighlighted,
          subtasks: item.subtasks || [],
          disconnected: platformSyncs.ketangpai?.connection_state === 'disconnected',
          isTodayAction: todayScheduledRefs.has(`ketangpai:${item.id}`),
        });
      });

      tongjiojItems.forEach(item => {
        if (tongjiojDeletedIds.includes(item.id)) return;
        const isHidden = tongjiojHiddenIds.includes(item.id);
        const isHighlighted = tongjiojHighlightedIds.includes(item.id);
        unified.push({
          id: `t${item.id}`,
          source: 'tongjioj',
          title: item.title,
          course: item.course,
          due_str: item.due_str,
          due_ts: item.due_ts,
          type: item.type || '同济OJ',
          url: item.url,
          done: Boolean(item.done) || isHidden,
          hidden: isHidden,
          highlighted: isHighlighted,
          rawId: item.id,
          manualHighlighted: isHighlighted,
          subtasks: item.subtasks || [],
          disconnected: platformSyncs.tongjioj?.connection_state === 'disconnected',
          isTodayAction: todayScheduledRefs.has(`tongjioj:${item.id}`),
        });
      });

      projectItems.forEach(item => {
        const category = item.project_category || '项目';
        unified.push({
          id: `p${item.id}`,
          source: 'project',
          title: item.title,
          course: item.project_name,
          category: category,
          isNextAction: Boolean(item.is_next_action),
          isMainProject: Boolean(item.is_main),
          groupName: item.group_name || '',
          due_str: item.due_date || '',
          due_ts: item.due_date ? `${item.due_date}T23:59:59` : null,
          type: category,
          url: '',
          done: false,
          hidden: false,
          highlighted: Boolean(item.flagged),
          rawId: item.id,
          manualHighlighted: Boolean(item.flagged),
          projectId: item.project_id,
          taskId: item.task_id,
          projectKind: item.kind,
          isTodayAction: Boolean(item.is_today),
          plannedOn: item.planned_on || '',
          occurrences: item.occurrences || [],
          ref: item.ref,
        });
      });

      customItems.forEach(item => {
        const isOverdue = item.due_date && item.due_date < today && !item.done;
        const displayHighlighted = (item.highlighted || isOverdue) && !item.done;
        const isTodayAction = Boolean(item.isTodayAction || (item.ref && todayScheduledRefs.has(item.ref)));
        unified.push({
          id: `x${item.id}`,
          source: 'custom',
          title: item.text,
          course: '',
          labels: item.labels || [],
          due_str: item.due_date || '',
          due_ts: item.due_date ? `${item.due_date}T23:59:59+08:00` : null,
          type: '自定义',
          url: '',
          done: item.done,
          hidden: false,
          highlighted: displayHighlighted,
          rawId: item.id,
          manualHighlighted: item.highlighted || false,
          subtasks: item.subtasks || [],
          is_recurring: Boolean(item.is_recurring),
          series_id: item.series_id,
          original_due_date: item.original_due_date,
          repeat_label: item.repeat_label,
          ref: item.ref,
          isTodayAction: isTodayAction,
        });
      });

      (window.projectPreviousActions || []).forEach(item => {
        if (!unified.some(u => u.ref === item.ref)) {
          unified.push({
            id: `p${item.id}`,
            source: 'project',
            title: item.title,
            course: item.project_name,
            category: '此前未完成',
            isNextAction: false,
            isMainProject: false,
            groupName: '',
            due_str: item.due_date || item.planned_on || '',
            due_ts: item.due_date ? `${item.due_date}T23:59:59` : null,
            type: '此前未完成',
            url: '',
            done: false,
            hidden: false,
            highlighted: false,
            rawId: item.id,
            manualHighlighted: false,
            projectId: item.project_id,
            taskId: item.task_id,
            projectKind: 'project_task',
            isTodayAction: false,
            is_previous: true,
            plannedOn: item.planned_on || '',
            occurrences: item.occurrences || [],
            ref: item.ref,
          });
        }
      });

      // Stable sorting happens inside each requested time group: highlighted
      // tasks never leap across a due-date group, and completed tasks remain
      // at that group's quiet bottom until their normal retention expires.
      unified.forEach((item, index) => { item._stableIndex = index; });

      renderTodoSourceFilters(unified);
      updateStatsBar(unified);
      // 侧栏 nav-count 数字：今日总览的未完成待办数；长期项目的进行中数（从 #active-project-count 读）
      const overviewCount = unified.filter((it) => !it.done && !it.hidden && !it.is_previous).length;
      const overviewEl = document.querySelector('[data-nav-count="overview"]');
      if (overviewEl) {
        if (overviewCount > 0) { overviewEl.textContent = overviewCount; overviewEl.hidden = false; }
        else { overviewEl.textContent = ''; overviewEl.hidden = true; }
      }

      const todayStr = window.customToday || new Date().toISOString().split('T')[0];

      const filteredItems = todoSourceFilter === 'all'
        ? unified
        : unified.filter((item) => item.source === todoSourceFilter);

      if (filteredItems.length === 0) {
        let emptyTitle = '没有待办事项';
        let emptyDesc = '新的课程任务同步后会显示在这里。';
        if (todoSourceFilter !== 'all') {
          emptyTitle = '该来源暂无待办事项';
          emptyDesc = '切换来源或清除筛选后可查看其他待办。';
        }
        container.innerHTML = `
          <div class="ui-empty empty-state">
            <span class="ui-empty__art" aria-hidden="true">
              <svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/>
                <rect x="18" y="14" width="36" height="36" rx="6" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/>
                <rect x="24" y="22" width="8" height="8" rx="2" stroke="#3B82F6" stroke-width="1.5" fill="#FFFFFF"/>
                <path d="M26 26L28 28L30 25" stroke="#2563EB" stroke-width="1.5" stroke-linecap="round"/>
                <rect x="36" y="25" width="12" height="3" rx="1.5" fill="#60A5FA"/>
                <rect x="24" y="36" width="20" height="3" rx="1.5" fill="#BFDBFE"/>
                <path d="M54 14L55 17L58 18L55 19L54 22L53 19L50 18L53 17L54 14Z" fill="#3B82F6"/>
              </svg>
            </span>
            <strong>${escapeHtml(emptyTitle)}</strong>
            <p>${escapeHtml(emptyDesc)}</p>
          </div>`;
        return;
      }


      const renderTodoItem = (item) => {
        const isDismissed = item.done || item.hidden;
        const manualFlag = item.manualHighlighted || false;

        let urgencyClass = '';
        if (!isDismissed) {
          const effectiveDueTs = item.due_ts;
          if (effectiveDueTs) {
            const dueStr = effectiveDueTs.split('T')[0];
            const dueTime = new Date(effectiveDueTs).getTime();
            const now = Date.now();
            const hoursLeft = (dueTime - now) / 3600000;

            if (dueStr < todayStr || hoursLeft < 0) {
              urgencyClass = 'urgent is-overdue';
            } else if (dueStr === todayStr || (hoursLeft >= 0 && hoursLeft <= 24)) {
              urgencyClass = 'is-today';
            } else if (hoursLeft <= 72) {
              urgencyClass = 'approaching is-approaching';
            } else {
              urgencyClass = 'remote is-normal';
            }
          } else if (item.isTodayAction) {
            urgencyClass = 'is-today';
          } else {
            urgencyClass = 'remote';
          }
        }

        const flagIcon = manualFlag ? '&#x2691;' : '&#x2690;';
        const flagTitle = manualFlag ? '\u53d6\u6d88\u6807\u7ea2' : '\u6807\u7ea2';
        const flagClass = manualFlag ? 'btn-flag active' : 'btn-flag';
        const dismissTitle = isDismissed ? '\u53d6\u6d88\u5b8c\u6210' : '\u5b8c\u6210';
        const uiListStateClass = urgencyClass.includes('is-overdue')
          ? ' ui-list-item--danger'
          : urgencyClass.includes('approaching')
            ? ' ui-list-item--warning'
            : '';
        const uiListMutedClass = isDismissed ? ' ui-list-item--muted' : '';

        let actionsHtml = '';
        if (item.source === 'canvas') {
          actionsHtml = `
            <button class="todo-action-button ${flagClass}" onclick="toggleHighlight('${item.id}', ${manualFlag})" title="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>
            <button class="btn-dismiss" onclick="togglePlatformCompletion('canvas', '${item.rawId}', ${item.done})" title="${dismissTitle}">${item.done ? '↺' : '✓'}</button>
            <button class="btn-delete" onclick="toggleCanvasDelete('${item.rawId}')" title="\u5220\u9664">&#x1f5d1;</button>
          `;
        } else if (item.source === 'haoke') {
          actionsHtml = `
            <button class="todo-action-button ${flagClass}" onclick="toggleHaokeHighlight('${item.id}', ${manualFlag})" title="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>
            <button class="btn-dismiss" onclick="togglePlatformCompletion('haoke', ${item.rawId}, ${item.done})" title="${dismissTitle}">${item.done ? '↺' : '✓'}</button>
            <button class="btn-delete" onclick="toggleHaokeDelete(${item.rawId})" title="\u5220\u9664">&#x1f5d1;</button>
          `;
        } else if (item.source === 'custom') {
          if (item.is_recurring) {
            actionsHtml = `
              <button class="btn-dismiss" onclick="toggleRecurringCheck(${item.series_id}, '${item.original_due_date}', ${item.done})" title="${dismissTitle}">${item.done ? '↺' : '✓'}</button>
              <button class="todo-action-button btn-action-skip" onclick="skipRecurringOccurrence(${item.series_id}, '${item.original_due_date}')" title="跳过本次" style="background:none; border:none; cursor:pointer; font-size:14px; color:var(--text-muted, #888); padding:0 4px;" aria-label="跳过本次">⏭</button>
              <button class="btn-delete" onclick="deleteRecurringSeries(${item.series_id})" title="删除重复待办">&#x1f5d1;</button>
            `;
          } else {
            const isDeleting = deletingCustomIds.has(item.rawId);
            actionsHtml = `
              <button class="todo-action-button ${flagClass}" onclick="toggleCustomHighlight(${item.rawId}, ${manualFlag})" title="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>
              <button class="btn-dismiss" onclick="toggleTodoCheck(${item.rawId}, ${item.done})" title="${dismissTitle}">${item.done ? '↺' : '✓'}</button>
              <button class="btn-delete" onclick="toggleCustomDelete(${item.rawId})" ${isDeleting ? 'disabled aria-busy="true"' : ''} title="\u5220\u9664">&#x1f5d1;</button>
            `;
          }
        } else if (item.source === 'zhixuemeng') {
          actionsHtml = `
            <button class="todo-action-button ${flagClass}" onclick="toggleZhixuemengHighlight('${item.id.substring(1)}', ${manualFlag})" title="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>
            <button class="btn-dismiss" onclick="togglePlatformCompletion('zhixuemeng', '${item.id.substring(1)}', ${item.done})" title="${dismissTitle}">${item.done ? '↺' : '✓'}</button>
            <button class="btn-delete" onclick="toggleZhixuemengDelete('${item.id.substring(1)}')" title="\u5220\u9664">&#x1f5d1;</button>
          `;
        } else if (item.source === 'zhihuishu') {
          actionsHtml = `
            <button class="todo-action-button ${flagClass}" onclick="toggleZhihuishuHighlight('${item.rawId}', ${manualFlag})" title="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>
            <button class="btn-dismiss" onclick="togglePlatformCompletion('zhihuishu', '${item.rawId}', ${item.done})" title="${dismissTitle}">${item.done ? '↺' : '✓'}</button>
            <button class="btn-delete" onclick="toggleZhihuishuDelete('${item.rawId}')" title="\u5220\u9664">&#x1f5d1;</button>
          `;
        } else if (item.source === 'ketangpai') {
          actionsHtml = `
            <button class="todo-action-button ${flagClass}" onclick="toggleKetangpaiHighlight('${item.rawId}', ${manualFlag})" title="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>
            <button class="btn-dismiss" onclick="togglePlatformCompletion('ketangpai', '${item.rawId}', ${item.done})" title="${dismissTitle}">${item.done ? '↺' : '✓'}</button>
            <button class="btn-delete" onclick="toggleKetangpaiDelete('${item.rawId}')" title="\u5220\u9664">&#x1f5d1;</button>
          `;
        } else if (item.source === 'tongjioj') {
          actionsHtml = `
            <button class="todo-action-button ${flagClass}" onclick="toggleTongjiojHighlight('${item.rawId}', ${manualFlag})" title="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>
            <button class="btn-dismiss" onclick="togglePlatformCompletion('tongjioj', '${item.rawId}', ${item.done})" title="${dismissTitle}">${item.done ? '↺' : '✓'}</button>
            <button class="btn-delete" onclick="toggleTongjiojDelete('${item.rawId}')" title="\u5220\u9664">&#x1f5d1;</button>
          `;
        } else if (item.source === 'project') {
          actionsHtml = `
            <button class="todo-action-button ${flagClass}" onclick="toggleProjectTodoFlag(${item.projectId}, ${item.taskId === null ? 'null' : item.taskId}, '${item.projectKind}', ${manualFlag})" title="${flagTitle}" aria-label="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>
            <button class="btn-dismiss" onclick="completeProjectTodo(${item.projectId}, ${item.taskId === null ? 'null' : item.taskId}, '${item.projectKind}')" title="完成" aria-label="完成">✓</button>
            <button class="btn-delete" onclick="deleteProjectTodo(${item.projectId}, ${item.taskId === null ? 'null' : item.taskId}, '${item.projectKind}')" title="\u5220\u9664" aria-label="\u5220\u9664">&#x1f5d1;</button>
          `;
        }

        const safeUrl = sanitizeExternalUrl(item.url);
        const titleHtml = item.is_recurring
          ? `<button type="button" class="ui-button ui-button--text ui-list-item__title item-title action-title-button" onclick="openActionDetail('${item.ref}')">${escapeHtml(item.title)}</button>`
          : (item.source === 'custom'
            ? `<span class="ui-list-item__title item-title item-title-plain editable-title" data-id="${item.rawId}" data-field="text">${escapeHtml(item.title)}</span>`
            : (item.source === 'project'
              ? `<button type="button" class="ui-button ui-button--text ui-list-item__title item-title action-title-button" onclick="openActionDetail('${item.taskId === null ? 'project_due:' + item.projectId : 'project:' + item.projectId + ':' + item.taskId}')">${escapeHtml(item.title)}</button>`
              : (safeUrl ? `<a class="ui-list-item__title item-title" href="${safeUrl}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</a>` : `<span class="ui-list-item__title item-title item-title-plain">${escapeHtml(item.title)}</span>`)));
        const dueLabel = `<span class="todo-date-desktop">${escapeHtml(item.due_str || (item.source === 'project' ? item.plannedOn : '') || '')}</span><span class="todo-date-mobile">${escapeHtml(compactTodoDateLabel(item, todayStr))}</span>`;
        const dueHtml = (item.source === 'custom' && !item.is_recurring)
          ? `<span class="ui-list-item__meta item-due editable-due" data-id="${item.rawId}" data-field="due_date" data-value="${escapeHtml(item.due_str || '')}">${dueLabel}</span>`
          : item.source === 'project'
            ? `<button class="ui-button ui-button--text ui-list-item__meta item-due project-due-editable" data-project-id="${item.projectId}" data-task-id="${item.taskId === null ? '' : item.taskId}" data-project-kind="${item.projectKind}" data-date-field="${!item.due_str && item.isTodayAction ? 'planned_on' : 'due_date'}" data-date-value="${item.due_str || item.plannedOn}" aria-label="${!item.due_str && item.isTodayAction ? '修改计划日期' : '修改截止日期'}" title="${!item.due_str && item.isTodayAction ? '计划推进：' + (item.plannedOn || '') + '（点击修改）' : '截止日期：' + (item.due_str || item.plannedOn || '') + '（点击修改）'}">${dueLabel}</button>`
            : `<span class="ui-list-item__meta item-due">${dueLabel}</span>`;

        const srcLabels = { canvas: 'Canvas', haoke: '好课', zhixuemeng: '智学盟', zhihuishu: '智慧树', ketangpai: '课堂派', tongjioj: '同济OJ', project: '项目', custom: '自定义' };
        const tagLabel = srcLabels[item.source] || item.type || '';
        const tagHtml = tagLabel ? `<span class="ui-source-tag ui-source-tag--${item.source}">${escapeHtml(tagLabel)}</span>` : '';

        // courseHtml 改为整合进副标题，详见下方 rowHtml 重构
        let courseHtml = '';
        if (item.source === 'project') {
          courseHtml = `<button class="ui-button ui-button--text ui-list-item__meta item-course project-todo-link" onclick="openProjectsView(${item.projectId})">${escapeHtml(item.course)} ↗</button>`;
        } else if (item.course) {
          courseHtml = `<span class="ui-list-item__meta item-course">${escapeHtml(item.course)}</span>`;
        } else if (item.labels && item.labels.length > 0) {
          courseHtml = `<span class="ui-tag item-course label-badge">${escapeHtml(item.labels[0])}</span>`;
        } else {
          courseHtml = `<span class="ui-list-item__meta item-course item-course-empty">—</span>`;
        }
        const labelsHtml = '';

        const subtasks = item.subtasks || [];
        const supportsSubtasks = ['custom', 'canvas', 'haoke', 'zhixuemeng', 'zhihuishu', 'ketangpai', 'tongjioj'].includes(item.source) && !item.is_recurring;
        const itemKey = todoKey(item.source, item.rawId);
        const isSubtaskExpanded = supportsSubtasks && (expandedTodoKeys.includes(itemKey) || (item.source === 'custom' && expandedCustomTodoIds.includes(item.rawId)));
        const subtaskToggleLabel = isSubtaskExpanded ? '\u6536\u8d77\u5b50\u4efb\u52a1' : '\u5c55\u5f00\u5b50\u4efb\u52a1';
        const subtaskToggleIcon = isSubtaskExpanded ? '&#x25be;' : '&#x25b8;';
        const sourceArg = JSON.stringify(item.source);
        const rawIdArg = JSON.stringify(String(item.rawId));
        const subtaskToggleHtml = supportsSubtasks
          ? `<button class="subtask-toggle" onclick='toggleSubtasks(${sourceArg}, ${rawIdArg})' title="${subtaskToggleLabel}" aria-label="${subtaskToggleLabel}">${subtaskToggleIcon}</button>`
          : '<span class="subtask-toggle subtask-toggle-placeholder" aria-hidden="true"></span>';
        const mobileActionsOpen = openMobileActionItemId === item.id;


        // 设计稿两行结构：body（上：标题+副标题）+ right（下：来源+截止胶囊+操作）
        // 副标题：课程名 · 类型 · 截止时间（与原 .item-course 合并到副标题）
        const metaParts = [];
        if (item.is_recurring) {
          metaParts.push(`↻ 重复待办 · ${escapeHtml(item.repeat_label || '每周')}`);
        } else if (item.course) {
          metaParts.push(item.source === 'project'
            ? `<button type="button" class="project-todo-link" onclick="openProjectsView(${item.projectId})">${escapeHtml(item.course)}</button>`
            : escapeHtml(item.course));
        }
        if (item.groupName) metaParts.push(escapeHtml(item.groupName));
        if (item.plannedOn && item.due_str) metaParts.push(`计划 ${escapeHtml(item.plannedOn)}`);
        if (item.occurrences?.length) metaParts.push(item.occurrences.map(e => `${escapeHtml(e.start_time)}–${escapeHtml(e.end_time)}`).join('、'));
        if (item.type && !item.course && item.type !== tagLabel && item.source !== 'custom') metaParts.push(escapeHtml(item.type));
        if (!item.course && item.labels && item.labels.length) metaParts.push(escapeHtml(item.labels[0]));
        const metaText = metaParts.join(' · ');
        const metaHtml = (tagHtml || metaText) ? `<div class="biz-todo__meta">${tagHtml}${metaText ? `<span class="biz-todo__meta-text">${metaText}</span>` : ''}</div>` : '';

        const projectMainClass = item.isMainProject ? ' is-project-main' : '';

        const rowHtml = `
          <div class="ui-list-item ui-list-item--interactive todo-row${uiListStateClass}${uiListMutedClass}${projectMainClass} ${urgencyClass} ${manualFlag ? 'manual-flagged' : ''} ${isDismissed ? 'dismissed' : ''}">
            <div class="biz-todo__body">
              <div class="biz-todo__title">${titleHtml}</div>
              ${metaHtml}
            </div>
            <div class="biz-todo__right">
              <span class="item-source-badge" title="${item.course ? escapeHtml(item.course) : item.type}">
                <span class="ui-badge ui-badge--source ui-source--${item.source} src-${item.source}">${escapeHtml(item.type)}</span>
                ${item.disconnected ? '<span class="ui-status ui-status--warning">已断开</span>' : ''}
              </span>
              ${dueHtml}
              <span class="item-subtask-slot">${subtaskToggleHtml}</span>
              <span class="item-desktop-actions">${actionsHtml}</span>
            </div>
            <button class="ui-icon-button mobile-action-trigger" onclick="toggleMobileActions('${item.id}')" aria-label="更多操作" aria-expanded="${mobileActionsOpen}">•••</button>
            <span class="item-mobile-actions ${mobileActionsOpen ? 'open' : ''}">${actionsHtml}<button type="button" class="ui-button ui-button--secondary" data-mobile-detail="${escapeHtml(item.ref || (item.source === 'project' ? (item.taskId === null ? 'project_due:' + item.projectId : 'project:' + item.projectId + ':' + item.taskId) : item.source + ':' + item.rawId))}">详情</button></span>
          </div>
        `;

        if (!supportsSubtasks) {
          return rowHtml;
        }

        const panelHtml = isSubtaskExpanded ? renderSubtaskPanel(item.source, item.rawId, subtasks) : '';
        const previewHtml = '';
        return `
          <div class="todo-row-wrap">
            ${rowHtml}
            ${previewHtml}
            ${panelHtml}
          </div>
        `;
      };

      container.innerHTML = buildTodoGroups(filteredItems).map((group) => {
        const isCollapsed = collapsedTodoGroups.has(group.key);
        return `
        <section class="todo-group ${group.key === 'overdue' ? 'is-overdue' : ''} ${group.key === 'completed' ? 'is-completed' : ''} ${isCollapsed ? 'is-collapsed' : ''}" data-group-key="${group.key}">
          <div class="todo-group-heading" onclick="toggleTodoGroup('${group.key}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleTodoGroup('${group.key}');}" role="button" tabindex="0" aria-expanded="${!isCollapsed}" title="点击${isCollapsed ? '展开' : '折叠'}">
            <div class="todo-group-heading-left">
              <span class="todo-group-chevron-wrap" aria-hidden="true">
                <svg class="todo-group-chevron" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="4 6 8 10 12 6"></polyline>
                </svg>
              </span>
              <h3 class="ui-card__title">${escapeHtml(group.title)}</h3>
              <span class="ui-count-pill">${group.items.length}</span>
            </div>
            <div class="todo-group-divider-line" aria-hidden="true"></div>
          </div>
          <div class="todo-group-items" style="${isCollapsed ? 'display: none;' : ''}">${isCollapsed ? '' : group.items.map(renderTodoItem).join('')}</div>
        </section>
        `;
      }).join('');

      container.scrollTop = savedScrollTop;
      for (const draft of subtaskDrafts) {
        const input = document.getElementById(draft.id);
        if (!input) continue;
        input.value = draft.value;
        if (draft.focused) {
          input.focus({preventScroll: true});
          if (input.type !== 'date' && draft.start !== null) input.setSelectionRange(draft.start, draft.end);
        }
      }


      const projectsEl = document.querySelector('[data-nav-count="projects"]');
      const activeProjectsEl = document.getElementById('active-project-count');
      if (projectsEl && activeProjectsEl) {
        const n = Number(activeProjectsEl.textContent || '0');
        if (n > 0) { projectsEl.textContent = n; projectsEl.hidden = false; }
        else { projectsEl.textContent = ''; projectsEl.hidden = true; }
      }

    }

    function updateStatsBar(unified) {
      const activeItems = unified.filter(item => !item.done && !item.hidden && !item.is_previous);
      const pending = activeItems.length;

      const todayStr = window.customToday || new Date().toISOString().slice(0, 10);
      const now = Date.now();

      let due48h = 0;
      let overdue = 0;
      activeItems.forEach(item => {
        if (item.due_ts) {
          const dueStr = item.due_ts.slice(0, 10);
          const dueTime = new Date(item.due_ts).getTime();
          const hoursLeft = (dueTime - now) / 3600000;
          if (dueStr < todayStr || hoursLeft < 0) {
            overdue++;
            due48h++;
          } else if (hoursLeft <= 48) {
            due48h++;
          }
        }
      });

      const totalEl = document.getElementById('stat-total');
      const urgentEl = document.getElementById('stat-urgent');
      if (totalEl) totalEl.textContent = pending;
      if (urgentEl) urgentEl.textContent = overdue + due48h;

      // Update Top KPI Cards
      const pendingCountEl = document.getElementById('stat-pending-count');
      const pendingDiffEl = document.getElementById('stat-pending-diff');
      const dueCountEl = document.getElementById('stat-due-count');
      const dueOverdueEl = document.getElementById('stat-due-overdue');

      if (pendingCountEl) pendingCountEl.textContent = pending;
      if (pendingDiffEl) pendingDiffEl.textContent = pending > 0 ? `${pending} 项待处理` : '待办已清空';
      if (dueCountEl) dueCountEl.textContent = due48h;
      if (dueOverdueEl) {
        dueOverdueEl.textContent = overdue > 0 ? `含 ${overdue} 项已逾期` : '无逾期事项';
        dueOverdueEl.classList.toggle('warn', overdue > 0);
      }
    }

    async function togglePlatformCompletion(platform, id, done) {
      const endpoint = `/api/${platform}/state`;
      const response = await fetch(endpoint, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: done ? 'uncomplete' : 'complete', id}),
      });
      if (!response.ok) return;
      const collections = {canvas: canvasItems, haoke: haokeItems, zhixuemeng: zhixuemengItems, zhihuishu: zhihuishuItems, ketangpai: ketangpaiItems, tongjioj: tongjiojItems};
      const item = (collections[platform] || []).find((entry) => String(entry.id) === String(id));
      if (item) item.done = !done;
      renderUnifiedList();
      if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
    }

    function renderSubtaskPanel(source, todoId, subtasks) {
      if (typeof source === 'number' || (typeof source === 'string' && subtasks === undefined)) {
        subtasks = todoId;
        todoId = source;
        source = 'custom';
      }
      const todayStr = getTodayDateString();
      const sourceArg = JSON.stringify(source);
      const todoIdArg = JSON.stringify(String(todoId));
      const rowsHtml = (subtasks || []).map((subtask, idx) => {
        const sid = subtask.id != null ? subtask.id : idx;
        const dueDateVal = subtask.due_date || todayStr;
        return `
        <div class="ui-list-item todo-subtask-row">
          <input type="checkbox" ${subtask.done ? 'checked' : ''} onchange='toggleSubtaskDone(${sourceArg}, ${todoIdArg}, ${sid})' class="ui-checkbox">
          <span class="ui-list-item__title subtask-text ${subtask.done ? 'done' : ''}" title="${escapeHtml(subtask.text)}" onclick='startSubtaskEdit(${sourceArg}, ${todoIdArg}, ${sid}, this)'>${escapeHtml(subtask.text)}</span>
          <input type="date" class="ui-control subtask-due-input" value="${dueDateVal}" onchange='handleSubtaskDueChange(${sourceArg}, ${todoIdArg}, ${sid}, this.value)' title="截止日期">
          <button class="ui-icon-button ui-icon-button--danger subtask-delete" onclick='deleteSubtask(${sourceArg}, ${todoIdArg}, ${sid})' title="delete subtask">x</button>
        </div>
      `;
      }).join('');

      return `
        <div class="ui-card ui-card--subtle todo-subtask-panel">
          ${rowsHtml || '<div class="ui-empty ui-empty--compact subtask-empty"><strong>还没有子任务</strong></div>'}
          <div class="subtask-add-row">
            <input class="ui-control subtask-add-input" id="subtask-add-text-${source}-${todoId}" placeholder="添加子任务..." onkeydown='handleSubtaskAddKey(event, ${sourceArg}, ${todoIdArg})'>
            <input type="date" class="ui-control subtask-add-due-input" id="subtask-add-due-${source}-${todoId}" value="${todayStr}" onkeydown='handleSubtaskAddKey(event, ${sourceArg}, ${todoIdArg})' title="截止日期">
            <button type="button" class="ui-button ui-button--primary subtask-add-btn" onclick='submitSubtaskAdd(${sourceArg}, ${todoIdArg})' title="添加子任务">添加</button>
          </div>
        </div>
      `;
    }

    async function toggleHighlight(itemId, current) {
      const rawId = itemId.startsWith('c') ? itemId.substring(1) : itemId;
      const action = current ? 'unhighlight' : 'highlight';
      await fetch('/api/canvas/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: rawId }),
      });
      if (current) {
        highlightedIds = highlightedIds.filter(id => String(id) !== String(rawId));
      } else {
        highlightedIds.push(rawId);
      }
      renderUnifiedList();
    }

    async function toggleHide(itemId, current) {
      const rawId = itemId.startsWith('c') ? itemId.substring(1) : itemId;
      const action = current ? 'unhide' : 'hide';
      await fetch('/api/canvas/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: rawId }),
      });
      if (current) {
        hiddenIds = hiddenIds.filter(id => String(id) !== String(rawId));
      } else {
        hiddenIds.push(rawId);
      }
      renderUnifiedList();
    }

    // ---- Unified Todos Subtasks & CRUD ----
    function findTodo(source, todoId) {
      if (todoId === undefined) {
        todoId = source;
        source = 'custom';
      }
      const idStr = String(todoId);
      if (source === 'custom') {
        return customItems.find(item => String(item.id) === idStr);
      } else if (source === 'canvas') {
        return canvasItems.find(item => String(item.id) === idStr);
      } else if (source === 'haoke') {
        return haokeItems.find(item => String(item.id) === idStr);
      } else if (source === 'zhixuemeng') {
        return zhixuemengItems.find(item => String(item.id) === idStr);
      } else if (source === 'zhihuishu') {
        return zhihuishuItems.find(item => String(item.id) === idStr);
      } else if (source === 'ketangpai') {
        return ketangpaiItems.find(item => String(item.id) === idStr);
      } else if (source === 'tongjioj') {
        return tongjiojItems.find(item => String(item.id) === idStr);
      }
      return null;
    }

    function findCustomTodo(todoId) {
      return findTodo('custom', todoId);
    }

    function toggleSubtasks(source, todoId) {
      if (todoId === undefined) {
        todoId = source;
        source = 'custom';
      }
      const key = todoKey(source, todoId);
      if (expandedTodoKeys.includes(key)) {
        expandedTodoKeys = expandedTodoKeys.filter(k => k !== key);
      } else {
        expandedTodoKeys.push(key);
      }
      expandedCustomTodoIds = expandedTodoKeys;
      renderUnifiedList();
    }

    function handleSubtaskAddKey(event, source, todoId) {
      if (todoId === undefined) {
        todoId = source;
        source = 'custom';
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        submitSubtaskAdd(source, todoId);
      } else if (event.key === 'Escape') {
        const textInput = document.getElementById(`subtask-add-text-${source}-${todoId}`) || document.getElementById(`subtask-add-text-${todoId}`) || event.target;
        if (textInput) {
          textInput.value = '';
          textInput.blur();
        }
      }
    }

    async function submitSubtaskAdd(source, todoId) {
      if (todoId === undefined) {
        todoId = source;
        source = 'custom';
      }
      const textInput = document.getElementById(`subtask-add-text-${source}-${todoId}`) || document.getElementById(`subtask-add-text-${todoId}`) || document.querySelector('.subtask-add-input');
      const dueInput = document.getElementById(`subtask-add-due-${source}-${todoId}`) || document.getElementById(`subtask-add-due-${todoId}`) || document.querySelector('.subtask-add-due-input');
      if (!textInput) return;
      const text = textInput.value.trim();
      const dueDate = dueInput ? dueInput.value : getTodayDateString();
      if (!text) return;
      const saved = await addSubtask(source, todoId, text, dueDate);
      if (saved) {
        const currentInput = document.getElementById(textInput.id);
        const currentDue = dueInput && document.getElementById(dueInput.id);
        if (currentInput?.value.trim() === text) currentInput.value = '';
        if (currentDue?.value === dueDate) currentDue.value = getTodayDateString();
      }
    }

    async function saveSubtasks(source, todoId, subtasks) {
      if (subtasks === undefined) {
        subtasks = todoId;
        todoId = source;
        source = 'custom';
      }
      if (source === 'custom') customDataRevision++;
      try {
        const todo = findTodo(source, todoId);
        if (source === 'custom') {
          const payload = { subtasks };
          if (todo && todo.updated_at) payload.updated_at = todo.updated_at;
          const resp = await fetch(`/api/custom/todos/${todoId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (!resp.ok) throw new Error('save failed');
          const data = await resp.json();
          customDataRevision++;
          const current = findTodo(source, todoId);
          if (current) {
            current.subtasks = data.todo?.subtasks || subtasks;
            if (data.todo?.updated_at) current.updated_at = data.todo.updated_at;
          }
        } else {
          const resp = await fetch('/api/external-subtasks', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source, item_id: String(todoId), subtasks }),
          });
          if (!resp.ok) throw new Error('save failed');
          const data = await resp.json();
          const current = findTodo(source, todoId);
          if (current) current.subtasks = data.subtasks || subtasks;
        }
        renderUnifiedList();
        return true;
      } catch (e) {
        alert('保存失败');
        if (source === 'custom') fetchCustomTodos();
        else if (source === 'canvas') fetchCanvasTodos();
        else if (source === 'haoke') fetchHaokeTodos();
        else if (source === 'zhixuemeng') fetchZhixuemengTodos();
        else if (source === 'zhihuishu') fetchZhihuishuTodos();
        else if (source === 'ketangpai') fetchKetangpaiTodos();
        else if (source === 'tongjioj') fetchTongjiojTodos();
        return false;
      }
    }

    function saveCustomSubtasks(todoId, subtasks) {
      return saveSubtasks('custom', todoId, subtasks);
    }

    async function addSubtask(source, todoId, text, dueDate) {
      if (dueDate === undefined) {
        dueDate = text;
        text = todoId;
        todoId = source;
        source = 'custom';
      }
      const trimmed = text.trim();
      if (!trimmed) return;

      const todo = findTodo(source, todoId);
      if (!todo) return;

      const currentSubtasks = todo.subtasks || [];
      const newId = Math.max(0, ...currentSubtasks.map(subtask => subtask.id || 0)) + 1;
      const finalDueDate = (dueDate !== undefined && dueDate !== null && dueDate !== '') ? dueDate : getTodayDateString();
      const subtasks = [
        ...currentSubtasks,
        { id: newId, text: trimmed, done: false, due_date: finalDueDate },
      ];
      return await saveSubtasks(source, todoId, sortSubtasks(subtasks));
    }

    async function toggleSubtaskDone(source, todoId, subtaskId) {
      if (subtaskId === undefined) {
        subtaskId = todoId;
        todoId = source;
        source = 'custom';
      }
      const todo = findTodo(source, todoId);
      if (!todo) return;

      const sid = Number(subtaskId);
      const subtasks = (todo.subtasks || []).map((subtask, idx) => {
        const id = subtask.id != null ? subtask.id : idx;
        if (id === sid) {
          const newSubtask = { ...subtask, done: !subtask.done };
          if (newSubtask.id == null) {
            newSubtask.id = idx;
          }
          return newSubtask;
        }
        if (subtask.id == null) {
          return { ...subtask, id: idx };
        }
        return subtask;
      });

      await saveSubtasks(source, todoId, sortSubtasks(subtasks));
    }

    async function deleteSubtask(source, todoId, subtaskId) {
      if (subtaskId === undefined) {
        subtaskId = todoId;
        todoId = source;
        source = 'custom';
      }
      const todo = findTodo(source, todoId);
      if (!todo) return;

      const sid = Number(subtaskId);
      const subtasks = (todo.subtasks || []).filter((subtask, idx) => {
        const id = subtask.id != null ? subtask.id : idx;
        return id !== sid;
      });
      await saveSubtasks(source, todoId, sortSubtasks(subtasks));
    }

    async function handleSubtaskDueChange(source, todoId, subtaskId, dueDate) {
      if (dueDate === undefined) {
        dueDate = subtaskId;
        subtaskId = todoId;
        todoId = source;
        source = 'custom';
      }
      const todo = findTodo(source, todoId);
      if (!todo) return;

      const sid = Number(subtaskId);
      const subtasks = (todo.subtasks || []).map((subtask, idx) => {
        const id = subtask.id != null ? subtask.id : idx;
        return id === sid ? { ...subtask, due_date: dueDate || null } : subtask;
      });
      await saveSubtasks(source, todoId, sortSubtasks(subtasks));
    }

    function startSubtaskEdit(source, todoId, subtaskId, spanEl) {
      if (spanEl === undefined) {
        spanEl = subtaskId;
        subtaskId = todoId;
        todoId = source;
        source = 'custom';
      }
      const todo = findTodo(source, todoId);
      if (!todo) return;

      const sid = Number(subtaskId);
      const subtask = (todo.subtasks || []).find((item, idx) => {
        const id = item.id != null ? item.id : idx;
        return id === sid;
      });
      if (!subtask) return;

      const originalText = subtask.text;
      const input = document.createElement('input');
      input.type = 'text';
      input.className = 'ui-control subtask-edit-input';
      input.value = originalText;
      spanEl.replaceWith(input);
      input.focus();
      input.select();

      async function finish(save) {
        const nextText = input.value.trim();
        if (!save || !nextText || nextText === originalText) {
          renderUnifiedList();
          return;
        }

        const subtasks = (todo.subtasks || []).map((item, idx) => {
          const id = item.id != null ? item.id : idx;
          return id === sid ? { ...item, text: nextText } : item;
        });
        await saveSubtasks(source, todoId, sortSubtasks(subtasks));
      }

      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') finish(true);
        if (event.key === 'Escape') finish(false);
      });
      input.addEventListener('blur', () => finish(true));
    }

    let isSubmittingTodo = false;
    let currentTodoRequestId = null;

    function resetTodoRequestId() {
      currentTodoRequestId = null;
      const errEl = document.getElementById('add-todo-error');
      if (errEl) { errEl.textContent = ''; errEl.style.display = 'none'; }
    }

    async function addTodo(e) {
      if (e && e.preventDefault) e.preventDefault();
      if (isSubmittingTodo) return;

      const input = document.getElementById('new-todo-input');
      const dueInput = document.getElementById('new-todo-due');
      const repeatSelect = document.getElementById('new-todo-repeat');
      const submitBtn = document.getElementById('btn-add-todo') || document.querySelector('#add-todo-form button[type="submit"]');
      const errEl = document.getElementById('add-todo-error');

      const text = input ? input.value.trim() : '';
      if (!text) return;

      if (!currentTodoRequestId) {
        currentTodoRequestId = (typeof crypto !== 'undefined' && crypto.randomUUID)
          ? crypto.randomUUID()
          : ('req-' + Date.now() + '-' + Math.random().toString(36).slice(2));
      }

      let labels = [];
      const parts = text.split(/\s+(#[^#\s]+)/);
      let taskText = parts[0];
      if (parts.length > 1) {
        taskText = parts[0].trim();
        labels = parts.slice(1).map(tag => tag.substring(1)).filter(tag => tag);
      }

      const repeatVal = repeatSelect ? repeatSelect.value : 'none';
      const origBtnText = submitBtn ? submitBtn.textContent : '添加';

      isSubmittingTodo = true;
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.setAttribute('aria-busy', 'true');
        submitBtn.textContent = '添加中…';
      }
      if (errEl) {
        errEl.textContent = '';
        errEl.style.display = 'none';
      }

      try {
        let resp;
        const headers = {
          'Content-Type': 'application/json',
          'Idempotency-Key': currentTodoRequestId,
        };
        if (repeatVal === 'weekly' || repeatVal === 'biweekly') {
          resp = await fetch('/api/recurring-todos', {
            method: 'POST',
            headers,
            body: JSON.stringify({
              title: taskText,
              first_due_date: dueInput.value || (window.customToday || new Date().toISOString().split('T')[0]),
              interval_weeks: repeatVal === 'weekly' ? 1 : 2,
              details: labels.length ? ('标签: ' + labels.join(', ')) : '',
              request_id: currentTodoRequestId,
            }),
          });
        } else {
          resp = await fetch('/api/custom/todos', {
            method: 'POST',
            headers,
            body: JSON.stringify({
              text: taskText,
              due_date: dueInput.value,
              labels: labels,
              request_id: currentTodoRequestId,
            }),
          });
        }

        if (resp.ok) {
          input.value = '';
          dueInput.value = '';
          if (repeatSelect) repeatSelect.value = 'none';
          currentTodoRequestId = null;
          setNewTodoDueDefault(window.customToday || new Date().toISOString().split('T')[0]);
          document.getElementById('add-todo-form').dispatchEvent(new Event('todo:created'));
          await fetchCustomTodos();
          if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
        } else {
          const err = await resp.json().catch(() => ({}));
          const errMsg = err.error || err.message || ('服务端错误（' + resp.status + '）');
          if (errEl) {
            errEl.textContent = '添加失败：' + errMsg;
            errEl.style.display = 'block';
          } else {
            alert('添加失败：' + errMsg);
          }
        }
      } catch (networkErr) {
        if (errEl) {
          errEl.textContent = '网络连接失败，请检查网络后重试。';
          errEl.style.display = 'block';
        } else {
          alert('网络连接失败，请检查网络后重试。');
        }
      } finally {
        isSubmittingTodo = false;
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.removeAttribute('aria-busy');
          submitBtn.textContent = origBtnText;
        }
      }
    }

    async function toggleTodoCheck(id, done) {
      if (typeof id === 'string' && id.startsWith('recurring_')) {
        const parts = id.split('_');
        const seriesId = parts[1];
        const origDate = parts.slice(2).join('_');
        await toggleRecurringCheck(seriesId, origDate, done);
        return;
      }
      const item = Array.isArray(customItems) ? customItems.find(t => String(t.id) === String(id)) : null;
      const payload = { done: !done };
      if (item && item.updated_at) payload.expected_updated_at = item.updated_at;
      const resp = await fetch(`/api/custom/todos/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      await fetchCustomTodos();
      if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
    }

    async function toggleRecurringCheck(seriesId, origDate, done) {
      await fetch(`/api/recurring-todos/${seriesId}/occurrences/${origDate}/complete`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ done: !done }),
      });
      await fetchCustomTodos();
      if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
    }

    async function skipRecurringOccurrence(seriesId, origDate) {
      await fetch(`/api/recurring-todos/${seriesId}/occurrences/${origDate}/skip`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skipped: true }),
      });
      await fetchCustomTodos();
      if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
    }

    async function deleteRecurringSeries(seriesId) {
      if (!confirm('确定要删除此重复待办系列吗？')) return;
      await fetch(`/api/recurring-todos/${seriesId}`, {
        method: 'DELETE',
      });
      await fetchCustomTodos();
      if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
    }

    async function toggleCustomHighlight(id, current) {
      const item = Array.isArray(customItems) ? customItems.find(t => String(t.id) === String(id)) : null;
      const payload = { highlighted: !current };
      if (item && item.updated_at) payload.expected_updated_at = item.updated_at;
      await fetch(`/api/custom/todos/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      fetchCustomTodos();
    }


    async function toggleCanvasDelete(id) {
      await fetch('/api/canvas/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id }),
      });
      canvasDeletedIds.push(id);
      renderUnifiedList();
    }

    async function toggleHaokeDelete(id) {
      await fetch('/api/haoke/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id }),
      });
      haokeDeletedIds.push(id);
      renderUnifiedList();
    }

    async function toggleZhixuemengDelete(id) {
      await fetch('/api/zhixuemeng/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id }),
      });
      zhixuemengDeletedIds.push(id);
      renderUnifiedList();
    }

    async function toggleZhihuishuDelete(id) {
      const resp = await fetch('/api/zhihuishu/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id }),
      });
      if (!resp.ok) return;
      zhihuishuDeletedIds.push(id);
      renderUnifiedList();
    }

    async function toggleKetangpaiDelete(id) {
      const resp = await fetch('/api/ketangpai/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id }),
      });
      if (!resp.ok) return;
      ketangpaiDeletedIds.push(id);
      renderUnifiedList();
    }

    async function toggleTongjiojDelete(id) {
      const resp = await fetch('/api/tongjioj/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id }),
      });
      if (!resp.ok) return;
      tongjiojDeletedIds.push(id);
      renderUnifiedList();
    }

    async function toggleCustomDelete(id) {
      if (deletingCustomIds.has(id)) return;
      const item = customItems.find(t => t.id === id);
      const title = item ? item.text : '此待办';
      const subtaskCount = item && Array.isArray(item.subtasks) ? item.subtasks.length : 0;
      const subtaskWarning = subtaskCount > 0 ? `\n将同时删除其包含的 ${subtaskCount} 个子任务。` : '';
      if (!window.confirm(`确定永久删除待办「${title}」吗？${subtaskWarning}\n此操作不可撤销。`)) {
        return;
      }

      deletingCustomIds.add(id);
      renderUnifiedList();
      try {
        const resp = await fetch(`/api/custom/todos/${id}`, { method: 'DELETE' });
        if (resp.ok) {
          await fetchCustomTodos();
          if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
          if (typeof loadForwardAgenda === 'function') loadForwardAgenda();
        } else {
          const err = await resp.json().catch(() => ({}));
          const errMsg = err.error || err.message || ('服务端状态 ' + resp.status);
          alert('删除待办失败：' + errMsg);
        }
      } catch (err) {
        alert('删除待办失败，网络连接异常，请重试。');
      } finally {
        deletingCustomIds.delete(id);
        renderUnifiedList();
      }
    }

    async function saveInlineEdit(id, field, value) {
      customDataRevision++;
      const item = customItems.find(t => t.id === id);
      const prevText = item ? item.text : undefined;
      const prevDue = item ? item.due_date : undefined;
      const prevLabels = item && Array.isArray(item.labels) ? [...item.labels] : [];

      if (item) {
        if (field === 'multi') {
          item.text = value.text;
          item.labels = value.labels;
        } else if (field === 'text') {
          item.text = value;
        } else if (field === 'due_date') {
          item.due_date = value || null;
        } else if (field === 'labels') {
          item.labels = value;
        }
      }
      renderUnifiedList();

      const payload = {};
      if (item && item.updated_at) {
        payload.expected_updated_at = item.updated_at;
      }
      if (field === 'multi') {
        payload.text = value.text;
        payload.labels = value.labels;
      } else {
        payload[field] = value;
      }

      try {
        const response = await fetch(`/api/custom/todos/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) {
          throw new Error(data.error || `保存失败（${response.status}）`);
        }
        customDataRevision++;
        const current = findTodo('custom', id);
        if (current && data.todo?.updated_at) {
          current.updated_at = data.todo.updated_at;
        }
        if (typeof notifyCrossTabChange === 'function') notifyCrossTabChange('custom');
        if (typeof refreshWorkspaceSurfaces === 'function') {
          await refreshWorkspaceSurfaces();
        } else {
          await fetchCustomTodos();
          if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
        }
      } catch (err) {
        if (item) {
          item.text = prevText;
          item.due_date = prevDue;
          item.labels = prevLabels;
        }
        renderUnifiedList();
        alert('修改未保存：' + (err.message || '网络或服务异常'));
      }
    }

    function startInlineEdit(spanEl, field) {
      const id = parseInt(spanEl.dataset.id);
      const originalValue = field === 'due_date' ? (spanEl.dataset.value ?? spanEl.textContent.trim()) : spanEl.textContent.trim();

      const input = document.createElement('input');
      input.type = field === 'due_date' ? 'date' : 'text';
      input.className = field === 'due_date' ? 'inline-edit-date-input' : 'inline-edit-input';

      if (field === 'due_date' && originalValue) {
        input.value = originalValue;
      } else {
        input.value = originalValue;
      }

      spanEl.replaceWith(input);
      input.focus();
      if (input.type === 'text') input.select();
      let finished = false;

      function commit() {
        if (finished) return;
        finished = true;
        const newValue = input.value.trim();
        input.replaceWith(spanEl);
        if (newValue !== originalValue) {
          // 濡傛灉鏄紪杈戜换鍔℃爣棰橈紝妫€鏌ユ槸鍚︽湁鏍囩
          if (field === 'text') {
            const parts = newValue.split(/\s+(#[^#\s]+)/);
            let taskText = parts[0];
            let labels = [];
            if (parts.length > 1) {
              taskText = parts[0].trim();
              labels = parts.slice(1).map(tag => tag.substring(1)).filter(tag => tag);
            }

            // 鍚堝苟涓轰竴娆¤姹傦紝閬垮厤绔炴€佹潯浠?
            saveInlineEdit(id, 'multi', { text: taskText, labels });
          } else {
            saveInlineEdit(id, field, newValue);
          }
        } else {
          renderUnifiedList();
        }
      }

      function cancel() {
        if (finished) return;
        finished = true;
        input.replaceWith(spanEl);
        renderUnifiedList();
      }

      input.addEventListener('blur', commit);
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
        if (e.key === 'Escape') { e.preventDefault(); cancel(); }
      });
    }


(function initializeTodoFeature() {
  const byId = (id) => document.getElementById(id);
  byId('todo-list')?.addEventListener('click', (event) => {
    const detail = event.target.closest('[data-mobile-detail]');
    if (detail) openActionDetail(detail.dataset.mobileDetail);
  });

  const composer = byId('todo-composer');
  const toggle = byId('mobile-add-toggle');
  const mobile = window.matchMedia('(max-width: 768px)');
  let composerOpen = false;
  function updateComposer() {
    composer?.classList.toggle('is-collapsed', mobile.matches && !composerOpen);
    toggle?.setAttribute('aria-expanded', String(composerOpen));
    if (toggle) toggle.textContent = composerOpen ? '收起' : '＋ 新增';
  }
  toggle?.addEventListener('click', () => {
    composerOpen = !composerOpen;
    updateComposer();
    if (composerOpen) byId('new-todo-input')?.focus();
  });
  composer?.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && mobile.matches) {
      composerOpen = false;
      updateComposer();
      toggle?.focus();
    }
  });
  byId('add-todo-form')?.addEventListener('todo:created', () => {
    if (!mobile.matches) return;
    composerOpen = false;
    updateComposer();
    toggle?.focus({preventScroll: true});
  });
  mobile.addEventListener('change', updateComposer);
  updateComposer();

  byId('add-todo-form')?.addEventListener('submit', addTodo);
  byId('new-todo-input')?.addEventListener('input', () => { if (typeof resetTodoRequestId === 'function') resetTodoRequestId(); });
  byId('new-todo-due')?.addEventListener('change', () => { if (typeof resetTodoRequestId === 'function') resetTodoRequestId(); });
  byId('new-todo-repeat')?.addEventListener('change', () => { if (typeof resetTodoRequestId === 'function') resetTodoRequestId(); });
  byId('btn-refresh')?.addEventListener('click', async () => {
    if (workspaceRefreshing) return;
    workspaceRefreshing = true;
    workspaceRefreshFailed = false;
    renderDashboardSyncStatus();
    try {
      if (typeof fetchCanvasTodos === 'function') fetchCanvasTodos(true);
      if (typeof fetchHaokeTodos === 'function') fetchHaokeTodos(true);
      if (typeof fetchZhixuemengTodos === 'function') fetchZhixuemengTodos();
      if (typeof fetchZhihuishuTodos === 'function') fetchZhihuishuTodos();
      if (typeof fetchKetangpaiTodos === 'function') fetchKetangpaiTodos();
      if (typeof fetchTongjiojTodos === 'function') fetchTongjiojTodos('', true);
      if (typeof refreshWorkspaceSurfaces === 'function') {
        await refreshWorkspaceSurfaces();
      } else {
        if (typeof fetchProjectTodos === 'function') await fetchProjectTodos();
        if (typeof fetchCustomTodos === 'function') await fetchCustomTodos();
        if (typeof loadTodaySchedule === 'function') await loadTodaySchedule();
      }
    } catch (_) {
      workspaceRefreshFailed = true;
    } finally {
      workspaceRefreshing = false;
      renderDashboardSyncStatus();
    }
  });
  byId('list-updated')?.addEventListener('click', openSyncStatus);
  byId('todo-source-select')?.addEventListener('change', (event) => setTodoSourceFilter(event.target.value));
  byId('todo-source-filters')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-todo-source]');
    if (button) setTodoSourceFilter(button.dataset.todoSource);
  });
  byId('todo-source-visibility-options')?.addEventListener('change', (event) => {
    const input = event.target.closest('[data-todo-source-visibility]');
    if (input) setTodoSourceVisibility(input.dataset.todoSourceVisibility, input.checked);
  });
  document.addEventListener('click', (event) => {
    const manager = byId('todo-source-manager');
    if (manager?.open && !manager.contains(event.target)) manager.removeAttribute('open');
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') byId('todo-source-manager')?.removeAttribute('open');
  });
  byId('todo-list')?.addEventListener('click', (event) => {
    const projectDueEl = event.target.closest('.project-due-editable');
    if (projectDueEl) { startProjectTodoDueEdit(projectDueEl); return; }
    const titleEl = event.target.closest('.editable-title');
    if (titleEl) { startInlineEdit(titleEl, 'text'); return; }
    const dueEl = event.target.closest('.editable-due');
    if (dueEl) startInlineEdit(dueEl, 'due_date');
  });
})();
