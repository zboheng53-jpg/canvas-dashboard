/* Long-term projects V2: overview, project workspace, and todo linkage. */
let projectRecords = [];
let selectedProjectId = null;
let mainProjectId = null;
let lastViewedProjectId = null;
let projectModalOpener = null;
let activeProjectModal = null;
let projectConfirmAction = null;
let projectDragId = null;
let projectGroupDragId = null;
let projectTaskDragId = null;
let newlyCreatedProjectId = null;

const pEscape = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function setProjectStatus(message, error = false) {
  const status = document.getElementById("project-manager-status");
  if (!status) return;
  status.textContent = message;
  const semantic = error
    ? "danger"
    : !message
      ? "neutral"
      : message.startsWith("正在")
        ? "info"
        : "success";
  applyFeedbackSemantic(status, semantic);
}

async function projectRequest(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "操作失败，请稍后重试");
  }
  return data;
}

function projectById(projectId) {
  return projectRecords.find((project) => project.id === Number(projectId));
}

function projectDueText(project) {
  if (!project.due_date) return "";
  if (project.due_state === "overdue") return `已逾期 ${project.due_days} 天`;
  if (project.due_state === "today") return "今天截止";
  return `距离截止 ${project.due_days} 天`;
}

function projectTimestamp(value) {
  return value ? value.slice(0, 10) : "";
}

function projectGroupName(project, groupId) {
  if (groupId === null || groupId === undefined) return "未分组";
  return project.groups.find((group) => group.id === groupId)?.name || "未分组";
}

function taskMeta(project, task) {
  const parts = [];
  if (task.group_id !== null) parts.push(projectGroupName(project, task.group_id));
  if (task.due_date) parts.push(task.due_date);
  return parts.join(" · ");
}

function openTrackedModal(modalId, focusSelector) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  projectModalOpener = document.activeElement;
  activeProjectModal = modal;
  modal.dataset.dirty = "false";
  modal.classList.remove("hidden");
  requestAnimationFrame(() => modal.querySelector(focusSelector)?.focus());
}

function closeTrackedModal(modalId, force = true) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  if (!force && modal.dataset.dirty === "true") {
    const error = modal.querySelector(".project-modal-error");
    if (error) error.textContent = "有未保存的输入，请使用“取消”明确关闭。";
    return;
  }
  modal.classList.add("hidden");
  modal.dataset.dirty = "false";
  if (activeProjectModal === modal) activeProjectModal = null;
  const opener = projectModalOpener;
  projectModalOpener = null;
  if (opener && document.contains(opener)) opener.focus();
}

function markProjectModalClean(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.dataset.dirty = "false";
}

function openProjectModal(projectId = null) {
  const form = document.getElementById("project-editor-form");
  const project = projectId === null ? null : projectById(projectId);
  form.reset();
  form.project_id.value = project?.id || "";
  form.name.value = project?.name || "";
  form.objective.value = project?.objective || "";
  form.due_date.value = project?.due_date || "";
  document.getElementById("project-editor-title").textContent = project ? "编辑项目" : "新建项目";
  document.getElementById("project-editor-error").textContent = "";
  openTrackedModal("project-editor-modal", "[name=name]");
}

function closeProjectModal() {
  closeTrackedModal("project-editor-modal");
}

function populateProjectGroupOptions(select, project, selectedGroupId) {
  select.replaceChildren();
  const ungrouped = document.createElement("option");
  ungrouped.value = "";
  ungrouped.textContent = "未分组";
  select.append(ungrouped);
  [...project.groups]
    .sort((a, b) => a.sort_order - b.sort_order)
    .forEach((group) => {
      const option = document.createElement("option");
      option.value = String(group.id);
      option.textContent = group.name;
      select.append(option);
    });
  select.value = selectedGroupId === null || selectedGroupId === undefined ? "" : String(selectedGroupId);
}

function openProjectTaskModal(projectId, taskId = null, groupId = null, forceNext = false) {
  const project = projectById(projectId);
  if (!project) return;
  const task = taskId === null ? null : project.tasks.find((item) => item.id === Number(taskId));
  const form = document.getElementById("project-task-form");
  form.reset();
  form.project_id.value = project.id;
  form.task_id.value = task?.id || "";
  form.name.value = task?.name || "";
  form.due_date.value = task?.due_date || "";
  form.is_next_action.checked = forceNext || Boolean(task?.is_next_action);
  populateProjectGroupOptions(form.group_id, project, task ? task.group_id : groupId);
  document.getElementById("project-task-title").textContent = task ? "编辑任务" : (forceNext ? "添加下一步行动" : "添加任务");
  document.getElementById("project-task-error").textContent = "";
  openTrackedModal("project-task-modal", "[name=name]");
}

function closeProjectTaskModal() {
  closeTrackedModal("project-task-modal");
}

function openProjectGroupModal(projectId, groupId = null) {
  const project = projectById(projectId);
  if (!project) return;
  const group = groupId === null ? null : project.groups.find((item) => item.id === Number(groupId));
  const form = document.getElementById("project-group-form");
  form.reset();
  form.project_id.value = project.id;
  form.group_id.value = group?.id || "";
  form.name.value = group?.name || "";
  document.getElementById("project-group-title").textContent = group ? "重命名分组" : "新建分组";
  document.getElementById("project-group-error").textContent = "";
  openTrackedModal("project-group-modal", "[name=name]");
}

function closeProjectGroupModal() {
  closeTrackedModal("project-group-modal");
}

