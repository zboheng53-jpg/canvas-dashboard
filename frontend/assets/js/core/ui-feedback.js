/* Dashboard shared feedback & accessible dialog primitives: window.uiToast, uiConfirm, withButtonBusy, copyWithFeedback, uiDialog */
(function attachUiFeedback(global) {
  const VALID_TONES = new Set(['neutral', 'info', 'success', 'warning', 'danger']);
  const MAX_TOASTS = 2;
  const DEFAULT_TOAST_DURATION = 4500;
  const DEFAULT_COPY_DURATION = 1800;

  const dialogStates = new WeakMap();
  const copyTimers = new WeakMap();
  const copyOriginalHtml = new WeakMap();
  let activeConfirmReject = null;

  function prefersReducedMotion() {
    return Boolean(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function ensureToastRegion() {
    let region = document.getElementById('ui-toast-region');
    if (region) return region;
    region = document.createElement('div');
    region.id = 'ui-toast-region';
    region.className = 'ui-toast-region';
    region.setAttribute('role', 'region');
    region.setAttribute('aria-live', 'polite');
    region.setAttribute('aria-label', '系统提示');
    document.body.appendChild(region);
    return region;
  }

  function removeToastNode(toastEl, immediate = false) {
    if (!toastEl || !toastEl.parentNode) return;
    if (toastEl.dataset.dismissed === '1') return;
    toastEl.dataset.dismissed = '1';
    if (immediate || prefersReducedMotion()) {
      toastEl.remove();
      return;
    }
    toastEl.classList.add('is-leaving');
    let removed = false;
    const cleanup = () => {
      if (removed) return;
      removed = true;
      toastEl.remove();
    };
    toastEl.addEventListener('transitionend', cleanup, { once: true });
    global.setTimeout(cleanup, 200);
  }

  const uiToast = {
    show(message, options = {}) {
      const {
        tone = 'neutral',
        actionLabel = null,
        onAction = null,
        duration = DEFAULT_TOAST_DURATION,
      } = options || {};
      const region = ensureToastRegion();
      const safeTone = VALID_TONES.has(tone) ? tone : 'neutral';

      const liveToasts = Array.from(region.querySelectorAll('.ui-toast:not(.is-leaving)'));
      while (liveToasts.length >= MAX_TOASTS) {
        const oldest = liveToasts.shift();
        if (oldest) removeToastNode(oldest, true);
      }

      const toastEl = document.createElement('div');
      toastEl.className = `ui-toast ui-toast--${safeTone}`;
      toastEl.setAttribute('role', safeTone === 'danger' ? 'alert' : 'status');

      const dotEl = document.createElement('span');
      dotEl.className = 'ui-toast__dot';
      dotEl.setAttribute('aria-hidden', 'true');

      const messageEl = document.createElement('span');
      messageEl.className = 'ui-toast__message';
      messageEl.textContent = String(message || '');

      toastEl.append(dotEl, messageEl);

      let timerId = null;
      let remaining = typeof duration === 'number' ? duration : DEFAULT_TOAST_DURATION;
      let startedAt = 0;

      const clearTimer = () => {
        if (timerId !== null) {
          global.clearTimeout(timerId);
          timerId = null;
        }
      };

      const dismiss = () => {
        clearTimer();
        removeToastNode(toastEl, false);
      };

      const startTimer = () => {
        clearTimer();
        if (remaining <= 0) return;
        startedAt = Date.now();
        timerId = global.setTimeout(dismiss, remaining);
      };

      const pauseTimer = () => {
        if (timerId === null) return;
        const elapsed = Date.now() - startedAt;
        remaining = Math.max(250, remaining - elapsed);
        clearTimer();
      };

      if (actionLabel) {
        const actionBtn = document.createElement('button');
        actionBtn.type = 'button';
        actionBtn.className = 'ui-toast__action';
        actionBtn.textContent = String(actionLabel);
        actionBtn.addEventListener('click', () => {
          dismiss();
          if (typeof onAction === 'function') {
            onAction();
          }
        });
        toastEl.appendChild(actionBtn);
      }

      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'ui-toast__close';
      closeBtn.setAttribute('aria-label', '关闭提示');
      closeBtn.textContent = '×';
      closeBtn.addEventListener('click', dismiss);
      toastEl.appendChild(closeBtn);

      toastEl.addEventListener('mouseenter', pauseTimer);
      toastEl.addEventListener('mouseleave', startTimer);
      toastEl.addEventListener('focusin', pauseTimer);
      toastEl.addEventListener('focusout', (event) => {
        if (!toastEl.contains(event.relatedTarget)) {
          startTimer();
        }
      });

      region.appendChild(toastEl);
      startTimer();

      return { dismiss };
    },
  };

  function getFocusableElements(container) {
    if (!container) return [];
    const selector = [
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled]):not([type="hidden"])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      'summary',
      '[tabindex]:not([tabindex="-1"])',
    ].join(', ');
    return Array.from(container.querySelectorAll(selector)).filter((node) => {
      if (!(node instanceof HTMLElement)) return false;
      if (node.closest('.hidden, [hidden]')) return false;
      const style = global.getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      return true;
    });
  }

  function isDialogOpen(el) {
    if (!el) return false;
    if (el.tagName === 'DIALOG') {
      return Boolean(el.open);
    }
    return !el.classList.contains('hidden') && !el.hasAttribute('hidden');
  }

  function getOrCreateState(el) {
    let state = dialogStates.get(el);
    if (!state) {
      state = {
        opener: null,
        onClose: null,
        isDirty: null,
        bound: false,
        promptingDiscard: false,
      };
      dialogStates.set(el, state);
    }
    return state;
  }

  function restoreOpenerFocus(state) {
    const opener = state?.opener;
    state.opener = null;
    if (opener && document.contains(opener) && typeof opener.focus === 'function') {
      try {
        opener.focus({ preventScroll: true });
      } catch (_) {
        try { opener.focus(); } catch (__) {}
      }
    }
  }

  function finishClose(el, reason) {
    const state = getOrCreateState(el);
    if (el.tagName === 'DIALOG') {
      if (el.open && typeof el.close === 'function') {
        el.close(reason || '');
      } else {
        el.removeAttribute('open');
      }
    } else {
      el.classList.add('hidden');
    }
    restoreOpenerFocus(state);
  }

  async function requestClose(el, reason = 'dismiss', force = false) {
    if (!el || !isDialogOpen(el)) return true;
    const state = getOrCreateState(el);
    if (!force && typeof state.isDirty === 'function' && state.isDirty()) {
      if (state.promptingDiscard) return false;
      state.promptingDiscard = true;
      try {
        const discard = await uiConfirm({
          title: '放弃未保存的更改？',
          message: '当前内容尚未保存，关闭后将丢失本次编辑。',
          confirmLabel: '放弃更改',
          cancelLabel: '继续编辑',
          tone: 'danger',
        });
        if (!discard) return false;
      } finally {
        state.promptingDiscard = false;
      }
    }
    if (typeof state.onClose === 'function') {
      const verdict = state.onClose({ reason, element: el });
      if (verdict === false) return false;
    }
    finishClose(el, reason);
    return true;
  }

  function trapFocus(el, event) {
    if (event.key !== 'Tab') return;
    const focusables = getFocusableElements(el);
    if (focusables.length === 0) {
      event.preventDefault();
      if (el.tabIndex < 0) el.tabIndex = -1;
      el.focus();
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey) {
      if (document.activeElement === first || !el.contains(document.activeElement)) {
        event.preventDefault();
        last.focus();
      }
    } else if (document.activeElement === last || !el.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    }
  }

  const uiDialog = {
    bindDialog(dialogEl, options = {}) {
      if (!dialogEl) return;
      const state = getOrCreateState(dialogEl);
      if (Object.prototype.hasOwnProperty.call(options, 'onClose')) {
        state.onClose = typeof options.onClose === 'function' ? options.onClose : null;
      }
      if (Object.prototype.hasOwnProperty.call(options, 'isDirty')) {
        state.isDirty = typeof options.isDirty === 'function' ? options.isDirty : null;
      }
      if (state.bound) return;
      state.bound = true;

      if (dialogEl.tagName === 'DIALOG') {
        dialogEl.addEventListener('cancel', (event) => {
          event.preventDefault();
          void requestClose(dialogEl, 'escape', false);
        });
        dialogEl.addEventListener('close', () => {
          restoreOpenerFocus(state);
        });
      }

      dialogEl.addEventListener('click', (event) => {
        if (event.target === dialogEl) {
          void requestClose(dialogEl, 'backdrop', false);
          return;
        }
        const closeTrigger = event.target.closest('[data-dialog-close]');
        if (closeTrigger && dialogEl.contains(closeTrigger)) {
          void requestClose(dialogEl, 'close-button', false);
        }
      });

      dialogEl.addEventListener('keydown', (event) => {
        if (!isDialogOpen(dialogEl)) return;
        if (event.key === 'Escape' && dialogEl.tagName !== 'DIALOG') {
          event.preventDefault();
          event.stopPropagation();
          void requestClose(dialogEl, 'escape', false);
          return;
        }
        trapFocus(dialogEl, event);
      });
    },

    open(el, focusSelector) {
      if (!el) return;
      const state = getOrCreateState(el);
      if (!state.bound) {
        uiDialog.bindDialog(el);
      }
      const active = document.activeElement;
      if (active instanceof HTMLElement && !el.contains(active)) {
        state.opener = active;
      }
      if (el.tagName === 'DIALOG') {
        if (!el.open) {
          if (typeof el.showModal === 'function') {
            el.showModal();
          } else {
            el.setAttribute('open', '');
          }
        }
      } else {
        el.classList.remove('hidden');
        el.removeAttribute('hidden');
      }

      let target = null;
      if (focusSelector) {
        target = el.querySelector(focusSelector);
      }
      if (!target) {
        target = getFocusableElements(el)[0] || el;
      }
      if (target instanceof HTMLElement) {
        if (target === el && el.tabIndex < 0) {
          el.tabIndex = -1;
        }
        try {
          target.focus({ preventScroll: true });
        } catch (_) {
          try { target.focus(); } catch (__) {}
        }
      }
    },

    close(el, { force = true } = {}) {
      if (!el) return;
      if (!force) {
        void requestClose(el, 'api', false);
        return;
      }
      const state = getOrCreateState(el);
      if (typeof state.onClose === 'function') {
        state.onClose({ reason: 'api', element: el });
      }
      finishClose(el, 'api');
    },
  };

  function ensureConfirmDialog() {
    let dialog = document.getElementById('ui-confirm-dialog');
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = 'ui-confirm-dialog';
    dialog.className = 'action-dialog ui-confirm-dialog';
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'ui-confirm-title');
    dialog.setAttribute('aria-describedby', 'ui-confirm-message');
    dialog.innerHTML = [
      '<div class="ui-confirm-header">',
      '  <h3 id="ui-confirm-title" class="ui-confirm-title">确认操作</h3>',
      '  <button type="button" class="ui-icon-button" data-ui-confirm-cancel aria-label="关闭确认框">×</button>',
      '</div>',
      '<p id="ui-confirm-message" class="ui-confirm-message"></p>',
      '<div class="ui-confirm-actions">',
      '  <button type="button" class="ui-button ui-button--secondary" data-ui-confirm-cancel>取消</button>',
      '  <button type="button" class="ui-button ui-button--danger" data-ui-confirm-accept>确认</button>',
      '</div>',
    ].join('\n');
    document.body.appendChild(dialog);
    return dialog;
  }

  function uiConfirm({
    title = '确认操作',
    message = '',
    confirmLabel = '确认',
    cancelLabel = '取消',
    tone = 'danger',
  } = {}) {
    if (typeof activeConfirmReject === 'function') {
      activeConfirmReject();
      activeConfirmReject = null;
    }

    const dialog = ensureConfirmDialog();
    const titleEl = dialog.querySelector('#ui-confirm-title');
    const messageEl = dialog.querySelector('#ui-confirm-message');
    const acceptBtn = dialog.querySelector('[data-ui-confirm-accept]');
    const cancelBtns = Array.from(dialog.querySelectorAll('[data-ui-confirm-cancel]'));
    const textCancelBtn = cancelBtns.find((btn) => !btn.classList.contains('ui-icon-button')) || cancelBtns[0];

    if (titleEl) titleEl.textContent = String(title || '确认操作');
    if (messageEl) messageEl.textContent = String(message || '');
    if (acceptBtn) {
      acceptBtn.textContent = String(confirmLabel || '确认');
      const toneClass = tone === 'primary' || tone === 'info'
        ? 'ui-button--primary'
        : (tone === 'neutral' || tone === 'secondary' ? 'ui-button--secondary' : 'ui-button--danger');
      acceptBtn.className = `ui-button ${toneClass}`;
    }
    if (textCancelBtn) {
      textCancelBtn.textContent = String(cancelLabel || '取消');
    }

    return new Promise((resolve) => {
      let settled = false;
      const settle = (value) => {
        if (settled) return;
        settled = true;
        activeConfirmReject = null;
        cleanup();
        uiDialog.close(dialog, { force: true });
        resolve(Boolean(value));
      };

      const onAccept = () => settle(true);
      const onCancel = () => settle(false);

      const cleanup = () => {
        acceptBtn?.removeEventListener('click', onAccept);
        cancelBtns.forEach((btn) => btn.removeEventListener('click', onCancel));
      };

      activeConfirmReject = () => settle(false);
      uiDialog.bindDialog(dialog, {
        onClose: ({ reason }) => {
          if (!settled && (reason === 'escape' || reason === 'backdrop')) {
            settled = true;
            activeConfirmReject = null;
            cleanup();
            resolve(false);
          }
        },
      });

      acceptBtn?.addEventListener('click', onAccept);
      cancelBtns.forEach((btn) => btn.addEventListener('click', onCancel));
      uiDialog.open(dialog, tone === 'primary' ? '[data-ui-confirm-accept]' : '[data-ui-confirm-cancel].ui-button');
    });
  }

  async function withButtonBusy(button, busyLabel, asyncFn) {
    if (typeof asyncFn !== 'function') return undefined;
    if (!button) return await asyncFn();
    if (button.dataset.uiBusy === '1') return undefined;

    const origHtml = button.innerHTML;
    const origDisabled = Boolean(button.disabled);
    button.dataset.uiBusy = '1';
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    if (typeof busyLabel === 'string' && busyLabel.length > 0) {
      button.textContent = busyLabel;
    }

    let keepDisabled = false;
    try {
      const result = await asyncFn();
      keepDisabled = Boolean(result && result.keepDisabled);
      return result;
    } finally {
      delete button.dataset.uiBusy;
      button.removeAttribute('aria-busy');
      if (keepDisabled) {
        button.disabled = true;
      } else {
        button.disabled = origDisabled;
        button.innerHTML = origHtml;
      }
    }
  }

  async function copyTextRaw(text) {
    if (global.navigator?.clipboard && typeof global.navigator.clipboard.writeText === 'function') {
      try {
        await global.navigator.clipboard.writeText(text);
        return true;
      } catch (_) { /* Fallback to execCommand copy below. */ }
    }
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.top = '-9999px';
      textarea.style.left = '-9999px';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand('copy');
      textarea.remove();
      return Boolean(copied);
    } catch (_) {
      return false;
    }
  }

  async function copyWithFeedback(text, button, { copiedLabel = '已复制', duration = DEFAULT_COPY_DURATION } = {}) {
    const str = String(text ?? '');
    const copied = await copyTextRaw(str);
    if (!copied || !button) return copied;

    const pendingTimer = copyTimers.get(button);
    if (pendingTimer) {
      global.clearTimeout(pendingTimer);
    }
    if (!copyOriginalHtml.has(button)) {
      copyOriginalHtml.set(button, button.innerHTML);
    }

    button.classList.add('is-copied');
    const check = document.createElement('span');
    check.className = 'ui-copied-check';
    check.setAttribute('aria-hidden', 'true');
    check.textContent = '✓';
    const label = document.createElement('span');
    label.textContent = String(copiedLabel || '已复制');
    button.replaceChildren(check, label);

    const timerId = global.setTimeout(() => {
      copyTimers.delete(button);
      button.classList.remove('is-copied');
      if (copyOriginalHtml.has(button)) {
        button.innerHTML = copyOriginalHtml.get(button);
        copyOriginalHtml.delete(button);
      }
    }, Math.max(400, Number(duration) || DEFAULT_COPY_DURATION));
    copyTimers.set(button, timerId);

    return true;
  }

  global.uiToast = uiToast;
  global.uiConfirm = uiConfirm;
  global.withButtonBusy = withButtonBusy;
  global.copyWithFeedback = copyWithFeedback;
  global.uiDialog = uiDialog;
})(window);
