/* Dashboard: features/integrations.js; loaded in index.html order. */
    // ---- Platform connection card status ----
    function setCardStatus(platform, text, cls) {
      const el = document.getElementById(`card-status-${platform}`);
      const semantic = cls === 'connected'
        ? 'success'
        : cls === 'attention' && /失败|错误|不可用/.test(text)
          ? 'danger'
          : cls === 'attention'
            ? 'warning'
            : 'info';
      if (el) {
        el.textContent = text;
        applyStatusSemantic(el, semantic);
      }
      const detailBadge = document.getElementById(`detail-status-badge-${platform}`);
      if (detailBadge) {
        detailBadge.textContent = text;
        applyStatusSemantic(detailBadge, semantic);
      }
      updateAttentionStatus();
    }

    function updateAttentionStatus() {
      const allAttentionElements = document.querySelectorAll('#login-cards .login-card-status.attention');
      const attentionElements = Array.from(allAttentionElements).filter(item => {
        const platform = item.id.replace('card-status-', '');
        return typeof visibleTodoSources !== 'undefined' ? visibleTodoSources.has(platform) : true;
      });
      const attentionCount = attentionElements.length;
      const attentionDot = document.getElementById('connections-attention');
      if (attentionDot) {
        attentionDot.classList.toggle('hidden', attentionCount === 0);
      }
      const mobileBadge = document.getElementById('mobile-connections-badge');
      if (mobileBadge) {
        mobileBadge.textContent = attentionCount;
        mobileBadge.classList.toggle('hidden', attentionCount === 0);
      }
      const mobileAttentionBanner = document.getElementById('mobile-attention-banner');
      const mobileAttentionText = document.getElementById('mobile-attention-text');
      if (mobileAttentionBanner) {
        if (attentionCount > 0) {
          const names = Array.from(attentionElements).map(item => {
            const card = item.closest('.login-card');
            return card ? card.querySelector('.login-card-title')?.textContent?.trim() : '';
          }).filter(Boolean);
          if (mobileAttentionText) {
            mobileAttentionText.textContent = `${attentionCount} 个平台需要处理配置${names.length ? ' (' + names.slice(0, 2).join('、') + ')' : ''}`;
          }
          mobileAttentionBanner.classList.remove('hidden');
        } else {
          mobileAttentionBanner.classList.add('hidden');
        }
      }
    }

    async function refreshPlatformConnections() {
      if (connectionsRefreshActive) return;
      connectionsRefreshActive = true;
      connectionsRequestsPending = true;
      workspaceRefreshFailed = false;
      renderDashboardSyncStatus();
      try {
        await Promise.all([
          fetchCanvasTodos(),
          fetchHaokeTodos(true),
          fetchZhixuemengTodos(),
          fetchZhihuishuTodos(),
          fetchKetangpaiTodos(),
          fetchTongjiojTodos('', true),
        ]);
      } catch (error) {
        workspaceRefreshFailed = true;
      } finally {
        connectionsRequestsPending = false;
        renderDashboardSyncStatus();
      }
    }

    async function doLogout() {
      try {
        await fetch('/api/auth/logout', { method: 'POST' });
      } catch (e) { /* ignore */ }
      window.location.href = '/login';
    }

    const platformSyncs = {};
    const platformRequests = {};
    let workspaceRefreshing = false;
    let workspaceRefreshFailed = false;
    let connectionsRefreshActive = false;
    let connectionsRequestsPending = false;
    const platformLabels = {canvas: 'Canvas', haoke: '好课', zhixuemeng: '智学盟', zhihuishu: '智慧树', ketangpai: '课堂派', tongjioj: '同济OJ'};
    function beginPlatformRequest(platform) {
      platformRequests[platform] = (platformRequests[platform] || 0) + 1;
      renderDashboardSyncStatus();
      return () => {
        platformRequests[platform]--;
        renderDashboardSyncStatus();
      };
    }
    function recordPlatformFailure(platform, message = '网络错误') {
      platformSyncs[platform] = {...platformSyncs[platform], refreshing: false,
        connection_state: platformSyncs[platform]?.connection_state || 'connected',
        error_code: 'sync_failed', error_message: message};
      renderDashboardSyncStatus();
    }
    function recordPlatformSync(platform, result) {
      if (!result?.sync) {
        if (!result?.ok && !result?.need_setup) recordPlatformFailure(platform, result?.error || '更新失败');
        return;
      }
      const sync = {...result.sync};
      if (platform === 'tongjioj') sync.has_cache = !!result.has_cache;
      if (result.stale) sync.data_state = 'stale';
      else if (result.cached && sync.data_state === 'fresh') sync.data_state = 'cached';
      platformSyncs[platform] = sync;
      renderDashboardSyncStatus();
    }
    function syncPriority(sync) {
      if (sync.refreshing) return 99;
      if (sync.connection_state === 'needs_reauth') return 1;
      if (sync.error_code || sync.error_message) return 2;
      return 99;
    }
    function isPlatformConfigured(platform) {
      const sync = platformSyncs[platform];
      if (!sync) return true;
      return sync.connection_state !== 'unconfigured';
    }
    window.isPlatformConfigured = isPlatformConfigured;
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') return;
      if (platformSyncs.canvas?.refreshing) fetchCanvasTodos(false, true);
      if (platformSyncs.haoke?.refreshing) fetchHaokeTodos(false, true);
      if (platformSyncs.tongjioj?.refreshing) fetchTongjiojTodos();
    });

    function renderDashboardSyncStatus() {
      const refreshing = workspaceRefreshing || connectionsRequestsPending || Object.values(platformRequests).some(count => count > 0)
        || Object.values(platformSyncs).some(sync => sync.refreshing);
      const refreshButton = document.getElementById('btn-refresh');
      refreshButton?.classList.toggle('is-refreshing', refreshing);
      if (refreshing) refreshButton?.setAttribute('aria-busy', 'true');
      else refreshButton?.removeAttribute('aria-busy');
      const button = document.getElementById('list-updated');
      if (!button) return;
      const entries = Object.entries(platformSyncs).filter(([platform]) => {
        return typeof visibleTodoSources !== 'undefined' ? visibleTodoSources.has(platform) : true;
      });
      const active = entries.filter(([, sync]) => sync.connection_state !== 'unconfigured');
      const issues = active.filter(([platform, sync]) => !platformRequests[platform] && syncPriority(sync) < 99).sort((a, b) => {
        const priority = syncPriority(a[1]) - syncPriority(b[1]);
        return priority || String(a[1].last_success_at || '').localeCompare(String(b[1].last_success_at || ''));
      });
      const connections = issues.filter(([, sync]) => sync.connection_state === 'needs_reauth').length;
      const unsynced = issues.length - connections + Number(workspaceRefreshFailed);
      const text = refreshing ? '' : [connections ? `${connections} 处连接失败` : '', unsynced ? `${unsynced} 处未同步` : ''].filter(Boolean).join('，');
      button.textContent = text;
      button.classList.toggle('hidden', !text);
      button.setAttribute('aria-label', `${text}；打开连接与同步`);
      button.dataset.syncTarget = issues[0]?.[0] || active.find(([, sync]) => sync.connection_state === 'connected')?.[0] || '';
      if (connectionsRefreshActive) {
        const connectionButton = document.getElementById('connections-refresh-button');
        if (connectionButton) {
          connectionButton.disabled = refreshing;
          connectionButton.setAttribute('aria-busy', String(refreshing));
          connectionButton.textContent = refreshing ? '正在刷新…' : '刷新全部状态';
        }
        document.getElementById('connections-detail-panel')?.setAttribute('aria-busy', String(refreshing));
        const status = document.getElementById('connections-manager-status');
        if (status) {
          status.textContent = text;
          applyFeedbackSemantic(status, text ? 'warning' : 'info');
        }
        if (!refreshing) connectionsRefreshActive = false;
      }
    }
    function openSyncStatus() {
      const target = document.getElementById('list-updated').dataset.syncTarget;
      switchDashboardView('connections');
      if (target && typeof selectConnectionPlatform === 'function') selectConnectionPlatform(target);
    }

    let canvasPollTimer = null;
    let canvasLoadVersion = 0;
    async function fetchCanvasTodos(force = false, cacheOnly = false) {
      if (cacheOnly && document.visibilityState === 'hidden') return;
      const version = ++canvasLoadVersion;
      clearTimeout(canvasPollTimer);
      const finish = beginPlatformRequest('canvas');
      try {
        const params = new URLSearchParams();
        if (force) params.set('refresh', '1');
        if (cacheOnly) params.set('cache_only', '1');
        const resp = await fetch(`/api/canvas/todos${params.size ? '?' + params : ''}`);
        const result = await resp.json();
        if (version !== canvasLoadVersion) return;
        recordPlatformSync('canvas', result);
        if (result.sync?.refreshing) {
          canvasPollTimer = setTimeout(() => fetchCanvasTodos(false, true), 2000);
        }

        if (result.need_setup && result.sync?.connection_state !== 'disconnected') {
          setCardStatus('canvas', '未关联', 'attention');
          canvasItems = [];
          hiddenIds = [];
          highlightedIds = [];
          renderUnifiedList();
          return;
        }

        if (!result.ok) {
          setCardStatus('canvas', result.error || '获取失败', 'attention');
        } else if (result.sync?.refreshing) {
          setCardStatus('canvas', '同步中…', 'connected');
        } else {
          setCardStatus('canvas', '已连接', 'connected');
        }

        if (result.data && (result.data.length > 0 || !result.sync?.refreshing || !canvasItems.length)) {
          canvasItems = result.data || [];
          canvasItems.forEach(item => {
            if (item.subtasks) {
              item.subtasks.forEach((subtask, idx) => {
                if (subtask.id == null) subtask.id = idx + 1;
              });
              item.subtasks = sortSubtasks(item.subtasks);
            }
          });
          hiddenIds = result.hidden || [];
          highlightedIds = result.highlighted || [];
          canvasDeletedIds = result.deleted || [];
        }
        renderUnifiedList();
      } catch (e) {
        if (version !== canvasLoadVersion) return;
        setCardStatus('canvas', '网络错误', 'attention');
        recordPlatformFailure('canvas');
      } finally {
        finish();
      }
    }


    // ---- Haoke Todos ----
    let haokePollTimer = null;
    let haokeLoadVersion = 0;
    async function fetchHaokeTodos(force = false, cacheOnly = false) {
      if (cacheOnly && document.visibilityState === 'hidden') return;
      const version = ++haokeLoadVersion;
      clearTimeout(haokePollTimer);
      const finish = beginPlatformRequest('haoke');
      try {
        const params = new URLSearchParams();
        if (force) params.set('refresh', '1');
        if (cacheOnly) params.set('cache_only', '1');
        const resp = await fetch(`/api/haoke/todos${params.size ? '?' + params : ''}`);
        const result = await resp.json();
        if (version !== haokeLoadVersion) return;
        recordPlatformSync('haoke', result);
        if (result.sync?.refreshing) haokePollTimer = setTimeout(() => fetchHaokeTodos(false, true), 2000);

        if (result.need_setup && result.sync?.connection_state !== 'disconnected') {
          setCardStatus('haoke', '未关联', 'attention');
          haokeItems = [];
          haokeHiddenIds = [];
          haokeHighlightedIds = [];
          renderUnifiedList();
          return;
        }

        if (!result.ok) {
          setCardStatus('haoke', result.error || '\u83b7\u53d6\u5931\u8d25', 'attention');
        } else {
          setCardStatus('haoke', '已连接', 'connected');
        }

        haokeItems = result.data || [];
        haokeItems.forEach(item => {
          if (item.subtasks) {
            item.subtasks.forEach((subtask, idx) => {
              if (subtask.id == null) subtask.id = idx + 1;
            });
            item.subtasks = sortSubtasks(item.subtasks);
          }
        });
        haokeHiddenIds = result.hidden || [];
        haokeHighlightedIds = result.highlighted || [];
        haokeDeletedIds = result.deleted || [];
        renderUnifiedList();
      } catch (e) {
        if (version !== haokeLoadVersion) return;
        setCardStatus('haoke', '\u7f51\u7edc\u9519\u8bef', 'attention');
        recordPlatformFailure('haoke');
      } finally {
        finish();
      }
    }

    async function toggleHaokeHighlight(itemId, current) {
      const rawId = parseInt(itemId.substring(1));
      const action = current ? 'unhighlight' : 'highlight';
      await fetch('/api/haoke/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: rawId }),
      });
      if (current) {
        haokeHighlightedIds = haokeHighlightedIds.filter(id => id !== rawId);
      } else {
        haokeHighlightedIds.push(rawId);
      }
      renderUnifiedList();
    }

    async function toggleHaokeHide(itemId, current) {
      const rawId = parseInt(itemId.substring(1));
      const action = current ? 'unhide' : 'hide';
      await fetch('/api/haoke/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: rawId }),
      });
      if (current) {
        haokeHiddenIds = haokeHiddenIds.filter(id => id !== rawId);
      } else {
        haokeHiddenIds.push(rawId);
      }
      renderUnifiedList();
    }

    // ---- Zhixuemeng Todos ----
    async function fetchZhixuemengTodos() {
      const finish = beginPlatformRequest('zhixuemeng');
      try {
        const resp = await fetch('/api/zhixuemeng/todos');
        const result = await resp.json();
        recordPlatformSync('zhixuemeng', result);

        if (result.need_setup && result.sync?.connection_state !== 'disconnected') {
          setCardStatus('zhixuemeng', '未关联', 'attention');
          zhixuemengItems = [];
          zhixuemengHiddenIds = [];
          zhixuemengHighlightedIds = [];
          renderUnifiedList();
          return;
        }

        if (!result.ok) {
          setCardStatus('zhixuemeng', result.error || '\u83b7\u53d6\u5931\u8d25', 'attention');
        } else {
          setCardStatus('zhixuemeng', '已连接', 'connected');
        }

        zhixuemengItems = result.data || [];
        zhixuemengItems.forEach(item => {
          if (item.subtasks) {
            item.subtasks.forEach((subtask, idx) => {
              if (subtask.id == null) subtask.id = idx + 1;
            });
            item.subtasks = sortSubtasks(item.subtasks);
          }
        });
        zhixuemengHiddenIds = result.hidden || [];
        zhixuemengHighlightedIds = result.highlighted || [];
        zhixuemengDeletedIds = result.deleted || [];
        renderUnifiedList();
      } catch (e) {
        setCardStatus('zhixuemeng', '\u7f51\u7edc\u9519\u8bef', 'attention');
        recordPlatformFailure('zhixuemeng');
      } finally {
        finish();
      }
    }

    async function toggleZhixuemengHide(itemId, current) {
      const action = current ? 'unhide' : 'hide';
      await fetch('/api/zhixuemeng/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: itemId }),
      });
      if (current) {
        zhixuemengHiddenIds = zhixuemengHiddenIds.filter(id => id !== itemId);
      } else {
        zhixuemengHiddenIds.push(itemId);
      }
      renderUnifiedList();
    }

    async function toggleZhixuemengHighlight(itemId, current) {
      const action = current ? 'unhighlight' : 'highlight';
      await fetch('/api/zhixuemeng/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: itemId }),
      });
      if (current) {
        zhixuemengHighlightedIds = zhixuemengHighlightedIds.filter(id => id !== itemId);
      } else {
        zhixuemengHighlightedIds.push(itemId);
      }
      renderUnifiedList();
    }

    // ---- Ketangpai Todos ----
    async function fetchKetangpaiTodos(courseId = '') {
      const finish = beginPlatformRequest('ketangpai');
      try {
        const url = courseId ? `/api/ketangpai/todos?course_id=${encodeURIComponent(courseId)}` : '/api/ketangpai/todos';
        const resp = await fetch(url);
        const result = await resp.json();
        recordPlatformSync('ketangpai', result);

        if (result.need_setup && result.sync?.connection_state !== 'disconnected') {
          setCardStatus('ketangpai', '未关联', 'attention');
          ketangpaiItems = [];
          ketangpaiHiddenIds = [];
          ketangpaiHighlightedIds = [];
          renderUnifiedList();
          return;
        }

        if (!result.ok) {
          setCardStatus('ketangpai', result.error || '获取失败', 'attention');
        } else {
          setCardStatus('ketangpai', '已连接', 'connected');
        }

        ketangpaiItems = result.data || [];
        ketangpaiItems.forEach(item => {
          if (item.subtasks) {
            item.subtasks.forEach((subtask, idx) => {
              if (subtask.id == null) subtask.id = idx + 1;
            });
            item.subtasks = sortSubtasks(item.subtasks);
          }
        });
        ketangpaiHiddenIds = result.hidden || [];
        ketangpaiHighlightedIds = result.highlighted || [];
        ketangpaiDeletedIds = result.deleted || [];
        renderUnifiedList();
      } catch (e) {
        setCardStatus('ketangpai', '网络错误', 'attention');
        recordPlatformFailure('ketangpai');
      } finally {
        finish();
      }
    }

    async function toggleKetangpaiHide(itemId, current) {
      const action = current ? 'unhide' : 'hide';
      await fetch('/api/ketangpai/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: itemId }),
      });
      if (current) {
        ketangpaiHiddenIds = ketangpaiHiddenIds.filter(id => id !== itemId);
      } else {
        ketangpaiHiddenIds.push(itemId);
      }
      renderUnifiedList();
    }

    async function toggleKetangpaiHighlight(itemId, current) {
      const action = current ? 'unhighlight' : 'highlight';
      await fetch('/api/ketangpai/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: itemId }),
      });
      if (current) {
        ketangpaiHighlightedIds = ketangpaiHighlightedIds.filter(id => id !== itemId);
      } else {
        ketangpaiHighlightedIds.push(itemId);
      }
      renderUnifiedList();
    }

    // ---- Tongji OJ Todos ----
    let tongjiojPending = null;
    let tongjiojLoadVersion = 0;
    let tongjiojPollTimer = null;
    function fetchTongjiojTodos(courseId = '', force = false) {
      // Coalesce refresh clicks; a response for an older course must not replace the new selection.
      if (tongjiojPending?.courseId === courseId) {
        tongjiojPending.force ||= force;
        return tongjiojPending.promise;
      }
      const version = ++tongjiojLoadVersion;
      clearTimeout(tongjiojPollTimer);
      const finish = beginPlatformRequest('tongjioj');
      const promise = loadTongjiojTodos(courseId, force, version).finally(() => {
        if (tongjiojPending?.promise === promise) tongjiojPending = null;
        finish();
      });
      tongjiojPending = {courseId, promise, force};
      return promise;
    }

    async function loadTongjiojTodos(courseId, force, version) {
      try {
        const params = new URLSearchParams();
        if (courseId) params.set('course_id', courseId);
        params.set('cache_only', '1');
        const cached = await (await fetch(`/api/tongjioj/todos?${params}`)).json();
        if (version !== tongjiojLoadVersion) return;
        const refresh = !cached.need_setup && cached.ok && (force || tongjiojPending?.force || cached.stale);
        if (cached.sync) cached.sync.refreshing ||= !!refresh;
        applyTongjiojTodos(cached);
        if (!refresh) {
          scheduleTongjiojPoll(courseId, version, cached);
          return;
        }

        params.delete('cache_only');
        params.set('refresh', '1');
        const result = await (await fetch(`/api/tongjioj/todos?${params}`)).json();
        if (version !== tongjiojLoadVersion) return;
        applyTongjiojTodos(result);
        scheduleTongjiojPoll(courseId, version, result);
      } catch (e) {
        if (version !== tongjiojLoadVersion) return;
        setCardStatus('tongjioj', '网络错误', 'attention');
        recordPlatformFailure('tongjioj');
      }
    }

    function scheduleTongjiojPoll(courseId, version, result) {
      if (!result.sync?.refreshing || version !== tongjiojLoadVersion) return;
      clearTimeout(tongjiojPollTimer);
      tongjiojPollTimer = setTimeout(async () => {
        if (document.visibilityState === 'hidden') return;
        if (version !== tongjiojLoadVersion) return;
        try {
          const params = new URLSearchParams({cache_only: '1'});
          if (courseId) params.set('course_id', courseId);
          const next = await (await fetch(`/api/tongjioj/todos?${params}`)).json();
          if (version !== tongjiojLoadVersion) return;
          applyTongjiojTodos(next);
          scheduleTongjiojPoll(courseId, version, next);
        } catch (_) {
          if (version !== tongjiojLoadVersion) return;
          recordPlatformFailure('tongjioj');
        }
      }, 2000);
    }

    function applyTongjiojTodos(result) {
        // HTTP errors can omit sync/state metadata; keep the already rendered projection.
        if (!result.sync) {
          result.has_cache = platformSyncs.tongjioj?.has_cache || false;
          result.sync = {...platformSyncs.tongjioj, refreshing: false,
            connection_state: platformSyncs.tongjioj?.connection_state || 'connected',
            error_code: 'sync_failed', error_message: result.error || '获取失败'};
        }
        recordPlatformSync('tongjioj', result);

        if (result.need_setup && result.sync?.connection_state !== 'disconnected') {
          setCardStatus('tongjioj', '未关联', 'attention');
          tongjiojItems = [];
          tongjiojHiddenIds = [];
          tongjiojHighlightedIds = [];
          renderUnifiedList();
          return;
        }

        if (!result.ok || result.error || (!result.sync.refreshing && result.sync.error_message)) {
          setCardStatus('tongjioj', result.error || result.sync.error_message || '获取失败', 'attention');
        } else if (result.sync?.refreshing) {
          setCardStatus('tongjioj', '已连接', 'connected');
        } else {
          setCardStatus('tongjioj', '已连接', 'connected');
        }

        if (result.ok) tongjiojItems = result.data || [];
        tongjiojItems.forEach(item => {
          if (item.subtasks) {
            item.subtasks.forEach((subtask, idx) => {
              if (subtask.id == null) subtask.id = idx + 1;
            });
            item.subtasks = sortSubtasks(item.subtasks);
          }
        });
        if (result.ok) {
          tongjiojHiddenIds = result.hidden || [];
          tongjiojHighlightedIds = result.highlighted || [];
          tongjiojDeletedIds = result.deleted || [];
        }
        if (result.has_cache && Array.isArray(result.courses)) {
          const select = document.getElementById('tjoj-course-select-inline');
          const selected = result.selected_course ?? select?.value ?? '';
          if (select) populateTongjiojCourseSelectInline(select, result.courses, selected);
        }
        renderUnifiedList();
    }

    async function toggleTongjiojHide(itemId, current) {
      const action = current ? 'unhide' : 'hide';
      await fetch('/api/tongjioj/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: itemId }),
      });
      if (current) {
        tongjiojHiddenIds = tongjiojHiddenIds.filter(id => id !== itemId);
      } else {
        tongjiojHiddenIds.push(itemId);
      }
      renderUnifiedList();
    }

    async function toggleTongjiojHighlight(itemId, current) {
      const action = current ? 'unhighlight' : 'highlight';
      await fetch('/api/tongjioj/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: itemId }),
      });
      if (current) {
        tongjiojHighlightedIds = tongjiojHighlightedIds.filter(id => id !== itemId);
      } else {
        tongjiojHighlightedIds.push(itemId);
      }
      renderUnifiedList();
    }

    // ---- Zhihuishu Todos ----
    async function fetchZhihuishuTodos() {
      const finish = beginPlatformRequest('zhihuishu');
      try {
        const resp = await fetch('/api/zhihuishu/todos');
        const result = await resp.json();
        recordPlatformSync('zhihuishu', result);

        if (result.need_setup && result.sync?.connection_state !== 'disconnected') {
          setCardStatus('zhihuishu', result.data && result.data.length ? '需要重新登录' : '未关联', 'attention');
        } else if (!result.ok) {
          setCardStatus('zhihuishu', result.error || '\u83b7\u53d6\u5931\u8d25', 'attention');
        } else if (result.stale) {
          setCardStatus('zhihuishu', '\u7f13\u5b58\u8fc7\u671f', 'attention');
        } else {
          setCardStatus('zhihuishu', '已连接', 'connected');
        }

        zhihuishuItems = result.data || [];
        zhihuishuItems.forEach(item => {
          if (item.subtasks) {
            item.subtasks.forEach((subtask, idx) => {
              if (subtask.id == null) subtask.id = idx + 1;
            });
            item.subtasks = sortSubtasks(item.subtasks);
          }
        });
        zhihuishuHiddenIds = result.hidden || [];
        zhihuishuHighlightedIds = result.highlighted || [];
        zhihuishuDeletedIds = result.deleted || [];
        renderUnifiedList();
      } catch (e) {
        setCardStatus('zhihuishu', '\u7f51\u7edc\u9519\u8bef', 'attention');
        recordPlatformFailure('zhihuishu');
      } finally {
        finish();
      }
    }

    async function toggleZhihuishuHide(itemId, current) {
      const action = current ? 'unhide' : 'hide';
      const resp = await fetch('/api/zhihuishu/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: itemId }),
      });
      if (!resp.ok) return;
      if (current) {
        zhihuishuHiddenIds = zhihuishuHiddenIds.filter(id => id !== itemId);
      } else {
        zhihuishuHiddenIds.push(itemId);
      }
      renderUnifiedList();
    }

    async function toggleZhihuishuHighlight(itemId, current) {
      const action = current ? 'unhighlight' : 'highlight';
      const resp = await fetch('/api/zhihuishu/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, id: itemId }),
      });
      if (!resp.ok) return;
      if (current) {
        zhihuishuHighlightedIds = zhihuishuHighlightedIds.filter(id => id !== itemId);
      } else {
        zhihuishuHighlightedIds.push(itemId);
      }
      renderUnifiedList();
    }

    // ---- Connections Master-Detail Controllers ----
    let activeConnectionPlatform = 'canvas';

    async function selectConnectionPlatform(platform) {
      activeConnectionPlatform = platform;
      
      // Update selected class in platform list
      document.querySelectorAll('#login-cards .connection-platform-item').forEach(card => {
        const selected = card.dataset.platform === platform;
        card.classList.toggle('is-selected', selected);
        card.setAttribute('aria-pressed', String(selected));
      });

      // Update right details panels visibility
      document.querySelectorAll('.connection-detail-section').forEach(section => {
        section.classList.toggle('hidden', section.id !== `detail-${platform}`);
      });

      // Load status/data for this platform
      if (platform === 'canvas') await loadCanvasStatusInline();
      if (platform === 'haoke') await loadHaokeStatusInline();
      if (platform === 'zhixuemeng') await loadZhixuemengStatusInline();
      if (platform === 'zhihuishu') await loadZhihuishuStatusInline();
      if (platform === 'ketangpai') await loadKetangpaiStatusInline();
      if (platform === 'tongjioj') await loadTongjiojStatusInline();
    }

    // --- Canvas Detail Panel ---
    async function loadCanvasStatusInline() {
      const badge = document.getElementById('detail-status-badge-canvas');
      try {
        const resp = await fetch('/api/config');
        const result = await resp.json();
        badge.textContent = result.has_feed ? '已连接' : '未配置';
        applyStatusSemantic(badge, result.has_feed ? 'success' : 'warning');
      } catch (e) {
        badge.textContent = '状态获取失败';
        applyStatusSemantic(badge, 'danger');
      }
    }

    async function saveCanvasFeedUrlInline(e) {
      e.preventDefault();
      const input = document.getElementById('feed-url-input-inline');
      const url = input.value.trim();
      if (!url) return;

      const btn = document.querySelector('#canvas-setup-form-inline button');
      const err = document.getElementById('canvas-error-inline');
      btn.textContent = '...';
      btn.disabled = true;
      err.classList.add('hidden');

      try {
        const resp = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ calendar_feed_url: url }),
        });
        const result = await resp.json();
        if (result.ok) {
          input.value = '';
          await loadCanvasStatusInline();
          await fetchCanvasTodos();
        } else {
          err.textContent = result.error || '保存失败';
          err.classList.remove('hidden');
        }
      } catch (e) {
        err.textContent = '网络错误';
        err.classList.remove('hidden');
      } finally {
        btn.textContent = '保存';
        btn.disabled = false;
      }
    }

    // --- 好课 Detail Panel ---
    async function loadHaokeStatusInline() {
      const badge = document.getElementById('detail-status-badge-haoke');
      try {
        const resp = await fetch('/api/haoke/config');
        const result = await resp.json();
        badge.textContent = result.has_credentials ? '已连接' : '未配置';
        applyStatusSemantic(badge, result.has_credentials ? 'success' : 'warning');
      } catch (e) {
        badge.textContent = '状态获取失败';
        applyStatusSemantic(badge, 'danger');
      }
    }

    async function saveHaokeCredentialsInline(e) {
      e.preventDefault();
      const username = document.getElementById('haoke-username-inline').value.trim();
      const password = document.getElementById('haoke-password-inline').value.trim();
      if (!username || !password) return;

      const btn = document.querySelector('#haoke-setup-form-inline button');
      const err = document.getElementById('haoke-error-inline');
      btn.textContent = '...';
      btn.disabled = true;
      err.classList.add('hidden');

      try {
        const resp = await fetch('/api/haoke/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        });
        const result = await resp.json();
        if (result.ok) {
          document.getElementById('haoke-username-inline').value = '';
          document.getElementById('haoke-password-inline').value = '';
          await loadHaokeStatusInline();
          await fetchHaokeTodos();
        } else {
          err.textContent = result.error || '保存失败';
          err.classList.remove('hidden');
        }
      } catch (e) {
        err.textContent = '网络错误';
        err.classList.remove('hidden');
      } finally {
        btn.textContent = '保存并登录';
        btn.disabled = false;
      }
    }

    // --- 智学盟 Detail Panel ---
    async function loadZhixuemengStatusInline() {
      const badge = document.getElementById('detail-status-badge-zhixuemeng');
      const setupDiv = document.getElementById('zxm-setup-inline');
      const loggedInDiv = document.getElementById('zxm-logged-in-inline');
      try {
        const resp = await fetch('/api/zhixuemeng/config');
        const result = await resp.json();
        if (result.ok && result.has_token) {
          badge.textContent = '已登录';
          applyStatusSemantic(badge, 'success');
          setupDiv.classList.add('hidden');
          loggedInDiv.classList.remove('hidden');
          if (result.courses) {
            const select = document.getElementById('zxm-course-select-inline');
            populateZhixuemengCourseSelect(select, result.courses, result.selected_course);
          }
        } else {
          badge.textContent = '未登录';
          applyStatusSemantic(badge, 'warning');
          setupDiv.classList.remove('hidden');
          loggedInDiv.classList.add('hidden');
        }
      } catch (e) {
        badge.textContent = '状态获取失败';
        applyStatusSemantic(badge, 'danger');
        setupDiv.classList.remove('hidden');
        loggedInDiv.classList.add('hidden');
      }
    }

    let zxmSmsCountdownInline = 0;
    let zxmSmsTimerInline = null;

    async function sendZhixuemengSmsInline() {
      if (zxmSmsCountdownInline > 0) return;
      const phone = document.getElementById('zxm-phone-inline').value.trim();
      if (!phone) { alert('请输入手机号'); return; }

      const btn = document.getElementById('zxm-send-sms-btn-inline');
      btn.disabled = true;

      try {
        const resp = await fetch('/api/zhixuemeng/send-sms', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phone }),
        });
        const result = await resp.json();
        if (result.ok) {
          zxmSmsCountdownInline = 60;
          if (zxmSmsTimerInline) clearInterval(zxmSmsTimerInline);
          zxmSmsTimerInline = setInterval(() => {
            zxmSmsCountdownInline--;
            if (zxmSmsCountdownInline <= 0) {
              clearInterval(zxmSmsTimerInline);
              zxmSmsTimerInline = null;
              btn.textContent = '发送验证码';
              btn.disabled = false;
            } else {
              btn.textContent = `${zxmSmsCountdownInline}秒后发送`;
            }
          }, 1000);
          btn.textContent = `${zxmSmsCountdownInline}秒后发送`;
        } else {
          alert(result.error || '发送失败');
          btn.disabled = false;
        }
      } catch (e) {
        alert('网络错误');
        btn.disabled = false;
      }
    }

    async function doZhixuemengLoginInline() {
      const phone = document.getElementById('zxm-phone-inline').value.trim();
      const captcha = document.getElementById('zxm-captcha-inline').value.trim();
      if (!phone || !captcha) { alert('请输入手机号和验证码'); return; }

      try {
        const resp = await fetch('/api/zhixuemeng/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phone, captcha }),
        });
        const result = await resp.json();
        if (result.ok) {
          document.getElementById('zxm-captcha-inline').value = '';
          if (zxmSmsTimerInline) { clearInterval(zxmSmsTimerInline); zxmSmsTimerInline = null; zxmSmsCountdownInline = 0; }
          document.getElementById('zxm-send-sms-btn-inline').textContent = '发送验证码';
          document.getElementById('zxm-send-sms-btn-inline').disabled = false;
          await loadZhixuemengStatusInline();
          await fetchZhixuemengTodos();
        } else {
          alert(result.error || '登录失败');
        }
      } catch (e) {
        alert('网络错误');
      }
    }

    function showZxmPasswordLoginInline() {
      document.getElementById('zxm-password-login-inline').classList.toggle('hidden');
    }

    async function doZhixuemengPasswordLoginInline(e) {
      e.preventDefault();
      const username = document.getElementById('zxm-username-inline').value.trim();
      const password = document.getElementById('zxm-password-inline').value.trim();
      if (!username || !password) return;

      try {
        const resp = await fetch('/api/zhixuemeng/login-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: username, password: password }),
        });
        const result = await resp.json();
        if (result.ok) {
          await loadZhixuemengStatusInline();
          await fetchZhixuemengTodos();
        } else {
          alert(result.error || '登录失败');
        }
      } catch (e) {
        alert('网络错误');
      }
    }

    async function changeZhixuemengCourseInline() {
      const select = document.getElementById('zxm-course-select-inline');
      const courseCode = select.value;
      try {
        await fetch('/api/zhixuemeng/course', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ course_code: courseCode }),
        });
        await fetchZhixuemengTodos();
      } catch (e) { /* ignore */ }
    }

    async function logoutZhixuemengInline() {
      try {
        await fetch('/api/zhixuemeng/logout', { method: 'POST' });
      } catch (e) { /* ignore */ }
      document.getElementById('zxm-password-login-inline').classList.add('hidden');
      document.getElementById('zhixuemeng-error-inline').classList.add('hidden');
      await loadZhixuemengStatusInline();
      await fetchZhixuemengTodos();
    }

    // --- 智慧树 Detail Panel ---
    let zhsCurrentLoginTokenInline = null;
    let zhsCurrentLoginWindowInline = null;
    let zhsHasActiveLoginSessionInline = false;

    function formatZhsTime(value) {
      if (!value) return '--';
      if (typeof value === 'number') return new Date(value * 1000).toLocaleString();
      return value;
    }

    function setZhsMessageInline(text, cls) {
      const el = document.getElementById('zhs-login-session-message-inline');
      el.textContent = text || '';
      const semantic = cls === 'connected' ? 'success' : cls === 'attention' ? 'warning' : cls || 'info';
      applyFeedbackSemantic(el, semantic);
      el.classList.remove('attention', 'connected');
      if (cls === 'connected' || cls === 'attention') el.classList.add(cls);
    }

    function setZhsSessionButtonsInline(active) {
      document.getElementById('zhs-btn-open-login-inline').disabled = active;
      document.getElementById('zhs-btn-complete-login-inline').disabled = !active;
      document.getElementById('zhs-btn-cancel-login-inline').disabled = !active && !zhsHasActiveLoginSessionInline;
    }

    async function loadZhihuishuStatusInline() {
      const badge = document.getElementById('detail-status-badge-zhihuishu');
      try {
        const resp = await fetch('/api/zhihuishu/config');
        const data = await resp.json();
        const status = data.status || {};
        const loginSession = data.login_session || {};
        zhsHasActiveLoginSessionInline = Boolean(loginSession.active);

        // Update status badge
        badge.textContent = status.session || '--';
        applyStatusSemantic(badge, status.session === 'active' ? 'success' : 'warning');

        document.getElementById('zhs-session-inline').textContent = status.session || '--';
        document.getElementById('zhs-worker-inline').textContent = status.worker || '--';
        document.getElementById('zhs-last-keepalive-inline').textContent = formatZhsTime(status.last_keepalive_at);
        document.getElementById('zhs-last-fetch-inline').textContent = formatZhsTime(status.last_fetch_at);
        document.getElementById('zhs-last-success-inline').textContent = formatZhsTime(status.last_success_at);
        document.getElementById('zhs-last-error-inline').textContent = status.last_error || '--';
        
        setZhsSessionButtonsInline(Boolean(zhsCurrentLoginTokenInline));
        if (zhsHasActiveLoginSessionInline && !zhsCurrentLoginTokenInline) {
          setZhsMessageInline(`已有一个登录会话正在进行，将于 ${formatZhsTime(loginSession.expires_at)} 过期。可以取消后重新打开。`, 'attention');
        }
      } catch (e) {
        badge.textContent = '获取失败';
        applyStatusSemantic(badge, 'danger');
      }
    }

    async function openZhihuishuLoginSessionInline() {
      setZhsMessageInline('正在打开登录窗口...');
      try {
        const resp = await fetch('/api/zhihuishu/login-session', { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok || !data.ok) throw new Error(data.error || '启动失败');
        zhsCurrentLoginTokenInline = data.token;
        zhsCurrentLoginWindowInline = window.open(data.url, '_blank', 'noopener,noreferrer,width=1280,height=900');
        setZhsSessionButtonsInline(true);
        setZhsMessageInline('登录窗口已打开。完成智慧树登录后回到这里确认。', 'connected');
      } catch (e) {
        setZhsMessageInline(e.message || '登录窗口启动失败', 'danger');
      }
    }

    async function completeZhihuishuLoginSessionInline() {
      if (!zhsCurrentLoginTokenInline) return;
      setZhsMessageInline('正在检查登录状态...');
      try {
        const resp = await fetch(`/api/zhihuishu/login-session/${zhsCurrentLoginTokenInline}/complete`, { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok || !data.ok) throw new Error(data.error || '还没有检测到登录状态');
        setZhsSessionButtonsInline(false);
        zhsCurrentLoginTokenInline = null;
        if (zhsCurrentLoginWindowInline) zhsCurrentLoginWindowInline.close();
        setZhsMessageInline('登录成功，智慧树待办将在后台同步。', 'connected');
        await loadZhihuishuStatusInline();
        await fetchZhihuishuTodos();
      } catch (e) {
        setZhsMessageInline(e.message || '登录检查失败', 'danger');
      }
    }

    async function cancelZhihuishuLoginSessionInline() {
      if (zhsCurrentLoginTokenInline) {
        await fetch(`/api/zhihuishu/login-session/${zhsCurrentLoginTokenInline}`, { method: 'DELETE' });
      } else {
        await fetch('/api/zhihuishu/login-session', { method: 'DELETE' });
      }
      if (zhsCurrentLoginWindowInline) zhsCurrentLoginWindowInline.close();
      zhsCurrentLoginTokenInline = null;
      zhsHasActiveLoginSessionInline = false;
      setZhsSessionButtonsInline(false);
      setZhsMessageInline('当前登录会话已取消。');
      await loadZhihuishuStatusInline();
      await fetchZhihuishuTodos();
    }

    // --- 课堂派 Detail Panel ---
    function populateKetangpaiCourseSelectInline(select, courses) {
      if (!select) return;
      select.replaceChildren(new Option('全部课程 (' + (courses ? courses.length : 0) + ')', ''));
      (Array.isArray(courses) ? courses : []).forEach((course) => {
        const option = document.createElement('option');
        option.value = String(course.id || '');
        option.textContent = `${course.coursename || ''}${course.classname ? ' (' + course.classname + ')' : ''}`;
        select.append(option);
      });
    }

    async function loadKetangpaiStatusInline() {
      const badge = document.getElementById('detail-status-badge-ketangpai');
      const setupDiv = document.getElementById('ktp-setup-inline');
      const loggedInDiv = document.getElementById('ktp-logged-in-inline');
      try {
        const resp = await fetch('/api/ketangpai/config');
        if (!resp.ok) {
          throw new Error('HTTP ' + resp.status);
        }
        const result = await resp.json();
        if (result.ok && result.has_token) {
          if (badge) { badge.textContent = '已登录'; badge.className = 'ui-status ui-status--success status-badge'; }
          setCardStatus('ketangpai', '已连接', 'connected');
          if (setupDiv) setupDiv.classList.add('hidden');
          if (loggedInDiv) loggedInDiv.classList.remove('hidden');
          if (result.courses) {
            const select = document.getElementById('ktp-course-select-inline');
            populateKetangpaiCourseSelectInline(select, result.courses);
          }
        } else {
          if (badge) { badge.textContent = '未登录'; badge.className = 'ui-status ui-status--neutral status-badge'; }
          setCardStatus('ketangpai', '未关联', 'attention');
          if (setupDiv) setupDiv.classList.remove('hidden');
          if (loggedInDiv) loggedInDiv.classList.add('hidden');
        }
      } catch (e) {
        if (badge) { badge.textContent = '未登录'; badge.className = 'ui-status ui-status--neutral status-badge'; }
        setCardStatus('ketangpai', '未关联', 'attention');
        if (setupDiv) setupDiv.classList.remove('hidden');
        if (loggedInDiv) loggedInDiv.classList.add('hidden');
      }
    }

    let ktpSmsCountdownInline = 0;
    let ktpSmsTimerInline = null;
    let ktpFigureSessionId = '';
    let ktpPendingPhone = '';

    async function sendKetangpaiSmsInline() {
      if (ktpSmsCountdownInline > 0) return;
      const phone = (document.getElementById('ktp-phone-inline')?.value || '').trim();
      if (!phone) { showKetangpaiErrorInline('请输入手机号'); return; }
      hideKetangpaiErrorInline();
      ktpPendingPhone = phone;
      await openKetangpaiFigureModal();
    }

    async function openKetangpaiFigureModal() {
      const modal = document.getElementById('ktp-figure-modal');
      const err = document.getElementById('ktp-figure-error');
      const input = document.getElementById('ktp-figure-input');
      if (err) { err.textContent = ''; err.classList.add('hidden'); }
      if (input) input.value = '';
      if (modal) modal.classList.remove('hidden');
      await refreshKetangpaiFigureCode();
      if (input) input.focus();
    }

    function closeKetangpaiFigureModal() {
      const modal = document.getElementById('ktp-figure-modal');
      if (modal) modal.classList.add('hidden');
      const input = document.getElementById('ktp-figure-input');
      if (input) input.value = '';
      const err = document.getElementById('ktp-figure-error');
      if (err) { err.textContent = ''; err.classList.add('hidden'); }
    }

    async function refreshKetangpaiFigureCode() {
      const img = document.getElementById('ktp-figure-img');
      const err = document.getElementById('ktp-figure-error');
      try {
        const resp = await fetch('/api/ketangpai/figure-code');
        const data = await resp.json();
        if (data.ok) {
          ktpFigureSessionId = data.sessionid || '';
          if (img) {
            img.src = data.image_data || data.url || '';
          }
        } else {
          if (err) {
            err.textContent = data.error || '获取图形验证码失败';
            err.classList.remove('hidden');
          }
        }
      } catch (e) {
        if (err) {
          err.textContent = '网络错误，获取图形验证码失败';
          err.classList.remove('hidden');
        }
      }
    }

    async function submitKetangpaiFigureCode(e) {
      if (e) e.preventDefault();
      const input = document.getElementById('ktp-figure-input');
      const verify = (input?.value || '').trim();
      const err = document.getElementById('ktp-figure-error');
      const submitBtn = document.getElementById('ktp-figure-submit-btn');
      const mainBtn = document.getElementById('ktp-send-sms-btn-inline');

      if (!verify) {
        if (err) {
          err.textContent = '请输入计算结果';
          err.classList.remove('hidden');
        }
        return;
      }
      if (err) { err.textContent = ''; err.classList.add('hidden'); }
      if (submitBtn) submitBtn.disabled = true;

      try {
        const resp = await fetch('/api/ketangpai/send-sms', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            phone: ktpPendingPhone,
            verify: verify,
            sessionid: ktpFigureSessionId,
          }),
        });
        const result = await resp.json();
        if (result.ok) {
          closeKetangpaiFigureModal();
          ktpSmsCountdownInline = 60;
          if (ktpSmsTimerInline) clearInterval(ktpSmsTimerInline);
          ktpSmsTimerInline = setInterval(() => {
            ktpSmsCountdownInline--;
            if (ktpSmsCountdownInline <= 0) {
              clearInterval(ktpSmsTimerInline);
              ktpSmsTimerInline = null;
              if (mainBtn) { mainBtn.textContent = '发送验证码'; mainBtn.disabled = false; }
            } else {
              if (mainBtn) mainBtn.textContent = `${ktpSmsCountdownInline}秒后发送`;
            }
          }, 1000);
          if (mainBtn) {
            mainBtn.textContent = `${ktpSmsCountdownInline}秒后发送`;
            mainBtn.disabled = true;
          }
          const captchaInput = document.getElementById('ktp-captcha-inline');
          if (captchaInput) captchaInput.focus();
        } else {
          if (err) {
            err.textContent = result.error || '验证失败，请重新输入';
            err.classList.remove('hidden');
          }
          if (input) input.value = '';
          await refreshKetangpaiFigureCode();
          if (input) input.focus();
        }
      } catch (ex) {
        if (err) {
          err.textContent = '网络错误，发送失败';
          err.classList.remove('hidden');
        }
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    }

    async function doKetangpaiLoginInline() {
      const phone = (document.getElementById('ktp-phone-inline')?.value || '').trim();
      const code = (document.getElementById('ktp-captcha-inline')?.value || '').trim();
      if (!phone || !code) { showKetangpaiErrorInline('请输入手机号和验证码'); return; }
      hideKetangpaiErrorInline();

      try {
        const resp = await fetch('/api/ketangpai/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phone, code }),
        });
        const result = await resp.json();
        if (result.ok) {
          const capInput = document.getElementById('ktp-captcha-inline');
          if (capInput) capInput.value = '';
          if (ktpSmsTimerInline) { clearInterval(ktpSmsTimerInline); ktpSmsTimerInline = null; ktpSmsCountdownInline = 0; }
          const btn = document.getElementById('ktp-send-sms-btn-inline');
          if (btn) { btn.textContent = '发送验证码'; btn.disabled = false; }
          await loadKetangpaiStatusInline();
          await fetchKetangpaiTodos();
        } else {
          showKetangpaiErrorInline(result.error || '登录失败');
        }
      } catch (e) {
        showKetangpaiErrorInline('网络错误');
      }
    }

    function switchKtpAuthTab(tab) {
      const smsPanel = document.getElementById('ktp-sms-login-panel');
      const pwdPanel = document.getElementById('ktp-password-login-inline');
      const smsTab = document.getElementById('ktp-tab-btn-sms');
      const pwdTab = document.getElementById('ktp-toggle-login-mode-btn');
      hideKetangpaiErrorInline();

      if (tab === 'pwd') {
        if (smsPanel) smsPanel.classList.add('hidden');
        if (pwdPanel) pwdPanel.classList.remove('hidden');
        if (smsTab) {
          smsTab.classList.remove('is-active');
          smsTab.setAttribute('aria-selected', 'false');
        }
        if (pwdTab) {
          pwdTab.classList.add('is-active');
          pwdTab.setAttribute('aria-selected', 'true');
        }
      } else {
        if (smsPanel) smsPanel.classList.remove('hidden');
        if (pwdPanel) pwdPanel.classList.add('hidden');
        if (smsTab) {
          smsTab.classList.add('is-active');
          smsTab.setAttribute('aria-selected', 'true');
        }
        if (pwdTab) {
          pwdTab.classList.remove('is-active');
          pwdTab.setAttribute('aria-selected', 'false');
        }
      }
    }

    function toggleKtpLoginModeInline() {
      const pwdPanel = document.getElementById('ktp-password-login-inline');
      const isPwdHidden = !pwdPanel || pwdPanel.classList.contains('hidden');
      switchKtpAuthTab(isPwdHidden ? 'pwd' : 'sms');
    }

    function showKtpPasswordLoginInline() {
      switchKtpAuthTab('pwd');
    }

    async function doKetangpaiPasswordLoginInline(e) {
      if (e) e.preventDefault();
      const account = (document.getElementById('ktp-username-inline')?.value || '').trim();
      const password = (document.getElementById('ktp-password-inline')?.value || '').trim();
      if (!account || !password) { showKetangpaiErrorInline('请输入账号和密码'); return; }
      hideKetangpaiErrorInline();

      try {
        const resp = await fetch('/api/ketangpai/login-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account, password }),
        });
        const result = await resp.json();
        if (result.ok) {
          await loadKetangpaiStatusInline();
          await fetchKetangpaiTodos();
        } else {
          showKetangpaiErrorInline(result.error || '登录失败');
        }
      } catch (e) {
        showKetangpaiErrorInline('网络错误');
      }
    }

    function showKetangpaiErrorInline(msg) {
      const el = document.getElementById('ketangpai-error-inline');
      if (el) { el.textContent = msg; el.classList.remove('hidden'); }
    }

    function hideKetangpaiErrorInline() {
      const el = document.getElementById('ketangpai-error-inline');
      if (el) el.classList.add('hidden');
    }

    async function changeKetangpaiCourseInline() {
      const select = document.getElementById('ktp-course-select-inline');
      const courseId = select ? select.value : '';
      await fetchKetangpaiTodos(courseId);
    }

    async function logoutKetangpaiInline() {
      try {
        await fetch('/api/ketangpai/logout', { method: 'POST' });
      } catch (e) { /* ignore */ }
      switchKtpAuthTab('sms');
      hideKetangpaiErrorInline();
      await loadKetangpaiStatusInline();
      await fetchKetangpaiTodos();
    }

    // --- 同济OJ Detail Panel ---
    function populateTongjiojCourseSelectInline(select, courses, selectedCourse) {
      if (!select) return;
      select.replaceChildren(new Option('全部课程 (' + (courses ? courses.length : 0) + ')', ''));
      (Array.isArray(courses) ? courses : []).forEach((course) => {
        const option = document.createElement('option');
        option.value = String(course.id || '');
        option.textContent = course.name || `课程 ${course.id}`;
        select.append(option);
      });
      select.value = selectedCourse || '';
    }

    async function loadTongjiojStatusInline() {
      const badge = document.getElementById('detail-status-badge-tongjioj');
      const setupDiv = document.getElementById('tjoj-setup-inline');
      const loggedInDiv = document.getElementById('tjoj-logged-in-inline');
      const secondAuthBox = document.getElementById('tjoj-second-auth-box-inline');
      try {
        const resp = await fetch('/api/tongjioj/config');
        if (!resp.ok) {
          throw new Error('HTTP ' + resp.status);
        }
        const result = await resp.json();
        if (result.ok && result.has_token) {
          if (badge) { badge.textContent = '已登录'; badge.className = 'ui-status ui-status--success status-badge'; }
          setCardStatus('tongjioj', '已连接', 'connected');
          hideTongjiojErrorInline();
          if (secondAuthBox) secondAuthBox.classList.add('hidden');
          if (setupDiv) setupDiv.classList.add('hidden');
          if (loggedInDiv) loggedInDiv.classList.remove('hidden');
          if (result.courses) {
            const select = document.getElementById('tjoj-course-select-inline');
            populateTongjiojCourseSelectInline(select, result.courses, result.selected_course || '');
          }
        } else {
          if (badge) { badge.textContent = '未登录'; badge.className = 'ui-status ui-status--neutral status-badge'; }
          setCardStatus('tongjioj', '未关联', 'attention');
          if (setupDiv) setupDiv.classList.remove('hidden');
          if (loggedInDiv) loggedInDiv.classList.add('hidden');
        }
      } catch (e) {
        if (badge) { badge.textContent = '未登录'; badge.className = 'ui-status ui-status--neutral status-badge'; }
        setCardStatus('tongjioj', '未关联', 'attention');
        if (setupDiv) setupDiv.classList.remove('hidden');
        if (loggedInDiv) loggedInDiv.classList.add('hidden');
      }
    }

    function switchTjojAuthTab(tab) {
      const iamPanel = document.getElementById('tjoj-iam-login-panel');
      const localPanel = document.getElementById('tjoj-local-login-panel');
      const iamTab = document.getElementById('tjoj-tab-btn-iam');
      const localTab = document.getElementById('tjoj-tab-btn-local');
      const secondAuthBox = document.getElementById('tjoj-second-auth-box-inline');
      hideTongjiojErrorInline();
      if (secondAuthBox) secondAuthBox.classList.add('hidden');

      if (tab === 'local') {
        if (iamPanel) iamPanel.classList.add('hidden');
        if (localPanel) localPanel.classList.remove('hidden');
        if (iamTab) {
          iamTab.classList.remove('is-active');
          iamTab.setAttribute('aria-selected', 'false');
        }
        if (localTab) {
          localTab.classList.add('is-active');
          localTab.setAttribute('aria-selected', 'true');
        }
      } else {
        if (iamPanel) iamPanel.classList.remove('hidden');
        if (localPanel) localPanel.classList.add('hidden');
        if (iamTab) {
          iamTab.classList.add('is-active');
          iamTab.setAttribute('aria-selected', 'true');
        }
        if (localTab) {
          localTab.classList.remove('is-active');
          localTab.setAttribute('aria-selected', 'false');
        }
      }
    }

    function populateTjojSecondAuthMethodsInline(result) {
      const select = document.getElementById('tjoj-second-auth-type-inline');
      if (!select) return;
      select.replaceChildren();
      const methods = Array.isArray(result.auth_methods) && result.auth_methods.length
        ? result.auth_methods
        : [{ type: 'sms', label: result.mobile ? `手机短信 (${result.mobile})` : '手机短信验证' }];
      methods.forEach((m) => {
        const opt = document.createElement('option');
        opt.value = m.type || 'sms';
        opt.textContent = m.label || (m.type === 'email' ? '电子邮箱验证' : '手机短信验证');
        select.append(opt);
      });
    }

    async function doTongjiojIamLoginInline(e) {
      if (e) e.preventDefault();
      const studentId = (document.getElementById('tjoj-student-id-inline')?.value || '').trim();
      const password = (document.getElementById('tjoj-iam-password-inline')?.value || '').trim();
      if (!studentId || !password) { showTongjiojErrorInline('请输入同济大学学号和统一身份认证密码'); return; }
      hideTongjiojErrorInline();

      try {
        const resp = await fetch('/api/tongjioj/login-iam', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ student_id: studentId, password }),
        });
        const result = await resp.json();
        if (result.ok) {
          hideTongjiojErrorInline();
          const secondAuthBox = document.getElementById('tjoj-second-auth-box-inline');
          if (secondAuthBox) secondAuthBox.classList.add('hidden');
          if (typeof visibleTodoSources !== 'undefined') visibleTodoSources.add('tongjioj');
          await loadTongjiojStatusInline();
          await fetchTongjiojTodos();
        } else if (result.need_second_auth) {
          populateTjojSecondAuthMethodsInline(result);
          const secondAuthBox = document.getElementById('tjoj-second-auth-box-inline');
          if (secondAuthBox) secondAuthBox.classList.remove('hidden');
          showTongjiojErrorInline(result.error || '统一身份认证要求陌生设备加强认证，请点击“发送验证码”完成验证');
        } else {
          showTongjiojErrorInline(result.error || '统一身份认证登录失败');
        }
      } catch (e) {
        showTongjiojErrorInline('网络错误');
      }
    }

    let tjojSecondAuthCountdownTimer = null;
    async function sendTongjiojSecondAuthCodeInline() {
      const select = document.getElementById('tjoj-second-auth-type-inline');
      const btn = document.getElementById('tjoj-send-code-btn-inline');
      const authType = select ? select.value : 'sms';
      hideTongjiojErrorInline();
      if (btn) btn.disabled = true;

      try {
        const resp = await fetch('/api/tongjioj/iam-send-code', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: authType }),
        });
        const result = await resp.json();
        if (result.ok) {
          let remain = 60;
          if (tjojSecondAuthCountdownTimer) clearInterval(tjojSecondAuthCountdownTimer);
          if (btn) btn.textContent = `${remain}s`;
          tjojSecondAuthCountdownTimer = setInterval(() => {
            remain -= 1;
            if (remain <= 0) {
              clearInterval(tjojSecondAuthCountdownTimer);
              tjojSecondAuthCountdownTimer = null;
              if (btn) { btn.disabled = false; btn.textContent = '发送验证码'; }
            } else if (btn) {
              btn.textContent = `${remain}s`;
            }
          }, 1000);
        } else {
          if (btn) btn.disabled = false;
          showTongjiojErrorInline(result.error || '发送验证码失败');
        }
      } catch (e) {
        if (btn) btn.disabled = false;
        showTongjiojErrorInline('网络错误');
      }
    }

    async function verifyTongjiojSecondAuthCodeInline() {
      const select = document.getElementById('tjoj-second-auth-type-inline');
      const codeInput = document.getElementById('tjoj-second-auth-code-inline');
      const authType = select ? select.value : 'sms';
      const code = (codeInput?.value || '').trim();
      if (!code) { showTongjiojErrorInline('请输入收到的安全验证码'); return; }
      hideTongjiojErrorInline();

      try {
        const resp = await fetch('/api/tongjioj/iam-verify-code', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: authType, code }),
        });
        const result = await resp.json();
        if (result.ok) {
          hideTongjiojErrorInline();
          const secondAuthBox = document.getElementById('tjoj-second-auth-box-inline');
          if (secondAuthBox) secondAuthBox.classList.add('hidden');
          if (codeInput) codeInput.value = '';
          if (typeof visibleTodoSources !== 'undefined') visibleTodoSources.add('tongjioj');
          await loadTongjiojStatusInline();
          await fetchTongjiojTodos();
        } else {
          showTongjiojErrorInline(result.error || '加强认证验证失败');
        }
      } catch (e) {
        showTongjiojErrorInline('网络错误');
      }
    }

    async function doTongjiojLocalLoginInline(e) {
      if (e) e.preventDefault();
      const account = (document.getElementById('tjoj-username-inline')?.value || '').trim();
      const password = (document.getElementById('tjoj-local-password-inline')?.value || '').trim();
      if (!account || !password) { showTongjiojErrorInline('请输入 OJ 用户名和密码'); return; }
      hideTongjiojErrorInline();

      try {
        const resp = await fetch('/api/tongjioj/login-local', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account, password }),
        });
        const result = await resp.json();
        if (result.ok) {
          hideTongjiojErrorInline();
          if (typeof visibleTodoSources !== 'undefined') visibleTodoSources.add('tongjioj');
          await loadTongjiojStatusInline();
          await fetchTongjiojTodos();
        } else {
          showTongjiojErrorInline(result.error || '登录失败');
        }
      } catch (e) {
        showTongjiojErrorInline('网络错误');
      }
    }

    function showTongjiojErrorInline(msg) {
      const el = document.getElementById('tongjioj-error-inline');
      if (el) { el.textContent = msg; el.classList.remove('hidden'); }
    }

    function hideTongjiojErrorInline() {
      const el = document.getElementById('tongjioj-error-inline');
      if (el) el.classList.add('hidden');
    }

    async function changeTongjiojCourseInline() {
      const select = document.getElementById('tjoj-course-select-inline');
      const courseId = select ? select.value : '';
      try {
        await fetch('/api/tongjioj/course', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ course_id: courseId }),
        });
      } catch (e) { /* ignore */ }
      await fetchTongjiojTodos(courseId);
    }

    async function logoutTongjiojInline() {
      try {
        await fetch('/api/tongjioj/logout', { method: 'POST' });
      } catch (e) { /* ignore */ }
      switchTjojAuthTab('iam');
      hideTongjiojErrorInline();
      await loadTongjiojStatusInline();
      await fetchTongjiojTodos();
    }

    let platformPendingClear = null;
    const platformDisconnectEndpoints = {
      canvas: ['/api/config', 'DELETE'], haoke: ['/api/haoke/config', 'DELETE'],
      zhixuemeng: ['/api/zhixuemeng/logout', 'POST'], zhihuishu: ['/api/zhihuishu/config', 'DELETE'],
      ketangpai: ['/api/ketangpai/logout', 'POST'], tongjioj: ['/api/tongjioj/logout', 'POST'],
    };
    async function refreshOnePlatform(platform) {
      const loaders = {canvas: fetchCanvasTodos, haoke: fetchHaokeTodos, zhixuemeng: fetchZhixuemengTodos, zhihuishu: fetchZhihuishuTodos, ketangpai: fetchKetangpaiTodos, tongjioj: fetchTongjiojTodos};
      if (platform === 'tongjioj') await fetchTongjiojTodos('', true);
      else if (platform === 'haoke') await fetchHaokeTodos(true);
      else if (platform === 'canvas') await fetchCanvasTodos(true);
      else if (loaders[platform]) await loaders[platform]();
      if (typeof selectConnectionPlatform === 'function') selectConnectionPlatform(platform);
    }
    async function disconnectPlatform(platform) {
      const [url, method] = platformDisconnectEndpoints[platform] || [];
      if (!url) return;
      try {
        const response = await fetch(url, {method});
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '断开失败');
        await refreshOnePlatform(platform);
      } catch (error) { document.getElementById('connections-manager-status').textContent = error.message || '断开失败'; }
    }
    function showClearPlatformData(platform) {
      platformPendingClear = platform;
      document.getElementById('platform-data-confirm-copy').textContent = `将删除${platformLabels[platform]}的连接凭据、缓存作业、完成/隐藏/标红/删除状态和本地标题或截止时间覆盖${platform === 'zhihuishu' ? '，以及浏览器登录资料' : ''}。此操作不可撤销；其他平台、自定义待办、项目、课表和账户不受影响。`;
      document.getElementById('platform-data-confirm-modal').classList.remove('hidden');
    }
    function closePlatformDataConfirm() { platformPendingClear = null; document.getElementById('platform-data-confirm-modal').classList.add('hidden'); }
    async function confirmClearPlatformData() {
      const platform = platformPendingClear;
      if (!platform) return;
      try {
        const response = await fetch(`/api/platform/${platform}/data`, {method: 'DELETE'});
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '清除失败');
        closePlatformDataConfirm();
        await refreshOnePlatform(platform);
      } catch (error) { document.getElementById('platform-data-confirm-copy').textContent = error.message || '清除失败，请稍后重试。'; }
    }