function openProjectChoiceModal(projectId) {
  const project = projectById(projectId);
  const list = document.getElementById("project-choice-list");
  if (!project || !list) return;
  const tasks = project.tasks.filter((task) => !task.done);
  list.innerHTML = tasks.length
    ? tasks.map((task) => `
        <button type="button" class="project-choice-row" onclick="chooseProjectNextTask(${project.id}, ${task.id})">
          <strong>${pEscape(task.name)}</strong>
          <small>${pEscape(taskMeta(project, task) || "未设置分组和日期")}</small>
        </button>
      `).join("")
    : `<div class="ui-empty project-detail-empty"><span class="ui-empty__art" aria-hidden="true"></span><strong>暂无可选择的任务</strong><p>请先添加一条任务。</p></div>`;
  openTrackedModal("project-choice-modal", ".project-choice-row, .project-modal-close");
}

function closeProjectChoiceModal() {
  closeTrackedModal("project-choice-modal");
}

function showProjectConfirm(title, copy, label, action) {
  document.getElementById("project-confirm-title").textContent = title;
  document.getElementById("project-confirm-copy").textContent = copy;
  document.getElementById("project-confirm-submit").textContent = label;
  projectConfirmAction = action;
  openTrackedModal("project-confirm-modal", "#project-confirm-submit");
}

function closeProjectConfirmModal(confirmed) {
  const action = projectConfirmAction;
  projectConfirmAction = null;
  closeTrackedModal("project-confirm-modal");
  if (confirmed && action) action();
}

async function refreshProjectSurfaces() {
  await Promise.all([loadProjects(selectedProjectId), loadProjectOverview(), fetchProjectTodos()]);
}

function selectProjectIdFromContext(preferredId = null) {
  const urlId = Number(new URLSearchParams(window.location.search).get("project"));
  const candidates = [preferredId, urlId, selectedProjectId, mainProjectId, lastViewedProjectId]
    .map(Number)
    .filter(Number.isInteger);
  for (const id of candidates) {
    if (projectById(id)) return id;
  }
  return projectRecords.find((project) => project.status === "active")?.id || null;
}

async function loadProjects(preferredId = null) {
  const list = document.getElementById("project-manager-list");
  if (list) list.setAttribute("aria-busy", "true");
  setProjectStatus("正在加载项目…");
  try {
    const data = await projectRequest("/api/projects");
    projectRecords = data.projects || [];
    mainProjectId = data.main_project_id;
    lastViewedProjectId = data.last_viewed_project_id;
    selectedProjectId = selectProjectIdFromContext(preferredId);
    renderProjectWorkspace();
    setProjectStatus("");
    return true;
  } catch (error) {
    setProjectStatus(error.message || "项目加载失败，请稍后重试", true);
    const detail = document.getElementById("project-detail");
    if (detail) {
      detail.innerHTML = `<div class="ui-empty ui-empty--danger project-detail-empty is-error"><span class="ui-empty__art" aria-hidden="true"></span><strong>项目加载失败</strong><p>请稍后重试。</p></div>`;
    }
    return false;
  } finally {
    if (list) list.setAttribute("aria-busy", "false");
  }
}

function renderProjectWorkspace() {
  const active = projectRecords.filter((project) => project.status === "active");
  const completed = projectRecords.filter((project) => project.status === "completed");
  const archived = projectRecords.filter((project) => project.status === "archived");

  const activeCountEl = document.getElementById("active-project-count");
  if (activeCountEl) activeCountEl.textContent = active.length;
  const completedCountEl = document.getElementById("completed-project-count");
  if (completedCountEl) completedCountEl.textContent = completed.length;
  const archivedCountEl = document.getElementById("archived-project-count");
  if (archivedCountEl) archivedCountEl.textContent = archived.length;

  const activeTabBtn = document.querySelector('.project-tab-btn.active');
  const activeTab = activeTabBtn ? activeTabBtn.dataset.tab : 'active';

  if (activeTab === 'active') {
    renderProjectList("project-manager-list", active, false);
  } else if (activeTab === 'completed') {
    renderProjectList("project-manager-list", completed, true);
  } else if (activeTab === 'archived') {
    renderProjectList("project-manager-list", archived, true);
  }

  renderProjectDetail();
}

function switchProjectTab(tabName) {
  const buttons = document.querySelectorAll('.project-tab-btn');
  buttons.forEach(btn => {
    if (btn.dataset.tab === tabName) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
  renderProjectWorkspace();
}

function renderProjectList(containerId, values, history) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!values.length) {
    container.innerHTML = `<div class="ui-empty ui-empty--compact project-list-empty"><strong>${history ? "暂无记录" : "还没有进行中的项目"}</strong></div>`;
    return;
  }
  container.innerHTML = values.map((project) => {
    const isMain = project.id === mainProjectId;
    const historyDate = project.status === "completed"
      ? `完成于 ${projectTimestamp(project.completed_at)}`
      : project.status === "archived"
        ? `归档于 ${projectTimestamp(project.archived_at)}`
        : projectDueText(project);

    const totalTasks = project.completed_count + project.pending_count;
    const progressPercent = totalTasks > 0 ? Math.round((project.completed_count / totalTasks) * 100) : 0;
    const nextTask = project.tasks.find(t => t.is_next_action && !t.done);
    const nextTaskText = nextTask ? `下一步: ${nextTask.name}` : "无下一步行动";

    return `
      <button type="button"
        class="ui-nav-item project-browser-item${project.id === selectedProjectId ? " is-selected" : ""}"
        data-project-id="${project.id}"
        draggable="${!history && !isMain}"
        onclick="selectProject(${project.id})"
        ondragstart="startProjectDrag(event, ${project.id})"
        ondragover="allowProjectDrop(event)"
        ondrop="dropProjectBefore(event, ${project.id})">
        <span class="project-list-name">${pEscape(project.name)}${isMain ? '<em class="ui-tag">主项目</em>' : ""}</span>
        <small class="project-list-next-task">${pEscape(nextTaskText)}</small>
        <div class="project-list-progress-wrapper">
          <div class="project-list-progress-bar" style="width: ${progressPercent}%"></div>
        </div>
      </button>
    `;
  }).join("");
}

