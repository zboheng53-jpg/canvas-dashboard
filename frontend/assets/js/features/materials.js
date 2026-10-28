/* Dashboard: features/materials.js; loaded in index.html order. */
let materialsProjects = [];
let materialsEntries = [];
let selectedMaterialsProjectId = null;
let materialEditorOpener = null;
let legacyMaterialsOpener = null;
let currentEditingMaterial = null;

function mEscape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

async function loadMaterials(projectId = null) {
  selectedMaterialsProjectId = projectId ? Number(projectId) : null;
  const container = document.getElementById('materials-container');
  if (container) container.setAttribute('aria-busy', 'true');
  const filterSelect = document.getElementById('materials-project-filter');
  if (filterSelect && selectedMaterialsProjectId) {
    filterSelect.value = String(selectedMaterialsProjectId);
  }

  try {
    const url = `/api/materials${selectedMaterialsProjectId ? `?project_id=${selectedMaterialsProjectId}` : ''}`;
    let resp = await fetch(url);
    if (!resp.ok) {
      // Fallback if backend /api/materials is not integrated yet: synthesize from /api/projects
      const projResp = await fetch('/api/projects');
      if (projResp.ok) {
        const projData = await projResp.json();
        const projects = projData.projects || [];
        const entries = [];
        projects.forEach((p) => {
          if (p.materials && p.materials.trim()) {
            entries.push({
              id: `legacy-${p.id}`,
              project_id: p.id,
              project_name: p.name,
              date: null,
              body: p.materials,
              legacy: true,
              created_at: p.created_at,
              updated_at: p.updated_at,
            });
          }
        });
        materialsProjects = projects;
        materialsEntries = entries;
        renderMaterials();
        return;
      }
      throw new Error(`加载资料失败: ${resp.status}`);
    }
    const data = await resp.json();
    materialsProjects = data.projects || [];
    materialsEntries = data.entries || [];
    renderMaterials();
  } catch (error) {
    console.error('Failed to load materials:', error);
    if (container) {
      container.innerHTML = `<div class="ui-empty ui-empty--danger"><p>加载项目资料失败：${mEscape(error.message)}</p></div>`;
    }
  } finally {
    if (container) container.setAttribute('aria-busy', 'false');
  }
}

function onMaterialsProjectFilterChange(value) {
  selectedMaterialsProjectId = value ? Number(value) : null;
  loadMaterials(selectedMaterialsProjectId);
}

function openProjectMaterials(projectId) {
  selectedMaterialsProjectId = Number(projectId);
  switchDashboardView('materials');
  loadMaterials(selectedMaterialsProjectId);
}
window.openProjectMaterials = openProjectMaterials;

