/* Dashboard: core/shell.js; loaded in index.html order. */
const SIDEBAR_COLLAPSED_KEY = 'cda_sidebar_collapsed_v1';
const dashboardShell = document.getElementById('dashboard-shell');
const workspaceStack = document.getElementById('workspace-stack');
const academicSidebar = document.getElementById('academic-sidebar');
const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
const sidebarCollapseToggle = document.getElementById('sidebar-collapse-toggle');
const mobileSidebarQuery = window.matchMedia('(max-width: 960px)');

let activeDashboardView = 'overview';
let mobileMenuOpener = null;

function getSidebarFocusables() {
  if (!academicSidebar) return [];
  const selector = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';
  return Array.from(academicSidebar.querySelectorAll(selector)).filter((node) => {
    if (!(node instanceof HTMLElement)) return false;
    if (node.closest('.hidden, [hidden]')) return false;
    const style = window.getComputedStyle(node);
    return style.display !== 'none' && style.visibility !== 'hidden';
  });
}

function syncSidebarCollapseUi(isCollapsed) {
  if (!dashboardShell) return;
  dashboardShell.classList.toggle('sidebar-collapsed', Boolean(isCollapsed));
  document.documentElement.dataset.sidebarCollapsed = isCollapsed ? '1' : '0';
  if (sidebarCollapseToggle) {
    sidebarCollapseToggle.setAttribute('aria-expanded', String(!isCollapsed));
    sidebarCollapseToggle.setAttribute('aria-label', isCollapsed ? '展开侧栏' : '收起侧栏');
  }
}

function restoreSidebarCollapsePreference() {
  let saved = null;
  try {
    saved = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
  } catch (_) { /* Storage may be disabled. */ }
  const isCollapsed = saved === '1' && !mobileSidebarQuery.matches;
  syncSidebarCollapseUi(isCollapsed);
}

function syncSidebarState() {
  if (!dashboardShell || !academicSidebar || !mobileMenuToggle) return;
  const isMobile = mobileSidebarQuery.matches;
  const isOpen = dashboardShell.classList.contains('mobile-nav-open');
  const drawerActive = isMobile && isOpen;
  academicSidebar.setAttribute('aria-hidden', String(isMobile && !isOpen));
  mobileMenuToggle.setAttribute('aria-expanded', String(drawerActive));
  mobileMenuToggle.setAttribute('aria-label', isOpen ? '关闭菜单' : '打开菜单');
  document.body.classList.toggle('mobile-nav-locked', drawerActive);
}

function toggleMobileMenu() {
  if (!dashboardShell) return;
  const willOpen = !dashboardShell.classList.contains('mobile-nav-open');
  if (willOpen) {
    mobileMenuOpener = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : mobileMenuToggle;
    dashboardShell.classList.add('mobile-nav-open');
    syncSidebarState();
    const firstFocusable = getSidebarFocusables()[0] || sidebarCollapseToggle || academicSidebar;
    if (firstFocusable && typeof firstFocusable.focus === 'function') {
      try {
        firstFocusable.focus({ preventScroll: true });
      } catch (_) {
        firstFocusable.focus();
      }
    }
  } else {
    closeMobileMenu({ restoreFocus: true });
  }
}

function closeMobileMenu({ restoreFocus = false } = {}) {
  if (!dashboardShell) return;
  const wasOpen = dashboardShell.classList.contains('mobile-nav-open');
  dashboardShell.classList.remove('mobile-nav-open');
  syncSidebarState();
  if (wasOpen && restoreFocus) {
    const target = (mobileMenuOpener && document.contains(mobileMenuOpener))
      ? mobileMenuOpener
      : mobileMenuToggle;
    mobileMenuOpener = null;
    if (target && typeof target.focus === 'function') {
      try {
        target.focus({ preventScroll: true });
      } catch (_) {
        target.focus();
      }
    }
  } else if (!wasOpen) {
    mobileMenuOpener = null;
  }
}

const feedbackSemanticClasses = [
  'ui-feedback--neutral',
  'ui-feedback--info',
  'ui-feedback--success',
  'ui-feedback--warning',
  'ui-feedback--danger',
];
const statusSemanticClasses = [
  'ui-status--neutral',
  'ui-status--info',
  'ui-status--success',
  'ui-status--warning',
  'ui-status--danger',
];

function applyFeedbackSemantic(element, semantic = 'neutral') {
  if (!element) return;
  element.classList.remove(...feedbackSemanticClasses, 'is-error');
  element.classList.add(`ui-feedback--${semantic}`);
  element.setAttribute('role', semantic === 'danger' ? 'alert' : 'status');
}

