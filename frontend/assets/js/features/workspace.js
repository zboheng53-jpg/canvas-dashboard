/* Shared action details and date-range views. The dashboard shell stays in place. */
let workspaceDetail = null;
let workspaceDetailOpener = null;
let workspacePeriodOpener = null;
let workspaceWeekDay = null;
let workspaceWeekRequest = 0;
let lastScheduleWeekOffset = null;
let workspaceTodayData = null;
let workspaceTodayRequest = 0;

const wEscape = (value) => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
const wNode = (tag, css, text) => {
  const node = document.createElement(tag);
  if (css) node.className = css;
  if (text !== undefined) node.textContent = text;
  return node;
};
function showWorkspaceToast(message, options = {}) {
  if (window.uiToast?.show) {
    return window.uiToast.show(message, options);
  }
  return { dismiss() {} };
}
async function confirmWorkspaceAction({ title, message, confirmLabel = '确认', cancelLabel = '取消', tone = 'danger' }) {
  if (typeof window.uiConfirm === 'function') {
    return await window.uiConfirm({ title, message, confirmLabel, cancelLabel, tone });
  }
  return false;
}
async function workspaceRequest(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok || !data.ok) throw new Error(data.error || '加载失败，请重试');
  return data;
}
function workspaceWrite(url, data, method = 'PUT') {
  return workspaceRequest(url, {method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
}
function workspaceTodayISO() {
  if (typeof window.getShanghaiTodayISO === 'function') {
    return window.getShanghaiTodayISO();
  }
  if (window.customToday) return window.customToday;
  return new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
}
function workspaceDateLabel(day) {
  const today = workspaceTodayISO();
  const delta = Math.round((Date.parse(day) - Date.parse(today)) / 86400000);
  const prefix = delta === 0 ? '今天' : delta === 1 ? '明天' : new Date(`${day}T12:00:00+08:00`).toLocaleDateString('zh-CN', {weekday: 'long', timeZone: 'Asia/Shanghai'});
  return `${prefix} · ${Number(day.slice(5, 7))}月${Number(day.slice(8))}日`;
}

async function refreshWorkspaceSurfaces() {
  await Promise.all([
    typeof loadProjects === 'function' ? loadProjects(selectedProjectId) : Promise.resolve(),
    typeof loadProjectOverview === 'function' ? loadProjectOverview() : Promise.resolve(),
    typeof fetchProjectTodos === 'function' ? fetchProjectTodos() : Promise.resolve(),
    typeof fetchCustomTodos === 'function' ? fetchCustomTodos() : Promise.resolve(),
    typeof loadTodaySchedule === 'function' ? loadTodaySchedule() : Promise.resolve(),
  ]);
  if (typeof loadForwardAgenda === 'function') {
    try { await loadForwardAgenda(); } catch (_) {}
  }
  if (!document.getElementById('dashboard-view-schedule')?.classList.contains('hidden') && typeof loadScheduleManager === 'function') {
    await loadScheduleManager();
  }
}
window.refreshWorkspaceSurfaces = refreshWorkspaceSurfaces;
window.refreshAllSurfaces = refreshWorkspaceSurfaces;

function isActionEditorDirty() {
  const form = document.getElementById('action-edit-form');
  const initial = workspaceDetail?.editorInitial;
  if (!form || !initial) return false;
  return (
    form.elements.title.value !== initial.title ||
    form.elements.details.value !== initial.details ||
    form.elements.planned_on.value !== initial.planned_on ||
    form.elements.due_date.value !== initial.due_date ||
    form.elements.estimate_minutes.value !== initial.estimate_minutes
  );
}

async function cancelActionEditor() {
  if (!document.getElementById('action-edit-form')) return;
  if (isActionEditorDirty()) {
    const discard = await confirmWorkspaceAction({
      title: '放弃未保存的修改？',
      message: '当前事项编辑内容尚未保存，确定放弃修改并返回详情吗？',
      confirmLabel: '放弃修改',
      cancelLabel: '继续编辑',
      tone: 'warning',
    });
    if (!discard) return;
  }
  renderActionDetail();
}

async function openActionDetail(ref, occurrence = null) {
  const dialog = document.getElementById('action-detail-dialog');
  if (!dialog) return;
  const body = document.getElementById('action-detail-body');
  const wasOpen = dialog.open;
  if (!wasOpen) {
    workspaceDetailOpener = document.activeElement;
    body.innerHTML = '<p class="muted" role="status">正在加载事项…</p>';
    document.getElementById('action-detail-title').textContent = '事项详情';
    if (window.uiDialog?.open) {
      window.uiDialog.open(dialog);
    } else {
      dialog.showModal();
    }
  } else {
    body.setAttribute('aria-busy', 'true');
  }
  const requestToken = {};
  workspaceDetail = { ...(workspaceDetail || {}), requestToken };
  try {
    const data = await workspaceRequest(`/api/actions/${encodeURIComponent(ref)}`);
    if (workspaceDetail?.requestToken !== requestToken || !dialog.open) return;
    workspaceDetail = { ...data, occurrence };
    body.removeAttribute('aria-busy');
    renderActionDetail();
  } catch (error) {
    if (workspaceDetail?.requestToken !== requestToken) return;
    body.removeAttribute('aria-busy');
    if (wasOpen && workspaceDetail?.action) {
      showWorkspaceToast(error.message || '刷新事项失败', { tone: 'danger' });
    } else {
      body.textContent = error.message;
    }
  }
}

async function closeActionDetail({ force = false } = {}) {
  const dialog = document.getElementById('action-detail-dialog');
  if (!dialog) return;
  if (!force && isActionEditorDirty()) {
    const discard = await confirmWorkspaceAction({
      title: '放弃未保存的修改？',
      message: '当前事项编辑内容尚未保存，确定放弃修改并关闭窗口吗？',
      confirmLabel: '放弃修改',
      cancelLabel: '继续编辑',
      tone: 'warning',
    });
    if (!discard) return;
  }
  if (window.uiDialog?.close) {
    window.uiDialog.close(dialog, { force: true });
  } else if (dialog.open) {
    dialog.close();
  }
  workspaceDetail = null;
  if (!window.uiDialog?.close && workspaceDetailOpener?.isConnected) {
    workspaceDetailOpener.focus();
  }
}

function renderActionDetail() {
  const {action: a, schedules, occurrence} = workspaceDetail;
  document.getElementById('action-detail-title').textContent = a.title;
  const body = document.getElementById('action-detail-body');
  const meta = [a.project_name || a.course, a.done ? '已完成' : '',
    a.planned_on ? `计划 ${a.planned_on}` : '', a.due_date ? `截止 ${a.due_date}${a.deadline_time ? ' ' + a.deadline_time : ''}` : '',
    a.estimate_minutes ? `${a.estimate_minutes} 分钟` : ''].filter(Boolean);
  body.innerHTML = `<p class="action-detail-meta">${meta.map(wEscape).join(' · ')}</p>
    ${a.commitment === 'legacy' ? '<p class="action-legacy-hint">这条早期事项保留了原日期。如需按日历计划推进，可点编辑调整计划日期与截止日期。</p>' : ''}
    <div class="action-detail-text">${wEscape(a.details || '暂无详细说明')}</div>
    ${a.original_name ? `<details class="action-original"><summary><svg class="project-disclosure-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"></polyline></svg><span>原始标题</span></summary><p>${wEscape(a.original_name)}</p></details>` : ''}
    <div class="action-detail-buttons" id="action-primary-buttons"></div>
    <section class="action-linked-section"><h3>时间安排</h3><div id="action-linked-list"></div></section>
    <p id="action-detail-error" class="ui-error" role="alert"></p>`;
  body.querySelectorAll('details.action-original').forEach((d) => window.uiMotion?.enhanceDisclosure?.(d));
  const buttons = document.getElementById('action-primary-buttons');
  const dangerGroup = wNode('div', 'action-detail-danger-group');
  const button = (label, fn, primary = false, danger = false) => {
    const b = wNode('button', `ui-button ui-button--${danger ? 'danger is-danger' : primary ? 'primary' : 'secondary'}`, label);
    b.type = 'button';
    b.addEventListener('click', fn);
    if (danger) dangerGroup.append(b);
    else buttons.append(b);
    return b;
  };
  if (a.editable) button('编辑事项', renderActionEditor);
  const canCompleteOrReopen = a.source !== 'project_due' && a.source !== 'custom_subtask';
  if (!a.done && a.active !== false && canCompleteOrReopen) {
    button('安排时间', () => scheduleAction(a));
    button(a.source === 'recurring' ? '完成本次待办' : '完成事项', () => saveActionCompletion(true), true);
  } else if (a.done && canCompleteOrReopen && (a.editable || ['canvas', 'haoke', 'zhixuemeng', 'zhihuishu', 'ketangpai', 'tongjioj', 'project', 'custom', 'recurring'].includes(a.source))) {
    button(a.source === 'recurring' ? '撤销本次完成' : '重新开启事项', () => saveActionCompletion(false));
  }
  if (a.project_id) button('进入项目', () => { closeActionDetail({ force: true }); openProjectsView(a.project_id); });
  if (a.editable && a.source === 'project' && a.project_id && a.task_id) {
    button('删除事项', () => {
      closeActionDetail({ force: true });
      if (typeof confirmDeleteProjectTask === 'function') {
        confirmDeleteProjectTask(a.project_id, a.task_id);
      }
    }, false, true);
  }
  if (a.source === 'recurring') {
    if (!a.done && !a.skipped) {
      button('跳过本次', async () => {
        try {
          await workspaceWrite(`/api/recurring-todos/${a.series_id}/occurrences/${a.original_due_date}/skip`, {skipped: true});
          await refreshWorkspaceSurfaces();
          closeActionDetail({ force: true });
          showWorkspaceToast(`已跳过本次「${a.title}」`, {
            tone: 'neutral',
            actionLabel: '撤销',
            onAction: async () => {
              await workspaceWrite(`/api/recurring-todos/${a.series_id}/occurrences/${a.original_due_date}/skip`, {skipped: false});
              await refreshWorkspaceSurfaces();
            },
          });
        } catch (error) { document.getElementById('action-detail-error').textContent = error.message; }
      });
    }
    button('删除系列', async () => {
      const confirmed = await confirmWorkspaceAction({
        title: '删除重复待办系列',
        message: `确定永久删除重复待办「${a.title}」整个系列吗？此操作不可撤销。`,
        confirmLabel: '永久删除',
        tone: 'danger',
      });
      if (!confirmed) return;
      try {
        await workspaceRequest(`/api/recurring-todos/${a.series_id}`, {method: 'DELETE'});
        await refreshWorkspaceSurfaces();
        closeActionDetail({ force: true });
        showWorkspaceToast(`已删除重复待办「${a.title}」`, { tone: 'info' });
      } catch (error) { document.getElementById('action-detail-error').textContent = error.message; }
    }, false, true);
  }
  if (a.parent_ref) button('查看所属待办', () => openActionDetail(a.parent_ref));
  if (a.url) {
    const url = sanitizeExternalUrl(a.url);
    if (url) { const link = wNode('a', 'ui-button ui-button--secondary', '打开原始任务'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; buttons.append(link); }
  }
  const isRealScheduleOccurrence = occurrence?.id && ['one_off', 'recurring', 'one-off'].includes(occurrence.kind);
  if (isRealScheduleOccurrence && !a.done) {
    button(occurrence.occurrence_done ? '撤销本次安排完成' : '完成本次安排', async () => {
      try {
        await workspaceWrite(`/api/schedule/${occurrence.kind.replace('_', '-')}/${occurrence.id}/occurrence`, {date: occurrence.date, done: !occurrence.occurrence_done});
        occurrence.occurrence_done = !occurrence.occurrence_done;
        await refreshWorkspaceSurfaces(); await openActionDetail(a.ref, occurrence);
      } catch (error) { document.getElementById('action-detail-error').textContent = error.message; }
    });
  }
  if (dangerGroup.children.length > 0) {
    buttons.append(dangerGroup);
  }
  const list = document.getElementById('action-linked-list');
  if (!schedules.length) list.append(wNode('p', 'muted', a.planned_on ? `计划在 ${a.planned_on} 推进，尚未安排具体时间。` : '尚未安排时间。'));
  schedules.forEach(item => {
    const row = wNode('div', 'action-linked-row');
    const when = item.kind === 'recurring' ? `每${['周一','周二','周三','周四','周五','周六','周日'][item.weekday]}` : item.date;
    row.append(wNode('span', '', `${when} ${item.start_time}–${item.end_time}${a.done ? ' · 事项已完成' : ''}`));
    const edit = wNode('button', 'ui-button ui-button--text', '调整');
    edit.type = 'button';
    edit.addEventListener('click', () => {
      const sameOccurrence = occurrence?.id === item.id && occurrence?.kind === item.kind;
      closeActionDetail({ force: true });
      openScheduleItemModal(item.kind.replace('_', '-'), {...item, title: a.title}, {date: sameOccurrence ? occurrence.date : item.date});
    });
    row.append(edit); list.append(row);
  });
}

function renderActionEditor() {
  const a = workspaceDetail.action;
  workspaceDetail.editorInitial = {
    title: String(a.title || ''),
    details: String(a.details || ''),
    planned_on: String(a.planned_on || ''),
    due_date: String(a.due_date || ''),
    estimate_minutes: a.estimate_minutes ? String(a.estimate_minutes) : '',
  };
  const body = document.getElementById('action-detail-body');
  const titleLen = workspaceDetail.editorInitial.title.length;
  body.innerHTML = `<form id="action-edit-form" class="project-modal-form">
    <label class="ui-field ui-label">
      <span class="action-field-label-row" style="display:flex;justify-content:space-between;align-items:center;">
        <span>简短标题</span>
        <span class="muted action-title-counter" id="action-title-counter" style="font-size:11px;font-variant-numeric:tabular-nums;">${titleLen}/40</span>
      </span>
      <input class="ui-control" name="title" required maxlength="40" value="${wEscape(a.title)}">
    </label>
    <label class="ui-field ui-label">详细说明<textarea class="ui-control" name="details" rows="7" maxlength="12000" placeholder="步骤、材料和完成标准">${wEscape(a.details || '')}</textarea></label>
    <div class="action-date-fields"><label class="ui-field ui-label">计划日期<input class="ui-control" type="date" name="planned_on" value="${wEscape(a.planned_on || '')}"></label>
    <label class="ui-field ui-label">截止日期（选填）<input class="ui-control" type="date" name="due_date" value="${wEscape(a.due_date || '')}"></label></div>
    ${a.commitment === 'legacy' && a.due_date ? '<button type="button" class="ui-button ui-button--text" id="action-date-to-plan">将这个旧日期改作计划日期</button>' : ''}
    <label class="ui-field ui-label">预计分钟数<input class="ui-control" type="number" min="1" max="1440" name="estimate_minutes" value="${a.estimate_minutes || ''}"></label>
    <p class="ui-error" id="action-detail-error" role="alert"></p>
    <div class="project-modal-actions"><button type="button" class="ui-button ui-button--secondary" id="action-edit-cancel">取消</button><button type="submit" class="ui-button ui-button--primary">保存事项</button></div></form>`;
  const form = document.getElementById('action-edit-form');
  const titleInput = form.elements.title;
  const counterEl = document.getElementById('action-title-counter');
  titleInput.addEventListener('input', () => {
    if (counterEl) counterEl.textContent = `${titleInput.value.length}/40`;
  });
  titleInput.focus();
  document.getElementById('action-edit-cancel').onclick = () => cancelActionEditor();
  document.getElementById('action-date-to-plan')?.addEventListener('click', () => {
    form.elements.planned_on.value = form.elements.due_date.value; form.elements.due_date.value = '';
  });
  form.onsubmit = async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form));
    payload.estimate_minutes = payload.estimate_minutes ? Number(payload.estimate_minutes) : null;
    if (a.source === 'project' && a.commitment === 'legacy' && !payload.due_date && payload.planned_on) {
      payload.commitment = 'growth';
    }
    if (payload.title === a.title) delete payload.title;
    payload.expected_updated_at = a.updated_at;
    const submit = form.querySelector('[type=submit]');
    const saveTask = async () => {
      try {
        await workspaceWrite(`/api/actions/${encodeURIComponent(a.ref)}`, payload);
        await refreshWorkspaceSurfaces();
        await openActionDetail(a.ref);
        showWorkspaceToast('事项修改已保存', { tone: 'success' });
      } catch (error) {
        const errEl = document.getElementById('action-detail-error');
        if (errEl) {
          errEl.textContent = error.message;
          window.uiMotion?.nudgeError?.(errEl);
        }
      }
    };
    if (window.withButtonBusy) {
      await window.withButtonBusy(submit, '保存中…', saveTask);
    } else {
      submit.disabled = true;
      try { await saveTask(); } finally { submit.disabled = false; }
    }
  };
}
async function saveActionCompletion(done) {
  const a = workspaceDetail.action;
  try {
    await workspaceWrite(`/api/actions/${encodeURIComponent(a.ref)}`, {done, ...(a.editable ? {expected_updated_at: a.updated_at} : {})});
    const reloadSource = {canvas: fetchCanvasTodos, haoke: fetchHaokeTodos, zhixuemeng: fetchZhixuemengTodos, zhihuishu: fetchZhihuishuTodos, ketangpai: fetchKetangpaiTodos, tongjioj: fetchTongjiojTodos}[a.source];
    if (reloadSource) await reloadSource();
    await refreshWorkspaceSurfaces(); await openActionDetail(a.ref);
    if (done) {
      showWorkspaceToast(`已完成「${a.title}」`, { tone: 'success' });
    } else {
      showWorkspaceToast(`已恢复「${a.title}」`, { tone: 'info' });
    }
  } catch (error) { document.getElementById('action-detail-error').textContent = error.message; }
}
function scheduleAction(action) {
  closeActionDetail({ force: true });
  openScheduleItemModal('one-off', null, {action_ref: action.ref, title: action.title, date: action.planned_on || workspaceTodayISO()});
}
async function openTodoAction(source, id) {
  try {
    const {actions} = await workspaceRequest('/api/actions?status=all');
    const a = actions.find(a => a.source === source && String(a.id) === String(id));
    if (a) await openActionDetail(a.ref);
  } catch (error) { showWorkspaceToast(error.message || '加载事项失败', { tone: 'danger' }); }
}
function openAgendaEntry(event) {
  if (event.action_ref && !event.link_missing) return openActionDetail(event.action_ref, event);
  if (event.kind === 'course') return onScheduleCardClick({...event, raw: event.course, courseIndex: event.course_index}, event.date);
  openScheduleItemModal(event.kind.replace('_', '-'), event, {date: event.date});
}

