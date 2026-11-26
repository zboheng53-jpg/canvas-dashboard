/* Dashboard: features/settings.js; loaded in index.html order. */
async function revokeOtherSessions() {
  const input = document.getElementById('revoke-sessions-password');
  const button = document.getElementById('revoke-sessions-button');
  const status = document.getElementById('revoke-sessions-status');
  if (!input || !button || !status) return;

  const password = input.value;
  if (!password) {
    status.textContent = '请输入当前网站密码。';
    applyFeedbackSemantic(status, 'danger');
    window.uiMotion?.nudgeError(input);
    input.focus();
    return;
  }

  status.textContent = '正在验证当前网站密码…';
  applyFeedbackSemantic(status, 'info');

  await window.withButtonBusy(button, '正在验证…', async () => {
    try {
      const data = await dashboardApi.requestJson('/api/account/sessions/revoke-others', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      input.value = '';
      const message = data.message || '已退出其他设备';
      status.textContent = message;
      applyFeedbackSemantic(status, 'success');
      window.uiToast?.show(message, { tone: 'success' });
    } catch (error) {
      status.textContent = error.message || '操作失败';
      applyFeedbackSemantic(status, 'danger');
      window.uiMotion?.nudgeError(button.closest('form') || input);
    }
  });
}

let lastSessionActivityRequestAt = 0;
function refreshSessionActivity() {
  const now = Date.now();
  if (now - lastSessionActivityRequestAt < 12 * 60 * 60 * 1000) return;
  lastSessionActivityRequestAt = now;
  fetch('/api/session/activity', { method: 'POST' }).catch(() => {
    lastSessionActivityRequestAt = 0;
  });
}
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) refreshSessionActivity();
});
window.addEventListener('focus', refreshSessionActivity);

function syncDeleteAccountForm() {
  const password = document.getElementById('account-delete-password');
  const confirmation = document.getElementById('account-delete-confirmation');
  const button = document.querySelector('.settings-danger-button');
  const status = document.getElementById('account-delete-status');
  if (!password || !confirmation || !button || !status) return;

  const trimmedConfirmation = confirmation.value.trim();
  const ready = Boolean(password.value) && trimmedConfirmation === '永久删除';
  button.disabled = !ready;
  status.textContent = ready
    ? '确认信息已完整。点击按钮后将再次请求最终确认。'
    : trimmedConfirmation && trimmedConfirmation !== '永久删除'
      ? '确认文字需准确输入“永久删除”。'
      : '完成两项确认后，才能永久删除账户。';
  applyFeedbackSemantic(status, ready ? 'warning' : 'neutral');
}

async function deleteCurrentAccount() {
  const passwordEl = document.getElementById('account-delete-password');
  const confirmationEl = document.getElementById('account-delete-confirmation');
  const status = document.getElementById('account-delete-status');
  const button = document.querySelector('.settings-danger-button');
  if (!passwordEl || !confirmationEl || !status || !button) return;

  const password = passwordEl.value;
  const confirmation = confirmationEl.value.trim();
  if (!password || confirmation !== '永久删除') {
    syncDeleteAccountForm();
    window.uiMotion?.nudgeError(button.closest('form') || button);
    return;
  }

  const confirmed = await window.uiConfirm({
    title: '确认永久删除账户？',
    message: '此操作不可撤销。确认永久删除当前账户及全部在线数据？',
    confirmLabel: '永久删除账户',
    cancelLabel: '保留账户',
    tone: 'danger',
  });
  if (!confirmed) return;

  status.textContent = '正在停止同步并删除在线数据…';
  applyFeedbackSemantic(status, 'info');

  await window.withButtonBusy(button, '正在删除…', async () => {
    try {
      await dashboardApi.requestJson('/api/account', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password, confirmation }),
      });
      window.location.href = '/login';
      return { keepDisabled: true };
    } catch (error) {
      status.textContent = error.message || '删除失败，请检查当前密码与确认文字。';
      applyFeedbackSemantic(status, 'danger');
      window.uiMotion?.nudgeError(button.closest('form') || button);
      return { keepDisabled: false };
    }
  });
}

(function initializeSettingsFeature() {
  const form = document.getElementById('account-delete-form');
  form?.addEventListener('submit', (event) => {
    event.preventDefault();
    deleteCurrentAccount();
  });
  document.getElementById('account-delete-password')?.addEventListener('input', syncDeleteAccountForm);
  document.getElementById('account-delete-confirmation')?.addEventListener('input', syncDeleteAccountForm);
  document.querySelectorAll('#dashboard-view-settings details.settings-disclosure').forEach((detailsEl) => {
    window.uiMotion?.enhanceDisclosure(detailsEl);
  });
})();