function applyStatusSemantic(element, semantic = 'neutral') {
  if (!element) return;
  element.classList.remove(...statusSemanticClasses, 'connected', 'attention');
  element.classList.add(`ui-status--${semantic}`);
  if (semantic === 'success') element.classList.add('connected');
  if (semantic === 'warning' || semantic === 'danger') element.classList.add('attention');
}

function toggleSidebarCollapse() {
  if (mobileSidebarQuery.matches) {
    closeMobileMenu({ restoreFocus: true });
    return;
  }
  const isCollapsed = !dashboardShell.classList.contains('sidebar-collapsed');
  syncSidebarCollapseUi(isCollapsed);
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, isCollapsed ? '1' : '0');
  } catch (_) { /* Storage may be disabled. */ }
}

function replayViewEnterAnimation(panel) {
  if (!panel) return;
  if (window.uiMotion && window.uiMotion.prefersReducedMotion()) {
    panel.classList.remove('is-view-entering');
    return;
  }
  panel.classList.remove('is-view-entering');
  void panel.offsetWidth;
  panel.classList.add('is-view-entering');
  const clearEnter = () => panel.classList.remove('is-view-entering');
  panel.addEventListener('animationend', clearEnter, { once: true });
  window.setTimeout(clearEnter, 280);
}

function updateUrlHashForView(viewName, explicitHash = '') {
  if (!window.history || typeof window.history.pushState !== 'function') return;
  const basePath = `${window.location.pathname}${window.location.search}`;
  const targetHash = explicitHash
    ? (explicitHash.startsWith('#') ? explicitHash : `#${explicitHash}`)
    : (viewName === 'overview' ? '' : `#${viewName}`);
  if (window.location.hash === targetHash) return;
  const nextUrl = `${basePath}${targetHash}`;
  if (viewName === 'overview' && !targetHash && window.location.hash === '#overview') {
    window.history.replaceState(null, '', nextUrl);
  } else {
    window.history.pushState(null, '', nextUrl);
  }
}

function switchDashboardView(viewName, { scrollToTop = true, updateHash = true, explicitHash = '' } = {}) {
  if (!document.getElementById(`dashboard-view-${viewName}`)) viewName = 'overview';
  const viewChanged = viewName !== activeDashboardView;
  activeDashboardView = viewName;

  document.querySelectorAll('[data-view-panel]').forEach((panel) => {
    const isTarget = panel.dataset.viewPanel === viewName;
    const wasHidden = panel.classList.contains('hidden');
    panel.classList.toggle('hidden', !isTarget);
    if (isTarget && (wasHidden || viewChanged)) {
      replayViewEnterAnimation(panel);
    }
  });

  document.querySelectorAll('[data-dashboard-view]').forEach((button) => {
    const isActive = button.dataset.dashboardView === viewName;
    button.classList.toggle('is-active', isActive);
    if (isActive) {
      button.setAttribute('aria-current', 'page');
    } else {
      button.removeAttribute('aria-current');
    }
  });

  const rightRail = document.getElementById('dashboard-right-rail');
  if (rightRail) rightRail.classList.toggle('hidden', viewName !== 'overview');
  if (workspaceStack) workspaceStack.classList.toggle('is-focus-view', viewName !== 'overview');
  if (dashboardShell) dashboardShell.classList.toggle('schedule-workspace-active', viewName === 'schedule');

  if (updateHash) {
    updateUrlHashForView(viewName, explicitHash);
  }

  let loadPromise = Promise.resolve();
  if (viewName === 'schedule' && typeof loadScheduleManager === 'function') {
    loadPromise = loadScheduleManager();
  } else if (viewName === 'projects' && typeof loadProjects === 'function') {
    loadPromise = loadProjects();
  } else if (viewName === 'connections' && typeof selectConnectionPlatform === 'function') {
    selectConnectionPlatform(typeof activeConnectionPlatform !== 'undefined' ? activeConnectionPlatform : 'canvas');
  } else if (viewName === 'calendar' && typeof loadCalendarSubscription === 'function') {
    loadPromise = loadCalendarSubscription();
  } else if (viewName === 'agent' && typeof loadAgentSettings === 'function') {
    loadPromise = loadAgentSettings();
  }

  document.querySelectorAll('.mobile-nav-item').forEach((tab) => {
    const isActive = tab.dataset.mobileTab === viewName;
    tab.classList.toggle('is-active', isActive);
    if (isActive) {
      tab.setAttribute('aria-current', 'page');
    } else {
      tab.removeAttribute('aria-current');
    }
  });

  closeMobileMenu({ restoreFocus: false });
  if (scrollToTop) {
    const reduced = window.uiMotion && window.uiMotion.prefersReducedMotion();
    window.scrollTo({ top: 0, behavior: reduced ? 'instant' : 'smooth' });
  }
  return loadPromise;
}