function selectProject(projectId) {
  selectedProjectId = Number(projectId);
  const url = new URL(window.location.href);
  url.searchParams.set("project", selectedProjectId);
  history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  renderProjectWorkspace();
  fetch(`/api/projects/${selectedProjectId}/viewed`, {method: "POST"}).catch(() => {});
}

function openProjectsView(projectId = null) {
  if (projectId !== null) {
    selectedProjectId = Number(projectId);
    const url = new URL(window.location.href);
    url.searchParams.set("project", selectedProjectId);
    history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }
  return switchDashboardView("projects").then(() => {
    if (projectId !== null) selectProject(projectId);
  });
}

function openProjectDetail(projectId, create = false) {
  if (create) {
    openProjectsView().then(() => openProjectModal());
    return;
  }
  openProjectsView(projectId);
}

function renderProjectDetail() {
  const detail = document.getElementById("project-detail");
  const project = projectById(selectedProjectId);
  if (!detail) return;
  if (!project) {
    detail.innerHTML = `
      <div class="ui-empty project-detail-empty">
        <span class="ui-empty__art" aria-hidden="true">
          <svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/>
            <rect x="18" y="18" width="36" height="30" rx="6" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/>
            <path d="M26 33H46" stroke="#BFDBFE" stroke-width="1.5"/>
            <circle cx="26" cy="33" r="3" fill="#FFFFFF" stroke="#2563EB" stroke-width="1.5"/>
            <circle cx="36" cy="33" r="3" fill="#FFFFFF" stroke="#3B82F6" stroke-width="1.5"/>
            <circle cx="46" cy="33" r="3" fill="#FFFFFF" stroke="#60A5FA" stroke-width="1.5"/>
            <path d="M22 18V15C22 13.8954 22.8954 13 24 13H30C31.1046 13 32 13.8954 32 15V18" stroke="#93C5FD" stroke-width="1.5"/>
            <path d="M52 14L52.7 16.3L55 17L52.7 17.7L52 20L51.3 17.7L49 17L51.3 16.3L52 14Z" fill="#60A5FA"/>
          </svg>
        </span>
        <strong>${projectRecords.some((item) => item.status === "active") ? "选择一个项目查看详情" : "暂无长期项目"}</strong>
        <p>${projectRecords.length ? "从左侧项目列表中选择。" : "新建一个项目，开始组织长期目标。"}</p>
        ${projectRecords.length ? "" : '<button type="button" class="ui-button ui-button--primary project-button-primary" onclick="openProjectModal()">新建项目</button>'}
      </div>`;
    return;
  }
  const active = project.status === "active";
  const allDone = project.tasks.length > 0 && project.pending_count === 0;

  const statusLabel = project.status === "active" ? "进行中的项目" : project.status === "completed" ? "已完成的项目" : "已归档的项目";

  // Find incomplete next action task
  const activeTasks = project.tasks.filter(t => !t.done);
  const nextActionTask = activeTasks.find(t => t.is_next_action);

  let nextActionHtml = "";
  if (nextActionTask) {
    nextActionHtml = `
      <div class="project-next-action-card">
        <div class="project-next-action-left">
          <span class="project-next-action-label">下一步行动</span>
          <span class="project-next-action-text">${pEscape(nextActionTask.name)}</span>
        </div>
        <button type="button" class="ui-button ui-button--primary project-next-action-btn-complete" onclick="toggleProjectTask(${project.id}, ${nextActionTask.id}, true)">标记完成</button>
      </div>
    `;
  } else if (active && activeTasks.length > 0) {
    nextActionHtml = `
      <div class="project-next-action-card is-empty">
        <div class="project-next-action-left">
          <span class="project-next-action-label">下一步行动</span>
          <span class="project-next-action-text text-muted">暂无下一步行动，可从下方选择任务设为下一步</span>
        </div>
        <button type="button" class="ui-button ui-button--secondary project-next-action-btn-choose" onclick="openProjectChoiceModal(${project.id})">选择任务</button>
      </div>
    `;
  }

  detail.innerHTML = `
    <header class="project-detail-header">
      <div class="project-detail-title-row">
        <div>
          <span class="project-detail-kicker">${statusLabel}</span>
          <div class="project-title-line">
            <h2>${pEscape(project.name)}</h2>
          </div>
          <p class="project-objective">${pEscape(project.objective || "尚未填写一句话目标")}</p>
          <div class="project-tags-row">
            <span class="ui-status ui-status--${project.status === "active" ? "success" : project.status === "completed" ? "info" : "neutral"} project-tag-pill status-tag">${project.status === "active" ? "进行中" : project.status === "completed" ? "已完成" : "已归档"}</span>
            ${project.due_date ? `<span class="ui-tag project-tag-pill due-tag">截止 ${project.due_date}</span>` : ""}
            <span class="ui-count-pill project-tag-pill progress-tag"><b>${project.completed_count}</b> / ${project.completed_count + project.pending_count} 项完成</span>
            ${project.id === mainProjectId ? '<span class="ui-tag is-selected project-tag-pill main-project-tag">主项目</span>' : ""}
          </div>
        </div>
        <div class="project-detail-actions">
          ${active && project.id !== mainProjectId ? `<button type="button" class="ui-button ui-button--secondary project-button-secondary" onclick="setMainProject(${project.id})">设为主项目</button>` : ""}
          ${active ? `<button type="button" class="ui-button ui-button--primary project-button-primary" onclick="confirmCompleteProject(${project.id})">完成项目</button>` : `<button type="button" class="ui-button ui-button--primary project-button-primary" onclick="reopenProject(${project.id})">重新开启</button>`}
          <details class="project-more-menu">
            <summary aria-label="更多项目操作">•••</summary>
            <div>
              <button type="button" onclick="openProjectModal(${project.id})" class="ui-button ui-button--secondary"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="project-menu-icon"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg> 编辑项目信息</button>
              ${active ? `<button type="button" class="ui-button ui-button--danger is-danger" onclick="confirmArchiveProject(${project.id})"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="project-menu-icon"><polyline points="21 8 21 21 3 21 3 8"></polyline><rect x="1" y="3" width="22" height="5"></rect><line x1="10" y1="12" x2="14" y2="12"></line></svg> 归档项目</button>` : ""}
            </div>
          </details>
        </div>
      </div>
    </header>
    ${newlyCreatedProjectId === project.id ? `
      <div class="ui-feedback ui-feedback--success project-created-notice" role="status">
        <span>项目已创建。是否设为当前主项目？</span>
        <button type="button" onclick="setMainProject(${project.id})" class="ui-button ui-button--secondary">设为主项目</button>
        <button type="button" onclick="dismissCreatedProjectNotice()" class="ui-button ui-button--secondary">暂不设置</button>
      </div>` : ""}
    ${allDone && active ? `
      <div class="ui-alert ui-alert--success project-all-done" role="status">
        <div>
          <strong>所有任务已完成</strong>
          <p>项目不会自动完成；你可以继续添加任务或手动完成项目。</p>
          <div class="project-all-done-actions">
            <button type="button" onclick="openProjectTaskModal(${project.id})" class="ui-button ui-button--secondary">添加新任务</button>
            <button type="button" onclick="confirmCompleteProject(${project.id})" class="ui-button ui-button--secondary">完成项目</button>
          </div>
        </div>
      </div>` : ""}

    ${nextActionHtml}

    <hr class="project-detail-divider">

    <div class="project-task-toolbar">
      <div><h3>项目任务</h3><p>拖拽可调整分组和任务顺序；移动端可通过任务菜单修改分组。</p></div>
      ${active ? `
        <div>
          <button type="button" class="ui-button ui-button--secondary project-button-secondary" onclick="openProjectGroupModal(${project.id})">＋ 新建分组</button>
          <button type="button" class="ui-button ui-button--primary project-button-primary" onclick="openProjectTaskModal(${project.id})">＋ 添加任务</button>
        </div>` : ""}
    </div>
    <div class="project-groups" id="project-groups">
      ${renderProjectGroups(project)}
    </div>
  `;
}

