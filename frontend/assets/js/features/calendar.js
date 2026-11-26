/* Dashboard: features/calendar.js; loaded in index.html order. */
let calendarSubscriptionActive = false;
let calendarSubscriptionLoaded = false;
let calendarSubscriptionCreatedAt = '';

function formatCalendarCreatedDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    const match = String(value).match(/\d{4}-\d{2}-\d{2}/);
    return match ? match[0] : '';
  }
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(date);
  } catch (_) {
    return date.toISOString().slice(0, 10);
  }
}

function setCalendarSubscriptionStatus(message, semantic = 'info') {
  const status = document.getElementById('calendar-subscription-status');
  const error = document.getElementById('calendar-subscription-error');
  if (!status) return;
  status.textContent = message;
  applyFeedbackSemantic(status, semantic);
  if (error) {
    error.textContent = semantic === 'danger' ? message : '';
    error.classList.toggle('hidden', semantic !== 'danger');
  }
}

function syncCalendarSubscriptionUi({ active = false, createdAt = '', url = '' } = {}) {
  calendarSubscriptionActive = Boolean(active || url);
  const createButton = document.getElementById('calendar-subscription-create');
  const revokeButton = document.getElementById('calendar-subscription-revoke');
  const urlWrap = document.getElementById('calendar-subscription-url-wrap');
  const urlInput = document.getElementById('calendar-subscription-url');
  const openButton = document.getElementById('calendar-subscription-open');
  const copyButton = document.getElementById('calendar-subscription-copy');
  const summary = document.getElementById('calendar-active-summary');

  if (urlInput && url !== undefined) {
    urlInput.value = url;
  }
  const hasUrl = Boolean(urlInput?.value);

  if (createButton) {
    createButton.textContent = calendarSubscriptionActive ? '重新生成链接' : '生成日历订阅链接';
  }
  if (revokeButton) {
    revokeButton.classList.toggle('hidden', !calendarSubscriptionActive);
    revokeButton.disabled = !calendarSubscriptionActive;
  }
  if (urlWrap) {
    urlWrap.classList.toggle('hidden', !hasUrl);
  }
  if (openButton) openButton.disabled = !hasUrl;
  if (copyButton) copyButton.disabled = !hasUrl;

  if (summary) {
    if (calendarSubscriptionActive && !hasUrl) {
      const dateStr = formatCalendarCreatedDate(createdAt);
      const datePart = dateStr ? `（创建于 ${dateStr}）` : '';
      summary.textContent = `已启用日历订阅${datePart} · 出于安全考虑仅在生成时显示完整链接`;
      summary.classList.remove('hidden');
    } else {
      summary.textContent = '';
      summary.classList.add('hidden');
    }
  }
}

async function loadCalendarSubscription({ force = false } = {}) {
  if (!document.getElementById('dashboard-view-calendar')) return;
  const urlInput = document.getElementById('calendar-subscription-url');
  if (!force && urlInput?.value) {
    syncCalendarSubscriptionUi({
      active: true,
      createdAt: calendarSubscriptionCreatedAt,
      url: urlInput.value,
    });
    return;
  }
  try {
    const data = await dashboardApi.requestJson('/api/apple-calendar/subscription');
    calendarSubscriptionLoaded = true;
    const isActive = Boolean(data.active);
    calendarSubscriptionCreatedAt = isActive ? (data.created_at || calendarSubscriptionCreatedAt) : '';
    syncCalendarSubscriptionUi({
      active: isActive,
      createdAt: calendarSubscriptionCreatedAt,
      url: urlInput?.value || '',
    });
    if (isActive && !urlInput?.value) {
      setCalendarSubscriptionStatus('如需更换地址或查看新的分类订阅链接，可点击“重新生成链接”。', 'info');
    } else if (!isActive) {
      renderCalendarFeeds([]);
      setCalendarSubscriptionStatus('生成链接后可直接在 Apple 日历中打开，或复制到 Google 等日历订阅。', 'info');
    }
  } catch (_) {
    // Keep current UI state on transient errors
  }
}