function focusTargetElement(selector) {
  if (!selector) return;
  let target = document.querySelector(selector);
  if (!target) return;

  // If the target sits inside the collapsed mobile composer drawer, expand it first.
  const mobileAddDrawer = target.closest('#mobile-add-drawer');
  const mobileAddToggle = document.getElementById('mobile-add-toggle');
  if (mobileAddDrawer && mobileAddToggle && !mobileAddDrawer.classList.contains('is-open')) {
    const isHidden = window.getComputedStyle(mobileAddDrawer).display === 'none'
      || mobileAddDrawer.classList.contains('hidden');
    if (isHidden) {
      mobileAddToggle.click();
    }
  }

  target = document.querySelector(selector);
  if (!target || typeof target.focus !== 'function') return;
  try {
    target.scrollIntoView({ block: 'center', behavior: 'instant' });
  } catch (_) {}
  try {
    target.focus({ preventScroll: true });
  } catch (_) {
    target.focus();
  }
}

function syncViewFromLocationHash({ initial = false } = {}) {
  const rawHash = window.location.hash || '';
  if (!rawHash || rawHash === '#') {
    if (!initial && activeDashboardView !== 'overview') {
      switchDashboardView('overview', { scrollToTop: false, updateHash: false });
    }
    return;
  }
  const slug = rawHash.slice(1);
  if (slug.startsWith('guide-')) {
    const anchorTarget = document.getElementById(slug);
    switchDashboardView('guide', { scrollToTop: false, updateHash: false });
    if (anchorTarget) {
      anchorTarget.scrollIntoView({ block: 'start', behavior: 'instant' });
      anchorTarget.querySelector('h2')?.focus({ preventScroll: true });
    }
    return;
  }
  if (document.getElementById(`dashboard-view-${slug}`)) {
    if (!initial || slug !== 'overview') {
      switchDashboardView(slug, { scrollToTop: !initial, updateHash: false });
    }
  } else if (!initial && activeDashboardView !== 'overview') {
    switchDashboardView('overview', { scrollToTop: false, updateHash: false });
  }
}

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-open-view]');
  if (!button) return;
  const viewName = button.dataset.openView;
  const anchor = button.getAttribute('href');
  const target = anchor?.startsWith('#') ? document.getElementById(anchor.slice(1)) : null;
  const focusSelector = button.dataset.focusTarget;

  if (target && viewName === 'guide') {
    event.preventDefault();
    switchDashboardView('guide', { scrollToTop: false, explicitHash: anchor });
    target.scrollIntoView({ block: 'start', behavior: 'instant' });
    target.querySelector('h2')?.focus({ preventScroll: true });
    return;
  }

  const switched = switchDashboardView(viewName, { scrollToTop: !focusSelector });
  if (focusSelector) {
    Promise.resolve(switched).then(() => {
      window.requestAnimationFrame(() => focusTargetElement(focusSelector));
    });
  }
});

document.querySelectorAll('[data-dashboard-view]').forEach((button) => {
  button.addEventListener('click', () => switchDashboardView(button.dataset.dashboardView));
});

document.addEventListener('keydown', (event) => {
  if (!mobileSidebarQuery.matches || !dashboardShell?.classList.contains('mobile-nav-open')) {
    return;
  }
  if (event.key === 'Escape') {
    event.preventDefault();
    closeMobileMenu({ restoreFocus: true });
    return;
  }
  if (event.key === 'Tab') {
    const focusables = getSidebarFocusables();
    if (focusables.length === 0) {
      event.preventDefault();
      academicSidebar?.focus();
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey) {
      if (document.activeElement === first || !academicSidebar?.contains(document.activeElement)) {
        event.preventDefault();
        last.focus();
      }
    } else if (document.activeElement === last || !academicSidebar?.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    }
  }
});

window.addEventListener('hashchange', () => {
  syncViewFromLocationHash({ initial: false });
});

if (mobileSidebarQuery.addEventListener) {
  mobileSidebarQuery.addEventListener('change', () => {
    closeMobileMenu({ restoreFocus: false });
    restoreSidebarCollapsePreference();
  });
} else {
  mobileSidebarQuery.addListener(() => {
    closeMobileMenu({ restoreFocus: false });
    restoreSidebarCollapsePreference();
  });
}

restoreSidebarCollapsePreference();
syncSidebarState();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => syncViewFromLocationHash({ initial: true }));
} else {
  window.setTimeout(() => syncViewFromLocationHash({ initial: true }), 0);
}