function renderProjectGroups(project) {
  const groups = [...project.groups].sort((a, b) => a.sort_order - b.sort_order);
  const sections = groups.map((group) => renderProjectGroup(project, group));
  sections.push(renderProjectGroup(project, null));
  return sections.join("").replaceAll(
    'class="project-group-card"',
    'class="ui-card ui-card--subtle project-task-group"',
  );
}

function renderProjectGroup(project, group) {
  const groupId = group?.id ?? null;
  const tasks = project.tasks
    .filter((task) => task.group_id === groupId)
    .sort((a, b) => a.sort_order - b.sort_order);
  const pending = tasks.filter((task) => !task.done);
  const completed = tasks.filter((task) => task.done);
  const active = project.status === "active";
  const groupAttr = groupId === null ? "" : String(groupId);
  return `
    <section class="project-group-card"
      data-group-id="${groupAttr}"
      draggable="${active && group !== null}"
      ondragstart="startProjectGroupDrag(event, ${groupId === null ? "null" : groupId})"
      ondragover="allowProjectTaskDrop(event)"
      ondrop="dropProjectTaskAtEnd(event, ${groupId === null ? "null" : groupId})">
      <header class="project-group-heading">
        <h4>${pEscape(group?.name || "未分组")}</h4>
        ${active ? `<button type="button" class="ui-button ui-button--primary project-group-add-task-btn" onclick="openProjectTaskModal(${project.id}, null, ${groupId === null ? "null" : groupId})">＋ 添加任务</button>` : ""}
      </header>
      <div class="project-task-list">
        ${pending.length ? pending.map((task) => renderProjectTask(project, task, active)).join("") : '<div class="ui-empty ui-empty--compact project-task-empty"><strong>暂无未完成任务</strong></div>'}
      </div>
      ${completed.length ? `
        <details class="project-completed-tasks">
          <summary>已完成 ${completed.length} 项</summary>
          <div class="project-task-list">${completed.map((task) => renderProjectTask(project, task, active)).join("")}</div>
        </details>` : ""}
    </section>
  `;
}

