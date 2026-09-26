(function initializeTodoFeature() {
  const byId = (id) => document.getElementById(id);

  byId('add-todo-form')?.addEventListener('submit', addTodo);
  byId('new-todo-input')?.addEventListener('input', () => { if (typeof resetTodoRequestId === 'function') resetTodoRequestId(); });
  byId('new-todo-due')?.addEventListener('change', () => { if (typeof resetTodoRequestId === 'function') resetTodoRequestId(); });
  byId('new-todo-repeat')?.addEventListener('change', () => { if (typeof resetTodoRequestId === 'function') resetTodoRequestId(); });
  byId('btn-refresh')?.addEventListener('click', async () => {
    const btn = byId('btn-refresh');
    btn?.setAttribute('aria-busy', 'true');
    btn?.classList.add('is-refreshing');
    try {
      if (typeof fetchCanvasTodos === 'function') fetchCanvasTodos();
      if (typeof fetchHaokeTodos === 'function') fetchHaokeTodos();
      if (typeof fetchZhixuemengTodos === 'function') fetchZhixuemengTodos();
      if (typeof fetchZhihuishuTodos === 'function') fetchZhihuishuTodos();
      if (typeof fetchKetangpaiTodos === 'function') fetchKetangpaiTodos();
      if (typeof fetchTongjiojTodos === 'function') fetchTongjiojTodos();
      if (typeof refreshWorkspaceSurfaces === 'function') {
        await refreshWorkspaceSurfaces();
      } else {
        if (typeof fetchProjectTodos === 'function') await fetchProjectTodos();
        if (typeof fetchCustomTodos === 'function') await fetchCustomTodos();
        if (typeof loadTodaySchedule === 'function') await loadTodaySchedule();
      }
    } finally {
      btn?.removeAttribute('aria-busy');
      btn?.classList.remove('is-refreshing');
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