function renderMaterials() {
  const container = document.getElementById('materials-container');
  if (!container) return;

  // Update project dropdown options
  const filterSelect = document.getElementById('materials-project-filter');
  if (filterSelect) {
    const currentVal = selectedMaterialsProjectId ? String(selectedMaterialsProjectId) : '';
    filterSelect.innerHTML = `<option value="">全部项目</option>` +
      materialsProjects.map(p => `<option value="${p.id}" ${String(p.id) === currentVal ? 'selected' : ''}>${mEscape(p.name)}</option>`).join('');
  }

  // Filter entries
  let entries = materialsEntries;
  if (selectedMaterialsProjectId) {
    entries = entries.filter(e => Number(e.project_id) === Number(selectedMaterialsProjectId));
  }

  if (!entries.length) {
    container.innerHTML = `
      <div class="ui-empty" style="padding: 48px 16px; text-align: center;">
        <strong>暂无资料记录</strong>
        <p style="margin-top: 8px; color: var(--color-text-secondary);">
          ${selectedMaterialsProjectId ? '该项目暂无记录，可点击上方“新建资料”添加。' : '还没有任何项目的资料记录，点击上方“新建资料”开始记录。'}
        </p>
      </div>`;
    return;
  }

  // Separate dated entries vs undated/legacy
  const datedMap = new Map();
  const undatedEntries = [];

  entries.forEach(entry => {
    const d = (entry.date || '').trim();
    if (d && /^\d{4}-\d{2}-\d{2}/.test(d)) {
      const dateKey = d.slice(0, 10);
      if (!datedMap.has(dateKey)) datedMap.set(dateKey, []);
      datedMap.get(dateKey).push(entry);
    } else {
      undatedEntries.push(entry);
    }
  });

  const sortedDates = [...datedMap.keys()].sort((a, b) => b.localeCompare(a));

  // If no dated entries, render directly in History style without a huge blank Latest area
  if (sortedDates.length === 0) {
    container.innerHTML = `
      <div class="materials-history-standalone">
        <div class="materials-history-heading">
          <h3>资料记录 (${undatedEntries.length})</h3>
        </div>
        <div class="materials-entries-list">
          ${undatedEntries.map(e => renderMaterialEntryCard(e)).join('')}
        </div>
      </div>`;
    return;
  }

  // With dated entries:
  // Latest date is OPEN
  const latestDate = sortedDates[0];
  const latestEntries = datedMap.get(latestDate);
  const olderDates = sortedDates.slice(1);
  const historyCount = olderDates.reduce((acc, dt) => acc + datedMap.get(dt).length, 0) + undatedEntries.length;

  let html = `
    <div class="materials-latest-section">
      <div class="materials-date-group-header">
        <span class="materials-latest-badge ui-tag ui-tag--primary">最新</span>
        <h3>${mEscape(latestDate)}</h3>
        <span class="muted" style="font-size: 13px;">${latestEntries.length} 条记录</span>
      </div>
      <div class="materials-entries-list">
        ${latestEntries.map(e => renderMaterialEntryCard(e)).join('')}
      </div>
    </div>`;

  if (historyCount > 0) {
    html += `
      <details class="materials-history ui-card ui-card--subtle" style="margin-top: 24px;" id="materials-history">
        <summary class="materials-history-summary" style="padding: 12px 16px; cursor: pointer; font-weight: 600; display: flex; align-items: center; justify-content: space-between;">
          <span>历史资料与未定日期 · ${historyCount} 条</span>
          <span class="muted" style="font-size: 12px; font-weight: normal;">展开查看历史 →</span>
        </summary>
        <div class="materials-history-body" style="padding: 16px;">
          ${olderDates.map(dt => `
            <div class="materials-date-group" style="margin-bottom: 20px;">
              <h4 style="font-size: 14px; margin-bottom: 8px; color: var(--color-text-secondary);">${mEscape(dt)}</h4>
              <div class="materials-entries-list">
                ${datedMap.get(dt).map(e => renderMaterialEntryCard(e)).join('')}
              </div>
            </div>
          `).join('')}
          ${undatedEntries.length ? `
            <div class="materials-date-group" style="margin-bottom: 16px;">
              <h4 style="font-size: 14px; margin-bottom: 8px; color: var(--color-text-secondary);">未定日期 / 历史原稿</h4>
              <div class="materials-entries-list">
                ${undatedEntries.map(e => renderMaterialEntryCard(e)).join('')}
              </div>
            </div>
          ` : ''}
        </div>
      </details>`;
  }

  container.innerHTML = html;
}

function renderMaterialEntryCard(entry) {
  const isLegacy = Boolean(entry.legacy);
  return `
    <article class="material-entry-card ui-card" data-entry-id="${mEscape(entry.id)}" style="margin-bottom: 12px; padding: 14px 16px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface);">
      <div class="material-entry-header" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
        <div class="material-entry-meta" style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
          <span class="ui-tag ui-tag--accent" style="font-weight: 500;">${mEscape(entry.project_name || '项目')}</span>
          ${entry.date ? `<span class="muted" style="font-size: 12px;">${mEscape(entry.date)}</span>` : '<span class="muted" style="font-size: 12px;">未定日期</span>'}
          ${isLegacy ? '<span class="ui-tag" style="font-size: 11px;">历史原稿</span>' : ''}
        </div>
        <div class="material-entry-actions" style="display: flex; gap: 6px;">
          ${isLegacy ? `
            <button type="button" class="ui-button ui-button--secondary ui-button--compact" onclick="openLegacyMaterialsModal(${entry.project_id})" style="font-size: 12px; padding: 3px 8px; height: 26px;">编辑原文</button>
          ` : `
            <button type="button" class="ui-button ui-button--secondary ui-button--compact" onclick="openMaterialEditorModal(${entry.project_id}, '${mEscape(entry.id)}')" style="font-size: 12px; padding: 3px 8px; height: 26px;">编辑</button>
            <button type="button" class="ui-button ui-button--danger ui-button--compact is-danger" onclick="deleteMaterialEntry(${entry.project_id}, '${mEscape(entry.id)}', '${mEscape(entry.updated_at || '')}')" style="font-size: 12px; padding: 3px 8px; height: 26px;">删除</button>
          `}
        </div>
      </div>
      <div class="material-entry-body" style="white-space: pre-wrap; font-family: inherit; font-size: 14px; line-height: 1.6; color: var(--color-text-primary);">${mEscape(entry.body || '')}</div>
    </article>`;
}