function renderProjectTask(project, task, active) {
  const groupArg = task.group_id === null ? "null" : task.group_id;
  const dateText = task.due_date ? task.due_date.slice(5) : ""; // MM-DD
  return `
    <article class="ui-list-item ui-list-item--interactive ui-list-item--contained project-task-item${task.done ? " ui-list-item--muted is-done" : ""}${task.is_next_action ? " is-next" : ""}"
      data-task-id="${task.id}"
      draggable="${active}"
      ondragstart="startProjectTaskDrag(event, ${task.id})"
      ondragover="allowProjectTaskDrop(event)"
      ondrop="dropProjectTaskBefore(event, ${task.id}, ${groupArg})">
      <input type="checkbox" ${task.done ? "checked" : ""} ${active ? "" : "disabled"}
        aria-label="${task.done ? "取消完成" : "完成"}${pEscape(task.name)}"
        onchange="toggleProjectTask(${project.id}, ${task.id}, this.checked)" class="ui-checkbox">
      <button type="button" class="ui-button ui-button--text ui-button--start project-task-name-btn" onclick="openProjectTaskModal(${project.id}, ${task.id})">
        <span class="ui-list-item__title">${pEscape(task.name)}</span>
      </button>
      ${dateText ? `<span class="ui-list-item__meta project-task-date">${pEscape(dateText)}</span>` : ""}
      <div class="project-task-actions">
        ${active ? `
          <button type="button" class="ui-icon-button project-task-action-btn" title="编辑" onclick="openProjectTaskModal(${project.id}, ${task.id})">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
          </button>` : ""}
        ${active && !task.done ? `
          <button type="button" class="ui-icon-button project-task-action-btn${task.is_next_action ? " is-active-next" : ""}" title="设为下一步" aria-pressed="${task.is_next_action ? "true" : "false"}" onclick="chooseProjectNextTask(${project.id}, ${task.id})">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle></svg>
          </button>` : ""}
        <button type="button" class="ui-icon-button ui-icon-button--danger project-task-action-btn is-danger" title="删除任务" onclick="confirmDeleteProjectTask(${project.id}, ${task.id})">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
        </button>
      </div>
    </article>
  `;
}

function dismissCreatedProjectNotice() {
  newlyCreatedProjectId = null;
  renderProjectDetail();
}

async function saveProjectEditor(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector("[type=submit]");
  const id = Number(form.project_id.value) || null;
  const payload = {
    name: form.name.value.trim(),
    objective: form.objective.value.trim(),
    due_date: form.due_date.value || null,
  };
  submit.disabled = true;
  document.getElementById("project-editor-error").textContent = "";
  try {
    const data = await projectRequest(id ? `/api/projects/${id}` : "/api/projects", {
      method: id ? "PUT" : "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    selectedProjectId = data.project.id;
    if (!id) newlyCreatedProjectId = data.project.id;
    markProjectModalClean("project-editor-modal");
    closeProjectModal();
    setProjectStatus(id ? "项目已更新" : "项目已创建");
    await refreshProjectSurfaces();
  } catch (error) {
    document.getElementById("project-editor-error").textContent = `${error.message}，当前输入已保留。`;
  } finally {
    submit.disabled = false;
  }
}

async function saveProjectTaskEditor(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector("[type=submit]");
  const projectId = Number(form.project_id.value);
  const taskId = Number(form.task_id.value) || null;
  const payload = {
    name: form.name.value.trim(),
    group_id: form.group_id.value ? Number(form.group_id.value) : null,
    due_date: form.due_date.value || null,
    is_next_action: form.is_next_action.checked,
  };
  submit.disabled = true;
  document.getElementById("project-task-error").textContent = "";
  try {
    await projectRequest(
      taskId ? `/api/projects/${projectId}/tasks/${taskId}` : `/api/projects/${projectId}/tasks`,
      {
        method: taskId ? "PUT" : "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      },
    );
    markProjectModalClean("project-task-modal");
    closeProjectTaskModal();
    setProjectStatus(taskId ? "任务已更新" : "任务已添加");
    await refreshProjectSurfaces();
  } catch (error) {
    document.getElementById("project-task-error").textContent = `${error.message}，当前输入已保留。`;
  } finally {
    submit.disabled = false;
  }
}

async function saveProjectGroupEditor(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector("[type=submit]");
  const projectId = Number(form.project_id.value);
  const groupId = Number(form.group_id.value) || null;
  submit.disabled = true;
  document.getElementById("project-group-error").textContent = "";
  try {
    await projectRequest(
      groupId ? `/api/projects/${projectId}/groups/${groupId}` : `/api/projects/${projectId}/groups`,
      {
        method: groupId ? "PUT" : "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name: form.name.value.trim()}),
      },
    );
    markProjectModalClean("project-group-modal");
    closeProjectGroupModal();
    await refreshProjectSurfaces();
  } catch (error) {
    document.getElementById("project-group-error").textContent = `${error.message}，当前输入已保留。`;
  } finally {
    submit.disabled = false;
  }
}

async function setMainProject(projectId) {
  try {
    await projectRequest(`/api/projects/${projectId}/set-main`, {method: "POST"});
    newlyCreatedProjectId = null;
    selectedProjectId = projectId;
    setProjectStatus("主项目已更新");
    await refreshProjectSurfaces();
  } catch (error) {
    setProjectStatus(error.message, true);
  }
}

function confirmCompleteProject(projectId) {
  const project = projectById(projectId);
  if (!project) return;
  const impact = project.pending_count
    ? `仍有 ${project.pending_count} 项未完成任务；它们会保留原状态，但会从统一待办和 Apple 日历移除。`
    : "项目中的任务都已完成。";
  showProjectConfirm("完成项目", `${impact} 确认将“${project.name}”标记为已完成吗？`, "完成项目", async () => {
    try {
      await projectRequest(`/api/projects/${projectId}/complete`, {method: "POST"});
      await refreshProjectSurfaces();
    } catch (error) {
      setProjectStatus(error.message, true);
    }
  });
}

function confirmArchiveProject(projectId) {
  const project = projectById(projectId);
  if (!project) return;
  showProjectConfirm(
    "归档项目",
    `归档表示放弃或搁置，不等于完成。“${project.name}”的任务状态会保留，但项目会从总览、待办和日历移除。`,
    "归档项目",
    async () => {
      try {
        await projectRequest(`/api/projects/${projectId}/archive`, {method: "POST"});
        await refreshProjectSurfaces();
      } catch (error) {
        setProjectStatus(error.message, true);
      }
    },
  );
}

async function reopenProject(projectId) {
  try {
    await projectRequest(`/api/projects/${projectId}/reopen`, {method: "POST"});
    selectedProjectId = projectId;
    await refreshProjectSurfaces();
  } catch (error) {
    setProjectStatus(error.message, true);
  }
}

async function toggleProjectTask(projectId, taskId, done) {
  try {
    await projectRequest(`/api/projects/${projectId}/tasks/${taskId}`, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({done}),
    });
    await refreshProjectSurfaces();
  } catch (error) {
    setProjectStatus("任务状态同步失败，界面已恢复", true);
    await loadProjects(projectId);
  }
}

async function chooseProjectNextTask(projectId, taskId) {
  try {
    await projectRequest(`/api/projects/${projectId}/tasks/${taskId}/set-next`, {method: "POST"});
    closeProjectChoiceModal();
    await refreshProjectSurfaces();
  } catch (error) {
    setProjectStatus(error.message, true);
  }
}

function confirmDeleteProjectTask(projectId, taskId) {
  const project = projectById(projectId);
  const task = project?.tasks.find((item) => item.id === taskId);
  if (!task) return;
  showProjectConfirm(
    "删除任务",
    `“${task.name}”将被永久删除，且会从项目统计、统一待办和 Apple 日历中移除。此操作不可恢复。`,
    "永久删除",
    async () => {
      try {
        await projectRequest(`/api/projects/${projectId}/tasks/${taskId}`, {method: "DELETE"});
        await refreshProjectSurfaces();
      } catch (error) {
        setProjectStatus(error.message, true);
      }
    },
  );
}

function deleteProjectGroup(projectId, groupId) {
  const project = projectById(projectId);
  const group = project?.groups.find((item) => item.id === groupId);
  if (!project || !group) return;
  const taskCount = project.tasks.filter((task) => task.group_id === groupId).length;
  const remove = async () => {
    try {
      await projectRequest(`/api/projects/${projectId}/groups/${groupId}`, {method: "DELETE"});
      await refreshProjectSurfaces();
    } catch (error) {
      setProjectStatus(error.message, true);
    }
  };
  if (!taskCount) {
    remove();
    return;
  }
  showProjectConfirm(
    "删除非空分组",
    `“${group.name}”包含 ${taskCount} 项任务。删除分组后，任务会移动到“未分组”，名称、状态、日期和下一步标记均保持不变。`,
    "删除并移动任务",
    remove,
  );
}

function startProjectDrag(event, projectId) {
  projectDragId = projectId;
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", `project:${projectId}`);
}

function allowProjectDrop(event) {
  if (projectDragId !== null) event.preventDefault();
}

async function dropProjectBefore(event, targetId) {
  if (projectDragId === null || projectDragId === targetId) return;
  event.preventDefault();
  const active = projectRecords.filter((project) => project.status === "active").map((project) => project.id);
  const from = active.indexOf(projectDragId);
  const to = active.indexOf(targetId);
  if (from < 0 || to < 0) return;
  active.splice(from, 1);
  active.splice(to, 0, projectDragId);
  projectDragId = null;
  try {
    await projectRequest("/api/projects/reorder", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({project_ids: active}),
    });
    await loadProjects(selectedProjectId);
  } catch (error) {
    setProjectStatus("项目排序保存失败，已恢复原顺序", true);
    await loadProjects(selectedProjectId);
  }
}

function startProjectGroupDrag(event, groupId) {
  if (groupId === null) return;
  projectGroupDragId = groupId;
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", `group:${groupId}`);
}

async function dropProjectGroupBefore(event, targetGroupId) {
  if (projectGroupDragId === null || projectGroupDragId === targetGroupId) return;
  event.preventDefault();
  event.stopPropagation();
  const project = projectById(selectedProjectId);
  const ids = [...project.groups].sort((a, b) => a.sort_order - b.sort_order).map((group) => group.id);
  const from = ids.indexOf(projectGroupDragId);
  const to = ids.indexOf(targetGroupId);
  ids.splice(from, 1);
  ids.splice(to, 0, projectGroupDragId);
  projectGroupDragId = null;
  try {
    await projectRequest(`/api/projects/${project.id}/groups/reorder`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({group_ids: ids}),
    });
    await loadProjects(project.id);
  } catch (error) {
    setProjectStatus("分组排序保存失败，已恢复原顺序", true);
    await loadProjects(project.id);
  }
}