function isCoursePast(event) {
  if (event.kind !== 'course') return false;
  const today = workspaceTodayISO();
  if (event.date < today) return true;
  if (event.date > today) return false;
  if (!event.end_time) return false;
  const currentTime = new Intl.DateTimeFormat('en-GB', {timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit'}).format(new Date());
  return currentTime >= event.end_time;
}

function agendaEventButton(event) {
  const isDone = Boolean(event.done || event.occurrence_done || isCoursePast(event));
  const button = wNode('button', `period-event period-event--${event.kind} ${isDone ? 'is-done' : ''}`);
  button.type = 'button';
  const time = event.kind === 'deadline' ? `${event.deadline_time || '全天'} 截止` : event.kind === 'planned' ? '计划推进 · 未定时间' : `${event.start_time}–${event.end_time}`;
  const timeEl = wNode('span', 'period-event-time', time);
  button.append(timeEl, wNode('strong', 'period-event-title', event.title));
  const meta = [event.location, event.link_missing ? '原事项已移除' : '', event.occurrence_done ? '本次已完成' : ''].filter(Boolean).join(' · ');
  if (meta) button.append(wNode('small', '', meta));
  const tooltip = [event.title, time, meta].filter(Boolean).join('\n');
  button.title = tooltip;
  button.addEventListener('click', () => openAgendaEntry(event));
  return button;
}
async function renderPeriodSchedule(data) {
  const dates = getWeekDates(currentScheduleWeekOffset).map(formatDateISO);
  const requestId = ++workspaceWeekRequest;
  try {
    let agenda = data.agenda;
    if (!agenda || agenda.start !== dates[0]) {
      agenda = await workspaceRequest(`/api/agenda?start=${dates[0]}&end=${dates[6]}`);
      if (requestId !== workspaceWeekRequest) return;
      data.agenda = agenda;
    }
    const header = document.getElementById('schedule-grid-header');
    const grid = document.getElementById('schedule-timetable-grid');
    header.classList.add('period-grid'); grid.classList.add('period-grid');
    header.removeAttribute('aria-hidden'); header.replaceChildren(wNode('div', 'period-label', '时段'));
    grid.replaceChildren();
    if (!dates.includes(workspaceWeekDay)) workspaceWeekDay = dates.includes(workspaceTodayISO()) ? workspaceTodayISO() : dates[0];
    const dayMark = (node, day) => { node.dataset.date = day; node.dataset.selected = String(day === workspaceWeekDay); return node; };
    const selectScheduleDay = (day) => {
      workspaceWeekDay = day;
      header.querySelectorAll('.period-day').forEach((dayBtn) => {
        const selected = dayBtn.dataset.date === day;
        dayBtn.dataset.selected = String(selected);
        dayBtn.setAttribute('aria-pressed', String(selected));
      });
      grid.querySelectorAll('.period-cell').forEach((cell) => {
        cell.dataset.selected = String(cell.dataset.date === day);
      });
    };
    dates.forEach((day, i) => {
      const button = dayMark(wNode('button', `period-day ${day === workspaceTodayISO() ? 'is-today' : ''}`, `${weekdayLabels[i]} ${day.slice(5)}`), day);
      button.type = 'button'; button.setAttribute('aria-pressed', String(day === workspaceWeekDay));
      button.onclick = () => selectScheduleDay(day);
      header.append(button);
    });
    const bands = [{name: '全天', key: 'all', time: '09:00'}, {name: '上午', key: 'am', time: '09:00'}, {name: '下午', key: 'pm', time: '14:00'}, {name: '晚上', key: 'eve', time: '19:00'}];
    bands.forEach(band => {
      grid.append(wNode('div', 'period-label', band.name));
      agenda.days.forEach((day, i) => {
        const cell = dayMark(wNode('div', 'period-cell'), day.date);
        cell.dataset.period = band.key;
        let entries = band.key === 'all' ? [...day.deadlines, ...day.planned.filter(p => !day.deadlines.some(d => d.ref === p.ref))]
          : day.timed.filter(e => (e.start_time < '12:00' ? 'am' : e.start_time < '18:00' ? 'pm' : 'eve') === band.key);
        const list = wNode('div', 'period-cell-events');
        entries.forEach(event => list.append(agendaEventButton(event)));
        cell.append(list);
        const controls = wNode('div', 'period-cell-controls');
        const more = wNode('button', 'period-more'); more.type = 'button'; more.hidden = true;
        more.onclick = () => openPeriodEntries(day.date, band.name, entries);
        controls.append(more);
        if (band.key !== 'all') {
          const add = wNode('button', 'period-add', '+'); add.type = 'button';
          add.setAttribute('aria-label', `${day.date} ${band.name}添加安排`);
          add.onclick = () => openScheduleItemModal('one-off', null, {date: day.date, weekday: i, start_time: band.time});
          controls.append(add);
        } else if (!entries.length) list.append(wNode('span', 'period-empty', '—'));
        cell.append(controls);
        grid.append(cell);
      });
    });
    if (lastScheduleWeekOffset !== null && typeof currentScheduleWeekOffset === 'number' && currentScheduleWeekOffset !== lastScheduleWeekOffset) {
      grid.classList.remove('ui-slide-next', 'ui-slide-prev');
      if (!window.uiMotion?.prefersReducedMotion?.()) {
        const slideCls = currentScheduleWeekOffset > lastScheduleWeekOffset ? 'ui-slide-next' : 'ui-slide-prev';
        void grid.offsetWidth;
        grid.classList.add(slideCls);
        grid.addEventListener('animationend', () => grid.classList.remove('ui-slide-next', 'ui-slide-prev'), { once: true });
      }
    }
    if (typeof currentScheduleWeekOffset === 'number') {
      lastScheduleWeekOffset = currentScheduleWeekOffset;
    }
    requestAnimationFrame(fitPeriodCells);
  } catch (error) { setScheduleStatus(error.message, true); }
}
function fitPeriodCells() {
  const desktop = matchMedia('(min-width: 961px)').matches;
  document.querySelectorAll('.period-cell').forEach(cell => {
    const list = cell.querySelector('.period-cell-events');
    const more = cell.querySelector('.period-more');
    const events = [...list.querySelectorAll('.period-event')];
    if (!desktop || !cell.clientHeight) {
      more.hidden = true;
      return;
    }
    const hasOverflow = list.scrollHeight > list.clientHeight + 1;
    if (hasOverflow) {
      const gap = parseFloat(getComputedStyle(list).gap) || 0;
      let used = 0, visible = 0;
      for (const event of events) {
        const height = event.getBoundingClientRect().height;
        if (used + height > list.clientHeight + .5) break;
        used += height + gap; visible++;
      }
      const hidden = Math.max(1, events.length - visible);
      more.textContent = `还有 ${hidden} 项`;
      more.title = '可在此格内滚轮滑动查看，或点击查看全部';
      more.hidden = false;
    } else {
      more.hidden = true;
    }
  });
}
function openPeriodEntries(day, band, entries) {
  const dialog = document.getElementById('period-entries-dialog');
  if (!dialog) return;
  workspacePeriodOpener = document.activeElement;
  document.getElementById('period-entries-title').textContent = `${workspaceDateLabel(day)} · ${band}`;
  const list = document.getElementById('period-entries-list'); list.replaceChildren();
  entries.forEach(event => {
    const button = agendaEventButton(event);
    button.addEventListener('click', () => closePeriodEntriesDialog(), {capture: true});
    list.append(button);
  });
  if (window.uiDialog?.open) {
    window.uiDialog.open(dialog);
  } else {
    dialog.showModal();
  }
}

function closePeriodEntriesDialog() {
  const dialog = document.getElementById('period-entries-dialog');
  if (!dialog) return;
  if (window.uiDialog?.close) {
    window.uiDialog.close(dialog, { force: true });
  } else if (dialog.open) {
    dialog.close();
  }
  if (!window.uiDialog?.close && workspacePeriodOpener?.isConnected) {
    workspacePeriodOpener.focus();
  }
}

async function loadForwardAgenda() {
  if (typeof fetchProjectTodos === 'function') fetchProjectTodos();
  const requestId = ++workspaceTodayRequest;
  const start = workspaceTodayISO();
  const end = new Date(`${start}T12:00:00+08:00`); end.setUTCDate(end.getUTCDate() + 13);
  const endISO = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(end);
  try {
    const data = await workspaceRequest(`/api/agenda?start=${start}&end=${endISO}`);
    if (requestId !== workspaceTodayRequest) return;
    workspaceTodayData = data; renderForwardAgenda();
    if (typeof renderUnifiedList === 'function') renderUnifiedList();
    const courses = data.days[0].timed.filter(e => e.kind === 'course');
    const courseCountEl = document.getElementById('stat-course-count');
    if (courseCountEl) {
      if (window.uiMotion?.animateNumber) window.uiMotion.animateNumber(courseCountEl, courses.length);
      else courseCountEl.textContent = courses.length;
    }
    const currentTime = new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Shanghai', hour:'2-digit', minute:'2-digit'}).format(new Date());
    const next = courses.find(c => c.end_time > currentTime);
    document.getElementById('stat-course-next').textContent = next ? `${next.start_time} ${next.title}` : courses.length ? '今日课程已结束' : '今天没有课程';
  } catch (error) { renderTodayScheduleState('日程加载失败', error.message, true); }
}
function renderTodayScheduleEmptyState(container, title, detail) {
  const state = wNode('div', 'ui-empty rail-empty-state');
  const art = wNode('span', 'ui-empty__art');
  art.setAttribute('aria-hidden', 'true');
  art.innerHTML = `<svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/><rect x="20" y="16" width="32" height="34" rx="5" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/><path d="M20 23H52" stroke="#BFDBFE" stroke-width="1.5"/><line x1="28" y1="13" x2="28" y2="17" stroke="#3B82F6" stroke-width="1.5" stroke-linecap="round"/><line x1="44" y1="13" x2="44" y2="17" stroke="#3B82F6" stroke-width="1.5" stroke-linecap="round"/><circle cx="36" cy="35" r="7" fill="#FFFFFF" stroke="#2563EB" stroke-width="1.5"/><path d="M36 31V35L39 37" stroke="#2563EB" stroke-width="1.5" stroke-linecap="round"/><path d="M52 38L52.7 40.3L55 41L52.7 41.7L52 44L51.3 41.7L49 41L51.3 40.3L52 38Z" fill="#3B82F6"/></svg>`;
  const actions = wNode('div', 'ui-empty__actions');
  const addBtn = wNode('button', 'ui-button ui-button--primary ui-button--sm', '添加今日安排');
  addBtn.type = 'button';
  addBtn.onclick = () => {
    if (typeof openScheduleItemModal === 'function') {
      openScheduleItemModal('one-off', null, { date: workspaceTodayISO() });
    }
  };
  const importBtn = wNode('button', 'ui-button ui-button--secondary ui-button--sm', '导入课表');
  importBtn.type = 'button';
  importBtn.onclick = () => {
    if (typeof switchDashboardView === 'function') {
      Promise.resolve(switchDashboardView('schedule')).then(() => {
        if (typeof openScheduleManagementModal === 'function') openScheduleManagementModal();
      });
    }
  };
  actions.append(addBtn, importBtn);
  state.append(art, wNode('strong', '', title), wNode('p', '', detail), actions);
  container.replaceChildren(state);
}

function renderForwardAgenda() {
  const data = workspaceTodayData;
  const container = document.getElementById('today-schedule-content');
  if (!data || !container) return;
  container.setAttribute('aria-busy', 'false'); container.replaceChildren();

  const todayDay = data.days?.[0];
  const todaySub = document.getElementById('today-schedule-sub');
  if (!todayDay) {
    if (todaySub) todaySub.textContent = '今日无安排';
    renderTodayScheduleEmptyState(container, '今天没有安排', '课程与固定时段安排会显示在这里');
    return;
  }

  // Timeline = today's courses + actual time blocks only (agenda.days[0].timed);
  // never deadlines/planned-only/future spill.
  const timed = [...(todayDay.timed || [])].sort((a, b) => (a.start_time || '').localeCompare(b.start_time || ''));

  if (todaySub) todaySub.textContent = timed.length ? `${timed.length} 项日程` : '今日无安排';

  if (!timed.length) {
    renderTodayScheduleEmptyState(container, '今天没有日程安排', '今日的课程与时段安排会显示在这里');
    return;
  }

  const group = wNode('section', 'forward-day');
  group.append(wNode('h3', '', workspaceDateLabel(todayDay.date)));

  timed.forEach(event => {
    const btn = agendaEventButton(event);
    // Keep completed time blocks shown quietly, actual task remains pending until task completion.
    if (event.completed || event.done || event.occurrence_done) {
      btn.classList.add('is-done');
      btn.style.opacity = '0.65';
    }
    group.append(btn);
  });

  container.append(group);
}

let workspaceSearchOpener = null;
let workspaceSearchSelectCallback = null;
let workspaceSearchRequest = 0;

async function openActionSearch(options = {}) {
  const dialog = document.getElementById('action-search-dialog');
  if (!dialog) return;
  workspaceSearchOpener = document.activeElement;
  workspaceSearchSelectCallback = typeof options === 'function' ? options : options?.onSelect || null;
  const isSelectMode = Boolean(workspaceSearchSelectCallback);
  const titleEl = document.getElementById('action-search-title');
  const subtitleEl = document.getElementById('action-search-subtitle');
  const input = document.getElementById('action-search-input');
  if (titleEl) titleEl.textContent = isSelectMode ? '选择要安排的事项' : '查找事项';
  if (subtitleEl) {
    subtitleEl.textContent = isSelectMode
      ? '选择一项未完成待办或项目步骤关联到此日程'
      : '可检索未完成待办、项目行动与已排程日程';
  }
  if (input) {
    input.placeholder = isSelectMode ? '输入关键词筛选未完成待办或项目…' : '输入关键词查找待办、项目或日程…';
    input.value = '';
    input.removeAttribute('aria-activedescendant');
  }
  if (window.uiDialog?.open) {
    window.uiDialog.open(dialog, '#action-search-input');
  } else {
    if (!dialog.open) dialog.showModal();
    input?.focus();
  }
  const list = document.getElementById('action-search-list');
  list.textContent = '正在加载…';
  const reqId = ++workspaceSearchRequest;
  try {
    const [actionsRes, scheduleRes] = await Promise.all([
      workspaceRequest('/api/actions?status=all'),
      isSelectMode ? Promise.resolve(null) : workspaceRequest('/api/schedule').catch(() => null),
    ]);
    if (reqId !== workspaceSearchRequest || !dialog.open) return;
    const rawActions = actionsRes.actions || [];
    const actions = isSelectMode ? rawActions.filter((a) => !a.done && a.active !== false) : rawActions;
    let scheduleItems = [];
    if (!isSelectMode && scheduleRes) {
      const oneOff = (scheduleRes.items?.one_off || []).map(item => ({...item, kind: 'one-off', isSchedule: true}));
      const recurring = (scheduleRes.items?.recurring || []).map(item => ({...item, kind: 'recurring', isSchedule: true}));
      scheduleItems = [...oneOff, ...recurring];
    }

    let selectedIndex = -1;
    let renderedButtons = [];

    const updateSelection = (nextIdx) => {
      if (!renderedButtons.length) {
        selectedIndex = -1;
        input?.removeAttribute('aria-activedescendant');
        return;
      }
      selectedIndex = ((nextIdx % renderedButtons.length) + renderedButtons.length) % renderedButtons.length;
      renderedButtons.forEach((btn, idx) => {
        const active = idx === selectedIndex;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-selected', String(active));
      });
      const activeBtn = renderedButtons[selectedIndex];
      if (activeBtn) {
        input?.setAttribute('aria-activedescendant', activeBtn.id);
        activeBtn.scrollIntoView({ block: 'nearest' });
      }
    };

    const render = () => {
      list.replaceChildren();
      renderedButtons = [];
      const q = input.value.trim().toLocaleLowerCase();
      const matchedActions = actions.filter(a => [a.title, a.details, a.project_name, a.course].filter(Boolean).join(' ').toLocaleLowerCase().includes(q));
      let matchedSchedules = [];
      if (!isSelectMode) {
        matchedSchedules = scheduleItems.filter(s => [s.title, s.details, s.location].filter(Boolean).join(' ').toLocaleLowerCase().includes(q));
      }
      let optionCounter = 0;
      matchedActions.forEach(a => {
        const b = wNode('button', 'action-pool-item');
        b.type = 'button';
        b.id = `action-search-opt-${optionCounter++}`;
        b.setAttribute('role', 'option');
        b.setAttribute('aria-selected', 'false');
        const titleLine = wNode('strong', '', a.title);
        if (a.done) {
          const doneTag = wNode('span', 'ui-badge', '已完成');
          doneTag.style.cssText = 'font-size: 11px; margin-left: 6px; font-weight: normal; opacity: 0.7;';
          titleLine.append(doneTag);
        }
        b.append(titleLine, wNode('small', '', [a.project_name || a.course, a.planned_on ? `计划 ${a.planned_on}` : '', a.due_date ? `截止 ${a.due_date}` : ''].filter(Boolean).join(' · ')));
        b.onclick = () => {
          if (workspaceSearchSelectCallback) {
            const cb = workspaceSearchSelectCallback;
            closeActionSearch();
            cb(a);
          } else {
            closeActionDetailIfNeeded();
            closeActionSearch();
            openActionDetail(a.ref);
          }
        };
        renderedButtons.push(b);
        list.append(b);
      });
      if (!isSelectMode) {
        matchedSchedules.forEach(s => {
          const b = wNode('button', 'action-pool-item');
          b.type = 'button';
          b.id = `action-search-opt-${optionCounter++}`;
          b.setAttribute('role', 'option');
          b.setAttribute('aria-selected', 'false');
          const titleLine = wNode('strong', '', s.title);
          const badge = wNode('span', 'ui-badge', s.kind === 'recurring' ? '每周日程' : '独立日程');
          badge.style.cssText = 'font-size: 11px; margin-left: 6px; font-weight: normal; color: var(--accent); background: var(--accent-subtle, rgba(0,100,250,0.08));';
          titleLine.append(badge);
          const metaText = s.kind === 'recurring'
            ? `每周重复 · ${s.start_time || ''}-${s.end_time || ''}`
            : `${s.date || ''} · ${s.start_time || ''}-${s.end_time || ''}`;
          b.append(titleLine, wNode('small', '', [metaText, s.location].filter(Boolean).join(' · ')));
          b.onclick = () => {
            closeActionSearch();
            if (typeof openScheduleItemModal === 'function') {
              openScheduleItemModal(s.kind, s);
            }
          };
          renderedButtons.push(b);
          list.append(b);
        });
      }
      if (!renderedButtons.length) {
        selectedIndex = -1;
        input?.removeAttribute('aria-activedescendant');
        const emptyText = isSelectMode
          ? (q ? '未找到匹配的未完成事项' : '暂无可关联的未完成待办或项目行动')
          : (q ? '未找到匹配的事项或日程' : '暂无可查找的事项或日程');
        const emptyEl = wNode('p', 'muted', emptyText);
        emptyEl.style.cssText = 'text-align: center; padding: 20px 0;';
        list.append(emptyEl);
      } else {
        updateSelection(0);
      }
    };
    input.oninput = render;
    input.onkeydown = (event) => {
      if (!renderedButtons.length) return;
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        updateSelection(selectedIndex + 1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        updateSelection(selectedIndex - 1);
      } else if (event.key === 'Enter' && selectedIndex >= 0 && renderedButtons[selectedIndex]) {
        event.preventDefault();
        renderedButtons[selectedIndex].click();
      }
    };
    render();
  } catch (error) {
    if (reqId === workspaceSearchRequest) list.textContent = error.message;
  }
}

function closeActionDetailIfNeeded() {
  const detailDialog = document.getElementById('action-detail-dialog');
  if (detailDialog?.open) closeActionDetail({ force: true });
}

function closeActionSearch() {
  const dialog = document.getElementById('action-search-dialog');
  if (window.uiDialog?.close) {
    window.uiDialog.close(dialog, { force: true });
  } else if (dialog?.open) {
    dialog.close();
  }
  workspaceSearchSelectCallback = null;
  if (!window.uiDialog?.close && workspaceSearchOpener?.isConnected) {
    workspaceSearchOpener.focus();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const grid = document.getElementById('schedule-timetable-grid');
  if (grid) new ResizeObserver(() => requestAnimationFrame(fitPeriodCells)).observe(grid);

  const detailDialog = document.getElementById('action-detail-dialog');
  if (detailDialog) {
    detailDialog.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && document.getElementById('action-edit-form') && !document.getElementById('ui-confirm-dialog')?.open) {
        event.preventDefault();
        event.stopImmediatePropagation();
        cancelActionEditor();
      }
    }, true);
    detailDialog.addEventListener('cancel', (event) => {
      if (document.getElementById('action-edit-form') && !document.getElementById('ui-confirm-dialog')?.open) {
        event.preventDefault();
        event.stopImmediatePropagation();
        cancelActionEditor();
      }
    }, true);
    if (window.uiDialog?.bindDialog) {
      window.uiDialog.bindDialog(detailDialog, {
        isDirty: isActionEditorDirty,
        onClose: () => { workspaceDetail = null; },
      });
    } else {
      detailDialog.addEventListener('close', () => {
        workspaceDetail = null;
        if (workspaceDetailOpener?.isConnected) workspaceDetailOpener.focus();
      });
    }
  }

  const periodDialog = document.getElementById('period-entries-dialog');
  if (periodDialog) {
    if (window.uiDialog?.bindDialog) {
      window.uiDialog.bindDialog(periodDialog, {
        onClose: () => { workspacePeriodOpener = null; },
      });
    } else {
      periodDialog.addEventListener('close', () => {
        if (workspacePeriodOpener?.isConnected) workspacePeriodOpener.focus();
      });
    }
  }

  const searchDialog = document.getElementById('action-search-dialog');
  if (searchDialog) {
    if (window.uiDialog?.bindDialog) {
      window.uiDialog.bindDialog(searchDialog, {
        onClose: () => { workspaceSearchSelectCallback = null; },
      });
    } else {
      searchDialog.addEventListener('close', () => {
        workspaceSearchSelectCallback = null;
        if (workspaceSearchOpener?.isConnected) workspaceSearchOpener.focus();
      });
    }
  }

  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === 'k') {
      if (document.getElementById('ui-confirm-dialog')?.open) return;
      event.preventDefault();
      if (searchDialog?.open) {
        closeActionSearch();
      } else {
        openActionSearch();
      }
    }
  });
});
