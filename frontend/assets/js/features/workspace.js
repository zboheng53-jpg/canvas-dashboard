/* Shared action details and date-range views. The dashboard shell stays in place. */
let workspaceDetail = null;
let workspaceDetailOpener = null;
let workspaceWeekDay = null;
let workspaceWeekRequest = 0;
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
  return new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
}
function workspaceDateLabel(day) {
  const today = workspaceTodayISO();
  const delta = Math.round((Date.parse(day) - Date.parse(today)) / 86400000);
  const prefix = delta === 0 ? '今天' : delta === 1 ? '明天' : new Date(`${day}T12:00:00+08:00`).toLocaleDateString('zh-CN', {weekday: 'long', timeZone: 'Asia/Shanghai'});
  return `${prefix} · ${Number(day.slice(5, 7))}月${Number(day.slice(8))}日`;
}

async function refreshWorkspaceSurfaces() {
  await Promise.all([loadProjects(selectedProjectId), loadProjectOverview(), fetchProjectTodos(), fetchCustomTodos(), loadTodaySchedule()]);
  if (!document.getElementById('dashboard-view-schedule').classList.contains('hidden')) await loadScheduleManager();
}

async function openActionDetail(ref, occurrence = null) {
  const dialog = document.getElementById('action-detail-dialog');
  if (!dialog.open) {
    workspaceDetailOpener = document.activeElement;
    dialog.showModal();
  }
  const body = document.getElementById('action-detail-body');
  body.innerHTML = '<p class="muted" role="status">正在加载事项…</p>';
  document.getElementById('action-detail-title').textContent = '事项详情';
  const requestToken = {};
  workspaceDetail = {requestToken};
  try {
    const data = await workspaceRequest(`/api/actions/${encodeURIComponent(ref)}`);
    if (workspaceDetail?.requestToken !== requestToken || !dialog.open) return;
    workspaceDetail = {...data, occurrence};
    renderActionDetail();
  } catch (error) {
    body.textContent = error.message;
  }
}
function closeActionDetail() {
  document.getElementById('action-detail-dialog').close();
  workspaceDetail = null;
  if (workspaceDetailOpener?.isConnected) workspaceDetailOpener.focus();
}
function renderActionDetail() {
  const {action: a, schedules, occurrence} = workspaceDetail;
  document.getElementById('action-detail-title').textContent = a.title;
  const body = document.getElementById('action-detail-body');
  const meta = [a.project_name || a.course, a.done ? '已完成' : '',
    a.planned_on ? `计划 ${a.planned_on}` : '', a.due_date ? `截止 ${a.due_date}${a.deadline_time ? ' ' + a.deadline_time : ''}` : '',
    a.estimate_minutes ? `${a.estimate_minutes} 分钟` : ''].filter(Boolean);
  body.innerHTML = `<p class="action-detail-meta">${meta.map(wEscape).join(' · ')}</p>
    ${a.commitment === 'legacy' ? '<p class="action-legacy-hint">这条旧事项保留了原日期。编辑时可调整是否加入待办，以及计划日期和真实截止。</p>' : ''}
    <div class="action-detail-text">${wEscape(a.details || '暂无详细说明')}</div>
    ${a.original_name ? `<details class="action-original"><summary>原始标题</summary><p>${wEscape(a.original_name)}</p></details>` : ''}
    <div class="action-detail-buttons" id="action-primary-buttons"></div>
    <section class="action-linked-section"><h3>时间安排</h3><div id="action-linked-list"></div></section>
    <p id="action-detail-error" class="ui-error" role="alert"></p>`;
  const buttons = document.getElementById('action-primary-buttons');
  const button = (label, fn, primary = false) => {
    const b = wNode('button', `ui-button ui-button--${primary ? 'primary' : 'secondary'}`, label);
    b.type = 'button'; b.addEventListener('click', fn); buttons.append(b); return b;
  };
  if (a.editable) button('编辑事项', renderActionEditor);
  if (!a.done && a.active !== false && a.source !== 'project_due' && a.source !== 'custom_subtask') {
    button('安排时间', () => scheduleAction(a));
    button('完成事项', () => saveActionCompletion(true), true);
  } else if (a.done && a.editable) button('重新开启事项', () => saveActionCompletion(false));
  if (a.project_id) button('进入项目', () => { closeActionDetail(); openProjectsView(a.project_id); });
  if (a.parent_ref) button('查看所属待办', () => openActionDetail(a.parent_ref));
  if (a.url) {
    const url = sanitizeExternalUrl(a.url);
    if (url) { const link = wNode('a', 'ui-button ui-button--secondary', '打开原始任务'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; buttons.append(link); }
  }
  if (occurrence?.id && !a.done) {
    button(occurrence.occurrence_done ? '撤销本次完成' : '完成本次安排', async () => {
      try {
        await workspaceWrite(`/api/schedule/${occurrence.kind.replace('_', '-')}/${occurrence.id}/occurrence`, {date: occurrence.date, done: !occurrence.occurrence_done});
        occurrence.occurrence_done = !occurrence.occurrence_done;
        await refreshWorkspaceSurfaces(); await openActionDetail(a.ref, occurrence);
      } catch (error) { document.getElementById('action-detail-error').textContent = error.message; }
    });
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
      closeActionDetail();
      openScheduleItemModal(item.kind.replace('_', '-'), {...item, title: a.title}, {date: sameOccurrence ? occurrence.date : item.date});
    });
    row.append(edit); list.append(row);
  });
}
function renderActionEditor() {
  const a = workspaceDetail.action;
  const body = document.getElementById('action-detail-body');
  body.innerHTML = `<form id="action-edit-form" class="project-modal-form">
    <label class="ui-field ui-label">简短标题<input class="ui-control" name="title" required maxlength="40" value="${wEscape(a.title)}"></label>
    <label class="ui-field ui-label">详细说明<textarea class="ui-control" name="details" rows="7" maxlength="12000" placeholder="步骤、材料和完成标准">${wEscape(a.details || '')}</textarea></label>
    ${a.source === 'project' ? `<label class="action-todo-choice"><input type="checkbox" name="show_in_todos" ${a.commitment === 'obligation' || (a.commitment === 'legacy' && a.due_date) ? 'checked' : ''}>同时加入待办清单</label>` : ''}
    <div class="action-date-fields"><label class="ui-field ui-label">计划日期<input class="ui-control" type="date" name="planned_on" value="${wEscape(a.planned_on || '')}"></label>
    <label class="ui-field ui-label">真实截止（可空）<input class="ui-control" type="date" name="due_date" value="${wEscape(a.due_date || '')}"></label></div>
    ${a.commitment === 'legacy' && a.due_date ? '<button type="button" class="ui-button ui-button--text" id="action-date-to-plan">将这个旧日期改作计划日期</button>' : ''}
    <label class="ui-field ui-label">预计分钟数<input class="ui-control" type="number" min="1" max="1440" name="estimate_minutes" value="${a.estimate_minutes || ''}"></label>
    <p class="ui-error" id="action-detail-error" role="alert"></p>
    <div class="project-modal-actions"><button type="button" class="ui-button ui-button--secondary" id="action-edit-cancel">取消</button><button type="submit" class="ui-button ui-button--primary">保存事项</button></div></form>`;
  const form = document.getElementById('action-edit-form');
  form.elements.title.focus();
  document.getElementById('action-edit-cancel').onclick = renderActionDetail;
  document.getElementById('action-date-to-plan')?.addEventListener('click', () => {
    form.elements.planned_on.value = form.elements.due_date.value; form.elements.due_date.value = '';
  });
  form.onsubmit = async event => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form));
    payload.estimate_minutes = payload.estimate_minutes ? Number(payload.estimate_minutes) : null;
    if (a.source === 'project') {
      const show = form.elements.show_in_todos.checked;
      const originalShow = a.commitment === 'obligation' || (a.commitment === 'legacy' && Boolean(a.due_date));
      if (a.commitment !== 'legacy' || show !== originalShow || payload.due_date !== (a.due_date || '')) payload.commitment = show ? 'obligation' : 'growth';
      delete payload.show_in_todos;
    }
    if (payload.title === a.title) delete payload.title;
    payload.expected_updated_at = a.updated_at;
    const submit = form.querySelector('[type=submit]'); submit.disabled = true;
    try {
      await workspaceWrite(`/api/actions/${encodeURIComponent(a.ref)}`, payload);
      await refreshWorkspaceSurfaces(); await openActionDetail(a.ref);
    } catch (error) { document.getElementById('action-detail-error').textContent = error.message; }
    finally { submit.disabled = false; }
  };
}
async function saveActionCompletion(done) {
  const a = workspaceDetail.action;
  try {
    await workspaceWrite(`/api/actions/${encodeURIComponent(a.ref)}`, {done, ...(a.editable ? {expected_updated_at: a.updated_at} : {})});
    const reloadSource = {canvas: fetchCanvasTodos, haoke: fetchHaokeTodos, zhixuemeng: fetchZhixuemengTodos, zhihuishu: fetchZhihuishuTodos}[a.source];
    if (reloadSource) await reloadSource();
    await refreshWorkspaceSurfaces(); await openActionDetail(a.ref);
  } catch (error) { document.getElementById('action-detail-error').textContent = error.message; }
}
function scheduleAction(action) {
  closeActionDetail();
  openScheduleItemModal('one-off', null, {action_ref: action.ref, title: action.title, date: action.planned_on || workspaceTodayISO()});
}
async function openTodoAction(source, id) {
  try {
    const {actions} = await workspaceRequest('/api/actions?status=all');
    const a = actions.find(a => a.source === source && String(a.id) === String(id));
    if (a) await openActionDetail(a.ref);
  } catch (error) { alert(error.message); }
}
function openAgendaEntry(event) {
  if (event.action_ref && !event.link_missing) return openActionDetail(event.action_ref, event);
  if (event.kind === 'course') return onScheduleCardClick({...event, raw: event.course, courseIndex: event.course_index}, event.date);
  openScheduleItemModal(event.kind.replace('_', '-'), event, {date: event.date});
}