function startProjectTaskDrag(event, taskId) {
  projectTaskDragId = taskId;
  event.stopPropagation();
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", `task:${taskId}`);
}

function allowProjectTaskDrop(event) {
  if (projectTaskDragId !== null || projectGroupDragId !== null) event.preventDefault();
}

function projectTaskPlacements(project, draggedId, targetId, targetGroupId) {
  const groups = [...project.groups].sort((a, b) => a.sort_order - b.sort_order).map((group) => group.id);
  groups.push(null);
  const buckets = new Map(groups.map((groupId) => [
    groupId,
    project.tasks
      .filter((task) => task.group_id === groupId && task.id !== draggedId)
      .sort((a, b) => a.sort_order - b.sort_order),
  ]));
  const dragged = project.tasks.find((task) => task.id === draggedId);
  if (!dragged) return null;
  const target = buckets.get(targetGroupId);
  if (!target) return null;
  const index = targetId === null ? target.length : Math.max(0, target.findIndex((task) => task.id === targetId));
  target.splice(index < 0 ? target.length : index, 0, dragged);
  return groups.flatMap((groupId) => buckets.get(groupId).map((task) => ({id: task.id, group_id: groupId})));
}

async function persistProjectTaskDrop(targetId, targetGroupId) {
  const project = projectById(selectedProjectId);
  if (!project || projectTaskDragId === null) return;
  const placements = projectTaskPlacements(project, projectTaskDragId, targetId, targetGroupId);
  projectTaskDragId = null;
  if (!placements) return;
  try {
    await projectRequest(`/api/projects/${project.id}/tasks/reorder`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({tasks: placements}),
    });
    await loadProjects(project.id);
  } catch (error) {
    setProjectStatus("任务排序保存失败，已恢复原顺序", true);
    await loadProjects(project.id);
  }
}

