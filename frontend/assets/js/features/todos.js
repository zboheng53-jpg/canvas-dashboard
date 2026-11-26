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

    const todoInFlightKeys = new Set();
    let _bootCoalesceActive = false;
    let _bootCoalesceExpiresAt = 0;
    let _renderScheduledTimer = null;
    let _renderScheduledRaf = null;
    let _pendingPulseTodoKey = null;
    let _pendingFocusSelector = null;

    function beginBootRenderCoalesce(windowMs = 240) {
      _bootCoalesceActive = true;
      _bootCoalesceExpiresAt = Date.now() + windowMs;
    }

    function scheduleRenderUnifiedList() {
      if (_renderScheduledTimer !== null || _renderScheduledRaf !== null) return;
      _renderScheduledTimer = setTimeout(() => {
        _renderScheduledTimer = null;
        _renderScheduledRaf = requestAnimationFrame(() => {
          _renderScheduledRaf = null;
          _bootCoalesceActive = false;
          renderUnifiedListNow();
        });
      }, 30);
    }

    function renderUnifiedList({ immediate = false } = {}) {
      if (!immediate && _bootCoalesceActive) {
        if (Date.now() < _bootCoalesceExpiresAt) {
          scheduleRenderUnifiedList();
          return;
        }
        _bootCoalesceActive = false;
      }
      if (_renderScheduledTimer !== null) {
        clearTimeout(_renderScheduledTimer);
        _renderScheduledTimer = null;
      }
      if (_renderScheduledRaf !== null) {
        cancelAnimationFrame(_renderScheduledRaf);
        _renderScheduledRaf = null;
      }
      renderUnifiedListNow();
    }

    function showUiToast(message, options = {}) {
      if (window.uiToast?.show) {
        return window.uiToast.show(message, options);
      }
      return { dismiss() {} };
    }

    async function confirmUiAction({ title, message, confirmLabel = '确认', cancelLabel = '取消', tone = 'danger' }) {
      if (typeof window.uiConfirm === 'function') {
        return await window.uiConfirm({ title, message, confirmLabel, cancelLabel, tone });
      }
      return false;
    }

    function shortTodoToastTitle(title, maxLen = 18) {
      const text = String(title || '').trim();
      return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
    }

    function flipTodoList(mutateFn) {
      const container = document.getElementById('todo-list');
      if (container && window.uiMotion?.flipList) {
        return window.uiMotion.flipList(container, '.todo-group-items > [data-flip-key]', mutateFn);
      }
      return mutateFn();
    }

    function flipSubtasks(source, todoId, mutateFn) {
      const key = todoKey(source, todoId);
      const wrap = document.querySelector(`#todo-list .todo-row-wrap[data-todo-key="${CSS.escape(key)}"]`);
      const panel = wrap?.querySelector('.todo-subtask-panel');
      if (panel && window.uiMotion?.flipList) {
        return window.uiMotion.flipList(panel, '.todo-subtask-row[data-flip-key]', mutateFn);
      }
      return mutateFn();
    }

    function getTodayDateString() {
      if (typeof window.getShanghaiTodayISO === 'function') {
        return window.getShanghaiTodayISO();
      }
      if (window.customToday) return window.customToday;
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).format(new Date());
    }

    function sortSubtasks(subtasks) {
      return [...subtasks].sort((a, b) => {
        if (a.done === b.done) return 0;
        return a.done ? 1 : -1;
      });
    }

    function closeMobileActions({ restoreFocus = false } = {}) {
      if (!openMobileActionItemId) return;
      const prevId = openMobileActionItemId;
      openMobileActionItemId = null;
      const container = document.getElementById('todo-list');
      if (!container) return;
      const prevRow = container.querySelector(`.todo-row[data-todo-id="${CSS.escape(String(prevId))}"]`);
      if (prevRow) {
        prevRow.querySelector('.item-mobile-actions')?.classList.remove('open');
        const trigger = prevRow.querySelector('.mobile-action-trigger');
        if (trigger) {
          trigger.setAttribute('aria-expanded', 'false');
          if (restoreFocus) trigger.focus({ preventScroll: true });
        }
      }
    }

    function toggleMobileActions(itemId) {
      const container = document.getElementById('todo-list');
      if (!container) return;
      if (openMobileActionItemId === itemId) {
        closeMobileActions();
        return;
      }
      if (openMobileActionItemId) closeMobileActions();
      openMobileActionItemId = itemId;
      const row = container.querySelector(`.todo-row[data-todo-id="${CSS.escape(String(itemId))}"]`);
      if (row) {
        row.querySelector('.item-mobile-actions')?.classList.add('open');
        row.querySelector('.mobile-action-trigger')?.setAttribute('aria-expanded', 'true');
      }
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
        window.customToday = result.today || getTodayDateString();
        renderUnifiedList();
      } catch (e) {
        console.error('Failed to fetch custom todos:', e);
        window.customToday = window.customToday || getTodayDateString();
      }
    }

    const TODO_SOURCE_ORDER = ['canvas', 'haoke', 'zhixuemeng', 'zhihuishu', 'ketangpai', 'tongjioj', 'project', 'custom'];
    const TODO_PLATFORM_SOURCES = new Set(['canvas', 'haoke', 'zhixuemeng', 'zhihuishu', 'ketangpai', 'tongjioj']);
    let visibleTodoSources = new Set(TODO_SOURCE_ORDER);
    let committedVisibleTodoSources = new Set(TODO_SOURCE_ORDER);
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
        committedVisibleTodoSources = new Set(visibleTodoSources);
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
      renderUnifiedListNow();
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
          committedVisibleTodoSources = new Set(visibleTodoSources);
          if (status) status.textContent = '已保存；可选平台随连接状态自动更新。';
          renderUnifiedListNow();
          renderDashboardSyncStatus();
          updateAttentionStatus();
        } catch (error) {
          if (revision !== todoSourcePreferenceRevision) return;
          visibleTodoSources = new Set(committedVisibleTodoSources);
          if (todoSourceFilter !== 'all' && !visibleTodoSources.has(todoSourceFilter)) {
            todoSourceFilter = 'all';
          }
          if (status) status.textContent = '保存失败，已恢复原标签设置。';
          showUiToast('来源标签保存失败，已恢复原设置', { tone: 'danger' });
          renderUnifiedListNow();
          renderDashboardSyncStatus();
          updateAttentionStatus();
        }
      }, 250);
    }

    function syncTodoFilterGlide() {
      const filtersEl = document.getElementById('todo-source-filters');
      const activeBtn = filtersEl?.querySelector('button[data-todo-source].is-active:not(.hidden)');
      if (filtersEl && activeBtn && window.uiMotion?.glideIndicator) {
        window.uiMotion.glideIndicator(filtersEl, activeBtn, { indicatorClass: 'ui-glide-pill' });
      }
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
        element.classList.toggle('is-on', isActive);
        if (element.tagName === 'BUTTON') {
          element.setAttribute('aria-pressed', String(isActive));
        }
      });
      syncTodoFilterGlide();
      flipTodoList(() => renderUnifiedListNow());
    }

    let collapsedTodoGroups = new Set(['completed']);
    function toggleTodoGroup(key) {
      const isCollapsed = !collapsedTodoGroups.has(key);
      if (isCollapsed) {
        collapsedTodoGroups.add(key);
      } else {
        collapsedTodoGroups.delete(key);
      }
      const groupEl = document.querySelector(`#todo-list .todo-group[data-group-key="${CSS.escape(key)}"]`);
      if (!groupEl) return;
      groupEl.classList.toggle('is-collapsed', isCollapsed);
      const heading = groupEl.querySelector('.todo-group-heading');
      if (heading) {
        heading.setAttribute('aria-expanded', String(!isCollapsed));
        heading.title = isCollapsed ? '点击展开' : '点击折叠';
      }
      const collapseEl = groupEl.querySelector('.ui-collapse');
      if (collapseEl) {
        collapseEl.classList.toggle('is-collapsed', isCollapsed);
        if (getComputedStyle(collapseEl).display !== 'grid') {
          const itemsEl = collapseEl.querySelector('.todo-group-items');
          if (itemsEl) itemsEl.style.display = isCollapsed ? 'none' : '';
        }
      }
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
      // 计数只反映真正进入清单的事项：未被选为今日行动的项目步骤不占待办，也不计入统计。
      const listed = items.filter((item) => !item.is_scheduled_action || item.isTodayAction);
      const counts = { all: listed.length, canvas: 0, haoke: 0, zhixuemeng: 0, zhihuishu: 0, ketangpai: 0, tongjioj: 0, project: 0, custom: 0 };
      listed.forEach((item) => {
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
      syncTodoFilterGlide();
    }

    function todoDueDate(item) {
      // 唯一截止时间来源：优先精确时间戳，其次可解析的日期字符串。
      if (item.due_ts) {
        const parsed = new Date(String(item.due_ts).slice(0, 10) + 'T00:00:00');
        if (!Number.isNaN(parsed.getTime())) return parsed;
      }
      const raw = (item.due_str || '').trim();
      if (/^\d{4}-\d{2}-\d{2}/.test(raw)) {
        const parsed = new Date(raw.slice(0, 10) + 'T00:00:00');
        if (!Number.isNaN(parsed.getTime())) return parsed;
      }
      return null;
    }

    function todoDeadlineState(item) {
      const today = workspaceTodayISO();
      const raw = String(item.due_str || item.due_date || '').trim();
      const timestamp = item.due_ts ? new Date(item.due_ts) : null;
      const valid = timestamp && !Number.isNaN(timestamp.getTime());
      const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(raw);
      const day = valid
        ? new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai', year:'numeric', month:'2-digit', day:'2-digit'}).format(timestamp)
        : (raw.match(/^\d{4}-\d{2}-\d{2}/)?.[0] || '');
      return {day, overdue: Boolean(day && (day < today || (!dateOnly && valid && timestamp.getTime() < Date.now())))};
    }

    function buildTodoGroups(items) {
      const labels = {
        overdue: '已逾期',
        today: '今天',
        next3: '近三天',
        later: '以后',
        nodate: '无日期',
        completed: '已完成',
      };
      const groups = { overdue: [], today: [], next3: [], later: [], nodate: [], completed: [] };
      const todayStr = getTodayDateString();

      const todayDate = new Date(`${todayStr}T00:00:00+08:00`);
      const tomorrowDate = new Date(todayDate.getTime() + 86400000);
      const tomorrowStr = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(tomorrowDate);
      const next3EndDate = new Date(todayDate.getTime() + 3 * 86400000);
      const next3EndStr = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(next3EndDate);

      items.forEach((item) => {
        if (item.done) { groups.completed.push(item); return; }
        if (item.is_scheduled_action && !item.isTodayAction) return;

        // Determine if genuinely overdue:
        // True timestamp deadline before now => overdue; date-only due_date is end-of-day.
        const {day: datePart, overdue: isGenuinelyOverdue} = todoDeadlineState(item);
        item.isGenuinelyOverdue = isGenuinelyOverdue;

        // Genuine overdue priority
        if (isGenuinelyOverdue) {
          item.isGenuinelyOverdue = true;
          groups.overdue.push(item);
          return;
        }

        // Missed plan stays TODAY every day, label '原计划 YYYY-MM-DD', never fake overdue or rewrite due.
        const planDate = (item.plannedOn || item.planned_on || '').slice(0, 10);
        const isMissedPlan = Boolean(item.missed_plan || item.missedPlan || (planDate && planDate < todayStr));
        if (isMissedPlan) {
          item.missedPlan = true;
          groups.today.push(item);
          return;
        }

        // Today items:
        // - Genuine deadline is today
        // - Pure ordinary planned today
        // - Scheduled today / isTodayAction / is_today
        if (datePart === todayStr || planDate === todayStr || item.isTodayAction || item.is_today) {
          groups.today.push(item);
          return;
        }

        // Target comparison date (deadline takes priority, otherwise planned date)
        const targetDate = datePart || planDate;
        if (!targetDate) {
          groups.nodate.push(item);
          return;
        }

        if (targetDate >= tomorrowStr && targetDate <= next3EndStr) {
          groups.next3.push(item);
          return;
        }

        if (targetDate > next3EndStr) {
          groups.later.push(item);
          return;
        }

        groups.nodate.push(item);
      });

      const dueKey = (item) => item.due_ts || (item.plannedOn ? `${item.plannedOn}T00:00:00` : '9999-12-31T23:59:59');
      const sortGroup = (arr) => arr.sort((a, b) =>
        (a.done ? 1 : 0) - (b.done ? 1 : 0) ||
        (b.manualHighlighted ? 1 : 0) - (a.manualHighlighted ? 1 : 0) ||
        dueKey(a).localeCompare(dueKey(b)) || a._stableIndex - b._stableIndex
      );
      Object.values(groups).forEach(sortGroup);
      const order = ['overdue', 'today', 'next3', 'later', 'nodate', 'completed'];
      return order
        .filter((k) => groups[k].length)
        .map((k) => ({ key: k, title: labels[k], items: groups[k] }));
    }

    function compactTodoDateLabel(item, today) {
      if ((item.missedPlan || item.missed_plan) && !item.isGenuinelyOverdue) {
        const pDate = item.plannedOn || item.planned_on || '';
        if (pDate) return `原计划 ${pDate}`;
      }
      const hasDeadline = Boolean(item.due_ts || (item.due_str && !['—', '--'].includes(item.due_str.trim())));
      let day = (hasDeadline ? item.due_str : item.plannedOn) || '';
      let time = '';
      if (hasDeadline && item.due_ts) {
        const timestamp = new Date(item.due_ts);
        if (!Number.isNaN(timestamp.getTime())) {
          day = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(timestamp);
          if (/\d{2}:\d{2}/.test(item.due_str || '')) {
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

    function focusNewTodoComposer() {
      const mobile = window.matchMedia('(max-width: 768px)');
      const composer = document.getElementById('todo-composer');
      const toggle = document.getElementById('mobile-add-toggle');
      if (mobile.matches && composer?.classList.contains('is-collapsed')) {
        toggle?.click();
        return;
      }
      document.getElementById('new-todo-input')?.focus();
    }

    function handleKpiJump(kind) {
      if (kind === 'course') {
        const scheduleCard = document.getElementById('today-schedule-card');
        if (scheduleCard) {
          const behavior = window.uiMotion?.prefersReducedMotion?.() ? 'auto' : 'smooth';
          scheduleCard.scrollIntoView({ behavior, block: 'nearest' });
          window.uiMotion?.pulseArrival?.(scheduleCard);
        }
        return;
      }
      if (todoSourceFilter !== 'all') {
        setTodoSourceFilter('all');
      }
      if (kind === 'due') {
        for (const groupKey of ['overdue', 'today', 'next3']) {
          if (collapsedTodoGroups.has(groupKey)) toggleTodoGroup(groupKey);
        }
        const targetGroup = document.querySelector('#todo-list .todo-group[data-group-key="overdue"], #todo-list .todo-group[data-group-key="today"], #todo-list .todo-group[data-group-key="next3"]');
        if (targetGroup) {
          const behavior = window.uiMotion?.prefersReducedMotion?.() ? 'auto' : 'smooth';
          targetGroup.scrollIntoView({ behavior, block: 'start' });
          window.uiMotion?.pulseArrival?.(targetGroup);
          return;
        }
      }
      const pendingCount = Number(document.getElementById('stat-pending-count')?.textContent || '0');
      if (pendingCount === 0) {
        focusNewTodoComposer();
        return;
      }
      const listCard = document.getElementById('todo-workspace-card');
      const todoList = document.getElementById('todo-list');
      const behavior = window.uiMotion?.prefersReducedMotion?.() ? 'auto' : 'smooth';
      listCard?.scrollIntoView({ behavior, block: 'start' });
      todoList?.scrollTo({ top: 0, behavior });
    }

    function setAnimatedKpiNumber(el, nextValue) {
      if (!el) return;
      if (window.uiMotion?.animateNumber) {
        window.uiMotion.animateNumber(el, nextValue);
      } else {
        el.textContent = String(nextValue);
      }
    }

    function renderUnifiedListNow() {
      const container = document.getElementById('todo-list');
      if (!container) return;
      // Keep the live editor (and its handlers) until the user commits or cancels.
      // Each editor renders again on exit, using the latest fetched data.
      if (container.querySelector('.inline-edit-input, .inline-edit-date-input, .subtask-edit-input')) return;
      const savedScrollTop = container.scrollTop;
      // Background refreshes must not erase a subtask the user is still typing.
      const subtaskDrafts = Array.from(container.querySelectorAll('.subtask-add-row input')).map(input => ({
        id: input.id, value: input.value, focused: input === document.activeElement,
        start: input.selectionStart, end: input.selectionEnd,
      }));

      // Build unified items
      let unified = [];

      // LINK-05: collect today scheduled action references
      const today = getTodayDateString();
      const todayScheduledRefs = new Set();
      if (workspaceTodayData?.days?.[0]?.timed) {
        for (const e of workspaceTodayData.days[0].timed) {
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
          due_ts: item.due_date ? `${item.due_date}T23:59:59+08:00` : null,
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
          missedPlan: Boolean(item.missed_plan),
          plannedOn: item.planned_on || '',
          occurrences: item.occurrences || [],
          ref: item.ref || item.action_ref || `project:${item.project_id}:${item.task_id || item.id}`,
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
          plannedOn: item.planned_on || '',
        });
      });

      // Stable ref dedup
      const seenRefs = new Set();
      const dedupedUnified = [];
      unified.forEach((item) => {
        const ref = item.ref || `${item.source}:${item.rawId || item.id}`;
        if (seenRefs.has(ref)) return;
        seenRefs.add(ref);
        dedupedUnified.push(item);
      });
      unified = dedupedUnified;

      // Stable sorting happens inside each requested time group: highlighted
      // tasks never leap across a due-date group, and completed tasks remain
      // at that group's quiet bottom until their normal retention expires.
      unified.forEach((item, index) => { item._stableIndex = index; });

      renderTodoSourceFilters(unified);
      updateStatsBar(unified);

      // Render compact deadline list on Today overview

      // 侧栏 nav-count 数字：今日总览的未完成待办数
      const overviewCount = unified.filter((it) => !it.done && !it.hidden && (!it.is_scheduled_action || it.isTodayAction)).length;
      const overviewEl = document.querySelector('[data-nav-count="overview"]');
      if (overviewEl) {
        if (overviewCount > 0) { overviewEl.textContent = overviewCount; overviewEl.hidden = false; }
        else { overviewEl.textContent = ''; overviewEl.hidden = true; }
      }

      const todayStr = getTodayDateString();

      const filteredItems = todoSourceFilter === 'all'
        ? unified
        : unified.filter((item) => item.source === todoSourceFilter);

      if (filteredItems.length === 0) {
        const isFiltered = todoSourceFilter !== 'all';
        const emptyTitle = isFiltered ? '该来源暂无待办事项' : '没有待办事项';
        const emptyDesc = isFiltered ? '切换来源或查看全部待办。' : '写一句话就能记下新待办，连接平台后作业也会自动同步到这里。';
        const emptyCtaHtml = isFiltered
          ? '<button type="button" class="ui-button ui-button--secondary" onclick="setTodoSourceFilter(\'all\')">查看全部待办</button>'
          : '<button type="button" class="ui-button ui-button--primary" onclick="focusNewTodoComposer()">添加第一条待办</button>';
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
            <div class="ui-empty__actions">${emptyCtaHtml}</div>
          </div>`;
        return;
      }


      const renderTodoItem = (item) => {
        const isDismissed = item.done || item.hidden;
        const manualFlag = item.manualHighlighted || false;

        // 颜色只由有效截止时间决定，与来源无关：
        // 已逾期 / 今天标红；3 天内截止标黄；其余不标色。
        let urgencyClass = '';
        if (!isDismissed) {
          const dueDate = todoDueDate(item);
          if (dueDate) {
            const daysLeft = Math.round((dueDate.getTime() - new Date(todayStr + 'T00:00:00').getTime()) / 86400000);
            if (daysLeft < 0) {
              urgencyClass = 'urgent is-overdue';
            } else if (daysLeft === 0) {
              urgencyClass = 'urgent is-today';
            } else if (daysLeft <= 3) {
              urgencyClass = 'approaching is-approaching';
            } else {
              urgencyClass = 'remote is-normal';
            }
          } else if (item.isTodayAction) {
            urgencyClass = 'urgent is-today';
          } else {
            urgencyClass = 'remote';
          }
        }

        if (todoDeadlineState(item).overdue) urgencyClass = 'urgent is-overdue';
        else if (item.missedPlan) urgencyClass = 'remote is-missed-plan';
        const flagIcon = manualFlag ? '&#x2691;' : '&#x2690;';
        const flagTitle = manualFlag ? '取消标红' : '置顶标红';
        const flagClass = manualFlag ? 'btn-flag active' : 'btn-flag';
        const dismissTitle = isDismissed ? '取消完成' : '标记完成';
        const dismissAriaLabel = isDismissed ? '取消完成' : '完成';
        // 只有逾期行保留红底与左侧强调线；今天与近三天只用截止标签的颜色区分，行底色保持正常。
        const uiListStateClass = urgencyClass.includes('is-overdue') ? ' ui-list-item--danger' : '';
        const uiListMutedClass = isDismissed ? ' ui-list-item--muted' : '';

        const detailRef = item.ref || (item.source === 'project'
          ? (item.taskId === null ? `project_due:${item.projectId}` : `project:${item.projectId}:${item.taskId}`)
          : `${item.source}:${item.rawId}`);
        const escapedDetailRef = escapeHtml(detailRef);
        const detailBtnHtml = `<button type="button" class="todo-action-button btn-detail" data-todo-detail="${escapedDetailRef}" title="查看详情与排程" aria-label="查看详情与排程">详情</button>`;

        let flagBtnHtml = '';
        let dismissBtnHtml = '';
        let skipBtnHtml = '';
        let deleteBtnHtml = '';

        if (item.source === 'canvas') {
          flagBtnHtml = `<button type="button" class="todo-action-button ${flagClass}" onclick="toggleHighlight('${item.id}', ${manualFlag})" title="${flagTitle}" aria-label="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>`;
          dismissBtnHtml = `<button type="button" class="btn-dismiss" onclick="togglePlatformCompletion('canvas', '${escapeHtml(String(item.rawId))}', ${item.done})" title="${dismissTitle}" aria-label="${dismissAriaLabel}">${item.done ? '↺' : '✓'}</button>`;
          deleteBtnHtml = `<button type="button" class="btn-delete" onclick="toggleCanvasDelete('${escapeHtml(String(item.rawId))}')" title="从清单隐藏" aria-label="从清单隐藏">&#x1f5d1;</button>`;
        } else if (item.source === 'haoke') {
          flagBtnHtml = `<button type="button" class="todo-action-button ${flagClass}" onclick="togglePlatformHighlight('haoke', ${JSON.stringify(item.rawId)}, ${manualFlag})" title="${flagTitle}" aria-label="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>`;
          dismissBtnHtml = `<button type="button" class="btn-dismiss" onclick="togglePlatformCompletion('haoke', ${item.rawId}, ${item.done})" title="${dismissTitle}" aria-label="${dismissAriaLabel}">${item.done ? '↺' : '✓'}</button>`;
          deleteBtnHtml = `<button type="button" class="btn-delete" onclick="toggleHaokeDelete(${item.rawId})" title="从清单隐藏" aria-label="从清单隐藏">&#x1f5d1;</button>`;
        } else if (item.source === 'custom') {
          if (item.is_recurring) {
            dismissBtnHtml = `<button type="button" class="btn-dismiss" onclick="toggleRecurringCheck(${item.series_id}, '${escapeHtml(item.original_due_date)}', ${item.done})" title="${dismissTitle}" aria-label="${dismissAriaLabel}">${item.done ? '↺' : '✓'}</button>`;
            skipBtnHtml = `<button type="button" class="todo-action-button btn-action-skip" onclick="skipRecurringOccurrence(${item.series_id}, '${escapeHtml(item.original_due_date)}')" title="跳过本次" aria-label="跳过本次">⏭</button>`;
            deleteBtnHtml = `<button type="button" class="btn-delete" onclick="deleteRecurringSeries(${item.series_id})" title="删除系列" aria-label="永久删除重复待办系列">&#x1f5d1;</button>`;
          } else {
            const isDeleting = deletingCustomIds.has(item.rawId);
            flagBtnHtml = `<button type="button" class="todo-action-button ${flagClass}" onclick="toggleCustomHighlight(${item.rawId}, ${manualFlag})" title="${flagTitle}" aria-label="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>`;
            dismissBtnHtml = `<button type="button" class="btn-dismiss" onclick="toggleTodoCheck(${item.rawId}, ${item.done})" title="${dismissTitle}" aria-label="${dismissAriaLabel}">${item.done ? '↺' : '✓'}</button>`;
            deleteBtnHtml = `<button type="button" class="btn-delete" onclick="toggleCustomDelete(${item.rawId})" ${isDeleting ? 'disabled aria-busy="true"' : ''} title="永久删除" aria-label="永久删除">&#x1f5d1;</button>`;
          }
        } else if (item.source === 'zhixuemeng') {
          const zxmId = String(item.rawId);
          flagBtnHtml = `<button type="button" class="todo-action-button ${flagClass}" onclick="togglePlatformHighlight('zhixuemeng', ${JSON.stringify(zxmId)}, ${manualFlag})" title="${flagTitle}" aria-label="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>`;
          dismissBtnHtml = `<button type="button" class="btn-dismiss" onclick="togglePlatformCompletion('zhixuemeng', '${escapeHtml(zxmId)}', ${item.done})" title="${dismissTitle}" aria-label="${dismissAriaLabel}">${item.done ? '↺' : '✓'}</button>`;
          deleteBtnHtml = `<button type="button" class="btn-delete" onclick="toggleZhixuemengDelete('${escapeHtml(zxmId)}')" title="从清单隐藏" aria-label="从清单隐藏">&#x1f5d1;</button>`;
        } else if (item.source === 'zhihuishu') {
          flagBtnHtml = `<button type="button" class="todo-action-button ${flagClass}" onclick="togglePlatformHighlight('zhihuishu', ${JSON.stringify(item.rawId)}, ${manualFlag})" title="${flagTitle}" aria-label="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>`;
          dismissBtnHtml = `<button type="button" class="btn-dismiss" onclick="togglePlatformCompletion('zhihuishu', '${escapeHtml(String(item.rawId))}', ${item.done})" title="${dismissTitle}" aria-label="${dismissAriaLabel}">${item.done ? '↺' : '✓'}</button>`;
          deleteBtnHtml = `<button type="button" class="btn-delete" onclick="toggleZhihuishuDelete('${escapeHtml(String(item.rawId))}')" title="从清单隐藏" aria-label="从清单隐藏">&#x1f5d1;</button>`;
        } else if (item.source === 'ketangpai') {
          flagBtnHtml = `<button type="button" class="todo-action-button ${flagClass}" onclick="togglePlatformHighlight('ketangpai', ${JSON.stringify(item.rawId)}, ${manualFlag})" title="${flagTitle}" aria-label="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>`;
          dismissBtnHtml = `<button type="button" class="btn-dismiss" onclick="togglePlatformCompletion('ketangpai', '${escapeHtml(String(item.rawId))}', ${item.done})" title="${dismissTitle}" aria-label="${dismissAriaLabel}">${item.done ? '↺' : '✓'}</button>`;
          deleteBtnHtml = `<button type="button" class="btn-delete" onclick="toggleKetangpaiDelete('${escapeHtml(String(item.rawId))}')" title="从清单隐藏" aria-label="从清单隐藏">&#x1f5d1;</button>`;
        } else if (item.source === 'tongjioj') {
          flagBtnHtml = `<button type="button" class="todo-action-button ${flagClass}" onclick="togglePlatformHighlight('tongjioj', ${JSON.stringify(item.rawId)}, ${manualFlag})" title="${flagTitle}" aria-label="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>`;
          dismissBtnHtml = `<button type="button" class="btn-dismiss" onclick="togglePlatformCompletion('tongjioj', '${escapeHtml(String(item.rawId))}', ${item.done})" title="${dismissTitle}" aria-label="${dismissAriaLabel}">${item.done ? '↺' : '✓'}</button>`;
          deleteBtnHtml = `<button type="button" class="btn-delete" onclick="toggleTongjiojDelete('${escapeHtml(String(item.rawId))}')" title="从清单隐藏" aria-label="从清单隐藏">&#x1f5d1;</button>`;
        } else if (item.source === 'project') {
          const taskArg = item.taskId === null ? 'null' : item.taskId;
          flagBtnHtml = `<button type="button" class="todo-action-button ${flagClass}" onclick="toggleOverviewProjectFlag(${item.projectId}, ${taskArg}, '${item.projectKind}', ${manualFlag})" title="${flagTitle}" aria-label="${flagTitle}" aria-pressed="${manualFlag}">${flagIcon}</button>`;
          dismissBtnHtml = `<button type="button" class="btn-dismiss" onclick="completeOverviewProjectTodo(${item.projectId}, ${taskArg}, '${item.projectKind}')" title="标记完成" aria-label="完成">✓</button>`;
          deleteBtnHtml = `<button type="button" class="btn-delete" onclick="deleteProjectTodo(${item.projectId}, ${taskArg}, '${item.projectKind}')" title="${item.projectKind === 'project_due' ? '清除项目截止日期' : '永久删除'}" aria-label="${item.projectKind === 'project_due' ? '清除项目截止日期' : '删除'}">&#x1f5d1;</button>`;
        }

        const desktopActionsHtml = `${dismissBtnHtml}${flagBtnHtml}${detailBtnHtml}${skipBtnHtml}${deleteBtnHtml}`;
        const mobileActionsHtml = `${flagBtnHtml}${dismissBtnHtml}${deleteBtnHtml}${skipBtnHtml}<button type="button" class="ui-button ui-button--secondary" data-mobile-detail="${escapedDetailRef}">详情</button>`;

        const safeUrl = sanitizeExternalUrl(item.url);
        const titleHtml = item.is_recurring
          ? `<button type="button" class="ui-button ui-button--text ui-list-item__title item-title action-title-button" onclick="openActionDetail('${escapeHtml(item.ref)}')">${escapeHtml(item.title)}</button>`
          : (item.source === 'custom'
            ? `<span class="ui-list-item__title item-title item-title-plain editable-title" data-id="${item.rawId}" data-field="text" tabindex="0" role="button" aria-label="编辑待办标题：${escapeHtml(item.title)}" title="点击或按回车编辑标题">${escapeHtml(item.title)}</span>`
            : (item.source === 'project'
              ? `<button type="button" class="ui-button ui-button--text ui-list-item__title item-title action-title-button" onclick="openActionDetail('${item.taskId === null ? 'project_due:' + item.projectId : 'project:' + item.projectId + ':' + item.taskId}')">${escapeHtml(item.title)}</button>`
              : (safeUrl ? `<a class="ui-list-item__title item-title" href="${safeUrl}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</a>` : `<span class="ui-list-item__title item-title item-title-plain">${escapeHtml(item.title)}</span>`)));
        const dueLabel = `<span class="todo-date-desktop">${escapeHtml(item.due_str || (item.source === 'project' ? item.plannedOn : '') || '')}</span><span class="todo-date-mobile">${escapeHtml(compactTodoDateLabel(item, todayStr))}</span>`;
        const dueHtml = (item.source === 'custom' && !item.is_recurring)
          ? `<span class="ui-list-item__meta item-due editable-due" data-id="${item.rawId}" data-field="due_date" data-value="${escapeHtml(item.due_str || '')}" tabindex="0" role="button" aria-label="修改截止日期：${escapeHtml(item.due_str || '未设截止')}" title="点击或按回车修改截止日期">${dueLabel}</span>`
          : item.source === 'project'
            ? `<button type="button" class="ui-button ui-button--text ui-list-item__meta item-due project-due-editable" data-project-id="${item.projectId}" data-task-id="${item.taskId === null ? '' : item.taskId}" data-project-kind="${item.projectKind}" data-date-field="${(item.missedPlan && !item.isGenuinelyOverdue) || (!item.due_str && item.isTodayAction) ? 'planned_on' : 'due_date'}" data-date-value="${item.missedPlan && !item.isGenuinelyOverdue ? item.plannedOn : (item.due_str || item.plannedOn)}" aria-label="${(item.missedPlan && !item.isGenuinelyOverdue) || (!item.due_str && item.isTodayAction) ? '修改计划日期' : '修改截止日期'}" title="${(item.missedPlan && !item.isGenuinelyOverdue) || (!item.due_str && item.isTodayAction) ? '计划推进：' + (item.plannedOn || '') + '（点击修改）' : '截止日期：' + (item.due_str || item.plannedOn || '') + '（点击修改）'}">${dueLabel}</button>`
            : `<span class="ui-list-item__meta item-due">${dueLabel}</span>`;

        const srcLabels = { canvas: 'Canvas', haoke: '好课', zhixuemeng: '智学盟', zhihuishu: '智慧树', ketangpai: '课堂派', tongjioj: '同济OJ', project: '项目', custom: '自定义' };
        const tagLabel = srcLabels[item.source] || item.type || '';
        const tagHtml = tagLabel ? `<span class="ui-source-tag ui-source-tag--${item.source}">${escapeHtml(tagLabel)}</span>` : '';

        const subtasks = item.subtasks || [];
        const supportsSubtasks = ['custom', 'canvas', 'haoke', 'zhixuemeng', 'zhihuishu', 'ketangpai', 'tongjioj'].includes(item.source) && !item.is_recurring;
        const itemKey = todoKey(item.source, item.rawId);
        const isSubtaskExpanded = supportsSubtasks && (expandedTodoKeys.includes(itemKey) || (item.source === 'custom' && expandedCustomTodoIds.includes(item.rawId)));
        const doneSubtasks = subtasks.filter((s) => s.done).length;
        const subtaskCountSuffix = subtasks.length ? `（${doneSubtasks}/${subtasks.length}）` : '';
        const subtaskToggleLabel = (isSubtaskExpanded ? '收起子任务' : '展开子任务') + subtaskCountSuffix;
        const subtaskToggleIcon = isSubtaskExpanded ? '&#x25be;' : '&#x25b8;';
        const subtaskCountPill = (!isSubtaskExpanded && subtasks.length > 0)
          ? `<span class="subtask-count-pill" aria-hidden="true">${doneSubtasks}/${subtasks.length}</span>`
          : '';
        const sourceArg = JSON.stringify(item.source);
        const rawIdArg = JSON.stringify(String(item.rawId));
        const subtaskToggleHtml = supportsSubtasks
          ? `<button type="button" class="subtask-toggle" onclick='toggleSubtasks(${sourceArg}, ${rawIdArg})' title="${subtaskToggleLabel}" aria-label="${subtaskToggleLabel}" aria-expanded="${isSubtaskExpanded}">${subtaskToggleIcon}${subtaskCountPill}</button>`
          : '<span class="subtask-toggle subtask-toggle-placeholder" aria-hidden="true"></span>';
        const mobileActionsOpen = openMobileActionItemId === item.id;


        // 设计稿两行结构：body（上：标题+副标题）+ right（下：来源+截止胶囊+操作）
        // 副标题：课程名 · 类型 · 截止时间
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
        const flipKey = escapeHtml(item.ref || `${item.source}:${item.rawId}`);
        const rowFlipAttr = supportsSubtasks ? '' : ` data-flip-key="${flipKey}"`;

        const rowHtml = `
          <div class="ui-list-item ui-list-item--interactive todo-row${uiListStateClass}${uiListMutedClass}${projectMainClass} ${urgencyClass} ${manualFlag ? 'manual-flagged' : ''} ${isDismissed ? 'dismissed' : ''}"${rowFlipAttr} data-todo-id="${escapeHtml(item.id)}" data-source="${escapeHtml(item.source)}">
            <div class="biz-todo__body">
              <div class="biz-todo__title">${titleHtml}</div>
              ${metaHtml}
            </div>
            <div class="biz-todo__right">
              <span class="item-source-badge" title="${item.course ? escapeHtml(item.course) : escapeHtml(item.type)}">
                <span class="ui-badge ui-badge--source ui-source--${item.source} src-${item.source}">${escapeHtml(item.type)}</span>
                ${item.disconnected ? '<span class="ui-status ui-status--warning">已断开</span>' : ''}
              </span>
              ${dueHtml}
              <span class="item-subtask-slot">${subtaskToggleHtml}</span>
              <span class="item-desktop-actions">${desktopActionsHtml}</span>
            </div>
            <button type="button" class="ui-icon-button mobile-action-trigger" onclick="toggleMobileActions('${escapeHtml(item.id)}')" aria-label="更多操作" aria-expanded="${mobileActionsOpen}">•••</button>
            <span class="item-mobile-actions ${mobileActionsOpen ? 'open' : ''}">${mobileActionsHtml}</span>
          </div>
        `;

        if (!supportsSubtasks) {
          return rowHtml;
        }

        const panelHtml = isSubtaskExpanded ? renderSubtaskPanel(item.source, item.rawId, subtasks) : '';
        return `
          <div class="todo-row-wrap" data-flip-key="${flipKey}" data-todo-key="${escapeHtml(itemKey)}">
            ${rowHtml}
            <div class="ui-collapse todo-subtask-collapse${isSubtaskExpanded ? '' : ' is-collapsed'}">
              <div class="ui-collapse__inner">${panelHtml}</div>
            </div>
          </div>
        `;
      };

      container.innerHTML = buildTodoGroups(filteredItems).map((group) => {
        const isCollapsed = collapsedTodoGroups.has(group.key);
        return `
        <section class="todo-group ${group.key === 'overdue' ? 'is-overdue' : ''} ${group.key === 'completed' ? 'is-completed' : ''} ${isCollapsed ? 'is-collapsed' : ''}" data-group-key="${group.key}">
          <div class="todo-group-heading" onclick="toggleTodoGroup('${group.key}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleTodoGroup('${group.key}');}" role="button" tabindex="0" aria-expanded="${!isCollapsed}" title="${isCollapsed ? '点击展开' : '点击折叠'}">
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
          <div class="ui-collapse${isCollapsed ? ' is-collapsed' : ''}">
            <div class="todo-group-items ui-collapse__inner">${group.items.map(renderTodoItem).join('')}</div>
          </div>
        </section>
        `;
      }).join('');

      // Pre-merge progressive fallback when motion.css (.ui-collapse grid rules) is not loaded yet
      const firstCollapse = container.querySelector('.ui-collapse');
      if (firstCollapse && getComputedStyle(firstCollapse).display !== 'grid') {
        container.querySelectorAll('.ui-collapse.is-collapsed > .ui-collapse__inner').forEach((inner) => {
          inner.style.display = 'none';
        });
      }

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

      if (_pendingPulseTodoKey) {
        const pulseTarget = container.querySelector(`[data-flip-key="${CSS.escape(_pendingPulseTodoKey)}"]`);
        _pendingPulseTodoKey = null;
        const pulseRow = pulseTarget?.classList?.contains('todo-row') ? pulseTarget : pulseTarget?.querySelector('.todo-row');
        if (pulseRow) window.uiMotion?.pulseArrival?.(pulseRow);
      }
      if (_pendingFocusSelector) {
        const focusEl = container.querySelector(_pendingFocusSelector);
        _pendingFocusSelector = null;
        focusEl?.focus({ preventScroll: true });
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
      const activeItems = unified.filter(item => !item.done && !item.hidden && (!item.is_scheduled_action || item.isTodayAction));
      const pending = activeItems.length;
      const completedCount = unified.filter(item => item.done && !item.hidden).length;

      const todayStr = getTodayDateString();
      const now = Date.now();

      let due72h = 0;
      let overdue = 0;
      let todayCount = 0;
      activeItems.forEach(item => {
        const deadline = todoDeadlineState(item);
        const planDate = (item.plannedOn || item.planned_on || '').slice(0, 10);
        const isMissedPlan = Boolean(item.missed_plan || item.missedPlan || (planDate && planDate < todayStr));
        if (deadline.overdue) {
          overdue++;
          due72h++;
        } else {
          if (item.due_ts) {
            const dueTime = new Date(item.due_ts).getTime();
            const hoursLeft = (dueTime - now) / 3600000;
            if (hoursLeft <= 72) due72h++;
          }
          if (isMissedPlan || deadline.day === todayStr || planDate === todayStr || item.isTodayAction || item.is_today) {
            todayCount++;
          }
        }
      });

      // Update Top KPI Cards
      const pendingCountEl = document.getElementById('stat-pending-count');
      const pendingDiffEl = document.getElementById('stat-pending-diff');
      const dueCountEl = document.getElementById('stat-due-count');
      const dueOverdueEl = document.getElementById('stat-due-overdue');

      setAnimatedKpiNumber(pendingCountEl, pending);
      if (pendingDiffEl) {
        pendingDiffEl.textContent = pending > 0
          ? `今日 ${todayCount} 项 · 已完成 ${completedCount} 项`
          : (completedCount > 0 ? `全部清零 · 已完成 ${completedCount} 项` : '全部清零');
      }
      setAnimatedKpiNumber(dueCountEl, due72h);
      if (dueOverdueEl) {
        dueOverdueEl.textContent = overdue > 0 ? `含 ${overdue} 项已逾期` : '无逾期事项';
        dueOverdueEl.classList.toggle('warn', overdue > 0);
      }
    }

    const PLATFORM_COLLECTIONS = {
      canvas: {
        getItems: () => canvasItems,
        getDeleted: () => canvasDeletedIds,
        setDeleted: (v) => { canvasDeletedIds = v; },
        getHidden: () => hiddenIds,
        setHidden: (v) => { hiddenIds = v; },
        getHighlighted: () => highlightedIds,
        setHighlighted: (v) => { highlightedIds = v; },
        refresh: () => fetchCanvasTodos(),
      },
      haoke: {
        getItems: () => haokeItems,
        getDeleted: () => haokeDeletedIds,
        setDeleted: (v) => { haokeDeletedIds = v; },
        getHidden: () => haokeHiddenIds,
        setHidden: (v) => { haokeHiddenIds = v; },
        getHighlighted: () => haokeHighlightedIds,
        setHighlighted: (v) => { haokeHighlightedIds = v; },
        refresh: () => fetchHaokeTodos(),
      },
      zhixuemeng: {
        getItems: () => zhixuemengItems,
        getDeleted: () => zhixuemengDeletedIds,
        setDeleted: (v) => { zhixuemengDeletedIds = v; },
        getHidden: () => zhixuemengHiddenIds,
        setHidden: (v) => { zhixuemengHiddenIds = v; },
        getHighlighted: () => zhixuemengHighlightedIds,
        setHighlighted: (v) => { zhixuemengHighlightedIds = v; },
        refresh: () => fetchZhixuemengTodos(),
      },
      zhihuishu: {
        getItems: () => zhihuishuItems,
        getDeleted: () => zhihuishuDeletedIds,
        setDeleted: (v) => { zhihuishuDeletedIds = v; },
        getHidden: () => zhihuishuHiddenIds,
        setHidden: (v) => { zhihuishuHiddenIds = v; },
        getHighlighted: () => zhihuishuHighlightedIds,
        setHighlighted: (v) => { zhihuishuHighlightedIds = v; },
        refresh: () => fetchZhihuishuTodos(),
      },
      ketangpai: {
        getItems: () => ketangpaiItems,
        getDeleted: () => ketangpaiDeletedIds,
        setDeleted: (v) => { ketangpaiDeletedIds = v; },
        getHidden: () => ketangpaiHiddenIds,
        setHidden: (v) => { ketangpaiHiddenIds = v; },
        getHighlighted: () => ketangpaiHighlightedIds,
        setHighlighted: (v) => { ketangpaiHighlightedIds = v; },
        refresh: () => fetchKetangpaiTodos(),
      },
      tongjioj: {
        getItems: () => tongjiojItems,
        getDeleted: () => tongjiojDeletedIds,
        setDeleted: (v) => { tongjiojDeletedIds = v; },
        getHidden: () => tongjiojHiddenIds,
        setHidden: (v) => { tongjiojHiddenIds = v; },
        getHighlighted: () => tongjiojHighlightedIds,
        setHighlighted: (v) => { tongjiojHighlightedIds = v; },
        refresh: () => fetchTongjiojTodos(),
      },
    };

    async function togglePlatformCompletion(platform, id, done) {
      const lockKey = `${platform}:${id}`;
      if (todoInFlightKeys.has(lockKey)) return;
      const cfg = PLATFORM_COLLECTIONS[platform];
      const item = (cfg?.getItems() || []).find((entry) => String(entry.id) === String(id));
      const prevDone = Boolean(item?.done);
      const wasOverdue = item ? todoDeadlineState(item).overdue : false;
      const shortTitle = shortTodoToastTitle(item?.title || '该待办');

      todoInFlightKeys.add(lockKey);
      if (item) item.done = !done;
      flipTodoList(() => renderUnifiedListNow());

      try {
        const response = await fetch(`/api/${platform}/state`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({action: done ? 'uncomplete' : 'complete', id}),
        });
        if (!response.ok) throw new Error('state update failed');
        if (!done) {
          if (cfg?.refresh) await cfg.refresh();
          if (!wasOverdue) {
            showUiToast(`已完成「${shortTitle}」`, {
              tone: 'success',
              actionLabel: '撤销',
              onAction: () => togglePlatformCompletion(platform, id, true),
            });
          } else {
            showUiToast(`已完成「${shortTitle}」（已过截止，自动清理）`, { tone: 'info' });
          }
        } else {
          showUiToast(`已恢复「${shortTitle}」`, { tone: 'info' });
        }
        if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
      } catch (error) {
        if (item) item.done = prevDone;
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('状态更新失败，已恢复原状', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
    }

    function renderSubtaskPanel(source, todoId, subtasks) {
      if (typeof source === 'number' || (typeof source === 'string' && subtasks === undefined)) {
        subtasks = todoId;
        todoId = source;
        source = 'custom';
      }
      const sourceArg = JSON.stringify(source);
      const todoIdArg = JSON.stringify(String(todoId));
      const rowsHtml = (subtasks || []).map((subtask, idx) => {
        const sid = subtask.id != null ? subtask.id : idx;
        const dueDateVal = subtask.due_date || '';
        const subFlipKey = `sub:${source}:${todoId}:${sid}`;
        return `
        <div class="ui-list-item todo-subtask-row" data-flip-key="${escapeHtml(subFlipKey)}">
          <input type="checkbox" ${subtask.done ? 'checked' : ''} onchange='toggleSubtaskDone(${sourceArg}, ${todoIdArg}, ${sid})' class="ui-checkbox" aria-label="完成子任务：${escapeHtml(subtask.text)}">
          <span class="ui-list-item__title subtask-text ${subtask.done ? 'done' : ''}" title="${escapeHtml(subtask.text)}" tabindex="0" role="button" aria-label="编辑子任务：${escapeHtml(subtask.text)}" onclick='startSubtaskEdit(${sourceArg}, ${todoIdArg}, ${sid}, this)' onkeydown='if(event.key==="Enter"||event.key===" "){event.preventDefault();startSubtaskEdit(${sourceArg}, ${todoIdArg}, ${sid}, this);}'>${escapeHtml(subtask.text)}</span>
          <input type="date" class="ui-control subtask-due-input" value="${escapeHtml(dueDateVal)}" onchange='handleSubtaskDueChange(${sourceArg}, ${todoIdArg}, ${sid}, this.value)' title="截止日期" aria-label="子任务截止日期">
          <button type="button" class="ui-icon-button subtask-delete" onclick='deleteSubtask(${sourceArg}, ${todoIdArg}, ${sid})' title="删除子任务" aria-label="删除子任务">✕</button>
        </div>
      `;
      }).join('');

      return `
        <div class="ui-card ui-card--subtle todo-subtask-panel">
          ${rowsHtml}
          <form class="subtask-add-row subtask-add-form" onsubmit="event.preventDefault(); submitSubtaskAdd(${sourceArg}, ${todoIdArg});">
            <input type="text" class="ui-control subtask-add-input" id="subtask-add-text-${escapeHtml(String(source))}-${escapeHtml(String(todoId))}" name="subtask_title" placeholder="添加子步骤，按 Enter 快速添加..." autocomplete="off" data-lpignore="true" onkeydown='handleSubtaskAddKey(event, ${sourceArg}, ${todoIdArg})'>
            <input type="date" class="ui-control subtask-add-due-input" id="subtask-add-due-${escapeHtml(String(source))}-${escapeHtml(String(todoId))}" name="subtask_due" value="" autocomplete="off" onkeydown='handleSubtaskAddKey(event, ${sourceArg}, ${todoIdArg})' title="截止日期（选填）" aria-label="子任务截止日期">
            <button type="button" class="ui-button ui-button--primary subtask-add-btn" onclick='submitSubtaskAdd(${sourceArg}, ${todoIdArg})' title="添加子任务">添加</button>
          </form>
        </div>
      `;
    }

    function renderSubtaskPanelInPlace(source, todoId) {
      const key = todoKey(source, todoId);
      const wrap = document.querySelector(`#todo-list .todo-row-wrap[data-todo-key="${CSS.escape(key)}"]`);
      const todo = findTodo(source, todoId);
      if (!wrap || !todo) {
        renderUnifiedListNow();
        return;
      }
      const subtasks = todo.subtasks || [];
      const doneCount = subtasks.filter((s) => s.done).length;
      const isExpanded = expandedTodoKeys.includes(key);
      const toggleBtn = wrap.querySelector('.subtask-toggle');
      if (toggleBtn) {
        const countSuffix = subtasks.length ? `（${doneCount}/${subtasks.length}）` : '';
        const label = (isExpanded ? '收起子任务' : '展开子任务') + countSuffix;
        toggleBtn.title = label;
        toggleBtn.setAttribute('aria-label', label);
        toggleBtn.setAttribute('aria-expanded', String(isExpanded));
        toggleBtn.innerHTML = (isExpanded ? '&#x25be;' : '&#x25b8;')
          + (!isExpanded && subtasks.length > 0 ? `<span class="subtask-count-pill" aria-hidden="true">${doneCount}/${subtasks.length}</span>` : '');
      }
      const inner = wrap.querySelector('.todo-subtask-collapse .ui-collapse__inner');
      if (!inner) return;
      const draftInputs = Array.from(inner.querySelectorAll('.subtask-add-row input')).map((input) => ({
        id: input.id,
        value: input.value,
        focused: input === document.activeElement,
        start: input.selectionStart,
        end: input.selectionEnd,
      }));
      inner.innerHTML = renderSubtaskPanel(source, todoId, subtasks);
      for (const draft of draftInputs) {
        const input = document.getElementById(draft.id);
        if (!input) continue;
        input.value = draft.value;
        if (draft.focused) {
          input.focus({ preventScroll: true });
          if (input.type !== 'date' && draft.start !== null) input.setSelectionRange(draft.start, draft.end);
        }
      }
    }

    async function togglePlatformHighlight(platform, rawId, current) {
      const cfg = PLATFORM_COLLECTIONS[platform];
      if (!cfg) return;
      const lockKey = `${platform}:flag:${rawId}`;
      if (todoInFlightKeys.has(lockKey)) return;
      todoInFlightKeys.add(lockKey);

      const prevHighlighted = [...cfg.getHighlighted()];
      const nextHighlighted = current
        ? prevHighlighted.filter((id) => String(id) !== String(rawId))
        : (prevHighlighted.some((id) => String(id) === String(rawId)) ? prevHighlighted : [...prevHighlighted, rawId]);

      cfg.setHighlighted(nextHighlighted);
      flipTodoList(() => renderUnifiedListNow());

      try {
        const response = await fetch(`/api/${platform}/state`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: current ? 'unhighlight' : 'highlight', id: rawId }),
        });
        if (!response.ok) throw new Error('flag update failed');
      } catch (error) {
        cfg.setHighlighted(prevHighlighted);
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('标红状态更新失败，已恢复原状', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
    }

    async function toggleHighlight(itemId, current) {
      const rawId = String(itemId).startsWith('c') ? String(itemId).substring(1) : itemId;
      await togglePlatformHighlight('canvas', rawId, current);
    }

    async function toggleHide(itemId, current) {
      const rawId = String(itemId).startsWith('c') ? String(itemId).substring(1) : itemId;
      const lockKey = `canvas:hide:${rawId}`;
      if (todoInFlightKeys.has(lockKey)) return;
      todoInFlightKeys.add(lockKey);

      const item = canvasItems.find((entry) => String(entry.id) === String(rawId));
      const shortTitle = shortTodoToastTitle(item?.title || '该事项');
      const prevHidden = [...hiddenIds];
      hiddenIds = current
        ? prevHidden.filter((id) => String(id) !== String(rawId))
        : (prevHidden.some((id) => String(id) === String(rawId)) ? prevHidden : [...prevHidden, rawId]);
      flipTodoList(() => renderUnifiedListNow());

      try {
        const resp = await fetch('/api/canvas/state', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: current ? 'unhide' : 'hide', id: rawId }),
        });
        if (!resp.ok) throw new Error('hide update failed');
        if (!current) {
          showUiToast(`已隐藏「${shortTitle}」`, {
            tone: 'neutral',
            actionLabel: '撤销',
            onAction: () => toggleHide(itemId, true),
          });
        }
      } catch (error) {
        hiddenIds = prevHidden;
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('隐藏操作失败，已恢复原状', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
    }

    async function toggleOverviewProjectFlag(projectId, taskId, kind, current) {
      const lockKey = `project:flag:${projectId}:${taskId}`;
      if (todoInFlightKeys.has(lockKey)) return;
      todoInFlightKeys.add(lockKey);

      const matched = projectItems.filter((it) =>
        Number(it.project_id) === Number(projectId) &&
        (kind === 'project_due' ? it.kind === 'project_due' : Number(it.task_id) === Number(taskId))
      );
      const prevFlagged = matched.map((it) => Boolean(it.flagged));
      matched.forEach((it) => { it.flagged = !current; });
      flipTodoList(() => renderUnifiedListNow());

      const url = kind === 'project_due' ? `/api/projects/${projectId}` : `/api/projects/${projectId}/tasks/${taskId}`;
      const payload = kind === 'project_due' ? { due_highlighted: !current } : { highlighted: !current };
      try {
        const resp = await fetch(url, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.ok === false) throw new Error(data.error || '标红同步失败');
        if (typeof refreshProjectSurfaces === 'function') await refreshProjectSurfaces();
      } catch (error) {
        matched.forEach((it, idx) => { it.flagged = prevFlagged[idx]; });
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('标红状态同步失败，已恢复原状', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
    }

    async function completeOverviewProjectTodo(projectId, taskId, kind) {
      if (kind === 'project_due') {
        if (typeof completeProjectTodo === 'function') return completeProjectTodo(projectId, taskId, kind);
        return;
      }
      const lockKey = `project:${projectId}:${taskId}`;
      if (todoInFlightKeys.has(lockKey)) return;
      todoInFlightKeys.add(lockKey);

      const prevItems = [...projectItems];
      const target = projectItems.find((it) => Number(it.project_id) === Number(projectId) && Number(it.task_id) === Number(taskId));
      const shortTitle = shortTodoToastTitle(target?.title || '项目步骤');
      projectItems = projectItems.filter((it) => !(Number(it.project_id) === Number(projectId) && Number(it.task_id) === Number(taskId)));
      flipTodoList(() => renderUnifiedListNow());

      try {
        const resp = await fetch(`/api/projects/${projectId}/tasks/${taskId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ done: true }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.ok === false) throw new Error(data.error || '完成同步失败');
        if (typeof refreshProjectSurfaces === 'function') await refreshProjectSurfaces();
        else if (typeof fetchProjectTodos === 'function') await fetchProjectTodos();
        showUiToast(`已完成「${shortTitle}」`, {
          tone: 'success',
          actionLabel: '撤销',
          onAction: async () => {
            try {
              const undoResp = await fetch(`/api/projects/${projectId}/tasks/${taskId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ done: false }),
              });
              if (!undoResp.ok) throw new Error('undo failed');
              if (typeof refreshProjectSurfaces === 'function') await refreshProjectSurfaces();
              else if (typeof fetchProjectTodos === 'function') await fetchProjectTodos();
            } catch (_) {
              showUiToast('撤销失败，请到项目页操作', { tone: 'danger' });
            }
          },
        });
      } catch (error) {
        projectItems = prevItems;
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('任务完成状态同步失败，已恢复', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
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
      const isExpanding = !expandedTodoKeys.includes(key);
      if (isExpanding) {
        expandedTodoKeys.push(key);
      } else {
        expandedTodoKeys = expandedTodoKeys.filter(k => k !== key);
      }
      expandedCustomTodoIds = expandedTodoKeys;

      const wrap = document.querySelector(`#todo-list .todo-row-wrap[data-todo-key="${CSS.escape(key)}"]`);
      if (!wrap) return;
      const todo = findTodo(source, todoId);
      const subtasks = todo?.subtasks || [];
      const doneCount = subtasks.filter((s) => s.done).length;
      const countSuffix = subtasks.length ? `（${doneCount}/${subtasks.length}）` : '';
      const toggleBtn = wrap.querySelector('.subtask-toggle');
      if (toggleBtn) {
        const label = (isExpanding ? '收起子任务' : '展开子任务') + countSuffix;
        toggleBtn.title = label;
        toggleBtn.setAttribute('aria-label', label);
        toggleBtn.setAttribute('aria-expanded', String(isExpanding));
        toggleBtn.innerHTML = (isExpanding ? '&#x25be;' : '&#x25b8;')
          + (!isExpanding && subtasks.length > 0 ? `<span class="subtask-count-pill" aria-hidden="true">${doneCount}/${subtasks.length}</span>` : '');
      }
      const collapse = wrap.querySelector('.todo-subtask-collapse');
      const inner = collapse?.querySelector('.ui-collapse__inner');
      if (collapse && inner) {
        if (isExpanding) {
          if (!inner.querySelector('.todo-subtask-panel')) {
            inner.innerHTML = renderSubtaskPanel(source, todoId, subtasks);
          }
          if (getComputedStyle(collapse).display === 'grid') {
            void collapse.offsetHeight;
          } else {
            inner.style.display = '';
          }
          collapse.classList.remove('is-collapsed');
        } else {
          collapse.classList.add('is-collapsed');
          if (getComputedStyle(collapse).display !== 'grid') {
            inner.style.display = 'none';
          }
        }
      }
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
      if (textInput.dataset.submitting === 'true') return;
      const text = textInput.value.trim();
      const dueDate = dueInput ? dueInput.value : '';
      if (!text) return;
      textInput.dataset.submitting = 'true';
      try {
        const saved = await addSubtask(source, todoId, text, dueDate);
        if (saved) {
          const currentInput = document.getElementById(textInput.id);
          const currentDue = dueInput && document.getElementById(dueInput.id);
          if (currentInput?.value.trim() === text) currentInput.value = '';
          if (currentDue?.value === dueDate) currentDue.value = '';
        }
      } finally {
        if (textInput) delete textInput.dataset.submitting;
      }
    }

    async function saveSubtasks(source, todoId, subtasks, { prevSubtasks = null, optimistic = false } = {}) {
      if (subtasks === undefined) {
        subtasks = todoId;
        todoId = source;
        source = 'custom';
      }
      const todo = findTodo(source, todoId);
      const rollbackSubtasks = prevSubtasks || (todo?.subtasks ? todo.subtasks.map((s) => ({ ...s })) : []);
      if (source === 'custom') customDataRevision++;
      if (optimistic && todo) {
        todo.subtasks = subtasks;
        flipSubtasks(source, todoId, () => renderSubtaskPanelInPlace(source, todoId));
      }
      try {
        if (source === 'custom') {
          const payload = { subtasks };
          if (todo && todo.updated_at) payload.updated_at = todo.updated_at;
          const resp = await fetch(`/api/custom/todos/${todoId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.error || '');
          }
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
          if (!resp.ok) {
            const errData = await resp.json().catch(() => ({}));
            throw new Error(errData.error || '');
          }
          const data = await resp.json();
          const current = findTodo(source, todoId);
          if (current) current.subtasks = data.subtasks || subtasks;
        }
        if (!optimistic) {
          flipSubtasks(source, todoId, () => renderSubtaskPanelInPlace(source, todoId));
        } else {
          renderSubtaskPanelInPlace(source, todoId);
        }
        return true;
      } catch (e) {
        if (optimistic && todo) {
          todo.subtasks = rollbackSubtasks;
          renderSubtaskPanelInPlace(source, todoId);
        }
        showUiToast(e?.message ? `子任务保存失败：${e.message}` : '子任务保存失败，已恢复原状态', { tone: 'danger' });
        const cfg = PLATFORM_COLLECTIONS[source];
        if (source === 'custom') fetchCustomTodos();
        else if (cfg?.refresh) cfg.refresh();
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
      if (!trimmed) return false;

      const todo = findTodo(source, todoId);
      if (!todo) return false;

      const prevSubtasks = (todo.subtasks || []).map((s) => ({ ...s }));
      const newId = Math.max(0, ...prevSubtasks.map(subtask => subtask.id || 0)) + 1;
      const finalDueDate = (dueDate && String(dueDate).trim()) ? String(dueDate).trim() : null;
      const subtasks = [
        ...prevSubtasks,
        { id: newId, text: trimmed, done: false, due_date: finalDueDate },
      ];
      return await saveSubtasks(source, todoId, sortSubtasks(subtasks), { prevSubtasks });
    }

    async function toggleSubtaskDone(source, todoId, subtaskId) {
      if (subtaskId === undefined) {
        subtaskId = todoId;
        todoId = source;
        source = 'custom';
      }
      const todo = findTodo(source, todoId);
      if (!todo) return;

      const prevSubtasks = (todo.subtasks || []).map((s) => ({ ...s }));
      const sid = Number(subtaskId);
      const subtasks = prevSubtasks.map((subtask, idx) => {
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

      await saveSubtasks(source, todoId, sortSubtasks(subtasks), { prevSubtasks, optimistic: true });
    }

    async function deleteSubtask(source, todoId, subtaskId) {
      if (subtaskId === undefined) {
        subtaskId = todoId;
        todoId = source;
        source = 'custom';
      }
      const todo = findTodo(source, todoId);
      if (!todo) return;

      const prevSubtasks = (todo.subtasks || []).map((s) => ({ ...s }));
      const sid = Number(subtaskId);
      const removed = prevSubtasks.find((subtask, idx) => (subtask.id != null ? subtask.id : idx) === sid);
      const subtasks = prevSubtasks.filter((subtask, idx) => {
        const id = subtask.id != null ? subtask.id : idx;
        return id !== sid;
      });
      const ok = await saveSubtasks(source, todoId, sortSubtasks(subtasks), { prevSubtasks, optimistic: true });
      if (ok && removed) {
        showUiToast(`已删除子任务「${shortTodoToastTitle(removed.text)}」`, {
          tone: 'neutral',
          actionLabel: '撤销',
          onAction: () => saveSubtasks(source, todoId, sortSubtasks(prevSubtasks)),
        });
      }
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

      const prevSubtasks = (todo.subtasks || []).map((s) => ({ ...s }));
      const sid = Number(subtaskId);
      const subtasks = prevSubtasks.map((subtask, idx) => {
        const id = subtask.id != null ? subtask.id : idx;
        return id === sid ? { ...subtask, due_date: dueDate || null } : subtask;
      });
      await saveSubtasks(source, todoId, sortSubtasks(subtasks), { prevSubtasks });
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

      let finished = false;
      let restoreFocus = false;

      async function finish(save) {
        if (finished) return;
        finished = true;
        const nextText = input.value.trim();
        input.replaceWith(spanEl);
        if (!save || !nextText || nextText === originalText) {
          if (restoreFocus) spanEl.focus({ preventScroll: true });
          return;
        }

        const prevSubtasks = (todo.subtasks || []).map((s) => ({ ...s }));
        const subtasks = prevSubtasks.map((item, idx) => {
          const id = item.id != null ? item.id : idx;
          return id === sid ? { ...item, text: nextText } : item;
        });
        await saveSubtasks(source, todoId, sortSubtasks(subtasks), { prevSubtasks });
      }

      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); restoreFocus = true; finish(true); }
        if (event.key === 'Escape') { event.preventDefault(); restoreFocus = true; finish(false); }
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
              first_due_date: dueInput.value || getTodayDateString(),
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
          const created = await resp.json().catch(() => ({}));
          if (created?.todo?.ref) {
            _pendingPulseTodoKey = created.todo.ref;
          } else if (created?.todo?.id != null) {
            _pendingPulseTodoKey = `custom:${created.todo.id}`;
          } else if (created?.series?.id != null) {
            _pendingPulseTodoKey = `recurring:${created.series.id}:${dueInput.value || getTodayDateString()}`;
          }
          input.value = '';
          dueInput.value = '';
          delete dueInput.dataset.autoRepeatDefault;
          if (repeatSelect) repeatSelect.value = 'none';
          currentTodoRequestId = null;

          if (todoSourceFilter !== 'all' && todoSourceFilter !== 'custom') {
            setTodoSourceFilter('all');
            showUiToast('已添加到「自定义」，已切换至全部待办', { tone: 'info' });
          }

          document.getElementById('add-todo-form').dispatchEvent(new Event('todo:created'));
          await fetchCustomTodos();
          if (!window.matchMedia('(max-width: 768px)').matches) {
            input.focus({ preventScroll: true });
          }
          if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
        } else {
          const err = await resp.json().catch(() => ({}));
          const errMsg = err.error || err.message || ('服务端错误（' + resp.status + '）');
          if (errEl) {
            errEl.textContent = '添加失败：' + errMsg;
            errEl.style.display = 'block';
            window.uiMotion?.nudgeError?.(errEl);
          } else {
            showUiToast('添加失败：' + errMsg, { tone: 'danger' });
          }
        }
      } catch (networkErr) {
        if (errEl) {
          errEl.textContent = '网络连接失败，请检查网络后重试。';
          errEl.style.display = 'block';
          window.uiMotion?.nudgeError?.(errEl);
        } else {
          showUiToast('网络连接失败，请检查网络后重试。', { tone: 'danger' });
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
      const lockKey = `custom:${id}`;
      if (todoInFlightKeys.has(lockKey)) return;
      const item = Array.isArray(customItems) ? customItems.find(t => String(t.id) === String(id)) : null;
      const prevDone = Boolean(item?.done);
      const prevCompletedAt = item?.completed_at;
      const wasOverdue = Boolean(item?.due_date && item.due_date < getTodayDateString());
      const shortTitle = shortTodoToastTitle(item?.text || '该待办');

      todoInFlightKeys.add(lockKey);
      if (item) item.done = !done;
      flipTodoList(() => renderUnifiedListNow());

      const payload = { done: !done };
      if (item && item.updated_at) payload.expected_updated_at = item.updated_at;
      try {
        const resp = await fetch(`/api/custom/todos/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!resp.ok) throw new Error('update failed');
        await fetchCustomTodos();
        if (!done) {
          if (!wasOverdue) {
            showUiToast(`已完成「${shortTitle}」`, {
              tone: 'success',
              actionLabel: '撤销',
              onAction: () => toggleTodoCheck(id, true),
            });
          } else {
            showUiToast(`已完成「${shortTitle}」（已过截止，自动清理）`, { tone: 'info' });
          }
        } else {
          showUiToast(`已恢复「${shortTitle}」`, { tone: 'info' });
        }
        if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
      } catch (error) {
        if (item) {
          item.done = prevDone;
          item.completed_at = prevCompletedAt;
        }
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('状态更新失败，已恢复原状', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
    }

    async function toggleRecurringCheck(seriesId, origDate, done) {
      const lockKey = `recurring:${seriesId}:${origDate}`;
      if (todoInFlightKeys.has(lockKey)) return;
      const item = customItems.find((t) => Number(t.series_id) === Number(seriesId) && t.original_due_date === origDate);
      const prevDone = Boolean(item?.done);
      const wasOverdue = Boolean(item?.due_date && item.due_date < getTodayDateString());
      const shortTitle = shortTodoToastTitle(item?.text || '重复待办');

      todoInFlightKeys.add(lockKey);
      if (item) item.done = !done;
      flipTodoList(() => renderUnifiedListNow());

      try {
        const resp = await fetch(`/api/recurring-todos/${seriesId}/occurrences/${origDate}/complete`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ done: !done }),
        });
        if (!resp.ok) throw new Error('recurring complete failed');
        await fetchCustomTodos();
        if (!done) {
          if (!wasOverdue) {
            showUiToast(`已完成「${shortTitle}」`, {
              tone: 'success',
              actionLabel: '撤销',
              onAction: () => toggleRecurringCheck(seriesId, origDate, true),
            });
          } else {
            showUiToast(`已完成「${shortTitle}」（已过截止，自动清理）`, { tone: 'info' });
          }
        } else {
          showUiToast(`已恢复「${shortTitle}」`, { tone: 'info' });
        }
        if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
      } catch (error) {
        if (item) item.done = prevDone;
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('重复待办更新失败，已恢复原状', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
    }

    async function skipRecurringOccurrence(seriesId, origDate) {
      const lockKey = `recurring:${seriesId}:${origDate}`;
      if (todoInFlightKeys.has(lockKey)) return;
      const item = customItems.find((t) => Number(t.series_id) === Number(seriesId) && t.original_due_date === origDate);
      const shortTitle = shortTodoToastTitle(item?.text || '重复待办');
      const prevItems = [...customItems];

      todoInFlightKeys.add(lockKey);
      customItems = customItems.filter((t) => !(Number(t.series_id) === Number(seriesId) && t.original_due_date === origDate));
      flipTodoList(() => renderUnifiedListNow());

      try {
        const resp = await fetch(`/api/recurring-todos/${seriesId}/occurrences/${origDate}/skip`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ skipped: true }),
        });
        if (!resp.ok) throw new Error('skip failed');
        await fetchCustomTodos();
        showUiToast(`已跳过本次「${shortTitle}」`, {
          tone: 'neutral',
          actionLabel: '撤销',
          onAction: async () => {
            try {
              const undoResp = await fetch(`/api/recurring-todos/${seriesId}/occurrences/${origDate}/skip`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ skipped: false }),
              });
              if (!undoResp.ok) throw new Error('unskip failed');
              await fetchCustomTodos();
              if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
            } catch (_) {
              showUiToast('撤销跳过失败，请重试', { tone: 'danger' });
            }
          },
        });
        if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
      } catch (error) {
        customItems = prevItems;
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('跳过本次失败，已恢复原状', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
    }

    async function deleteRecurringSeries(seriesId) {
      const item = customItems.find((t) => Number(t.series_id) === Number(seriesId));
      const title = item ? item.text : '此重复待办';
      const confirmed = await confirmUiAction({
        title: '删除重复待办系列',
        message: `确定永久删除「${title}」整个重复系列吗？删除后后续周期将不再生成，此操作不可撤销。`,
        confirmLabel: '永久删除',
        tone: 'danger',
      });
      if (!confirmed) return;

      const lockKey = `recurring-series:${seriesId}`;
      if (todoInFlightKeys.has(lockKey)) return;
      todoInFlightKeys.add(lockKey);
      try {
        const resp = await fetch(`/api/recurring-todos/${seriesId}`, {
          method: 'DELETE',
        });
        if (!resp.ok) throw new Error('delete failed');
        await fetchCustomTodos();
        if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
        showUiToast(`已删除重复待办「${shortTodoToastTitle(title)}」`, { tone: 'info' });
      } catch (error) {
        showUiToast('删除重复待办失败，请重试', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
    }

    async function toggleCustomHighlight(id, current) {
      const lockKey = `custom:flag:${id}`;
      if (todoInFlightKeys.has(lockKey)) return;
      const item = Array.isArray(customItems) ? customItems.find(t => String(t.id) === String(id)) : null;
      const prevFlag = Boolean(item?.highlighted);

      todoInFlightKeys.add(lockKey);
      if (item) item.highlighted = !current;
      flipTodoList(() => renderUnifiedListNow());

      const payload = { highlighted: !current };
      if (item && item.updated_at) payload.expected_updated_at = item.updated_at;
      try {
        const resp = await fetch(`/api/custom/todos/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!resp.ok) throw new Error('highlight failed');
        fetchCustomTodos();
      } catch (error) {
        if (item) item.highlighted = prevFlag;
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('标红状态更新失败，已恢复原状', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
    }

    async function performPlatformDelete(platform, id) {
      const cfg = PLATFORM_COLLECTIONS[platform];
      if (!cfg) return;
      const lockKey = `${platform}:delete:${id}`;
      if (todoInFlightKeys.has(lockKey)) return;
      todoInFlightKeys.add(lockKey);

      const item = (cfg.getItems() || []).find((entry) => String(entry.id) === String(id));
      const shortTitle = shortTodoToastTitle(item?.title || '该事项');
      const prevDeleted = [...cfg.getDeleted()];
      if (!prevDeleted.some((x) => String(x) === String(id))) {
        cfg.setDeleted([...prevDeleted, id]);
      }
      flipTodoList(() => renderUnifiedListNow());

      try {
        const resp = await fetch(`/api/${platform}/state`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ action: 'delete', id }),
        });
        if (!resp.ok) throw new Error('delete failed');
        showUiToast(`已从清单隐藏「${shortTitle}」`, {
          tone: 'neutral',
          actionLabel: '撤销',
          onAction: async () => {
            try {
              const undoResp = await fetch(`/api/${platform}/state`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ action: 'undelete', id }),
              });
              if (!undoResp.ok) throw new Error('undelete failed');
              cfg.setDeleted(cfg.getDeleted().filter((x) => String(x) !== String(id)));
              flipTodoList(() => renderUnifiedListNow());
            } catch (_) {
              showUiToast('撤销隐藏失败，可在连接与同步页恢复', { tone: 'danger' });
            }
          },
        });
      } catch (error) {
        cfg.setDeleted(prevDeleted);
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('从清单隐藏失败，已恢复显示', { tone: 'danger' });
      } finally {
        todoInFlightKeys.delete(lockKey);
      }
    }

    function toggleCanvasDelete(id) { return performPlatformDelete('canvas', id); }
    function toggleHaokeDelete(id) { return performPlatformDelete('haoke', id); }
    function toggleZhixuemengDelete(id) { return performPlatformDelete('zhixuemeng', id); }
    function toggleZhihuishuDelete(id) { return performPlatformDelete('zhihuishu', id); }
    function toggleKetangpaiDelete(id) { return performPlatformDelete('ketangpai', id); }
    function toggleTongjiojDelete(id) { return performPlatformDelete('tongjioj', id); }

    async function toggleCustomDelete(id) {
      if (deletingCustomIds.has(id)) return;
      const item = customItems.find(t => t.id === id);
      const title = item ? item.text : '此待办';
      const subtaskCount = item && Array.isArray(item.subtasks) ? item.subtasks.length : 0;
      const subtaskWarning = subtaskCount > 0 ? ` 将同时删除其包含的 ${subtaskCount} 个子任务。` : '';
      const confirmed = await confirmUiAction({
        title: '永久删除待办',
        message: `确定永久删除待办「${title}」吗？${subtaskWarning}此操作不可撤销。`,
        confirmLabel: '永久删除',
        tone: 'danger',
      });
      if (!confirmed) return;

      deletingCustomIds.add(id);
      renderUnifiedListNow();
      try {
        const resp = await fetch(`/api/custom/todos/${id}`, { method: 'DELETE' });
        if (resp.ok) {
          await fetchCustomTodos();
          if (typeof loadTodaySchedule === 'function') loadTodaySchedule();
          if (typeof loadForwardAgenda === 'function') loadForwardAgenda();
          showUiToast(`已删除「${shortTodoToastTitle(title)}」`, { tone: 'info' });
        } else {
          const err = await resp.json().catch(() => ({}));
          const errMsg = err.error || err.message || ('服务端状态 ' + resp.status);
          showUiToast('删除待办失败：' + errMsg, { tone: 'danger' });
        }
      } catch (err) {
        showUiToast('删除待办失败，网络连接异常，请重试。', { tone: 'danger' });
      } finally {
        deletingCustomIds.delete(id);
        renderUnifiedListNow();
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
      flipTodoList(() => renderUnifiedListNow());

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
        flipTodoList(() => renderUnifiedListNow());
        showUiToast('修改未保存：' + (err.message || '网络或服务异常'), { tone: 'danger' });
      }
    }

    function startInlineEdit(spanEl, field) {
      const id = parseInt(spanEl.dataset.id, 10);
      const originalValue = field === 'due_date' ? (spanEl.dataset.value ?? spanEl.textContent.trim()) : spanEl.textContent.trim();

      const input = document.createElement('input');
      input.type = field === 'due_date' ? 'date' : 'text';
      input.className = field === 'due_date' ? 'inline-edit-date-input' : 'inline-edit-input';
      input.value = originalValue || '';

      spanEl.replaceWith(input);
      input.focus();
      if (input.type === 'text') input.select();
      let finished = false;
      let viaKeyboard = false;

      function commit() {
        if (finished) return;
        finished = true;
        const newValue = input.value.trim();
        input.replaceWith(spanEl);
        if (newValue !== originalValue) {
          if (viaKeyboard) {
            _pendingFocusSelector = `[data-id="${id}"][data-field="${field}"]`;
          }
          if (field === 'text') {
            const parts = newValue.split(/\s+(#[^#\s]+)/);
            let taskText = parts[0];
            let labels = [];
            if (parts.length > 1) {
              taskText = parts[0].trim();
              labels = parts.slice(1).map(tag => tag.substring(1)).filter(tag => tag);
            }
            saveInlineEdit(id, 'multi', { text: taskText, labels });
          } else {
            saveInlineEdit(id, field, newValue);
          }
        } else if (viaKeyboard) {
          spanEl.focus({ preventScroll: true });
        }
      }

      function cancel() {
        if (finished) return;
        finished = true;
        input.replaceWith(spanEl);
        if (viaKeyboard) spanEl.focus({ preventScroll: true });
      }

      input.addEventListener('blur', commit);
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); viaKeyboard = true; input.blur(); }
        if (e.key === 'Escape') { e.preventDefault(); viaKeyboard = true; cancel(); }
      });
    }


(function initializeTodoFeature() {
  const byId = (id) => document.getElementById(id);
  byId('todo-list')?.addEventListener('click', (event) => {
    const mobileDetail = event.target.closest('[data-mobile-detail]');
    if (mobileDetail) { openActionDetail(mobileDetail.dataset.mobileDetail); return; }
    const desktopDetail = event.target.closest('[data-todo-detail]');
    if (desktopDetail) { openActionDetail(desktopDetail.dataset.todoDetail); return; }
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
  byId('new-todo-due')?.addEventListener('change', () => {
    const dueEl = byId('new-todo-due');
    if (dueEl) delete dueEl.dataset.autoRepeatDefault;
    if (typeof resetTodoRequestId === 'function') resetTodoRequestId();
  });
  byId('new-todo-repeat')?.addEventListener('change', () => {
    const repeatEl = byId('new-todo-repeat');
    const dueEl = byId('new-todo-due');
    if (repeatEl && dueEl) {
      if (repeatEl.value !== 'none') {
        if (!dueEl.value) {
          dueEl.value = getTodayDateString();
          dueEl.dataset.autoRepeatDefault = 'true';
        }
      } else if (dueEl.dataset.autoRepeatDefault === 'true') {
        dueEl.value = '';
        delete dueEl.dataset.autoRepeatDefault;
      }
    }
    if (typeof resetTodoRequestId === 'function') resetTodoRequestId();
  });

  byId('btn-refresh')?.addEventListener('click', async () => {
    if (workspaceRefreshing) return;
    workspaceRefreshing = true;
    workspaceRefreshFailed = false;
    renderDashboardSyncStatus();

    const platformFetches = [];
    const canFetchPlatform = (name) => typeof isPlatformConfigured !== 'function' || isPlatformConfigured(name);
    if (typeof fetchCanvasTodos === 'function' && canFetchPlatform('canvas')) platformFetches.push(fetchCanvasTodos(true));
    if (typeof fetchHaokeTodos === 'function' && canFetchPlatform('haoke')) platformFetches.push(fetchHaokeTodos(true));
    if (typeof fetchZhixuemengTodos === 'function' && canFetchPlatform('zhixuemeng')) platformFetches.push(fetchZhixuemengTodos());
    if (typeof fetchZhihuishuTodos === 'function' && canFetchPlatform('zhihuishu')) platformFetches.push(fetchZhihuishuTodos());
    if (typeof fetchKetangpaiTodos === 'function' && canFetchPlatform('ketangpai')) platformFetches.push(fetchKetangpaiTodos());
    if (typeof fetchTongjiojTodos === 'function' && canFetchPlatform('tongjioj')) platformFetches.push(fetchTongjiojTodos('', true));

    try {
      if (typeof refreshWorkspaceSurfaces === 'function') {
        await refreshWorkspaceSurfaces();
      } else {
        const localResults = await Promise.allSettled([
          typeof fetchProjectTodos === 'function' ? fetchProjectTodos() : Promise.resolve(),
          typeof fetchCustomTodos === 'function' ? fetchCustomTodos() : Promise.resolve(),
          typeof loadTodaySchedule === 'function' ? loadTodaySchedule() : Promise.resolve(),
        ]);
        const rejected = localResults.find((r) => r.status === 'rejected');
        if (rejected) throw rejected.reason;
      }
    } catch (_) {
      workspaceRefreshFailed = true;
    } finally {
      workspaceRefreshing = false;
      renderDashboardSyncStatus();
    }

    if (platformFetches.length) {
      const results = await Promise.allSettled(platformFetches);
      if (results.some((r) => r.status === 'rejected')) {
        workspaceRefreshFailed = true;
      }
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
    if (openMobileActionItemId && !event.target.closest('.todo-row .item-mobile-actions, .todo-row .mobile-action-trigger, dialog')) {
      closeMobileActions();
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      byId('todo-source-manager')?.removeAttribute('open');
      if (openMobileActionItemId && !document.querySelector('dialog[open]') && !event.target?.closest?.('dialog')) {
        const insideActions = Boolean(document.activeElement?.closest('.item-mobile-actions'));
        closeMobileActions({ restoreFocus: insideActions });
      }
    }
  });
  byId('todo-list')?.addEventListener('click', (event) => {
    const projectDueEl = event.target.closest('.project-due-editable');
    if (projectDueEl) { startProjectTodoDueEdit(projectDueEl); return; }
    const titleEl = event.target.closest('.editable-title');
    if (titleEl) { startInlineEdit(titleEl, 'text'); return; }
    const dueEl = event.target.closest('.editable-due');
    if (dueEl) startInlineEdit(dueEl, 'due_date');
  });
  byId('todo-list')?.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const titleEl = event.target.closest('.editable-title');
    if (titleEl) { event.preventDefault(); startInlineEdit(titleEl, 'text'); return; }
    const dueEl = event.target.closest('.editable-due');
    if (dueEl) { event.preventDefault(); startInlineEdit(dueEl, 'due_date'); }
  });
})();