function agendaEventButton(event) {
  const button = wNode('button', `period-event period-event--${event.kind} ${event.done || event.occurrence_done ? 'is-done' : ''}`);
  button.type = 'button';
  const time = event.kind === 'deadline' ? `${event.deadline_time || '全天'} 截止` : event.kind === 'planned' ? '计划推进 · 未定时间' : `${event.start_time}–${event.end_time}`;
  button.append(wNode('span', 'period-event-time', time), wNode('strong', 'period-event-title', event.title));
  const meta = [event.location, event.link_missing ? '原事项已移除' : '', event.occurrence_done ? '本次已完成' : ''].filter(Boolean).join(' · ');
  if (meta) button.append(wNode('small', '', meta));
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
    dates.forEach((day, i) => {
      const button = dayMark(wNode('button', `period-day ${day === workspaceTodayISO() ? 'is-today' : ''}`, `${weekdayLabels[i]} ${day.slice(5)}`), day);
      button.type = 'button'; button.setAttribute('aria-pressed', String(day === workspaceWeekDay));
      button.onclick = () => { workspaceWeekDay = day; renderPeriodSchedule(data); };
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
    requestAnimationFrame(fitPeriodCells);
  } catch (error) { setScheduleStatus(error.message, true); }
}
function fitPeriodCells() {
  const desktop = matchMedia('(min-width: 961px)').matches;
  document.querySelectorAll('.period-cell').forEach(cell => {
    const list = cell.querySelector('.period-cell-events');
    const more = cell.querySelector('.period-more');
    const events = [...list.querySelectorAll('.period-event')];
    events.forEach(event => { event.hidden = false; });
    more.hidden = true;
    if (!desktop || !cell.clientHeight) return;
    const gap = parseFloat(getComputedStyle(list).gap) || 0;
    let used = 0, visible = 0;
    for (const event of events) {
      const height = event.getBoundingClientRect().height;
      if (used + height > list.clientHeight + .5) break;
      used += height + gap; visible++;
    }
    events.slice(visible).forEach(event => { event.hidden = true; });
    const hidden = events.length - visible;
    if (hidden) { more.textContent = visible ? `还有 ${hidden} 项` : `查看 ${hidden} 项`; more.hidden = false; }
  });
}
function openPeriodEntries(day, band, entries) {
  const dialog = document.getElementById('period-entries-dialog');
  document.getElementById('period-entries-title').textContent = `${workspaceDateLabel(day)} · ${band}`;
  const list = document.getElementById('period-entries-list'); list.replaceChildren();
  entries.forEach(event => {
    const button = agendaEventButton(event);
    button.addEventListener('click', () => dialog.close(), {capture: true});
    list.append(button);
  });
  dialog.showModal();
}

async function loadForwardAgenda() {
  const requestId = ++workspaceTodayRequest;
  const start = workspaceTodayISO();
  const end = new Date(`${start}T12:00:00+08:00`); end.setUTCDate(end.getUTCDate() + 13);
  try {
    const data = await workspaceRequest(`/api/agenda?start=${start}&end=${end.toISOString().slice(0,10)}`);
    if (requestId !== workspaceTodayRequest) return;
    workspaceTodayData = data; renderForwardAgenda();
    const courses = data.days[0].timed.filter(e => e.kind === 'course');
    document.getElementById('stat-course-count').textContent = courses.length;
    const currentTime = new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Shanghai', hour:'2-digit', minute:'2-digit'}).format(new Date());
    const next = courses.find(c => c.end_time > currentTime);
    document.getElementById('stat-course-next').textContent = next ? `${next.start_time} ${next.title}` : courses.length ? '今日课程已结束' : '今天没有课程';
  } catch (error) { renderTodayScheduleState('日程加载失败', error.message, true); }
}
function renderForwardAgenda() {
  const data = workspaceTodayData;
  const container = document.getElementById('today-schedule-content');
  if (!data || !container) return;
  container.setAttribute('aria-busy', 'false'); container.replaceChildren();
  const capacity = Math.min(9, Math.max(5, Math.floor((container.clientHeight || 420) / 68)));
  let count = 0; let shownDays = 0;
  data.days.forEach((day, index) => {
    const entries = [...day.deadlines, ...day.timed, ...day.planned.filter(p => !day.deadlines.some(d => d.ref === p.ref))];
    if (index > 0 && (!entries.length || count >= capacity)) return;
    const group = wNode('section', 'forward-day'); group.append(wNode('h3', '', workspaceDateLabel(day.date)));
    if (!entries.length) group.append(wNode('p', 'muted', '今天暂无安排，可以提前规划后续事项。'));
    entries.forEach(event => group.append(agendaEventButton(event)));
    container.append(group); count += entries.length; shownDays++;
  });
  const todayCount = data.days[0].timed.length + data.days[0].deadlines.length + data.days[0].planned.length;
  document.getElementById('today-schedule-sub').textContent = shownDays > 1 ? '含未来安排' : `${todayCount} 项`;
  const footer = wNode('div', 'forward-footer');
  const full = wNode('button', 'ui-button ui-button--text', '查看完整周排程 →'); full.type = 'button'; full.onclick = () => switchDashboardView('schedule');
  const search = wNode('button', 'ui-button ui-button--text', '查找所有事项'); search.type = 'button'; search.onclick = openActionSearch;
  footer.append(full, search); container.append(footer);
}
async function openActionSearch() {
  const dialog = document.getElementById('action-search-dialog'); dialog.showModal();
  const list = document.getElementById('action-search-list'); list.textContent = '正在加载…';
  const input = document.getElementById('action-search-input'); input.value = ''; input.focus();
  try {
    const {actions} = await workspaceRequest('/api/actions');
    const render = () => {
      list.replaceChildren(); const q = input.value.toLocaleLowerCase();
      actions.filter(a => [a.title,a.details,a.project_name].join(' ').toLocaleLowerCase().includes(q)).forEach(a => {
        const b = wNode('button', 'action-pool-item'); b.type = 'button'; b.append(wNode('strong', '', a.title), wNode('small', '', [a.project_name, a.planned_on ? `计划 ${a.planned_on}` : '', a.due_date ? `截止 ${a.due_date}` : ''].filter(Boolean).join(' · ')));
        b.onclick = () => { dialog.close(); openActionDetail(a.ref); }; list.append(b);
      });
      if (!list.children.length) list.textContent = '没有找到事项';
    };
    input.oninput = render; render();
  } catch (error) { list.textContent = error.message; }
}

document.addEventListener('DOMContentLoaded', () => {
  const grid = document.getElementById('schedule-timetable-grid');
  if (grid) new ResizeObserver(() => requestAnimationFrame(fitPeriodCells)).observe(grid);
  const container = document.getElementById('today-schedule-content');
  if (container) {
    let lastHeight = 0;
    new ResizeObserver(entries => {
      const height = Math.round(entries[0].contentRect.height);
      if (height !== lastHeight && height > 0) { lastHeight = height; renderForwardAgenda(); }
    }).observe(container);
  }
});