function dropProjectTaskBefore(event, targetId, targetGroupId) {
  if (projectTaskDragId === null || projectTaskDragId === targetId) return;
  event.preventDefault();
  event.stopPropagation();
  persistProjectTaskDrop(targetId, targetGroupId);
}

function dropProjectTaskAtEnd(event, targetGroupId) {
  if (projectGroupDragId !== null && targetGroupId !== null) {
    dropProjectGroupBefore(event, targetGroupId);
    return;
  }
  if (projectTaskDragId === null) return;
  event.preventDefault();
  persistProjectTaskDrop(null, targetGroupId);
}

function renderProjectOverviewState(title, copy, actionLabel = "", action = "") {
  const container = document.getElementById("project-overview-content");
  if (!container) return;
  container.innerHTML = `
    <div class="ui-empty rail-empty-state">
      <span class="ui-empty__art" aria-hidden="true">
        <svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/>
          <rect x="18" y="18" width="36" height="30" rx="6" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/>
          <path d="M26 33H46" stroke="#BFDBFE" stroke-width="1.5"/>
          <circle cx="26" cy="33" r="3" fill="#FFFFFF" stroke="#2563EB" stroke-width="1.5"/>
          <circle cx="36" cy="33" r="3" fill="#FFFFFF" stroke="#3B82F6" stroke-width="1.5"/>
          <circle cx="46" cy="33" r="3" fill="#FFFFFF" stroke="#60A5FA" stroke-width="1.5"/>
          <path d="M22 18V15C22 13.8954 22.8954 13 24 13H30C31.1046 13 32 13.8954 32 15V18" stroke="#93C5FD" stroke-width="1.5"/>
          <path d="M52 14L52.7 16.3L55 17L52.7 17.7L52 20L51.3 17.7L49 17L51.3 16.3L52 14Z" fill="#60A5FA"/>
        </svg>
      </span>
      <div><strong>${pEscape(title)}</strong><p>${pEscape(copy)}</p></div>
      ${actionLabel ? `<button type="button" class="ui-button ui-button--primary project-empty-create" onclick="${action}">${pEscape(actionLabel)}</button>` : ""}
    </div>`;
}

function overviewTaskRow(project, task, checkbox = false) {
  return `
    <div class="ui-list-item project-overview-task${task.is_next_action ? " is-next" : ""}">
      ${checkbox ? `<input type="checkbox" aria-label="完成${pEscape(task.name)}" onchange="completeOverviewTask(${project.id}, ${task.id}, this)" class="ui-checkbox">` : '<span class="project-overview-task-mark" aria-hidden="true">·</span>'}
      <button type="button" onclick="openProjectsView(${project.id})" class="ui-button ui-button--secondary">
        <strong>${pEscape(task.name)}</strong>
        ${task.group_name || task.due_date ? `<small>${pEscape([task.group_name, task.due_date].filter(Boolean).join(" · "))}</small>` : ""}
      </button>
    </div>`;
}

function renderProjectOverview(data) {
  const container = document.getElementById("project-overview-content");
  if (!container) return;
  // 同步填侧栏 nav-count 与项目视图 tab 计数（与 renderProjectWorkspace 行为一致）
  const activeCount = Number(data.active_project_count || 0);
  document.querySelectorAll("#active-project-count").forEach((el) => { el.textContent = activeCount; });
  // 右栏卡片副标题：设计稿为「N 个进行中」
  const railSub = document.getElementById("long-term-projects-sub");
  if (railSub) railSub.textContent = activeCount ? `${activeCount} 个进行中` : "暂无项目";
  const project = data.main_project;
  if (!activeCount) {
    renderProjectOverviewState("暂无长期项目", "创建一个长期项目，开始组织接下来的行动。", "新建项目", "openProjectsView().then(() => openProjectModal())");
    return;
  }
  if (!project) {
    renderProjectOverviewState("尚未设置主项目", "从进行中的项目里选择一个当前重点。", "选择主项目", "openProjectsView()");
    return;
  }
  const otherCount = Math.max(0, activeCount - 1);
  const total = project.completed_count + project.pending_count;
  const pct = total ? Math.min(100, Math.round((project.completed_count / total) * 100)) : 0;
  const dueText = projectDueText(project);
  const upcoming = project.upcoming_tasks || [];
  // 设计稿 .proj 块：名称 + 剩余天数 / 进度条 / 副信息 / 下一步蓝卡 / 任务预览
  container.innerHTML = `
    <div class="proj">
      <div class="proj-top">
        <button type="button" class="proj-name" onclick="openProjectsView(${project.id})" title="查看项目详情">${pEscape(project.name)}</button>
        ${dueText ? `<span class="proj-due${project.due_state === "overdue" ? " is-overdue" : ""}">${pEscape(dueText)}</span>` : ""}
      </div>
      <div class="bar"><i style="width:${pct}%"></i></div>
      <div class="proj-sub">${project.completed_count} / ${total} 任务完成${project.objective ? ` · ${pEscape(project.objective)}` : ""}</div>
      ${project.next_action ? `
        <button type="button" class="biz-project-item__next" onclick="openProjectsView(${project.id})" title="打开项目查看下一步">
          <b>下一步</b>${pEscape(project.next_action.name)}
          ${project.next_action.due_date ? `<span class="late">${pEscape(project.next_action.due_date)}</span>` : ""}
        </button>` : `
        <button type="button" class="biz-project-item__next is-empty" onclick="openProjectsView(${project.id})" title="选择下一步行动">
          <b>下一步</b>未设置
        </button>`}
      ${upcoming.length ? `
        <div class="proj-tasks">
          ${upcoming.map((task) => `
            <div class="pt${task.done ? " is-done" : ""}">
              <input type="checkbox" class="pt-check ui-checkbox" aria-label="完成${pEscape(task.name)}" onchange="completeOverviewTask(${project.id}, ${task.id}, this)" ${task.done ? "checked" : ""}>
              <span class="t">${pEscape(task.name)}</span>
              <span class="d">${pEscape(task.due_date || (task.done ? "已完成" : ""))}</span>
            </div>`).join("")}
        </div>` : ""}
      <div class="proj-links">
        ${project.hidden_task_count ? `<button type="button" onclick="openProjectsView(${project.id})" class="ui-button ui-button--text">还有 ${project.hidden_task_count} 项 →</button>` : ""}
        ${otherCount ? `<button type="button" onclick="openProjectsView()" class="ui-button ui-button--text">另外 ${otherCount} 个项目进行中 →</button>` : ""}
      </div>
    </div>`;
}

