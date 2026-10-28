/* Material logs use the project's API and shared tracked modals. */
let materialsProjects = [], materialsEntries = [];
let selectedMaterialsProjectId = null, materialsLoadSequence = 0;
let materialsReady = false, currentEditingMaterial = null, materialCreateAttempt = null;
let legacyMaterialsOriginal = '';
const mEscape = pEscape;

function setMaterialsStatus(message, error = false) {
  const status = document.getElementById('materials-status');
  status.textContent = message;
  status.classList.toggle('hidden', !message);
  applyFeedbackSemantic(status, error ? 'danger' : 'neutral');
}

async function loadMaterials(projectId = selectedMaterialsProjectId) {
  selectedMaterialsProjectId = projectId ? Number(projectId) : null;
  const sequence = ++materialsLoadSequence;
  const container = document.getElementById('materials-container');
  const createButton = document.getElementById('materials-new-button');
  container.setAttribute('aria-busy', 'true');
  createButton.disabled = true;
  try {
    const data = await projectRequest('/api/materials');
    if (sequence !== materialsLoadSequence) return false;
    if (!Array.isArray(data.projects) || !Array.isArray(data.entries)) throw new Error('资料响应不完整，请重试');
    materialsProjects = data.projects;
    materialsEntries = data.entries;
    materialsReady = true;
    setMaterialsStatus('');
    renderMaterials();
    return true;
  } catch (error) {
    if (sequence !== materialsLoadSequence) return false;
    materialsReady = false;
    setMaterialsStatus(`加载资料失败：${error.message}`, true);
    container.innerHTML = '<div class="ui-empty"><button type="button" class="ui-button ui-button--secondary" data-material-action="retry">重新加载</button></div>';
    return false;
  } finally {
    if (sequence === materialsLoadSequence) {
      container.setAttribute('aria-busy', 'false');
      createButton.disabled = !materialsReady || !materialsProjects.length;
    }
  }
}

function onMaterialsProjectFilterChange(value) {
  selectedMaterialsProjectId = value ? Number(value) : null;
  if (materialsReady) renderMaterials();
}
function openProjectMaterials(projectId) {
  selectedMaterialsProjectId = Number(projectId);
  return switchDashboardView('materials');
}
window.openProjectMaterials = openProjectMaterials;

function renderMaterials() {
  const container = document.getElementById('materials-container');
  const select = document.getElementById('materials-project-filter');
  select.innerHTML = '<option value="">全部项目</option>' + materialsProjects.map(project => `<option value="${project.id}">${mEscape(project.name)}</option>`).join('');
  select.value = selectedMaterialsProjectId ? String(selectedMaterialsProjectId) : '';
  const entries = materialsEntries.filter(entry => !selectedMaterialsProjectId || Number(entry.project_id) === selectedMaterialsProjectId);
  if (!entries.length) { container.innerHTML = '<div class="ui-empty"><strong>暂无资料记录</strong></div>'; return; }
  const dates = [...new Set(entries.map(entry => entry.date).filter(Boolean))].sort().reverse();
  const latestDate = dates[0];
  const latest = latestDate ? entries.filter(entry => entry.date === latestDate) : [];
  const history = entries.filter(entry => !latestDate || entry.date !== latestDate);
  const cards = values => values.map(renderMaterialEntryCard).join('');
  let html = latest.length ? `<section class="materials-latest-section"><div class="materials-date-group-header"><h3>${mEscape(latestDate)}</h3></div><div class="materials-entries-list">${cards(latest)}</div></section>` : '';
  if (history.length) {
    const groups = [...dates.slice(1), ...(history.some(entry => !entry.date) ? [null] : [])];
    html += `<details class="materials-history ui-card ui-card--subtle" id="materials-history"><summary class="materials-history-summary">历史 · ${history.length}</summary><div class="materials-history-body">${groups.map(day => `<section class="materials-date-group"><h4>${mEscape(day || '无日期')}</h4><div class="materials-entries-list">${cards(history.filter(entry => (entry.date || null) === day))}</div></section>`).join('')}</div></details>`;
  }
  container.innerHTML = html;
}