async function createCalendarSubscription() {
  const createButton = document.getElementById('calendar-subscription-create');
  const urlInput = document.getElementById('calendar-subscription-url');
  if (!createButton || !urlInput) return;

  if (calendarSubscriptionActive && window.uiConfirm) {
    const confirmed = await window.uiConfirm({
      title: '重新生成订阅链接',
      message: '重新生成将使旧的订阅链接与分类日历地址立即失效，已在手机或桌面日历添加的订阅需替换为新地址。确定继续吗？',
      confirmLabel: '重新生成链接',
      cancelLabel: '保留当前',
      tone: 'danger',
    });
    if (!confirmed) return;
  }

  let succeeded = false;
  const runCreate = async () => {
    setCalendarSubscriptionStatus('正在生成私有订阅链接…', 'info');
    try {
      const data = await dashboardApi.requestJson('/api/apple-calendar/subscription', { method: 'POST' });
      if (!data.path) throw new Error('subscription unavailable');
      const fullUrl = new URL(data.path, window.location.origin).href;
      calendarSubscriptionCreatedAt = data.created_at || new Date().toISOString();
      syncCalendarSubscriptionUi({ active: true, createdAt: calendarSubscriptionCreatedAt, url: fullUrl });
      document.getElementById('calendar-subscription-empty')?.classList.add('hidden');
      renderCalendarFeeds(data.feeds || []);
      setCalendarSubscriptionStatus('链接已生成；可直接在 Apple 日历中打开，也可复制到 Google 等日历或按分类独立订阅。', 'success');
      succeeded = true;
    } catch (error) {
      setCalendarSubscriptionStatus('暂时无法生成订阅链接，请稍后重试。', 'danger');
    }
  };

  if (window.withButtonBusy) {
    await window.withButtonBusy(createButton, '正在生成…', runCreate);
  } else {
    await runCreate();
  }
  syncCalendarSubscriptionUi({
    active: succeeded || calendarSubscriptionActive,
    createdAt: calendarSubscriptionCreatedAt,
    url: urlInput.value || '',
  });
}

function renderCalendarFeeds(feeds) {
  const container = document.getElementById('calendar-feeds-container');
  if (!container) return;
  container.replaceChildren();
  const categoryFeeds = (feeds || []).filter((feed) => feed && feed.id !== 'all');
  if (!categoryFeeds.length) {
    container.classList.add('hidden');
    return;
  }
  container.classList.remove('hidden');

  const heading = document.createElement('div');
  heading.className = 'calendar-feed-heading';
  heading.textContent = '推荐：按分类分别订阅（可在日历应用中独立配色）';
  container.appendChild(heading);

  categoryFeeds.forEach((feed) => {
    const item = document.createElement('div');
    item.className = 'calendar-feed-row';

    const info = document.createElement('div');
    info.className = 'calendar-feed-info';

    const dot = document.createElement('span');
    dot.className = 'calendar-feed-dot';
    if (feed.color) {
      dot.style.background = feed.color;
    }

    const textWrap = document.createElement('div');
    textWrap.className = 'calendar-feed-text';

    const title = document.createElement('div');
    title.className = 'calendar-feed-title';
    title.textContent = feed.name;

    const desc = document.createElement('div');
    desc.className = 'calendar-feed-desc';
    desc.textContent = feed.description;

    textWrap.append(title, desc);
    info.append(dot, textWrap);

    const actions = document.createElement('div');
    actions.className = 'calendar-feed-actions';

    const openBtn = document.createElement('button');
    openBtn.type = 'button';
    openBtn.className = 'ui-button ui-button--secondary ui-button--sm';
    openBtn.textContent = '在日历中添加';
    openBtn.onclick = () => {
      const fullUrl = new URL(feed.path, window.location.origin).href;
      window.location.href = fullUrl.replace(/^https?:/, 'webcal:');
    };

    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'ui-button ui-button--secondary ui-button--sm';
    copyBtn.textContent = '复制链接';
    copyBtn.onclick = async () => {
      const fullUrl = new URL(feed.path, window.location.origin).href;
      await copyCalendarText(fullUrl, copyBtn, `已复制「${feed.name}」订阅地址。`);
    };

    actions.append(openBtn, copyBtn);
    item.append(info, actions);
    container.appendChild(item);
  });
}