async function loadProjectOverview() {
  const container = document.getElementById("project-overview-content");
  if (container) container.setAttribute("aria-busy", "true");
  try {
    const data = await projectRequest("/api/projects/overview");
    renderProjectOverview(data);
  } catch (error) {
    renderProjectOverviewState("长期项目加载失败", "请稍后重试。");
  } finally {
    if (container) container.setAttribute("aria-busy", "false");
  }
}

async function completeOverviewTask(projectId, taskId, checkbox) {
  checkbox.disabled = true;
  try {
    await projectRequest(`/api/projects/${projectId}/tasks/${taskId}`, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({done: true}),
    });
    await refreshProjectSurfaces();
  } catch (error) {
    checkbox.checked = false;
    checkbox.disabled = false;
    renderProjectOverviewState("任务同步失败", "任务仍保持未完成，请稍后重试。");
  }
}

async function fetchProjectTodos() {
  try {
    const data = await projectRequest("/api/projects/todos");
    projectItems = data.items || [];
  } catch (error) {
    projectItems = [];
    console.error("Failed to fetch project todos:", error);
  }
  renderUnifiedList();
}

async function toggleProjectTodoFlag(projectId, taskId, kind, current) {
  const url = kind === "project_due"
    ? `/api/projects/${projectId}`
    : `/api/projects/${projectId}/tasks/${taskId}`;
  const payload = kind === "project_due"
    ? {due_highlighted: !current}
    : {highlighted: !current};
  try {
    await projectRequest(url, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    await refreshProjectSurfaces();
  } catch (error) {
    setProjectStatus("标红状态同步失败", true);
  }
}

async function completeProjectTodo(projectId, taskId, kind) {
  if (kind === "project_due") {
    if (!projectById(projectId)) await loadProjects(projectId);
    confirmCompleteProject(projectId);
    return;
  }
  try {
    await projectRequest(`/api/projects/${projectId}/tasks/${taskId}`, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({done: true}),
    });
    await refreshProjectSurfaces();
  } catch (error) {
    setProjectStatus("任务完成状态同步失败", true);
  }
}

function startProjectTodoDueEdit(button) {
  const projectId = Number(button.dataset.projectId);
  const taskId = Number(button.dataset.taskId) || null;
  const kind = button.dataset.projectKind;
  const input = document.createElement("input");
  input.type = "date";
  input.className = "inline-edit-date-input";
  input.value = button.textContent.trim();
  const original = input.value;
  let saved = false;
  const finish = async (commit) => {
    if (saved) return;
    saved = true;
    if (!commit || input.value === original) {
      renderUnifiedList();
      return;
    }
    const url = kind === "project_due"
      ? `/api/projects/${projectId}`
      : `/api/projects/${projectId}/tasks/${taskId}`;
    try {
      await projectRequest(url, {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({due_date: input.value || null}),
      });
      await refreshProjectSurfaces();
    } catch (error) {
      setProjectStatus("截止日期同步失败，已恢复原日期", true);
      await fetchProjectTodos();
    }
  };
  button.replaceWith(input);
  input.focus();
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") finish(true);
    if (event.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
}

document.getElementById("project-editor-form")?.addEventListener("submit", saveProjectEditor);
document.getElementById("project-task-form")?.addEventListener("submit", saveProjectTaskEditor);
document.getElementById("project-group-form")?.addEventListener("submit", saveProjectGroupEditor);
document.getElementById("project-confirm-submit")?.addEventListener("click", () => closeProjectConfirmModal(true));

document.querySelectorAll(".project-modal-form").forEach((form) => {
  form.addEventListener("input", () => {
    const modal = form.closest(".project-modal-backdrop");
    if (modal) modal.dataset.dirty = "true";
  });
});

document.querySelectorAll(".project-modal-backdrop").forEach((modal) => {
  modal.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const focusable = [...modal.querySelectorAll("button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled])")]
      .filter((element) => element.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !activeProjectModal) return;
  const modal = activeProjectModal;
  if (modal.dataset.dirty === "true") {
    const error = modal.querySelector(".project-modal-error");
    if (error) error.textContent = "有未保存的输入，请使用“取消”明确关闭。";
    return;
  }
  closeTrackedModal(modal.id);
});

if (!(window.location.protocol === 'file:' || window.location.hostname === '') || window.__OPEN_DESIGN_PREVIEW__) {
  loadProjectOverview();
  fetchProjectTodos();
}
