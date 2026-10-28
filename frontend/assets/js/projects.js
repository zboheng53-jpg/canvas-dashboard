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
  if (options.body) options.headers = {"Content-Type": "application/json", ...options.headers};
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
  if (form.materials) form.materials.value = project?.materials || "";
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
  form.details.value = task?.details || "";
  if (form.show_in_todos) {
    form.show_in_todos.checked = task?.commitment === "obligation" || (task?.commitment === "legacy" && Boolean(task?.due_date));
    form.dataset.originalShowInTodos = String(form.show_in_todos.checked);
  }
  form.dataset.originalCommitment = task?.commitment || "growth";
  form.dataset.originalDueDate = task?.due_date || "";
  form.planned_on.value = task?.planned_on || "";
  form.estimate_minutes.value = task?.estimate_minutes || "";
  form.dataset.updatedAt = task?.updated_at || "";
  form.dataset.originalName = task?.name || "";
  form.dataset.requestId = crypto.randomUUID();
  const pendingTasks = project.tasks.filter((item) => !item.done);
  const isOnlyNextCandidate = task
    ? (!task.done && pendingTasks.length === 1 && pendingTasks[0].id === task.id)
    : pendingTasks.length === 0;
  form.due_date.value = task?.due_date || "";
  form.is_next_action.checked = forceNext || isOnlyNextCandidate || Boolean(task?.is_next_action);
  populateProjectGroupOptions(form.group_id, project, task ? task.group_id : groupId);
  document.getElementById("project-task-title").textContent = task ? "编辑任务" : (forceNext ? "添加下一步行动" : "添加任务");
  document.getElementById("project-task-error").textContent = "";
  const deleteBtn = document.getElementById("project-task-delete-btn");
  if (deleteBtn) {
    if (task) {
      deleteBtn.classList.remove("hidden");
      deleteBtn.onclick = () => {
        closeProjectTaskModal();
        confirmDeleteProjectTask(project.id, task.id);
      };
    } else {
      deleteBtn.classList.add("hidden");
      deleteBtn.onclick = null;
    }
  }
  openTrackedModal("project-task-modal", "[name=name]");
}

function closeProjectTaskModal() {
  const deleteBtn = document.getElementById("project-task-delete-btn");
  if (deleteBtn) {
    deleteBtn.classList.add("hidden");
    deleteBtn.onclick = null;
  }
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
  await Promise.all([loadProjects(selectedProjectId), loadProjectOverview(), fetchProjectTodos(), loadTodaySchedule()]);
  if (!document.getElementById("dashboard-view-schedule").classList.contains("hidden")) await loadScheduleManager();
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
    if (preferredId && projectById(preferredId)) {
      document.querySelectorAll('.project-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === projectById(preferredId).status));
    }
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
  const activeTab = (activeTabBtn && ['active', 'completed', 'archived'].includes(activeTabBtn.dataset.tab)) ? activeTabBtn.dataset.tab : 'active';
  const visible = projectRecords.filter(p => p.status === activeTab);
  if (!visible.some(p => p.id === selectedProjectId)) selectedProjectId = visible[0]?.id || null;

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
        ? `暂放于 ${projectTimestamp(project.archived_at)}`
        : projectDueText(project);

    const totalTasks = project.completed_count + project.pending_count;
    const progressPercent = totalTasks > 0 ? Math.round((project.completed_count / totalTasks) * 100) : 0;
    const nextTask = project.tasks.find(t => t.is_next_action && !t.done) || project.tasks.find(t => !t.done);
    const nextTaskText = nextTask ? `下一步: ${nextTask.name}` : "暂无细分步骤";

    return `
      <button type="button"
        class="ui-nav-item project-browser-item${project.id === selectedProjectId ? " is-selected" : ""}"
        data-project-id="${project.id}"
        draggable="${!history && !isMain}"
        onclick="selectProject(${project.id})"
        ondragstart="startProjectDrag(event, ${project.id})"
        ondragover="allowProjectDrop(event)"
        ondrop="dropProjectBefore(event, ${project.id})">
        <span class="project-list-name">${pEscape(project.name)}${isMain ? '<em class="ui-tag" title="已置顶" style="display:inline-flex;align-items:center;gap:2px"><svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/></svg>置顶</em>' : ""}</span>
        <small class="project-list-next-task">${pEscape(nextTaskText)}</small>

      </button>
    `;
  }).join("");
}