function renderMaterialEntryCard(entry) {
  const actions = entry.legacy
    ? '<button type="button" class="ui-button ui-button--text" data-material-action="legacy">编辑原文</button>'
    : '<button type="button" class="ui-button ui-button--text" data-material-action="edit">编辑</button><button type="button" class="ui-button ui-button--text is-danger" data-material-action="delete">删除</button>';
  return `<article class="material-entry-card ui-card" data-project-id="${entry.project_id}" data-entry-id="${mEscape(entry.id)}"><div class="material-entry-header materials-header-actions">${selectedMaterialsProjectId ? '' : `<span class="material-entry-meta">${mEscape(entry.project_name)}</span>`}<div class="material-entry-actions materials-header-actions">${actions}</div></div><div class="material-entry-body action-detail-text">${mEscape(entry.body)}</div></article>`;
}

function openNewMaterialModal() {
  if (!materialsReady || !materialsProjects.length) return;
  currentEditingMaterial = null;
  materialCreateAttempt = null;
  const form = document.getElementById('material-entry-form');
  form.reset();
  form.elements.material_id.value = '';
  form.elements.expected_updated_at.value = '';
  form.elements.date.value = workspaceTodayISO();
  prepareMaterialEditor('新建资料记录', selectedMaterialsProjectId);
}
function prepareMaterialEditor(title, projectId) {
  document.getElementById('material-entry-title').textContent = title;
  document.getElementById('material-entry-error').textContent = '';
  document.getElementById('material-entry-delete-btn').classList.toggle('hidden', !currentEditingMaterial);
  const select = document.getElementById('material-form-project');
  select.innerHTML = materialsProjects.map(project => `<option value="${project.id}">${mEscape(project.name)}</option>`).join('');
  if (projectId) select.value = String(projectId);
  select.disabled = Boolean(currentEditingMaterial);
  openTrackedModal('material-entry-modal', '[name=body]');
}
function openMaterialEditorModal(projectId, entryId) {
  const entry = materialsEntries.find(value => String(value.id) === String(entryId) && Number(value.project_id) === Number(projectId));
  if (!entry || entry.legacy) return;
  currentEditingMaterial = entry;
  const form = document.getElementById('material-entry-form');
  form.elements.material_id.value = entry.id;
  form.elements.expected_updated_at.value = entry.updated_at;
  form.elements.date.value = entry.date;
  form.elements.body.value = entry.body;
  prepareMaterialEditor('编辑资料记录', projectId);
}
function closeMaterialEntryModal(force = false) {
  if (document.getElementById('material-entry-modal').dataset.saving !== 'true') closeTrackedModal('material-entry-modal', force);
}
function materialModalBusy(modalId, busy) {
  const modal = document.getElementById(modalId);
  modal.dataset.saving = String(busy);
  modal.querySelectorAll('button, textarea, input, select').forEach(control => {
    if (busy) { control.dataset.wasDisabled = String(control.disabled); control.disabled = true; }
    else { control.disabled = control.dataset.wasDisabled === 'true'; delete control.dataset.wasDisabled; }
  });
}
async function refreshMaterialsAfterWrite() {
  await loadMaterials(selectedMaterialsProjectId);
  document.getElementById('materials-project-filter').focus();
}
async function handleMaterialEntrySubmit(event) {
  event.preventDefault();
  const form = event.target;
  if (document.getElementById('material-entry-modal').dataset.saving === 'true') return;
  const projectId = form.elements.project_id.value, materialId = form.elements.material_id.value;
  const body = form.elements.body.value, day = form.elements.date.value;
  const error = document.getElementById('material-entry-error');
  if (!body.trim() || !day) { error.textContent = '请填写记录日期和资料内容'; return; }
  const payload = {date: day, body};
  if (materialId) payload.expected_updated_at = form.elements.expected_updated_at.value;
  else {
    const signature = JSON.stringify({projectId, ...payload});
    if (materialCreateAttempt?.signature !== signature) materialCreateAttempt = {signature, id: `mat-${crypto.randomUUID()}`};
    payload.request_id = materialCreateAttempt.id;
  }
  error.textContent = '';
  materialModalBusy('material-entry-modal', true);
  try {
    await projectRequest(`/api/projects/${projectId}/materials${materialId ? `/${materialId}` : ''}`, {method: materialId ? 'PUT' : 'POST', body: JSON.stringify(payload)});
    markProjectModalClean('material-entry-modal');
    closeTrackedModal('material-entry-modal');
    await refreshMaterialsAfterWrite();
  } catch (failure) { error.textContent = failure.message; }
  finally { materialModalBusy('material-entry-modal', false); }
}
async function deleteMaterialEntry(projectId, materialId, expectedUpdatedAt, fromEditor = false) {
  if (!confirm('删除这条资料记录？')) return false;
  if (fromEditor) materialModalBusy('material-entry-modal', true);
  try {
    await projectRequest(`/api/projects/${projectId}/materials/${materialId}`, {method: 'DELETE', body: JSON.stringify({expected_updated_at: expectedUpdatedAt})});
    if (fromEditor) { markProjectModalClean('material-entry-modal'); closeTrackedModal('material-entry-modal'); }
    await refreshMaterialsAfterWrite();
    return true;
  } catch (error) {
    if (fromEditor) document.getElementById('material-entry-error').textContent = error.message;
    else setMaterialsStatus(error.message, true);
    return false;
  } finally { if (fromEditor) materialModalBusy('material-entry-modal', false); }
}
function handleDeleteCurrentMaterial() {
  if (currentEditingMaterial && document.getElementById('material-entry-modal').dataset.saving !== 'true') return deleteMaterialEntry(currentEditingMaterial.project_id, currentEditingMaterial.id, currentEditingMaterial.updated_at, true);
}
function openLegacyMaterialsModal(projectId) {
  const project = materialsProjects.find(value => value.id === Number(projectId));
  if (!project) return;
  legacyMaterialsOriginal = project.materials;
  document.getElementById('legacy-project-id').value = projectId;
  document.getElementById('legacy-expected-updated-at').value = project.updated_at;
  document.getElementById('legacy-project-name').textContent = project.name;
  document.getElementById('legacy-materials-body').value = legacyMaterialsOriginal;
  document.getElementById('legacy-materials-error').textContent = '';
  openTrackedModal('legacy-materials-modal', '[name=materials]');
}
function closeLegacyMaterialsModal(force = false) {
  if (document.getElementById('legacy-materials-modal').dataset.saving !== 'true') closeTrackedModal('legacy-materials-modal', force);
}
async function handleLegacyMaterialsSubmit(event) {
  event.preventDefault();
  if (document.getElementById('legacy-materials-modal').dataset.saving === 'true') return;
  const value = document.getElementById('legacy-materials-body').value;
  // A textarea normalizes line endings even when the user did not edit them.
  const materials = value === legacyMaterialsOriginal.replace(/\r\n?/g, '\n') ? legacyMaterialsOriginal : value;
  const projectId = document.getElementById('legacy-project-id').value;
  const error = document.getElementById('legacy-materials-error');
  error.textContent = '';
  materialModalBusy('legacy-materials-modal', true);
  try {
    await projectRequest(`/api/projects/${projectId}`, {method: 'PUT', body: JSON.stringify({materials, expected_updated_at: document.getElementById('legacy-expected-updated-at').value})});
    markProjectModalClean('legacy-materials-modal');
    closeTrackedModal('legacy-materials-modal');
    await refreshMaterialsAfterWrite();
  } catch (failure) { error.textContent = failure.message; }
  finally { materialModalBusy('legacy-materials-modal', false); }
}

