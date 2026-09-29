/* Dashboard: features/calendar.js; loaded in index.html order. */
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

    async function createCalendarSubscription() {
      const createButton = document.getElementById('calendar-subscription-create');
      const urlInput = document.getElementById('calendar-subscription-url');
      const openButton = document.getElementById('calendar-subscription-open');
      const copyButton = document.getElementById('calendar-subscription-copy');
      const revokeButton = document.getElementById('calendar-subscription-revoke');
      if (!createButton || !urlInput || !openButton || !copyButton || !revokeButton) return;

      const originalLabel = createButton.textContent;
      createButton.disabled = true;
      createButton.setAttribute('aria-busy', 'true');
      createButton.textContent = '正在生成…';
      openButton.disabled = true;
      copyButton.disabled = true;
      revokeButton.disabled = true;
      setCalendarSubscriptionStatus('正在生成私有订阅链接…');
      try {
        const data = await dashboardApi.requestJson('/api/apple-calendar/subscription', { method: 'POST' });
        if (!data.path) throw new Error('subscription unavailable');
        urlInput.value = new URL(data.path, window.location.origin).href;
        openButton.disabled = false;
        copyButton.disabled = false;
        revokeButton.disabled = false;
        createButton.textContent = '重新生成链接';
        document.getElementById('calendar-subscription-empty')?.classList.add('hidden');
        renderCalendarFeeds(data.feeds || []);
        setCalendarSubscriptionStatus('链接已生成；可复制到 Google 等日历订阅，也可按分类独立订阅。', 'success');
      } catch (error) {
        setCalendarSubscriptionStatus('暂时无法生成订阅链接，请稍后重试。', 'danger');
      } finally {
        createButton.disabled = false;
        createButton.setAttribute('aria-busy', 'false');
        if (!urlInput.value) createButton.textContent = originalLabel;
      }
    }

    function renderCalendarFeeds(feeds) {
      const container = document.getElementById('calendar-feeds-container');
      if (!container) return;
      container.innerHTML = '';
      if (!feeds || !feeds.length) {
        container.classList.add('hidden');
        return;
      }
      container.classList.remove('hidden');

      const heading = document.createElement('div');
      heading.style.cssText = 'font-size: 12px; font-weight: 600; color: var(--ds-ink-2, #5b6472); margin-top: 4px; margin-bottom: 2px;';
      heading.textContent = '推荐：按分类分别订阅（可在日历应用中设置颜色）';
      container.appendChild(heading);

      feeds.forEach(feed => {
        const item = document.createElement('div');
        item.className = 'calendar-feed-row';
        item.style.cssText = 'display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: #fff; border: 1px solid var(--ds-line-soft, #eef0f3); border-radius: 8px; gap: 12px; flex-wrap: wrap;';

        const info = document.createElement('div');
        info.style.cssText = 'display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1 1 200px;';

        const dot = document.createElement('span');
        dot.style.cssText = 'width: 10px; height: 10px; border-radius: 50%; background: ' + feed.color + '; flex-shrink: 0; box-shadow: 0 0 0 2px ' + feed.color + '33;';

        const textWrap = document.createElement('div');
        textWrap.style.cssText = 'min-width: 0;';

        const title = document.createElement('div');
        title.style.cssText = 'font-size: 13px; font-weight: 600; color: var(--ds-ink, #1c2330);';
        title.textContent = feed.name;

        const desc = document.createElement('div');
        desc.style.cssText = 'font-size: 11.5px; color: var(--ds-ink-3, #7d8694); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
        desc.textContent = feed.description;

        textWrap.append(title, desc);
        info.append(dot, textWrap);

        const actions = document.createElement('div');
        actions.style.cssText = 'display: flex; gap: 6px; flex-shrink: 0;';

        const openBtn = document.createElement('button');
        openBtn.type = 'button';
        openBtn.className = 'ui-button ui-button--secondary';
        openBtn.style.cssText = 'padding: 4px 10px; font-size: 12px; height: auto; min-height: 28px;';
        openBtn.textContent = '在日历中添加';
        openBtn.onclick = () => {
          const fullUrl = new URL(feed.path, window.location.origin).href;
          window.location.href = fullUrl.replace(/^https?:/, 'webcal:');
        };

        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'ui-button ui-button--secondary';
        copyBtn.style.cssText = 'padding: 4px 10px; font-size: 12px; height: auto; min-height: 28px;';
        copyBtn.textContent = '复制链接';
        copyBtn.onclick = async () => {
          const fullUrl = new URL(feed.path, window.location.origin).href;
          try {
            await navigator.clipboard.writeText(fullUrl);
            setCalendarSubscriptionStatus('已复制「' + feed.name + '」订阅地址。', 'success');
          } catch (e) {
            setCalendarSubscriptionStatus('无法自动复制，请手动复制：' + fullUrl, 'danger');
          }
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

    async function copyCalendarSubscription() {
      const urlInput = document.getElementById('calendar-subscription-url');
      if (!urlInput || !urlInput.value) return;
      const copyButton = document.getElementById('calendar-subscription-copy');
      if (copyButton) { copyButton.disabled = true; copyButton.setAttribute('aria-busy', 'true'); copyButton.textContent = '正在复制…'; }
      try {
        await navigator.clipboard.writeText(urlInput.value);
        setCalendarSubscriptionStatus('订阅地址已复制。', 'success');
      } catch (error) {
        urlInput.select();
        const copied = document.execCommand('copy');
        if (!copied) setCalendarSubscriptionStatus('无法自动复制，请手动选择并复制订阅地址。', 'danger');
        else setCalendarSubscriptionStatus('订阅地址已复制。', 'success');
      } finally {
        if (copyButton) { copyButton.disabled = false; copyButton.setAttribute('aria-busy', 'false'); copyButton.textContent = '复制链接'; }
      }
    }

    async function revokeCalendarSubscription() {
      const urlInput = document.getElementById('calendar-subscription-url');
      const createButton = document.getElementById('calendar-subscription-create');
      const openButton = document.getElementById('calendar-subscription-open');
      const copyButton = document.getElementById('calendar-subscription-copy');
      const revokeButton = document.getElementById('calendar-subscription-revoke');
      if (!urlInput || !createButton || !openButton || !copyButton || !revokeButton) return;

      const originalLabel = revokeButton.textContent;
      revokeButton.disabled = true;
      revokeButton.setAttribute('aria-busy', 'true');
      revokeButton.textContent = '正在撤销…';
      createButton.disabled = true;
      openButton.disabled = true;
      copyButton.disabled = true;
      try {
        await dashboardApi.requestJson('/api/apple-calendar/subscription', { method: 'DELETE' });
        urlInput.value = '';
        openButton.disabled = true;
        copyButton.disabled = true;
        createButton.textContent = '生成订阅链接';
        document.getElementById('calendar-subscription-empty')?.classList.remove('hidden');
        renderCalendarFeeds([]);
        setCalendarSubscriptionStatus('日历订阅已撤销', 'success');
      } catch (error) {
        setCalendarSubscriptionStatus('撤销失败，请稍后重试。', 'danger');
      } finally {
        revokeButton.disabled = !urlInput.value;
        revokeButton.setAttribute('aria-busy', 'false');
        revokeButton.textContent = originalLabel;
        createButton.disabled = false;
      }
    }

