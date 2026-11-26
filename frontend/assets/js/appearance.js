/* Run in the shared head, before CSS, so saved theme, scheme, and sidebar state apply before first paint. */
(function initializeAppearance() {
  const legacyKey = 'cda_appearance';
  const storageKey = 'cda_appearance_v2';
  const colorModeKey = 'cda_color_mode_v1';
  const sidebarCollapsedKey = 'cda_sidebar_collapsed_v1';
  const root = document.documentElement;
  const darkMedia = typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null;
  const reducedMotionMedia = typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : null;
  const THEME_COLOR_META = {
    'blue:light': '#f7f8fa',
    'moss:light': '#f1f1e9',
    'blue:dark': '#0d1117',
    'moss:dark': '#111510',
  };

  let themeSwitchTimer = null;

  const normalizeTheme = (value) => (value === 'moss' ? 'moss' : 'blue');
  const normalizeColorMode = (value) => (value === 'light' || value === 'dark' ? value : 'system');

  function resolveScheme(colorMode) {
    if (colorMode === 'dark') return 'dark';
    if (colorMode === 'light') return 'light';
    return darkMedia && darkMedia.matches ? 'dark' : 'light';
  }

  function syncThemeColorMeta(theme, resolvedScheme) {
    const meta = document.getElementById('theme-color-meta')
      || document.querySelector('meta[name="theme-color"]');
    if (!meta) return;
    const color = THEME_COLOR_META[`${theme}:${resolvedScheme}`] || '#f7f8fa';
    meta.setAttribute('content', color);
  }

  function beginThemeTransition() {
    if (reducedMotionMedia && reducedMotionMedia.matches) return;
    root.classList.add('is-theme-switching');
    if (themeSwitchTimer) {
      window.clearTimeout(themeSwitchTimer);
    }
    themeSwitchTimer = window.setTimeout(() => {
      root.classList.remove('is-theme-switching');
      themeSwitchTimer = null;
    }, 240);
  }

  function syncControls() {
    const activeTheme = root.dataset.theme || 'blue';
    const activeMode = root.dataset.colorMode || 'system';
    const resolvedScheme = root.dataset.resolvedScheme || 'light';

    document.querySelectorAll('button[data-appearance-theme]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.appearanceTheme === activeTheme));
    });

    const modeButtons = document.querySelectorAll('button[data-color-mode]');
    modeButtons.forEach((button) => {
      const active = button.dataset.colorMode === activeMode;
      button.setAttribute('aria-pressed', String(active));
      button.classList.toggle('is-active', active);
    });

    const segmented = document.querySelector('.appearance-mode-segmented');
    if (segmented && window.uiMotion && typeof window.uiMotion.glideIndicator === 'function') {
      const activeBtn = segmented.querySelector(`button[data-color-mode="${activeMode}"]`);
      if (activeBtn) {
        window.uiMotion.glideIndicator(segmented, activeBtn);
      }
    }

    document.querySelectorAll('button[data-color-mode-toggle]').forEach((button) => {
      const isDark = resolvedScheme === 'dark';
      button.setAttribute('aria-pressed', String(isDark));
      button.dataset.resolvedScheme = resolvedScheme;
      button.setAttribute('aria-label', isDark ? '切换为浅色外观' : '切换为深色外观');
      button.setAttribute('title', isDark ? '切换为浅色外观' : '切换为深色外观');
      const label = button.querySelector('[data-color-mode-toggle-label]');
      if (label) {
        label.textContent = isDark ? '浅色' : '深色';
      }
    });
  }

  function apply(themeValue, colorModeValue, options = {}) {
    if (options.animate) {
      beginThemeTransition();
    }
    const theme = normalizeTheme(themeValue !== undefined ? themeValue : root.dataset.theme);
    const colorMode = normalizeColorMode(colorModeValue !== undefined ? colorModeValue : root.dataset.colorMode);
    const resolvedScheme = resolveScheme(colorMode);

    root.dataset.theme = theme;
    root.dataset.colorMode = colorMode;
    root.dataset.resolvedScheme = resolvedScheme;
    syncThemeColorMeta(theme, resolvedScheme);
    syncControls();
  }

  let savedTheme;
  let savedColorMode;
  let savedSidebarCollapsed;
  try {
    localStorage.removeItem(legacyKey);
    savedTheme = localStorage.getItem(storageKey);
    savedColorMode = localStorage.getItem(colorModeKey);
    savedSidebarCollapsed = localStorage.getItem(sidebarCollapsedKey);
  } catch (_) { /* Storage may be disabled. */ }

  const isMobileViewport = typeof window.matchMedia === 'function'
    && window.matchMedia('(max-width: 960px)').matches;
  if (savedSidebarCollapsed === '1' && !isMobileViewport) {
    root.dataset.sidebarCollapsed = '1';
  } else {
    root.dataset.sidebarCollapsed = '0';
  }

  apply(savedTheme, savedColorMode || 'system');

  document.addEventListener('DOMContentLoaded', () => {
    syncThemeColorMeta(root.dataset.theme || 'blue', root.dataset.resolvedScheme || 'light');
    syncControls();
  });

  document.addEventListener('click', (event) => {
    const themeBtn = event.target.closest('button[data-appearance-theme]');
    if (themeBtn) {
      apply(themeBtn.dataset.appearanceTheme, root.dataset.colorMode, { animate: true });
      let persisted = true;
      try { localStorage.setItem(storageKey, root.dataset.theme); } catch (_) { persisted = false; }
      const status = document.getElementById('appearance-status');
      if (status) {
        status.textContent = (root.dataset.theme === 'moss' ? '已切换为苔绿' : '已切换为蓝白')
          + (persisted ? '，此浏览器会记住你的选择。' : '。浏览器未允许保存，刷新后将恢复默认外观。');
      }
      return;
    }

    const modeBtn = event.target.closest('button[data-color-mode]');
    if (modeBtn) {
      apply(root.dataset.theme, modeBtn.dataset.colorMode, { animate: true });
      let persisted = true;
      try { localStorage.setItem(colorModeKey, root.dataset.colorMode); } catch (_) { persisted = false; }
      const status = document.getElementById('appearance-status');
      if (status) {
        const modeLabels = {
          system: '已切换为跟随系统',
          light: '已切换为浅色外观',
          dark: '已切换为深色外观',
        };
        const prefix = modeLabels[root.dataset.colorMode] || '已更新明暗外观';
        status.textContent = prefix + (persisted ? '，此浏览器会记住你的选择。' : '。浏览器未允许保存，刷新后将恢复默认外观。');
      }
      return;
    }

    const quickToggle = event.target.closest('button[data-color-mode-toggle]');
    if (quickToggle) {
      const nextMode = root.dataset.resolvedScheme === 'dark' ? 'light' : 'dark';
      apply(root.dataset.theme, nextMode, { animate: true });
      try { localStorage.setItem(colorModeKey, root.dataset.colorMode); } catch (_) { /* Storage may be disabled. */ }
    }
  });

  const handleOsSchemeChange = () => {
    if ((root.dataset.colorMode || 'system') === 'system') {
      apply(root.dataset.theme, 'system', { animate: false });
    }
  };
  if (darkMedia) {
    if (typeof darkMedia.addEventListener === 'function') {
      darkMedia.addEventListener('change', handleOsSchemeChange);
    } else if (typeof darkMedia.addListener === 'function') {
      darkMedia.addListener(handleOsSchemeChange);
    }
  }

  window.addEventListener('storage', (event) => {
    if (event.key === storageKey) {
      apply(event.newValue, root.dataset.colorMode);
    } else if (event.key === colorModeKey) {
      apply(root.dataset.theme, event.newValue || 'system');
    } else if (event.key === null) {
      apply('blue', 'system');
    }
  });

  window.cdaAppearance = {
    apply,
    syncControls,
  };
})();
