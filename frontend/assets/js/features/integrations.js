/* Dashboard: features/integrations.js; loaded in index.html order. */
    // ---- Platform connection card status ----
    function formatSyncHHMM(date = new Date()) {
      try {
        return new Intl.DateTimeFormat('zh-CN', {
          timeZone: 'Asia/Shanghai',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        }).format(date);
      } catch (_) {
        const hh = String(date.getHours()).padStart(2, '0');
        const mm = String(date.getMinutes()).padStart(2, '0');
        return `${hh}:${mm}`;
      }
    }

    function setCardStatus(platform, text, cls) {
      const el = document.getElementById(`card-status-${platform}`);
      const semantic = cls === 'connected'
        ? 'success'
        : cls === 'attention' && /失败|错误|不可用/.test(text)
          ? 'danger'
          : cls === 'attention'
            ? 'warning'
            : cls === 'info'
              ? 'info'
              : 'neutral';
      if (el) {
        el.textContent = text;
        applyStatusSemantic(el, semantic);
        el.classList.toggle('attention', cls === 'attention');
        el.classList.toggle('connected', cls === 'connected');
      }
      const detailBadge = document.getElementById(`detail-status-badge-${platform}`);
      if (detailBadge) {
        detailBadge.textContent = text;
        applyStatusSemantic(detailBadge, semantic);
        detailBadge.classList.toggle('attention', cls === 'attention');
        detailBadge.classList.toggle('connected', cls === 'connected');
      }
      updateAttentionStatus();
    }

    function updateAttentionStatus() {
      const allAttentionElements = document.querySelectorAll('#login-cards .connection-platform-status.attention');
      const attentionElements = Array.from(allAttentionElements).filter(item => {
        const platform = item.id.replace('card-status-', '');
        return typeof visibleTodoSources !== 'undefined' ? visibleTodoSources.has(platform) : true;
      });
      const attentionCount = attentionElements.length;
      const attentionDot = document.getElementById('connections-attention');
      if (attentionDot) {
        attentionDot.classList.toggle('hidden', attentionCount === 0);
      }
      const mobileAttentionDot = document.getElementById('mobile-connections-attention');
      if (mobileAttentionDot) {
        mobileAttentionDot.classList.toggle('hidden', attentionCount === 0);
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
            const card = item.closest('.connection-platform-item');
            return card ? card.querySelector('.connection-platform-title')?.textContent?.trim() : '';
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
          fetchZhixuemengTodos(true),
          fetchZhihuishuTodos(),
          fetchKetangpaiTodos('', true),
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
    function platformHasCachedItems(platform) {
      const map = {
        canvas: typeof canvasItems !== 'undefined' ? canvasItems : [],
        haoke: typeof haokeItems !== 'undefined' ? haokeItems : [],
        zhixuemeng: typeof zhixuemengItems !== 'undefined' ? zhixuemengItems : [],
        zhihuishu: typeof zhihuishuItems !== 'undefined' ? zhihuishuItems : [],
        ketangpai: typeof ketangpaiItems !== 'undefined' ? ketangpaiItems : [],
        tongjioj: typeof tongjiojItems !== 'undefined' ? tongjiojItems : [],
      };
      return Array.isArray(map[platform]) && map[platform].length > 0;
    }

    function updateConnectionDataActions(platform, overrides = {}) {
      const wrap = document.querySelector(`.connection-data-actions[data-platform-actions="${platform}"]`);
      if (!wrap) return;
      const sync = platformSyncs[platform] || {};
      const state = overrides.state !== undefined ? overrides.state : (sync.connection_state || '');
      const connected = overrides.connected !== undefined
        ? Boolean(overrides.connected)
        : state === 'connected';
      const needsReauth = overrides.needsReauth !== undefined
        ? Boolean(overrides.needsReauth)
        : state === 'needs_reauth';
      const hasCache = overrides.hasCache !== undefined
        ? Boolean(overrides.hasCache)
        : Boolean(sync.has_cache || sync.last_success_at || (sync.data_state && sync.data_state !== 'none') || platformHasCachedItems(platform));

      const showDisconnect = connected || needsReauth;
      const showClear = connected || needsReauth || hasCache;

      wrap.querySelector('.connection-disconnect-button')?.classList.toggle('hidden', !showDisconnect);
      wrap.querySelector('.connection-clear-button')?.classList.toggle('hidden', !showClear);
      wrap.classList.toggle('hidden', !(showDisconnect || showClear));
    }

    function recordPlatformSync(platform, result) {
      if (!result?.sync) {
        if (!result?.ok && !result?.need_setup) recordPlatformFailure(platform, result?.error || '更新失败');
        updateConnectionDataActions(platform);
        return;
      }
      const sync = {...result.sync};
      if (platform === 'tongjioj') sync.has_cache = !!result.has_cache;
      if (result.stale) sync.data_state = 'stale';
      else if (result.cached && sync.data_state === 'fresh') sync.data_state = 'cached';
      platformSyncs[platform] = sync;
      updateConnectionDataActions(platform);
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
          if (refreshing) {
            status.textContent = '正在刷新全部平台状态…';
            applyFeedbackSemantic(status, 'info');
          } else if (text) {
            status.textContent = text;
            applyFeedbackSemantic(status, 'warning');
          } else if (workspaceRefreshFailed) {
            status.textContent = '部分平台刷新失败，请稍后重试。';
            applyFeedbackSemantic(status, 'danger');
          } else {
            status.textContent = `全部平台状态已是最新（${formatSyncHHMM()}）`;
            applyFeedbackSemantic(status, 'success');
          }
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
          setCardStatus('canvas', '未连接', 'neutral');
          canvasItems = [];
          hiddenIds = [];
          highlightedIds = [];
          updateConnectionDataActions('canvas', { connected: false });
          renderUnifiedList();
          return;
        }

        if (!result.ok) {
          setCardStatus('canvas', '同步失败', 'attention');
        } else if (result.sync?.refreshing) {
          setCardStatus('canvas', '同步中…', 'info');
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
        updateConnectionDataActions('canvas');
        renderUnifiedList();
      } catch (e) {
        if (version !== canvasLoadVersion) return;
        setCardStatus('canvas', '同步失败', 'attention');
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
          setCardStatus('haoke', '未连接', 'neutral');
          haokeItems = [];
          haokeHiddenIds = [];
          haokeHighlightedIds = [];
          updateConnectionDataActions('haoke', { connected: false });
          renderUnifiedList();
          return;
        }

        if (!result.ok) {
          setCardStatus('haoke', '同步失败', 'attention');
        } else if (result.sync?.refreshing) {
          setCardStatus('haoke', '同步中…', 'info');
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
        updateConnectionDataActions('haoke');
        renderUnifiedList();
      } catch (e) {
        if (version !== haokeLoadVersion) return;
        setCardStatus('haoke', '同步失败', 'attention');
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
    let zhixuemengPollTimer = null;
    async function fetchZhixuemengTodos(refresh = false, cacheOnly = false) {
      clearTimeout(zhixuemengPollTimer);
      const finish = beginPlatformRequest('zhixuemeng');
      try {
        const resp = await fetch('/api/zhixuemeng/todos' + (refresh ? '?refresh=1' : cacheOnly ? '?cache_only=1' : ''));
        const result = await resp.json();
        recordPlatformSync('zhixuemeng', result);
        if (result.sync?.refreshing) zhixuemengPollTimer = setTimeout(() => fetchZhixuemengTodos(false, true), 2000);

        if (result.need_setup && result.sync?.connection_state !== 'disconnected') {
          setCardStatus('zhixuemeng', '未连接', 'neutral');
          zhixuemengItems = [];
          zhixuemengHiddenIds = [];
          zhixuemengHighlightedIds = [];
          updateConnectionDataActions('zhixuemeng', { connected: false });
          renderUnifiedList();
          return;
        }

        if (!result.ok) {
          setCardStatus('zhixuemeng', '同步失败', 'attention');
        } else if (result.sync?.refreshing) {
          setCardStatus('zhixuemeng', '同步中…', 'info');
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
        updateConnectionDataActions('zhixuemeng');
        renderUnifiedList();
      } catch (e) {
        setCardStatus('zhixuemeng', '同步失败', 'attention');
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
    let ketangpaiPollTimer = null;
    async function fetchKetangpaiTodos(courseId = '', refresh = false, cacheOnly = false) {
      clearTimeout(ketangpaiPollTimer);
      const finish = beginPlatformRequest('ketangpai');
      try {
        const url = courseId ? `/api/ketangpai/todos?course_id=${encodeURIComponent(courseId)}` : '/api/ketangpai/todos';
        const query = refresh ? 'refresh=1' : cacheOnly ? 'cache_only=1' : '';
        const resp = await fetch(url + (query ? (url.includes('?') ? '&' : '?') + query : ''));
        const result = await resp.json();
        recordPlatformSync('ketangpai', result);
        if (result.sync?.refreshing) ketangpaiPollTimer = setTimeout(() => fetchKetangpaiTodos(courseId, false, true), 2000);

        if (result.need_setup && result.sync?.connection_state !== 'disconnected') {
          setCardStatus('ketangpai', '未连接', 'neutral');
          ketangpaiItems = [];
          ketangpaiHiddenIds = [];
          ketangpaiHighlightedIds = [];
          updateConnectionDataActions('ketangpai', { connected: false });
          renderUnifiedList();
          return;
        }

        if (!result.ok) {
          setCardStatus('ketangpai', '同步失败', 'attention');
        } else if (result.sync?.refreshing) {
          setCardStatus('ketangpai', '同步中…', 'info');
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
        updateConnectionDataActions('ketangpai');
        renderUnifiedList();
      } catch (e) {
        setCardStatus('ketangpai', '同步失败', 'attention');
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
        setCardStatus('tongjioj', '同步失败', 'attention');
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
          setCardStatus('tongjioj', '未连接', 'neutral');
          tongjiojItems = [];
          tongjiojHiddenIds = [];
          tongjiojHighlightedIds = [];
          updateConnectionDataActions('tongjioj', { connected: false, hasCache: Boolean(result.has_cache) });
          renderUnifiedList();
          return;
        }

        if (result.sync?.connection_state === 'needs_reauth') {
          setCardStatus('tongjioj', '需重新登录', 'attention');
        } else if (!result.ok || result.error || (!result.sync.refreshing && result.sync.error_message)) {
          setCardStatus('tongjioj', '同步失败', 'attention');
        } else if (result.sync?.refreshing) {
          setCardStatus('tongjioj', '同步中…', 'info');
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
        updateConnectionDataActions('tongjioj', { hasCache: Boolean(result.has_cache || tongjiojItems.length) });
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
          const needsRelogin = Boolean((result.data && result.data.length) || result.sync?.connection_state === 'needs_reauth');
          setCardStatus('zhihuishu', needsRelogin ? '需重新登录' : '未连接', needsRelogin ? 'attention' : 'neutral');
        } else if (!result.ok) {
          setCardStatus('zhihuishu', '同步失败', 'attention');
        } else if (result.stale) {
          setCardStatus('zhihuishu', '需重新登录', 'attention');
        } else if (result.sync?.refreshing) {
          setCardStatus('zhihuishu', '同步中…', 'info');
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
        updateConnectionDataActions('zhihuishu');
        renderUnifiedList();
      } catch (e) {
        setCardStatus('zhihuishu', '同步失败', 'attention');
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

    function glideInlineTabIndicator(containerId, activeBtn) {
      const container = document.getElementById(containerId);
      if (!container || !activeBtn || !window.uiMotion?.glideIndicator) return;
      requestAnimationFrame(() => {
        if (!activeBtn.offsetWidth) return;
        window.uiMotion.glideIndicator(container, activeBtn);
      });
    }

    function openConnectionModal(modalId, focusSelector) {
      const modal = document.getElementById(modalId);
      if (!modal) return;
      if (window.uiDialog?.open) {
        window.uiDialog.open(modal, focusSelector);
        return;
      }
      modal.classList.remove('hidden');
      if (focusSelector) requestAnimationFrame(() => modal.querySelector(focusSelector)?.focus());
    }

    function closeConnectionModal(modalId) {
      const modal = document.getElementById(modalId);
      if (!modal) return;
      if (window.uiDialog?.close) {
        window.uiDialog.close(modal, { force: true });
        return;
      }
      modal.classList.add('hidden');
    }

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

      if (platform !== 'zhihuishu') stopZhsSessionPollInline();

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
      const summary = document.getElementById('canvas-connected-summary');
      const input = document.getElementById('feed-url-input-inline');
      try {
        const resp = await fetch('/api/config');
        const result = await resp.json();
        const connected = Boolean(result.has_feed);
        summary?.classList.toggle('hidden', !connected);
        if (input) {
          input.placeholder = connected
            ? '已配置订阅链接，粘贴新链接可替换（.ics）...'
            : '粘贴日历馈送 URL（.ics）...';
        }
        if (connected) {
          const isRefreshing = Boolean(platformSyncs.canvas?.refreshing);
          setCardStatus('canvas', isRefreshing ? '同步中…' : '已连接', isRefreshing ? 'info' : 'connected');
        } else {
          setCardStatus('canvas', '未连接', 'neutral');
        }
        updateConnectionDataActions('canvas', { connected });
      } catch (e) {
        setCardStatus('canvas', '同步失败', 'attention');
      }
    }

    async function saveCanvasFeedUrlInline(e) {
      e.preventDefault();
      const input = document.getElementById('feed-url-input-inline');
      const err = document.getElementById('canvas-error-inline');
      const url = (input?.value || '').trim();
      if (!url) {
        if (err) {
          err.textContent = '请粘贴 Canvas 日历馈送 URL（.ics）';
          err.classList.remove('hidden');
          window.uiMotion?.nudgeError?.(err);
        }
        input?.focus();
        return;
      }

      const btn = document.querySelector('#canvas-setup-form-inline button[type="submit"]');
      err?.classList.add('hidden');
      const runSave = async () => {
        try {
          const resp = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ calendar_feed_url: url }),
          });
          const result = await resp.json();
          if (result.ok) {
            if (input) input.value = '';
            await loadCanvasStatusInline();
            await fetchCanvasTodos();
          } else if (err) {
            err.textContent = result.error || '保存失败';
            err.classList.remove('hidden');
            window.uiMotion?.nudgeError?.(err);
          }
        } catch (e) {
          if (err) {
            err.textContent = '网络错误';
            err.classList.remove('hidden');
            window.uiMotion?.nudgeError?.(err);
          }
        }
      };

      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '保存中…', runSave);
      } else {
        await runSave();
      }
    }

    // --- 好课 Detail Panel ---
    async function loadHaokeStatusInline() {
      const summary = document.getElementById('haoke-connected-summary');
      const accountEl = document.getElementById('haoke-connected-account');
      try {
        const resp = await fetch('/api/haoke/config');
        const result = await resp.json();
        const connected = Boolean(result.has_credentials);
        summary?.classList.toggle('hidden', !connected);
        if (accountEl) {
          accountEl.textContent = result.username
            ? `已连接账号：${result.username}`
            : '已保存登录凭据，重新输入学号和密码即可更新。';
        }
        if (connected) {
          const isRefreshing = Boolean(platformSyncs.haoke?.refreshing);
          setCardStatus('haoke', isRefreshing ? '同步中…' : '已连接', isRefreshing ? 'info' : 'connected');
        } else {
          setCardStatus('haoke', '未连接', 'neutral');
        }
        updateConnectionDataActions('haoke', { connected });
      } catch (e) {
        setCardStatus('haoke', '同步失败', 'attention');
      }
    }

    async function saveHaokeCredentialsInline(e) {
      e.preventDefault();
      const userEl = document.getElementById('haoke-username-inline');
      const passEl = document.getElementById('haoke-password-inline');
      const err = document.getElementById('haoke-error-inline');
      const username = (userEl?.value || '').trim();
      const password = (passEl?.value || '').trim();
      if (!username || !password) {
        if (err) {
          err.textContent = '请输入学号和密码';
          err.classList.remove('hidden');
          window.uiMotion?.nudgeError?.(err);
        }
        (!username ? userEl : passEl)?.focus();
        return;
      }

      const btn = document.querySelector('#haoke-setup-form-inline button[type="submit"]');
      err?.classList.add('hidden');
      const runSave = async () => {
        try {
          const resp = await fetch('/api/haoke/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
          });
          const result = await resp.json();
          if (result.ok) {
            if (userEl) userEl.value = '';
            if (passEl) passEl.value = '';
            await loadHaokeStatusInline();
            await fetchHaokeTodos();
          } else if (err) {
            err.textContent = result.error || '保存失败';
            err.classList.remove('hidden');
            window.uiMotion?.nudgeError?.(err);
          }
        } catch (e) {
          if (err) {
            err.textContent = '网络错误';
            err.classList.remove('hidden');
            window.uiMotion?.nudgeError?.(err);
          }
        }
      };

      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '登录中…', runSave);
      } else {
        await runSave();
      }
    }

    // --- 智学盟 Detail Panel ---
    function showZhixuemengErrorInline(msg) {
      const el = document.getElementById('zhixuemeng-error-inline');
      if (!el) return;
      el.textContent = msg;
      el.classList.remove('hidden');
      window.uiMotion?.nudgeError?.(el);
    }

    function hideZhixuemengErrorInline() {
      const el = document.getElementById('zhixuemeng-error-inline');
      if (el) {
        el.textContent = '';
        el.classList.add('hidden');
      }
    }

    function switchZxmAuthTab(tab) {
      const smsPanel = document.getElementById('zxm-sms-login-panel');
      const pwdPanel = document.getElementById('zxm-password-login-inline');
      const smsTab = document.getElementById('zxm-tab-btn-sms');
      const pwdTab = document.getElementById('zxm-tab-btn-pwd');
      hideZhixuemengErrorInline();
      const usePwd = tab === 'pwd';
      smsPanel?.classList.toggle('hidden', usePwd);
      pwdPanel?.classList.toggle('hidden', !usePwd);
      if (smsTab) {
        smsTab.classList.toggle('is-active', !usePwd);
        smsTab.setAttribute('aria-selected', String(!usePwd));
      }
      if (pwdTab) {
        pwdTab.classList.toggle('is-active', usePwd);
        pwdTab.setAttribute('aria-selected', String(usePwd));
      }
      glideInlineTabIndicator('zxm-auth-tabs-inline', usePwd ? pwdTab : smsTab);
    }

    function showZxmPasswordLoginInline() {
      switchZxmAuthTab('pwd');
    }

    async function loadZhixuemengStatusInline() {
      const setupDiv = document.getElementById('zxm-setup-inline');
      const loggedInDiv = document.getElementById('zxm-logged-in-inline');
      try {
        const resp = await fetch('/api/zhixuemeng/config');
        const result = await resp.json();
        if (result.ok && result.has_token) {
          setCardStatus('zhixuemeng', '已连接', 'connected');
          hideZhixuemengErrorInline();
          setupDiv.classList.add('hidden');
          loggedInDiv.classList.remove('hidden');
          if (result.courses) {
            const select = document.getElementById('zxm-course-select-inline');
            populateZhixuemengCourseSelect(select, result.courses, result.selected_course);
          }
          updateConnectionDataActions('zhixuemeng', { connected: true });
        } else {
          setCardStatus('zhixuemeng', '未连接', 'neutral');
          setupDiv.classList.remove('hidden');
          loggedInDiv.classList.add('hidden');
          const activeTab = document.querySelector('#zxm-auth-tabs-inline .ktp-auth-tab.is-active')
            || document.getElementById('zxm-tab-btn-sms');
          glideInlineTabIndicator('zxm-auth-tabs-inline', activeTab);
          updateConnectionDataActions('zhixuemeng', { connected: false });
        }
      } catch (e) {
        setCardStatus('zhixuemeng', '同步失败', 'attention');
        setupDiv.classList.remove('hidden');
        loggedInDiv.classList.add('hidden');
      }
    }

    let zxmSmsCountdownInline = 0;
    let zxmSmsTimerInline = null;

    async function sendZhixuemengSmsInline() {
      if (zxmSmsCountdownInline > 0) return;
      const phoneInput = document.getElementById('zxm-phone-inline');
      const phone = (phoneInput?.value || '').trim();
      if (!phone) {
        showZhixuemengErrorInline('请输入手机号');
        phoneInput?.focus();
        return;
      }
      hideZhixuemengErrorInline();

      const btn = document.getElementById('zxm-send-sms-btn-inline');
      const origText = btn ? btn.textContent : '发送验证码';
      if (btn) {
        btn.disabled = true;
        btn.setAttribute('aria-busy', 'true');
        btn.textContent = '发送中…';
      }

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
          if (btn) {
            btn.removeAttribute('aria-busy');
            btn.textContent = `${zxmSmsCountdownInline}s 后重发`;
          }
          zxmSmsTimerInline = setInterval(() => {
            zxmSmsCountdownInline--;
            if (zxmSmsCountdownInline <= 0) {
              clearInterval(zxmSmsTimerInline);
              zxmSmsTimerInline = null;
              if (btn) {
                btn.textContent = '发送验证码';
                btn.disabled = false;
              }
            } else if (btn) {
              btn.textContent = `${zxmSmsCountdownInline}s 后重发`;
            }
          }, 1000);
          document.getElementById('zxm-captcha-inline')?.focus();
        } else {
          showZhixuemengErrorInline(result.error || '发送失败');
          if (btn) {
            btn.disabled = false;
            btn.removeAttribute('aria-busy');
            btn.textContent = origText;
          }
        }
      } catch (e) {
        showZhixuemengErrorInline('网络错误，请稍后重试');
        if (btn) {
          btn.disabled = false;
          btn.removeAttribute('aria-busy');
          btn.textContent = origText;
        }
      }
    }

    async function doZhixuemengLoginInline() {
      const phoneInput = document.getElementById('zxm-phone-inline');
      const captchaInput = document.getElementById('zxm-captcha-inline');
      const phone = (phoneInput?.value || '').trim();
      const captcha = (captchaInput?.value || '').trim();
      if (!phone || !captcha) {
        showZhixuemengErrorInline('请输入手机号和验证码');
        (!phone ? phoneInput : captchaInput)?.focus();
        return;
      }
      hideZhixuemengErrorInline();

      const btn = document.getElementById('zxm-sms-login-btn-inline');
      const runLogin = async () => {
        try {
          const resp = await fetch('/api/zhixuemeng/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone, captcha }),
          });
          const result = await resp.json();
          if (result.ok) {
            if (captchaInput) captchaInput.value = '';
            if (zxmSmsTimerInline) { clearInterval(zxmSmsTimerInline); zxmSmsTimerInline = null; zxmSmsCountdownInline = 0; }
            const sendBtn = document.getElementById('zxm-send-sms-btn-inline');
            if (sendBtn) { sendBtn.textContent = '发送验证码'; sendBtn.disabled = false; }
            await loadZhixuemengStatusInline();
            await fetchZhixuemengTodos();
          } else {
            showZhixuemengErrorInline(result.error || '登录失败');
          }
        } catch (e) {
          showZhixuemengErrorInline('网络错误，请稍后重试');
        }
      };

      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '登录中…', runLogin);
      } else {
        await runLogin();
      }
    }

    async function doZhixuemengPasswordLoginInline(e) {
      e.preventDefault();
      const userEl = document.getElementById('zxm-username-inline');
      const passEl = document.getElementById('zxm-password-inline');
      const username = (userEl?.value || '').trim();
      const password = (passEl?.value || '').trim();
      if (!username || !password) {
        showZhixuemengErrorInline('请输入智学盟用户名和密码');
        (!username ? userEl : passEl)?.focus();
        return;
      }
      hideZhixuemengErrorInline();

      const btn = document.getElementById('zxm-pwd-login-btn-inline');
      const runLogin = async () => {
        try {
          const resp = await fetch('/api/zhixuemeng/login-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username, password: password }),
          });
          const result = await resp.json();
          if (result.ok) {
            if (passEl) passEl.value = '';
            await loadZhixuemengStatusInline();
            await fetchZhixuemengTodos();
          } else {
            showZhixuemengErrorInline(result.error || '登录失败');
          }
        } catch (e) {
          showZhixuemengErrorInline('网络错误，请稍后重试');
        }
      };

      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '登录中…', runLogin);
      } else {
        await runLogin();
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
      switchZxmAuthTab('sms');
      hideZhixuemengErrorInline();
      await loadZhixuemengStatusInline();
      await fetchZhixuemengTodos();
    }

    // --- 智慧树 Detail Panel ---
    let zhsCurrentLoginTokenInline = null;
    let zhsCurrentLoginWindowInline = null;
    let zhsHasActiveLoginSessionInline = false;
    let zhsSessionPollTimerInline = null;
    let zhsSessionPollInFlightInline = false;

    const zhsSessionLabelsInline = {
      active: '已连接',
      ok: '已连接',
      need_relogin: '需重新登录',
      needs_reauth: '需重新登录',
      disconnected: '未连接',
      not_logged_in: '未连接',
      unconfigured: '未连接',
      checking: '同步中…',
    };
    const zhsWorkerLabelsInline = {
      running: '运行中',
      ok: '正常',
      idle: '空闲等待中',
      stopped: '未运行',
      error: '异常',
      dry_run: '演练模式',
      unknown: '等待首次同步',
    };

    function formatZhsTime(value) {
      if (!value) return '--';
      if (typeof value === 'number') return new Date(value * 1000).toLocaleString();
      return value;
    }

    function setZhsMessageInline(text, cls) {
      const el = document.getElementById('zhs-login-session-message-inline');
      if (!el) return;
      el.textContent = text || '';
      const semantic = cls === 'connected' ? 'success' : cls === 'attention' ? 'warning' : cls || 'info';
      applyFeedbackSemantic(el, semantic);
      el.classList.remove('attention', 'connected');
      if (cls === 'connected' || cls === 'attention') el.classList.add(cls);
    }

    function setZhsSessionButtonsInline(active) {
      const hasSession = Boolean(active || zhsHasActiveLoginSessionInline);
      document.getElementById('zhs-btn-open-login-inline').disabled = hasSession;
      document.getElementById('zhs-btn-complete-login-inline').disabled = !hasSession;
      document.getElementById('zhs-btn-cancel-login-inline').disabled = !hasSession;
    }

    function stopZhsSessionPollInline() {
      if (zhsSessionPollTimerInline) {
        clearInterval(zhsSessionPollTimerInline);
        zhsSessionPollTimerInline = null;
      }
    }

    function syncZhsSessionPollInline() {
      const shouldPoll = Boolean(zhsHasActiveLoginSessionInline || zhsCurrentLoginTokenInline)
        && activeConnectionPlatform === 'zhihuishu'
        && !document.getElementById('dashboard-view-connections')?.classList.contains('hidden');
      if (!shouldPoll) {
        stopZhsSessionPollInline();
        return;
      }
      if (zhsSessionPollTimerInline) return;
      zhsSessionPollTimerInline = setInterval(async () => {
        if (document.visibilityState === 'hidden') return;
        if (activeConnectionPlatform !== 'zhihuishu'
            || document.getElementById('dashboard-view-connections')?.classList.contains('hidden')) {
          stopZhsSessionPollInline();
          return;
        }
        if (zhsSessionPollInFlightInline) return;
        zhsSessionPollInFlightInline = true;
        try {
          await loadZhihuishuStatusInline();
        } finally {
          zhsSessionPollInFlightInline = false;
        }
      }, 4000);
    }

    async function loadZhihuishuStatusInline() {
      try {
        const resp = await fetch('/api/zhihuishu/config');
        const data = await resp.json();
        const status = data.status || {};
        const loginSession = data.login_session || {};
        zhsHasActiveLoginSessionInline = Boolean(loginSession.active);
        if (!zhsHasActiveLoginSessionInline) {
          zhsCurrentLoginTokenInline = null;
        }

        const sessionCode = String(status.session || '');
        const sessionText = zhsSessionLabelsInline[sessionCode] || (sessionCode ? '需重新登录' : '未连接');
        const isZhsConnected = sessionCode === 'active' || sessionCode === 'ok';
        const cardCls = isZhsConnected
          ? 'connected'
          : (sessionCode === 'need_relogin' || sessionCode === 'needs_reauth')
            ? 'attention'
            : sessionCode === 'checking'
              ? 'info'
              : 'neutral';
        setCardStatus('zhihuishu', sessionText, cardCls);

        document.getElementById('zhs-session-inline').textContent = sessionText;
        document.getElementById('zhs-worker-inline').textContent = zhsWorkerLabelsInline[status.worker] || '等待首次同步';
        document.getElementById('zhs-last-keepalive-inline').textContent = formatZhsTime(status.last_keepalive_at);
        document.getElementById('zhs-last-fetch-inline').textContent = formatZhsTime(status.last_fetch_at);
        document.getElementById('zhs-last-success-inline').textContent = formatZhsTime(status.last_success_at);
        const hasError = Boolean(status.last_error);
        document.getElementById('zhs-last-error-label-inline')?.classList.toggle('hidden', !hasError);
        const errEl = document.getElementById('zhs-last-error-inline');
        if (errEl) {
          errEl.textContent = hasError ? status.last_error : '';
          errEl.classList.toggle('hidden', !hasError);
        }

        setZhsSessionButtonsInline(Boolean(zhsCurrentLoginTokenInline || zhsHasActiveLoginSessionInline));
        updateConnectionDataActions('zhihuishu', {
          connected: isZhsConnected,
          needsReauth: sessionCode === 'need_relogin' || sessionCode === 'needs_reauth',
        });

        if (isZhsConnected && zhsHasActiveLoginSessionInline) {
          setZhsMessageInline('已检测到登录成功，如未自动保存请点击“我已完成登录”。', 'connected');
        } else if (zhsHasActiveLoginSessionInline && !zhsCurrentLoginTokenInline) {
          setZhsMessageInline(`检测到进行中的登录会话（将于 ${formatZhsTime(loginSession.expires_at)} 过期）。完成登录后可直接点击“我已完成登录”。`, 'attention');
        }
        syncZhsSessionPollInline();
      } catch (e) {
        setCardStatus('zhihuishu', '同步失败', 'attention');
      }
    }

    async function openZhihuishuLoginSessionInline() {
      const btn = document.getElementById('zhs-btn-open-login-inline');
      setZhsMessageInline('正在打开登录窗口…');
      const runOpen = async () => {
        try {
          const resp = await fetch('/api/zhihuishu/login-session', { method: 'POST' });
          const data = await resp.json();
          if (!resp.ok || !data.ok) throw new Error(data.error || '启动失败');
          zhsCurrentLoginTokenInline = data.token;
          zhsHasActiveLoginSessionInline = true;
          zhsCurrentLoginWindowInline = window.open(data.url, '_blank', 'noopener,noreferrer,width=1280,height=900');
          setZhsSessionButtonsInline(true);
          setZhsMessageInline('登录窗口已打开。完成智慧树登录后回到这里点击“我已完成登录”。', 'connected');
          syncZhsSessionPollInline();
        } catch (e) {
          setZhsMessageInline(e.message || '登录窗口启动失败', 'danger');
        }
      };
      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '正在打开…', runOpen);
      } else {
        await runOpen();
      }
      setZhsSessionButtonsInline(Boolean(zhsCurrentLoginTokenInline || zhsHasActiveLoginSessionInline));
    }

    async function completeZhihuishuLoginSessionInline() {
      const endpoint = zhsCurrentLoginTokenInline
        ? `/api/zhihuishu/login-session/${zhsCurrentLoginTokenInline}/complete`
        : zhsHasActiveLoginSessionInline
          ? '/api/zhihuishu/login-session/complete'
          : null;
      if (!endpoint) return;
      const btn = document.getElementById('zhs-btn-complete-login-inline');
      setZhsMessageInline('正在检查登录状态…');
      const runComplete = async () => {
        try {
          const resp = await fetch(endpoint, { method: 'POST' });
          const data = await resp.json();
          if (!resp.ok || !data.ok) throw new Error(data.error || '还没有检测到登录状态');
          zhsCurrentLoginTokenInline = null;
          zhsHasActiveLoginSessionInline = false;
          stopZhsSessionPollInline();
          setZhsSessionButtonsInline(false);
          if (zhsCurrentLoginWindowInline) zhsCurrentLoginWindowInline.close();
          setZhsMessageInline('登录成功，智慧树待办将在后台同步。', 'connected');
          await loadZhihuishuStatusInline();
          await fetchZhihuishuTodos();
        } catch (e) {
          setZhsMessageInline(e.message || '登录检查失败', 'danger');
        }
      };
      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '确认中…', runComplete);
      } else {
        await runComplete();
      }
      setZhsSessionButtonsInline(Boolean(zhsCurrentLoginTokenInline || zhsHasActiveLoginSessionInline));
    }

    async function cancelZhihuishuLoginSessionInline() {
      const btn = document.getElementById('zhs-btn-cancel-login-inline');
      const runCancel = async () => {
        if (zhsCurrentLoginTokenInline) {
          await fetch(`/api/zhihuishu/login-session/${zhsCurrentLoginTokenInline}`, { method: 'DELETE' });
        } else {
          await fetch('/api/zhihuishu/login-session', { method: 'DELETE' });
        }
        if (zhsCurrentLoginWindowInline) zhsCurrentLoginWindowInline.close();
        zhsCurrentLoginTokenInline = null;
        zhsHasActiveLoginSessionInline = false;
        stopZhsSessionPollInline();
        setZhsSessionButtonsInline(false);
        setZhsMessageInline('当前登录会话已取消。');
        await loadZhihuishuStatusInline();
        await fetchZhihuishuTodos();
      };
      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '取消中…', runCancel);
      } else {
        await runCancel();
      }
      setZhsSessionButtonsInline(Boolean(zhsCurrentLoginTokenInline || zhsHasActiveLoginSessionInline));
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
      const setupDiv = document.getElementById('ktp-setup-inline');
      const loggedInDiv = document.getElementById('ktp-logged-in-inline');
      try {
        const resp = await fetch('/api/ketangpai/config');
        if (!resp.ok) {
          throw new Error('HTTP ' + resp.status);
        }
        const result = await resp.json();
        if (result.ok && result.has_token) {
          setCardStatus('ketangpai', '已连接', 'connected');
          if (setupDiv) setupDiv.classList.add('hidden');
          if (loggedInDiv) loggedInDiv.classList.remove('hidden');
          if (result.courses) {
            const select = document.getElementById('ktp-course-select-inline');
            populateKetangpaiCourseSelectInline(select, result.courses);
          }
          updateConnectionDataActions('ketangpai', { connected: true });
        } else {
          setCardStatus('ketangpai', '未连接', 'neutral');
          if (setupDiv) setupDiv.classList.remove('hidden');
          if (loggedInDiv) loggedInDiv.classList.add('hidden');
          const activeTab = document.querySelector('#ktp-auth-tabs-inline .ktp-auth-tab.is-active')
            || document.getElementById('ktp-tab-btn-sms');
          glideInlineTabIndicator('ktp-auth-tabs-inline', activeTab);
          updateConnectionDataActions('ketangpai', { connected: false });
        }
      } catch (e) {
        setCardStatus('ketangpai', '同步失败', 'attention');
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
      const phoneInput = document.getElementById('ktp-phone-inline');
      const phone = (phoneInput?.value || '').trim();
      if (!phone) {
        showKetangpaiErrorInline('请输入手机号');
        phoneInput?.focus();
        return;
      }
      hideKetangpaiErrorInline();
      ktpPendingPhone = phone;
      await openKetangpaiFigureModal();
    }

    async function openKetangpaiFigureModal() {
      const err = document.getElementById('ktp-figure-error');
      const input = document.getElementById('ktp-figure-input');
      if (err) { err.textContent = ''; err.classList.add('hidden'); }
      if (input) input.value = '';
      openConnectionModal('ktp-figure-modal', '#ktp-figure-input');
      await refreshKetangpaiFigureCode();
    }

    function closeKetangpaiFigureModal() {
      closeConnectionModal('ktp-figure-modal');
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
          window.uiMotion?.nudgeError?.(err);
        }
        input?.focus();
        return;
      }
      if (err) { err.textContent = ''; err.classList.add('hidden'); }

      const runSubmit = async () => {
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
                if (mainBtn) mainBtn.textContent = `${ktpSmsCountdownInline}s 后重发`;
              }
            }, 1000);
            if (mainBtn) {
              mainBtn.textContent = `${ktpSmsCountdownInline}s 后重发`;
              mainBtn.disabled = true;
            }
            const captchaInput = document.getElementById('ktp-captcha-inline');
            if (captchaInput) captchaInput.focus();
          } else {
            if (err) {
              err.textContent = result.error || '验证失败，请重新输入';
              err.classList.remove('hidden');
              window.uiMotion?.nudgeError?.(err);
            }
            if (input) input.value = '';
            await refreshKetangpaiFigureCode();
            if (input) input.focus();
          }
        } catch (ex) {
          if (err) {
            err.textContent = '网络错误，发送失败';
            err.classList.remove('hidden');
            window.uiMotion?.nudgeError?.(err);
          }
        }
      };

      if (window.withButtonBusy && submitBtn) {
        await window.withButtonBusy(submitBtn, '发送中…', runSubmit);
      } else {
        await runSubmit();
      }
    }

    async function doKetangpaiLoginInline() {
      const phoneInput = document.getElementById('ktp-phone-inline');
      const captchaInput = document.getElementById('ktp-captcha-inline');
      const phone = (phoneInput?.value || '').trim();
      const code = (captchaInput?.value || '').trim();
      if (!phone || !code) {
        showKetangpaiErrorInline('请输入手机号和验证码');
        (!phone ? phoneInput : captchaInput)?.focus();
        return;
      }
      hideKetangpaiErrorInline();

      const btn = document.getElementById('ktp-sms-login-btn-inline');
      const runLogin = async () => {
        try {
          const resp = await fetch('/api/ketangpai/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone, code }),
          });
          const result = await resp.json();
          if (result.ok) {
            if (captchaInput) captchaInput.value = '';
            if (ktpSmsTimerInline) { clearInterval(ktpSmsTimerInline); ktpSmsTimerInline = null; ktpSmsCountdownInline = 0; }
            const sendBtn = document.getElementById('ktp-send-sms-btn-inline');
            if (sendBtn) { sendBtn.textContent = '发送验证码'; sendBtn.disabled = false; }
            await loadKetangpaiStatusInline();
            await fetchKetangpaiTodos();
          } else {
            showKetangpaiErrorInline(result.error || '登录失败');
          }
        } catch (e) {
          showKetangpaiErrorInline('网络错误');
        }
      };

      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '登录中…', runLogin);
      } else {
        await runLogin();
      }
    }

    function switchKtpAuthTab(tab) {
      const smsPanel = document.getElementById('ktp-sms-login-panel');
      const pwdPanel = document.getElementById('ktp-password-login-inline');
      const smsTab = document.getElementById('ktp-tab-btn-sms');
      const pwdTab = document.getElementById('ktp-toggle-login-mode-btn');
      hideKetangpaiErrorInline();

      const usePwd = tab === 'pwd';
      if (smsPanel) smsPanel.classList.toggle('hidden', usePwd);
      if (pwdPanel) pwdPanel.classList.toggle('hidden', !usePwd);
      if (smsTab) {
        smsTab.classList.toggle('is-active', !usePwd);
        smsTab.setAttribute('aria-selected', String(!usePwd));
      }
      if (pwdTab) {
        pwdTab.classList.toggle('is-active', usePwd);
        pwdTab.setAttribute('aria-selected', String(usePwd));
      }
      glideInlineTabIndicator('ktp-auth-tabs-inline', usePwd ? pwdTab : smsTab);
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
      const userInput = document.getElementById('ktp-username-inline');
      const passInput = document.getElementById('ktp-password-inline');
      const account = (userInput?.value || '').trim();
      const password = (passInput?.value || '').trim();
      if (!account || !password) {
        showKetangpaiErrorInline('请输入账号和密码');
        (!account ? userInput : passInput)?.focus();
        return;
      }
      hideKetangpaiErrorInline();

      const btn = document.getElementById('ktp-pwd-login-btn-inline');
      const runLogin = async () => {
        try {
          const resp = await fetch('/api/ketangpai/login-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account, password }),
          });
          const result = await resp.json();
          if (result.ok) {
            if (passInput) passInput.value = '';
            await loadKetangpaiStatusInline();
            await fetchKetangpaiTodos();
          } else {
            showKetangpaiErrorInline(result.error || '登录失败');
          }
        } catch (e) {
          showKetangpaiErrorInline('网络错误');
        }
      };

      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '登录中…', runLogin);
      } else {
        await runLogin();
      }
    }

    function showKetangpaiErrorInline(msg) {
      const el = document.getElementById('ketangpai-error-inline');
      if (el) {
        el.textContent = msg;
        el.classList.remove('hidden');
        window.uiMotion?.nudgeError?.(el);
      }
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
          setCardStatus('tongjioj', '已连接', 'connected');
          hideTongjiojErrorInline();
          if (secondAuthBox) secondAuthBox.classList.add('hidden');
          if (setupDiv) setupDiv.classList.add('hidden');
          if (loggedInDiv) loggedInDiv.classList.remove('hidden');
          if (result.courses) {
            const select = document.getElementById('tjoj-course-select-inline');
            populateTongjiojCourseSelectInline(select, result.courses, result.selected_course || '');
          }
          updateConnectionDataActions('tongjioj', { connected: true });
        } else {
          setCardStatus('tongjioj', '未连接', 'neutral');
          if (setupDiv) setupDiv.classList.remove('hidden');
          if (loggedInDiv) loggedInDiv.classList.add('hidden');
          const activeTab = document.querySelector('#tjoj-auth-tabs-inline .ktp-auth-tab.is-active')
            || document.getElementById('tjoj-tab-btn-iam');
          glideInlineTabIndicator('tjoj-auth-tabs-inline', activeTab);
          updateConnectionDataActions('tongjioj', { connected: false });
        }
      } catch (e) {
        setCardStatus('tongjioj', '同步失败', 'attention');
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

      const useLocal = tab === 'local';
      if (iamPanel) iamPanel.classList.toggle('hidden', useLocal);
      if (localPanel) localPanel.classList.toggle('hidden', !useLocal);
      if (iamTab) {
        iamTab.classList.toggle('is-active', !useLocal);
        iamTab.setAttribute('aria-selected', String(!useLocal));
      }
      if (localTab) {
        localTab.classList.toggle('is-active', useLocal);
        localTab.setAttribute('aria-selected', String(useLocal));
      }
      glideInlineTabIndicator('tjoj-auth-tabs-inline', useLocal ? localTab : iamTab);
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

    let tjojIamLoginPending = false;
    async function doTongjiojIamLoginInline(e) {
      if (e) e.preventDefault();
      if (tjojIamLoginPending) return;
      const sidInput = document.getElementById('tjoj-student-id-inline');
      const passInput = document.getElementById('tjoj-iam-password-inline');
      const studentId = (sidInput?.value || '').trim();
      const password = (passInput?.value || '').trim();
      if (!studentId || !password) {
        showTongjiojErrorInline('请输入同济大学学号和统一身份认证密码');
        (!studentId ? sidInput : passInput)?.focus();
        return;
      }
      hideTongjiojErrorInline();
      tjojIamLoginPending = true;
      const button = document.querySelector('#tjoj-iam-form-inline button[type="submit"]');

      const runLogin = async () => {
        try {
          const resp = await fetch('/api/tongjioj/login-iam', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ student_id: studentId, password }),
          });
          const result = await resp.json();
          if (result.ok) {
            hideTongjiojErrorInline();
            if (passInput) passInput.value = '';
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
        } finally {
          tjojIamLoginPending = false;
        }
      };

      if (window.withButtonBusy && button) {
        await window.withButtonBusy(button, '登录中…', runLogin);
      } else {
        if (button) button.disabled = true;
        try { await runLogin(); } finally { if (button) button.disabled = false; }
      }
    }

    let tjojSecondAuthCountdownTimer = null;
    async function sendTongjiojSecondAuthCodeInline() {
      const select = document.getElementById('tjoj-second-auth-type-inline');
      const btn = document.getElementById('tjoj-send-code-btn-inline');
      const authType = select ? select.value : 'sms';
      const origText = btn ? btn.textContent : '发送验证码';
      hideTongjiojErrorInline();
      if (btn) {
        btn.disabled = true;
        btn.setAttribute('aria-busy', 'true');
        btn.textContent = '发送中…';
      }

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
          if (btn) {
            btn.removeAttribute('aria-busy');
            btn.textContent = `${remain}s 后重发`;
          }
          tjojSecondAuthCountdownTimer = setInterval(() => {
            remain -= 1;
            if (remain <= 0) {
              clearInterval(tjojSecondAuthCountdownTimer);
              tjojSecondAuthCountdownTimer = null;
              if (btn) { btn.disabled = false; btn.textContent = '发送验证码'; }
            } else if (btn) {
              btn.textContent = `${remain}s 后重发`;
            }
          }, 1000);
          document.getElementById('tjoj-second-auth-code-inline')?.focus();
        } else {
          if (btn) { btn.disabled = false; btn.removeAttribute('aria-busy'); btn.textContent = origText; }
          showTongjiojErrorInline(result.error || '发送验证码失败');
        }
      } catch (e) {
        if (btn) { btn.disabled = false; btn.removeAttribute('aria-busy'); btn.textContent = origText; }
        showTongjiojErrorInline('网络错误');
      }
    }

    async function verifyTongjiojSecondAuthCodeInline() {
      const select = document.getElementById('tjoj-second-auth-type-inline');
      const codeInput = document.getElementById('tjoj-second-auth-code-inline');
      const authType = select ? select.value : 'sms';
      const code = (codeInput?.value || '').trim();
      if (!code) {
        showTongjiojErrorInline('请输入收到的安全验证码');
        codeInput?.focus();
        return;
      }
      hideTongjiojErrorInline();

      const btn = document.getElementById('tjoj-verify-code-btn-inline');
      const runVerify = async () => {
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
      };

      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '验证中…', runVerify);
      } else {
        await runVerify();
      }
    }

    async function doTongjiojLocalLoginInline(e) {
      if (e) e.preventDefault();
      const userInput = document.getElementById('tjoj-username-inline');
      const passInput = document.getElementById('tjoj-local-password-inline');
      const account = (userInput?.value || '').trim();
      const password = (passInput?.value || '').trim();
      if (!account || !password) {
        showTongjiojErrorInline('请输入 OJ 用户名和密码');
        (!account ? userInput : passInput)?.focus();
        return;
      }
      hideTongjiojErrorInline();

      const btn = document.getElementById('tjoj-local-login-btn-inline');
      const runLogin = async () => {
        try {
          const resp = await fetch('/api/tongjioj/login-local', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account, password }),
          });
          const result = await resp.json();
          if (result.ok) {
            hideTongjiojErrorInline();
            if (passInput) passInput.value = '';
            if (typeof visibleTodoSources !== 'undefined') visibleTodoSources.add('tongjioj');
            await loadTongjiojStatusInline();
            await fetchTongjiojTodos();
          } else {
            showTongjiojErrorInline(result.error || '登录失败');
          }
        } catch (e) {
          showTongjiojErrorInline('网络错误');
        }
      };

      if (window.withButtonBusy && btn) {
        await window.withButtonBusy(btn, '登录中…', runLogin);
      } else {
        await runLogin();
      }
    }

    function showTongjiojErrorInline(msg) {
      const el = document.getElementById('tongjioj-error-inline');
      if (el) {
        el.textContent = msg;
        el.classList.remove('hidden');
        window.uiMotion?.nudgeError?.(el);
      }
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
      const label = platformLabels[platform] || platform;
      if (window.uiConfirm) {
        const confirmed = await window.uiConfirm({
          title: `断开 ${label}`,
          message: `确定断开与 ${label} 的连接吗？\n已保存的凭据或订阅链接将被移除，历史作业缓存会保留。`,
          confirmLabel: '断开连接',
          cancelLabel: '取消',
          tone: 'danger',
        });
        if (!confirmed) return;
      }
      try {
        const response = await fetch(url, {method});
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '断开失败');
        await refreshOnePlatform(platform);
        const statusEl = document.getElementById('connections-manager-status');
        if (statusEl) {
          statusEl.textContent = `已断开 ${label}`;
          applyFeedbackSemantic(statusEl, 'info');
        }
      } catch (error) {
        const statusEl = document.getElementById('connections-manager-status');
        if (statusEl) {
          statusEl.textContent = error.message || '断开失败';
          applyFeedbackSemantic(statusEl, 'danger');
        }
      }
    }
    function showClearPlatformData(platform) {
      platformPendingClear = platform;
      document.getElementById('platform-data-confirm-copy').textContent = `将删除${platformLabels[platform]}的连接凭据、缓存作业、完成/隐藏/标红/删除状态和本地标题或截止时间覆盖${platform === 'zhihuishu' ? '，以及浏览器登录资料' : ''}。此操作不可撤销；其他平台、自定义待办、项目、课表和账户不受影响。`;
      openConnectionModal('platform-data-confirm-modal', '#platform-data-confirm-submit-btn');
    }
    function closePlatformDataConfirm() {
      platformPendingClear = null;
      closeConnectionModal('platform-data-confirm-modal');
    }
    async function confirmClearPlatformData() {
      const platform = platformPendingClear;
      if (!platform) return;
      const submitBtn = document.getElementById('platform-data-confirm-submit-btn');
      const runClear = async () => {
        try {
          const response = await fetch(`/api/platform/${platform}/data`, {method: 'DELETE'});
          const data = await response.json();
          if (!response.ok || !data.ok) throw new Error(data.error || '清除失败');
          closePlatformDataConfirm();
          await refreshOnePlatform(platform);
          updateConnectionDataActions(platform, { connected: false, needsReauth: false, hasCache: false });
          const statusEl = document.getElementById('connections-manager-status');
          if (statusEl) {
            statusEl.textContent = `已清除${platformLabels[platform] || platform}的全部数据`;
            applyFeedbackSemantic(statusEl, 'info');
          }
        } catch (error) {
          document.getElementById('platform-data-confirm-copy').textContent = error.message || '清除失败，请稍后重试。';
        }
      };
      if (window.withButtonBusy && submitBtn) {
        await window.withButtonBusy(submitBtn, '清除中…', runClear);
      } else {
        await runClear();
      }
    }