function openCalendarSubscription() {
  const urlInput = document.getElementById('calendar-subscription-url');
  if (!urlInput || !urlInput.value) return;
  window.location.href = urlInput.value.replace(/^https?:/, 'webcal:');
}

async function copyCalendarText(text, button, successMessage) {
  if (!text) return;
  if (window.copyWithFeedback) {
    const ok = await window.copyWithFeedback(text, button, { copiedLabel: '已复制' });
    if (ok) {
      setCalendarSubscriptionStatus(successMessage, 'success');
    } else {
      setCalendarSubscriptionStatus('无法自动复制，请手动选择并复制订阅地址。', 'danger');
    }
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    setCalendarSubscriptionStatus(successMessage, 'success');
  } catch (error) {
    setCalendarSubscriptionStatus('无法自动复制，请手动选择并复制订阅地址。', 'danger');
  }
}

async function copyCalendarSubscription() {
  const urlInput = document.getElementById('calendar-subscription-url');
  if (!urlInput || !urlInput.value) return;
  const copyButton = document.getElementById('calendar-subscription-copy');
  await copyCalendarText(urlInput.value, copyButton, '订阅地址已复制。');
}

async function revokeCalendarSubscription() {
  const urlInput = document.getElementById('calendar-subscription-url');
  const createButton = document.getElementById('calendar-subscription-create');
  const revokeButton = document.getElementById('calendar-subscription-revoke');
  if (!urlInput || !createButton || !revokeButton) return;

  if (window.uiConfirm) {
    const confirmed = await window.uiConfirm({
      title: '撤销所有日历订阅',
      message: '撤销后，当前综合订阅与分类日历链接将全部立即失效。确定继续吗？',
      confirmLabel: '确认撤销',
      cancelLabel: '保留',
      tone: 'danger',
    });
    if (!confirmed) return;
  }

  const runRevoke = async () => {
    try {
      await dashboardApi.requestJson('/api/apple-calendar/subscription', { method: 'DELETE' });
      syncCalendarSubscriptionUi({ active: false, url: '' });
      document.getElementById('calendar-subscription-empty')?.classList.remove('hidden');
      renderCalendarFeeds([]);
      setCalendarSubscriptionStatus('日历订阅已撤销', 'success');
    } catch (error) {
      setCalendarSubscriptionStatus('撤销失败，请稍后重试。', 'danger');
    }
  };

  if (window.withButtonBusy) {
    await window.withButtonBusy(revokeButton, '正在撤销…', runRevoke);
  } else {
    await runRevoke();
  }
  syncCalendarSubscriptionUi({
    active: calendarSubscriptionActive,
    createdAt: calendarSubscriptionCreatedAt,
    url: urlInput.value || '',
  });
}

(function initializeCalendarFeature() {
  const viewEl = document.getElementById('dashboard-view-calendar');
  if (!viewEl) return;

  viewEl.querySelectorAll('.calendar-details').forEach((detailsEl) => {
    window.uiMotion?.enhanceDisclosure?.(detailsEl);
  });

  if (typeof MutationObserver === 'function') {
    const observer = new MutationObserver(() => {
      if (!viewEl.classList.contains('hidden')) {
        void loadCalendarSubscription();
      }
    });
    observer.observe(viewEl, { attributes: true, attributeFilter: ['class'] });
  }

  if (!calendarSubscriptionLoaded) {
    void loadCalendarSubscription();
  }
})();