function openNewMaterialModal() {
  materialEditorOpener = document.activeElement;
  const modal = document.getElementById('material-entry-modal');
  const form = document.getElementById('material-entry-form');
  const title = document.getElementById('material-entry-title');
  const deleteBtn = document.getElementById('material-entry-delete-btn');
  const err = document.getElementById('material-entry-error');
  if (!modal || !form) return;

  currentEditingMaterial = null;
  form.reset();
  form.material_id.value = '';
  form.expected_updated_at.value = '';
  title.textContent = '新建资料记录';
  if (deleteBtn) deleteBtn.classList.add('hidden');
  if (err) { err.textContent = ''; err.style.display = 'none'; }

  // Populate projects select
  const select = document.getElementById('material-form-project');
  select.innerHTML = materialsProjects.map(p =>
    `<option value="${p.id}" ${selectedMaterialsProjectId && p.id === selectedMaterialsProjectId ? 'selected' : ''}>${mEscape(p.name)}</option>`
  ).join('');

  modal.classList.remove('hidden');
  setTimeout(() => form.querySelector('[name="body"]')?.focus(), 50);
}

function openMaterialEditorModal(projectId, entryId) {
  materialEditorOpener = document.activeElement;
  const modal = document.getElementById('material-entry-modal');
  const form = document.getElementById('material-entry-form');
  const title = document.getElementById('material-entry-title');
  const deleteBtn = document.getElementById('material-entry-delete-btn');
  const err = document.getElementById('material-entry-error');
  if (!modal || !form) return;

  const entry = materialsEntries.find(e => String(e.id) === String(entryId) && Number(e.project_id) === Number(projectId));
  if (!entry) return;

  currentEditingMaterial = entry;
  form.material_id.value = entry.id;
  form.expected_updated_at.value = entry.updated_at || '';
  form.date.value = entry.date || '';
  form.body.value = entry.body || '';
  title.textContent = '编辑资料记录';
  if (deleteBtn) deleteBtn.classList.remove('hidden');
  if (err) { err.textContent = ''; err.style.display = 'none'; }

  const select = document.getElementById('material-form-project');
  select.innerHTML = materialsProjects.map(p =>
    `<option value="${p.id}" ${p.id === Number(projectId) ? 'selected' : ''}>${mEscape(p.name)}</option>`
  ).join('');

  modal.classList.remove('hidden');
  setTimeout(() => form.querySelector('[name="body"]')?.focus(), 50);
}

function closeMaterialEntryModal() {
  const modal = document.getElementById('material-entry-modal');
  if (modal) modal.classList.add('hidden');
  if (materialEditorOpener?.isConnected) materialEditorOpener.focus();
}

async function handleMaterialEntrySubmit(event) {
  event.preventDefault();
  const form = event.target;
  const projectId = form.project_id.value;
  const materialId = form.material_id.value;
  const dateVal = form.date.value.trim() || null;
  const bodyVal = form.body.value.trim();
  const expectedUpdatedAt = form.expected_updated_at.value;
  const err = document.getElementById('material-entry-error');
  const saveBtn = document.getElementById('material-entry-save-btn');

  if (!bodyVal) {
    if (err) { err.textContent = '资料内容不能为空'; err.style.display = 'block'; }
    return;
  }

  saveBtn.disabled = true;
  if (err) { err.textContent = ''; err.style.display = 'none'; }

  try {
    const isEdit = Boolean(materialId);
    const url = isEdit
      ? `/api/projects/${projectId}/materials/${materialId}`
      : `/api/projects/${projectId}/materials`;
    const method = isEdit ? 'PUT' : 'POST';
    const payload = isEdit
      ? { date: dateVal, body: bodyVal, expected_updated_at: expectedUpdatedAt }
      : { date: dateVal, body: bodyVal, request_id: `mat-${Date.now()}` };

    const resp = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.CSRF_TOKEN || '',
      },
      body: JSON.stringify(payload),
    });

    const result = await resp.json().catch(() => ({}));
    if (!resp.ok || result.ok === false) {
      throw new Error(result.error || result.message || '保存资料失败');
    }

    closeMaterialEntryModal();
    await Promise.all([
      loadMaterials(selectedMaterialsProjectId),
      typeof loadProjectOverview === 'function' ? loadProjectOverview() : Promise.resolve(),
    ]);
  } catch (error) {
    // PRESERVE input on error/conflict
    if (err) {
      err.textContent = error.message;
      err.style.display = 'block';
    }
  } finally {
    saveBtn.disabled = false;
  }
}