function selectProject(projectId) {
  selectedProjectId = Number(projectId);
  const selected = projectById(projectId);
  if (selected) document.querySelectorAll('.project-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === selected.status));
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

  const statusLabel = project.status === "active" ? "进行中的项目" : project.status === "completed" ? "已完成的项目" : "暂放的项目";

  // Find incomplete next action task (default to first incomplete task if needed)
  const activeTasks = project.tasks.filter(t => !t.done);
  const nextActionTask = activeTasks.find(t => t.is_next_action) || activeTasks[0] || null;
  const completedTasks = project.tasks.filter(t => t.done);
  const totalTasksCount = (project.completed_count || 0) + (project.pending_count || 0);

  const currentGroup = nextActionTask?.group_id ? project.groups.find(g => g.id === nextActionTask.group_id) : null;
  const currentStageName = currentGroup?.name || "未分组";

  let nextActionHtml = "";
  if (nextActionTask && active) {
    nextActionHtml = `
      <div class="project-next-action-card project-current-step-card ui-card" style="margin-bottom: 20px; padding: 18px 20px; border: 1.5px solid var(--color-action); border-radius: 10px; background: var(--color-surface);">
        <div class="project-current-step-header" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; flex-wrap: wrap; gap: 8px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="ui-tag ui-tag--primary project-next-action-label" style="font-weight: 600;">当前步骤</span>
            <span class="muted" style="font-size: 13px;">${pEscape(currentStageName)}</span>
          </div>
          <div class="project-current-step-dates" style="display: flex; gap: 8px;">
            ${nextActionTask.planned_on ? `<span class="ui-tag">计划 ${pEscape(nextActionTask.planned_on)}</span>` : ''}
            ${nextActionTask.due_date ? `<span class="ui-tag ui-tag--danger">截止 ${pEscape(nextActionTask.due_date)}</span>` : ''}
          </div>
        </div>
        <h3 class="project-current-step-title project-next-action-text" style="margin: 0 0 10px 0; font-size: 17px; font-weight: 600;">${pEscape(nextActionTask.name)}</h3>
        <div class="project-current-step-details" style="white-space: pre-wrap; font-size: 14px; line-height: 1.6; color: var(--color-text-secondary); margin-bottom: 16px;">${pEscape(nextActionTask.details || '暂无详细说明')}</div>
        <div class="project-current-step-controls" style="display: flex; gap: 10px; flex-wrap: wrap; align-items: center;">
          <button type="button" class="ui-button ui-button--primary project-next-action-btn-complete" onclick="toggleProjectTask(${project.id}, ${nextActionTask.id}, true)">完成步骤</button>
          <button type="button" class="ui-button ui-button--secondary" onclick="openProjectTaskModal(${project.id}, ${nextActionTask.id})">编辑步骤</button>
          <button type="button" class="ui-button ui-button--secondary" onclick="scheduleProjectStep(${project.id}, ${nextActionTask.id})">安排日程</button>
          ${activeTasks.length > 1 ? `<button type="button" class="ui-button ui-button--secondary project-next-action-btn-choose" onclick="openProjectChoiceModal(${project.id})">更换下一步</button>` : ""}
        </div>
      </div>
    `;
  }

  // All other pending steps collapsed single title rows in chronological roadmap (planned_on ascending, null last, then group/task order)
  const otherPendingTasks = activeTasks.filter(t => t.id !== nextActionTask?.id);
  const groupOrderMap = new Map((project.groups || []).map((g, idx) => [g.id, g.sort_order ?? idx]));
  otherPendingTasks.sort((a, b) => {
    const aPlan = a.planned_on || '9999-99-99';
    const bPlan = b.planned_on || '9999-99-99';
    if (aPlan !== bPlan) return aPlan.localeCompare(bPlan);
    const aGrp = groupOrderMap.get(a.group_id) ?? 9999;
    const bGrp = groupOrderMap.get(b.group_id) ?? 9999;
    if (aGrp !== bGrp) return aGrp - bGrp;
    return (a.sort_order ?? 0) - (b.sort_order ?? 0);
  });

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
            <span class="ui-status ui-status--${project.status === "active" ? "success" : project.status === "completed" ? "info" : "neutral"} project-tag-pill status-tag">${project.status === "active" ? "进行中" : project.status === "completed" ? "已完成" : "暂放"}</span>
            ${currentGroup ? `<span class="ui-tag project-tag-pill stage-tag">${pEscape(currentGroup.name)}</span>` : ""}
            ${project.due_date ? `<span class="ui-tag project-tag-pill due-tag">截止 ${project.due_date}</span>` : ""}
            <span class="ui-count-pill project-progress-pill">进度 ${project.completed_count || 0}/${totalTasksCount}</span>
            ${project.id === mainProjectId ? '<span class="ui-tag is-selected project-tag-pill main-project-tag" style="display:inline-flex;align-items:center;gap:3px"><svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/></svg>已置顶</span>' : ""}
          </div>
        </div>
        <div class="project-detail-actions">
          <button type="button" class="ui-button ui-button--secondary project-materials-link-btn" onclick="openProjectMaterials(${project.id})" title="查看和维护项目资料">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px;vertical-align:-1px"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>项目资料 →
          </button>
          ${active && project.id !== mainProjectId ? `<button type="button" class="ui-button ui-button--secondary project-button-secondary" onclick="setMainProject(${project.id})"><svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" stroke="none" style="margin-right:3px;vertical-align:-1px"><path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/></svg>置顶项目</button>` : ""}
          ${active && project.id === mainProjectId ? `<button type="button" class="ui-button ui-button--secondary project-button-secondary" onclick="unsetMainProject()"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:3px;vertical-align:-1px"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>取消置顶</button>` : ""}
          ${active ? `<button type="button" class="ui-button ui-button--primary project-button-primary" onclick="confirmCompleteProject(${project.id})">完成项目</button>` : `<button type="button" class="ui-button ui-button--primary project-button-primary" onclick="reopenProject(${project.id})">重新开启</button>`}
          <details class="project-more-menu">
            <summary aria-label="更多项目操作">•••</summary>
            <div>
              <button type="button" class="ui-button ui-button--danger" onclick="deleteProjectRecoverably(${project.id})">删除项目</button>
              <button type="button" onclick="openProjectModal(${project.id})" class="ui-button ui-button--secondary"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="project-menu-icon"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg> 编辑项目信息</button>
              ${active ? `<button type="button" class="ui-button ui-button--danger is-danger" onclick="confirmArchiveProject(${project.id})"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="project-menu-icon"><polyline points="21 8 21 21 3 21 3 8"></polyline><rect x="1" y="3" width="22" height="5"></rect><line x1="10" y1="12" x2="14" y2="12"></line></svg> 暂放项目</button>` : ""}
            </div>
          </details>
        </div>
      </div>
    </header>
    ${newlyCreatedProjectId === project.id ? `
      <div class="ui-feedback ui-feedback--success project-created-notice" role="status">
        <span>项目已创建。是否将其置顶？</span>
        <button type="button" onclick="setMainProject(${project.id})" class="ui-button ui-button--secondary">置顶项目</button>
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

    <progress class="project-detail-progress" max="${totalTasksCount || 1}" value="${project.completed_count || 0}" aria-label="项目完成进度"></progress>
    ${nextActionHtml}

    <hr class="project-detail-divider">

    <div class="project-roadmap-section">
      <div class="project-task-toolbar" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <div>
          <h3 style="margin: 0; font-size: 16px;">后续步骤规划 (${otherPendingTasks.length})</h3>
          <p class="muted" style="font-size: 12px; margin: 2px 0 0 0;">按计划时间升序排序；点击可设为当前步骤或编辑。</p>
        </div>
        ${active ? `
          <div style="display: flex; gap: 8px;">
            <button type="button" class="ui-button ui-button--secondary project-button-secondary" onclick="openProjectGroupModal(${project.id})">＋ 新建分组</button>
            <button type="button" class="ui-button ui-button--primary project-button-primary" onclick="openProjectTaskModal(${project.id})">＋ 添加任务</button>
          </div>` : ""}
      </div>
      <div class="project-roadmap-list" style="display: flex; flex-direction: column; gap: 6px;">
        ${otherPendingTasks.length ? otherPendingTasks.map(t => renderRoadmapStep(project, t, active)).join('') : '<p class="muted">暂无后续步骤</p>'}
      </div>
    </div>

    ${completedTasks.length ? `
      <details class="project-finished-groups project-finished-tasks ui-card ui-card--subtle" style="margin-top: 20px;">
        <summary style="padding: 12px 16px; cursor: pointer; font-weight: 600; display: flex; align-items: center; justify-content: space-between;">
          <span>已完成步骤 · ${completedTasks.length} 项</span>
          <span class="muted" style="font-size: 12px; font-weight: normal;">展开查看历史 →</span>
        </summary>
        <div class="project-finished-tasks-list" style="padding: 12px 16px; display: flex; flex-direction: column; gap: 8px;">
          ${completedTasks.map(t => `
            <div class="project-finished-task-row" style="display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: var(--color-text-secondary); padding: 4px 0; border-bottom: 1px dashed var(--color-border);">
              <span style="text-decoration: line-through;">${pEscape(t.name)}</span>
              ${active ? `<button type="button" class="ui-button ui-button--text" onclick="toggleProjectTask(${project.id}, ${t.id}, false)">恢复步骤</button>` : ''}
            </div>
          `).join('')}
        </div>
      </details>
    ` : ''}
    ${active ? `<details class="project-order-management"><summary>管理分组与排序</summary><div class="project-groups">${renderProjectGroups(project)}</div></details>` : ''}

  `;
}

function scheduleProjectStep(projectId, taskId) {
  const task = projectById(projectId)?.tasks.find(t => t.id === taskId);
  if (task) scheduleAction({...task, ref: `project:${projectId}:${taskId}`, title: task.name});
}

function renderRoadmapStep(project, task, active) {
  const group = project.groups.find(g => g.id === task.group_id);
  const missed = task.planned_on && task.planned_on < workspaceTodayISO();
  return `<details class="project-roadmap-row" data-task-id="${task.id}">
    <summary><span class="roadmap-task-title">${pEscape(task.name)}</span>
      <span class="project-roadmap-meta">${task.planned_on ? `${missed ? '原计划' : '计划'} ${pEscape(task.planned_on)}` : ''}${task.due_date ? ` · 截止 ${pEscape(task.due_date)}` : ''}</span></summary>
    <div class="project-roadmap-body">
      ${group ? `<p class="muted">${pEscape(group.name)}</p>` : ''}
      <div class="project-step-details">${pEscape(task.details || '')}</div>
      ${active ? `<div class="project-current-step-controls">
        <button type="button" class="ui-button ui-button--secondary" onclick="toggleProjectTask(${project.id},${task.id},true)">完成步骤</button>
        <button type="button" class="ui-button ui-button--secondary" onclick="setProjectNextAction(${project.id},${task.id})">设为当前</button>
        <button type="button" class="ui-button ui-button--text" onclick="openProjectTaskModal(${project.id},${task.id})">编辑步骤</button>
        <button type="button" class="ui-button ui-button--text" onclick="scheduleProjectStep(${project.id},${task.id})">安排日程</button>
        <button type="button" class="ui-button ui-button--text" onclick="moveTaskToMaterials(${project.id},${task.id})">转为资料</button>
        <button type="button" class="ui-button ui-button--text" onclick="confirmDeleteProjectTask(${project.id},${task.id})">删除步骤</button>
      </div>` : ''}
    </div></details>`;
}

async function setProjectNextAction(projectId, taskId) {
  try {
    await projectRequest(`/api/projects/${projectId}/tasks/${taskId}`, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({is_next_action: true}),
    });
    await refreshProjectSurfaces();
  } catch (error) {
    setProjectStatus("更新当前步骤失败", true);
  }
}
window.setProjectNextAction = setProjectNextAction;

function renderProjectGroups(project) {
  const groups = [...project.groups].sort((a, b) => a.sort_order - b.sort_order);
  const current = [], finished = [];
  for (const group of [...groups, null]) {
    const tasks = project.tasks.filter(t => t.group_id === (group?.id ?? null));
    if (!group && !tasks.length) continue;
    const html = renderProjectGroup(project, group);
    (tasks.length && tasks.every(t => t.done) ? finished : current).push(html);
  }
  if (finished.length) current.push(`<details class="project-finished-groups"><summary>已完成步骤 · ${finished.length}</summary>${finished.join('')}</details>`);
  return current.join('').replaceAll('class="project-group-card"', 'class="ui-card ui-card--subtle project-task-group"');
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
        ${pending.length ? pending.map((task) => renderProjectTask(project, task, active)).join("") : ''}
      </div>
      ${completed.length ? `
        <details class="project-completed-tasks">
          <summary>
            <span class="project-completed-summary-main">
              <svg class="project-disclosure-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"></polyline></svg>
              <span>已完成 ${completed.length} 项</span>
            </span>
            ${active ? `<button type="button" class="ui-button ui-button--danger project-completed-clear-btn" onclick="event.preventDefault(); event.stopPropagation(); confirmClearCompletedTasks(${project.id}, ${groupId === null ? "null" : groupId})" title="清空该分组所有已完成任务">清空已完成</button>` : ""}
          </summary>
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
      <button type="button" class="ui-button ui-button--text ui-button--start project-task-name-btn" onclick="openActionDetail('project:${project.id}:${task.id}')">
        <span class="ui-list-item__title">${pEscape(task.name)}</span>${task.planned_on || task.details ? `<small class="action-task-caption">${[task.planned_on ? `计划 ${pEscape(task.planned_on)}` : "", task.details ? "有详情" : ""].filter(Boolean).join(" · ")}</small>` : ""}
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
        ${active && !task.done ? `<button type="button" class="ui-button ui-button--text" onclick="moveTaskToMaterials(${project.id}, ${task.id})">转为资料</button>` : ''}
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
    ...(form.materials ? {materials: form.materials.value.trim()} : {}),
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
    details: form.details.value,
    planned_on: form.planned_on.value || null,
    estimate_minutes: form.estimate_minutes.value ? Number(form.estimate_minutes.value) : null,
    ...(form.show_in_todos
      ? (form.dataset.originalCommitment !== 'legacy' || String(form.show_in_todos.checked) !== form.dataset.originalShowInTodos || form.due_date.value !== form.dataset.originalDueDate ? {commitment: form.show_in_todos.checked ? 'obligation' : 'growth'} : {})
      : (form.dataset.originalCommitment ? {commitment: form.dataset.originalCommitment} : {})),
    ...(taskId ? {expected_updated_at: form.dataset.updatedAt} : {request_id: form.dataset.requestId}),
    group_id: form.group_id.value ? Number(form.group_id.value) : null,
    due_date: form.due_date.value || null,
    is_next_action: form.is_next_action.checked,
  };
  if (taskId && payload.name === form.dataset.originalName) delete payload.name;
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
    setProjectStatus("项目已置顶");
    await refreshProjectSurfaces();
  } catch (error) {
    setProjectStatus(error.message, true);
  }
}

async function unsetMainProject() {
  try {
    await projectRequest("/api/projects/unset-main", {method: "POST"});
    mainProjectId = null;
    newlyCreatedProjectId = null;
    setProjectStatus("已取消置顶");
    await refreshProjectSurfaces();
  } catch (error) {
    setProjectStatus(error.message, true);
  }
}

async function togglePinProject(event, projectId) {
  if (event) {
    event.stopPropagation();
    event.preventDefault();
  }
  const isCurrentlyPinned = (mainProjectId === projectId);
  if (isCurrentlyPinned) {
    await unsetMainProject();
  } else {
    await setMainProject(projectId);
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
    "暂放项目",
    `暂放表示现在不推进，以后可以继续；完成表示目标已经达成。“${project.name}”的任务状态会保留，但项目会从总览、待办和日历移除。`,
    "暂放项目",
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
    `确定要永久删除“${task.name}”吗？此操作不可撤销，删除后将彻底消失。`,
    "永久删除",
    async () => {
      try {
        await projectRequest(`/api/projects/${projectId}/tasks/${taskId}`, {method: "DELETE", body: JSON.stringify({expected_updated_at: task.updated_at})});
        setProjectStatus("任务已永久删除");
        await refreshProjectSurfaces();
        if (typeof refreshWorkspaceSurfaces === "function") await refreshWorkspaceSurfaces();
      } catch (error) {
        setProjectStatus(error.message, true);
      }
    },
  );
}

function confirmClearCompletedTasks(projectId, groupId) {
  const project = projectById(projectId);
  if (!project) return;
  const tasks = project.tasks.filter((t) => t.group_id === groupId && t.done);
  if (!tasks.length) return;
  const groupName = groupId === null ? "未分组" : (project.groups.find((g) => g.id === groupId)?.name || "当前分组");
  showProjectConfirm(
    "清空已完成任务",
    `确定要永久删除“${groupName}”中的全部 ${tasks.length} 项已完成任务吗？此操作不可撤销。`,
    "永久删除",
    async () => {
      try {
        for (const task of tasks) {
          await projectRequest(`/api/projects/${projectId}/tasks/${task.id}`, {method: "DELETE", body: JSON.stringify({expected_updated_at: task.updated_at})});
        }
        await refreshProjectSurfaces();
        if (typeof refreshWorkspaceSurfaces === "function") await refreshWorkspaceSurfaces();
        setProjectStatus(`已永久删除 ${tasks.length} 项已完成任务`);
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

let cachedOverviewData = null;
let overviewSelectedProjectId = null;

function selectOverviewProject(projectId) {
  overviewSelectedProjectId = projectId;
  if (cachedOverviewData) {
    renderProjectOverview(cachedOverviewData);
  }
}

async function setMainProjectFromOverview(projectId) {
  try {
    await projectRequest(`/api/projects/${projectId}/set-main`, { method: "POST" });
    await refreshProjectSurfaces();
  } catch (error) {
    setProjectStatus("置顶项目失败", true);
  }
}

function renderProjectOverview(data) {
  const container = document.getElementById("project-overview-content");
  if (!container) return;
  cachedOverviewData = data;
  const activeCount = Number(data.active_project_count || 0);
  document.querySelectorAll("#active-project-count").forEach((el) => { el.textContent = activeCount; });
  const railSub = document.getElementById("long-term-projects-sub");
  if (railSub) railSub.textContent = activeCount ? `${activeCount} 个进行中` : "暂无项目";

  if (!activeCount) {
    renderProjectOverviewState("暂无长期项目", "创建一个长期项目，开始组织接下来的行动。", "新建项目", "openProjectsView().then(() => openProjectModal())");
    return;
  }

  const activeProjects = (data.active_projects && data.active_projects.length)
    ? data.active_projects
    : (data.main_project ? [data.main_project] : []);

  if (!activeProjects.length && !data.main_project) {
    renderProjectOverviewState("暂无长期项目", "创建一个长期项目，开始组织接下来的行动。", "新建项目", "openProjectsView().then(() => openProjectModal())");
    return;
  }

  // 置顶排序：已置顶的项目排在最前
  const sortedProjects = [...activeProjects].sort((a, b) => (b.is_main ? 1 : 0) - (a.is_main ? 1 : 0));
  const todayStr = window.customToday || (typeof workspaceTodayISO === 'function' ? workspaceTodayISO() : new Date().toISOString().slice(0, 10));

  // 全部概览模式：每个进行中项目一行紧凑摘要
  container.innerHTML = `<div class="proj project-summary-list">${sortedProjects.map(p => {
    const total = (p.completed_count || 0) + (p.pending_count || 0);
    const signals = [p.missed_plan_count ? `原计划未完成 ${p.missed_plan_count}` : '', p.due_today_count ? `今日截止 ${p.due_today_count}` : '', p.overdue_count ? `逾期 ${p.overdue_count}` : ''].filter(Boolean);
    return `<button type="button" class="ui-button ui-button--text proj-summary-row${p.is_main ? ' is-pinned' : ''}" aria-label="${pEscape(p.name)}" onclick="openProjectsView(${p.id})">
      <span class="proj-summary-copy"><strong title="${pEscape(p.name)}">${pEscape(p.name)}</strong>
      <span class="proj-summary-next" title="${pEscape(p.next_action?.name || '')}">${pEscape(p.next_action?.name || '暂无细分步骤')}</span>
      ${signals.length ? `<small>${pEscape(signals.join(' · '))}</small>` : ''}</span>
      <span class="proj-summary-progress">${p.completed_count || 0}/${total}</span></button>`;
  }).join('')}</div><button type="button" class="ui-button ui-button--text" onclick="openProjectsView()">查看所有项目 →</button>`;

}

async function loadProjectOverview() {
  const container = document.getElementById("project-overview-content");
  if (container) container.setAttribute("aria-busy", "true");
  try {
    const data = await projectRequest("/api/projects/overview");
    if (data.main_project) {
      mainProjectId = data.main_project.id;
    } else if (data.active_projects && !data.active_projects.some((p) => p.is_main)) {
      mainProjectId = null;
    }
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

let projectTodosRequest = 0;
async function fetchProjectTodos() {
  const requestId = ++projectTodosRequest;
  try {
    const data = await projectRequest("/api/projects/todos");
    if (requestId !== projectTodosRequest) return;
    const todayStr = window.customToday || (typeof workspaceTodayISO === 'function' ? workspaceTodayISO() : new Date().toISOString().slice(0, 10));
    const items = (data.items || []).map((item) => {
      const ref = item.ref || item.action_ref || (item.kind === 'project_due' ? `project_due:${item.project_id}` : `project:${item.project_id}:${item.task_id || item.id}`);
      const isMissed = item.missed_plan !== undefined
        ? Boolean(item.missed_plan)
        : Boolean(item.planned_on && item.planned_on < todayStr && !item.done);
      const isToday = item.is_today !== undefined
        ? Boolean(item.is_today)
        : Boolean(item.planned_on === todayStr || item.due_date === todayStr);
      return {
        ...item,
        ref,
        action_ref: ref,
        is_today: isToday,
        missed_plan: isMissed,
        occurrences: item.occurrences || [],
      };
    });
    // Schedule refreshes also fetch project actions. Keep an open row/menu intact
    // when the underlying project entries have not changed.
    if (JSON.stringify(items) === JSON.stringify(projectItems)) return;
    projectItems = items;
  } catch (error) {
    if (requestId !== projectTodosRequest) return;
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

async function deleteProjectTodo(projectId, taskId, kind) {
  if (kind === "project_due") {
    if (!projectById(projectId)) await loadProjects(projectId);
    const project = projectById(projectId);
    const name = project?.name || "该项目";
    showProjectConfirm(
      "清除截止日期",
      `确定要清除“${name}”的项目截止日期吗？清除后此项将不再显示在待办列表中。`,
      "清除截止日期",
      async () => {
        try {
          await projectRequest(`/api/projects/${projectId}`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({due_date: null}),
          });
          await refreshProjectSurfaces();
        } catch (error) {
          setProjectStatus("清除项目截止日期失败", true);
        }
      }
    );
    return;
  }
  if (!projectById(projectId)) await loadProjects(projectId);
  confirmDeleteProjectTask(projectId, taskId);
}

function startProjectTodoDueEdit(button) {
  const projectId = Number(button.dataset.projectId);
  const taskId = Number(button.dataset.taskId) || null;
  const kind = button.dataset.projectKind;
  const field = button.dataset.dateField === 'planned_on' ? 'planned_on' : 'due_date';
  const input = document.createElement("input");
  input.type = "date";
  input.className = "inline-edit-date-input";
  input.value = button.dataset.dateValue ?? button.textContent.trim();
  const original = input.value;
  let saved = false;
  const finish = async (commit) => {
    if (saved) return;
    saved = true;
    input.replaceWith(button);
    renderUnifiedList();
    if (!commit || input.value === original) return;
    const url = kind === "project_due"
      ? `/api/projects/${projectId}`
      : `/api/projects/${projectId}/tasks/${taskId}`;
    try {
      await projectRequest(url, {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({[field]: input.value || null}),
      });
      await refreshProjectSurfaces();
    } catch (error) {
      setProjectStatus("日期同步失败，已恢复原日期", true);
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


async function deleteProjectRecoverably(projectId) {
  const p = projectById(projectId);
  if (!p) return;
  showProjectConfirm('删除项目', `确定要永久删除“${p.name}”吗？此操作不可撤销，该项目及其所有任务将彻底消失。`, '永久删除', async () => {
    try {
      await projectRequest(`/api/projects/${projectId}`, {method:'DELETE', body:JSON.stringify({expected_updated_at:p.updated_at})});
      selectedProjectId = null;
      setProjectStatus("项目已永久删除");
      await refreshProjectSurfaces();
    } catch (error) { setProjectStatus(error.message, true); }
  });
}
async function moveTaskToMaterials(projectId, taskId) {
  const p = projectById(projectId), t = p?.tasks.find(t => t.id === taskId);
  if (!t) return;
  try {
    await projectRequest(`/api/projects/${projectId}/tasks/${taskId}/to-materials`, {method:'POST', body:JSON.stringify({expected_updated_at:t.updated_at, expected_project_updated_at:p.updated_at})});
    await refreshProjectSurfaces();
  } catch (error) { setProjectStatus(error.message, true); }
}
async function renderProjectTrash() {
  const detail = document.getElementById('project-detail');
  if (detail) detail.innerHTML = '<p class="muted">项目与任务删除后为永久删除，不设回收站。</p>';
}
