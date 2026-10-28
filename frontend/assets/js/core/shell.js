/* Dashboard: core/shell.js; loaded in index.html order. */
    const dashboardShell = document.getElementById('dashboard-shell');
    const workspaceStack = document.getElementById('workspace-stack');
    const academicSidebar = document.getElementById('academic-sidebar');
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const sidebarCollapseToggle = document.getElementById('sidebar-collapse-toggle');
    const mobileSidebarQuery = window.matchMedia('(max-width: 960px)');

    function syncSidebarState() {
      const isMobile = mobileSidebarQuery.matches;
      const isOpen = dashboardShell.classList.contains('mobile-nav-open');
      academicSidebar.setAttribute('aria-hidden', String(isMobile && !isOpen));
      mobileMenuToggle.setAttribute('aria-expanded', String(isMobile && isOpen));
      mobileMenuToggle.setAttribute('aria-label', isOpen ? '关闭菜单' : '打开菜单');
    }

    function toggleMobileMenu() {
      dashboardShell.classList.toggle('mobile-nav-open');
      syncSidebarState();
    }

    function closeMobileMenu() {
      dashboardShell.classList.remove('mobile-nav-open');
      syncSidebarState();
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
        closeMobileMenu();
        return;
      }
      const isCollapsed = dashboardShell.classList.toggle('sidebar-collapsed');
      sidebarCollapseToggle.setAttribute('aria-expanded', String(!isCollapsed));
      sidebarCollapseToggle.setAttribute('aria-label', isCollapsed ? '展开侧栏' : '收起侧栏');
    }

    function switchDashboardView(viewName, { scrollToTop = true } = {}) {
      if (!document.getElementById(`dashboard-view-${viewName}`)) viewName = 'overview';
      document.querySelectorAll('[data-view-panel]').forEach((panel) => {
        panel.classList.toggle('hidden', panel.dataset.viewPanel !== viewName);
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
      document.getElementById('dashboard-right-rail').classList.toggle('hidden', viewName !== 'overview');
      workspaceStack.classList.toggle('is-focus-view', viewName !== 'overview');
      dashboardShell.classList.toggle('schedule-workspace-active', viewName === 'schedule');
      let loadPromise = Promise.resolve();
      if (viewName === 'schedule') loadPromise = loadScheduleManager();
      if (viewName === 'projects') loadPromise = loadProjects();
      if (viewName === 'connections') {
        if (typeof selectConnectionPlatform === 'function') {
          selectConnectionPlatform(activeConnectionPlatform);
        }
      }
      if (viewName === 'agent') {
        if (typeof loadAgentSettings === 'function') {
          loadPromise = loadAgentSettings();
        }
      } else {
        if (typeof clearAgentTokenPlaintext === 'function') {
          clearAgentTokenPlaintext();
        }
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
      closeMobileMenu();
      if (scrollToTop) window.scrollTo({ top: 0, behavior: 'smooth' });
      return loadPromise;
    }

    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-open-view]');
      if (!button) return;
      const anchor = button.getAttribute('href');
      const target = anchor?.startsWith('#') ? document.getElementById(anchor.slice(1)) : null;
      if (target && button.dataset.openView === 'guide') {
        event.preventDefault();
        switchDashboardView('guide', { scrollToTop: false });
        target.scrollIntoView({ block: 'start', behavior: 'instant' });
        target.querySelector('h2')?.focus({ preventScroll: true });
      } else {
        switchDashboardView(button.dataset.openView);
      }
    });

    document.querySelectorAll('[data-dashboard-view]').forEach((button) => {
      button.addEventListener('click', () => switchDashboardView(button.dataset.dashboardView));
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closeMobileMenu();
      }
    });
    if (mobileSidebarQuery.addEventListener) {
      mobileSidebarQuery.addEventListener('change', closeMobileMenu);
    } else {
      mobileSidebarQuery.addListener(closeMobileMenu);
    }
    syncSidebarState();