async function deleteMaterialEntry(projectId, materialId, expectedUpdatedAt = '') {
  if (!confirm('确定要删除这条资料记录吗？此操作无法撤销。')) return;

  try {
    const url = `/api/projects/${projectId}/materials/${materialId}`;
    const resp = await fetch(url, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.CSRF_TOKEN || '',
      },
      body: JSON.stringify({ expected_updated_at: expectedUpdatedAt }),
    });
    const result = await resp.json().catch(() => ({}));
    if (!resp.ok || result.ok === false) {
      throw new Error(result.error || '删除资料失败');
    }
    await Promise.all([
      loadMaterials(selectedMaterialsProjectId),
      typeof loadProjectOverview === 'function' ? loadProjectOverview() : Promise.resolve(),
    ]);
  } catch (error) {
    alert(error.message);
  }
}

function handleDeleteCurrentMaterial() {
  if (!currentEditingMaterial) return;
  closeMaterialEntryModal();
  deleteMaterialEntry(
    currentEditingMaterial.project_id,
    currentEditingMaterial.id,
    currentEditingMaterial.updated_at
  );
}

function openLegacyMaterialsModal(projectId) {
  legacyMaterialsOpener = document.activeElement;
  const modal = document.getElementById('legacy-materials-modal');
  const form = document.getElementById('legacy-materials-form');
  const proj = materialsProjects.find(p => p.id === Number(projectId));
  if (!modal || !form) return;

  document.getElementById('legacy-project-id').value = String(projectId);
  document.getElementById('legacy-expected-updated-at').value = proj?.updated_at || '';
  document.getElementById('legacy-project-name').textContent = proj ? `所属项目：${proj.name}` : '';
  document.getElementById('legacy-materials-body').value = proj?.materials || '';

  const err = document.getElementById('legacy-materials-error');
  if (err) { err.textContent = ''; err.style.display = 'none'; }

  modal.classList.remove('hidden');
  setTimeout(() => document.getElementById('legacy-materials-body')?.focus(), 50);
}

function closeLegacyMaterialsModal() {
  const modal = document.getElementById('legacy-materials-modal');
  if (modal) modal.classList.add('hidden');
  if (legacyMaterialsOpener?.isConnected) legacyMaterialsOpener.focus();
}

async function handleLegacyMaterialsSubmit(event) {
  event.preventDefault();
  const form = event.target;
  const projectId = document.getElementById('legacy-project-id').value;
  const materials = document.getElementById('legacy-materials-body').value;
  const expectedUpdatedAt = document.getElementById('legacy-expected-updated-at').value;
  const err = document.getElementById('legacy-materials-error');
  const saveBtn = document.getElementById('legacy-materials-save-btn');

  saveBtn.disabled = true;
  if (err) { err.textContent = ''; err.style.display = 'none'; }

  try {
    const url = `/api/projects/${projectId}`;
    const resp = await fetch(url, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.CSRF_TOKEN || '',
      },
      body: JSON.stringify({
        materials,
        expected_updated_at: expectedUpdatedAt,
      }),
    });
    const result = await resp.json().catch(() => ({}));
    if (!resp.ok || result.ok === false) {
      throw new Error(result.error || result.message || '更新项目资料失败');
    }

    closeLegacyMaterialsModal();
    await Promise.all([
      loadMaterials(selectedMaterialsProjectId),
      typeof loadProjects === 'function' ? loadProjects(projectId) : Promise.resolve(),
      typeof loadProjectOverview === 'function' ? loadProjectOverview() : Promise.resolve(),
    ]);
  } catch (error) {
    if (err) {
      err.textContent = error.message;
      err.style.display = 'block';
    }
  } finally {
    saveBtn.disabled = false;
  }
}
