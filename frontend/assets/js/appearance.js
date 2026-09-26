/* Run in the shared head, before CSS, so a saved theme is used on first paint. */
(function initializeAppearance() {
  const storageKey = 'cda_appearance';
  const root = document.documentElement;
  const normalize = (value) => value === 'moss' ? 'moss' : 'blue';

  function apply(value) {
    root.dataset.theme = normalize(value);
    document.querySelectorAll('[data-appearance-theme]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.appearanceTheme === root.dataset.theme));
    });
  }

  let saved;
  try { saved = localStorage.getItem(storageKey); } catch (_) { /* Storage may be disabled. */ }
  apply(saved);
  document.addEventListener('DOMContentLoaded', () => apply(root.dataset.theme));
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-appearance-theme]');
    if (!button) return;
    apply(button.dataset.appearanceTheme);
    let persisted = true;
    try { localStorage.setItem(storageKey, root.dataset.theme); } catch (_) { persisted = false; }
    const status = document.getElementById('appearance-status');
    if (status) status.textContent = (root.dataset.theme === 'moss' ? '已切换为苔绿' : '已切换为蓝白')
      + (persisted ? '，此浏览器会记住你的选择。' : '。浏览器未允许保存，刷新后将恢复默认外观。');
  });
  window.addEventListener('storage', (event) => {
    if (event.key === storageKey || event.key === null) apply(event.newValue);
  });
})();