document.getElementById('materials-container')?.addEventListener('click', event => {
  const button = event.target.closest('[data-material-action]');
  if (!button) return;
  if (button.dataset.materialAction === 'retry') { loadMaterials(); return; }
  const card = button.closest('[data-entry-id]');
  const projectId = Number(card.dataset.projectId);
  const entry = materialsEntries.find(value => value.project_id === projectId && String(value.id) === card.dataset.entryId);
  if (!entry) return;
  if (button.dataset.materialAction === 'legacy') openLegacyMaterialsModal(projectId);
  if (button.dataset.materialAction === 'edit') openMaterialEditorModal(projectId, entry.id);
  if (button.dataset.materialAction === 'delete') deleteMaterialEntry(projectId, entry.id, entry.updated_at);
});
window.addEventListener('beforeunload', event => {
  if (['material-entry-modal', 'legacy-materials-modal'].some(id => {
    const modal = document.getElementById(id);
    return !modal.classList.contains('hidden') && modal.dataset.dirty === 'true';
  })) { event.preventDefault(); event.returnValue = ''; }
});
['material-entry-modal', 'legacy-materials-modal'].forEach(id => {
  document.getElementById(id)?.addEventListener('keydown', event => {
    if (event.key === 'Escape' && event.currentTarget.dataset.saving === 'true') {
      event.preventDefault(); event.stopPropagation();
    }
  });
});
