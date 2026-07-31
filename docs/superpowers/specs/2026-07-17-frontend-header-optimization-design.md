# Canvas Dashboard 前端界面重构设计文档

## 概述 (Overview)
本文档旨在对 Canvas Dashboard 前端主界面（`templates/index.html` 与 `static/style.css`）进行精细化重构优化。针对主待办卡片右上角原有的“更新时间戳、刷新按钮、平台登录入口、账号动作”三层混乱堆叠问题，进行去冗余与结构化重构；同时保留原版温暖素雅的极简设计风格（Warm Minimalist Style），优化列表右侧的对齐与排版。

---

## 优化目标 (Goals)
1. **去冗余 (Remove Redundancy)**：
   - 彻底移除界面顶部的“已更新时间戳”和“刷新按钮”（`#list-updated` 与 `#btn-refresh`）。由于部署在服务器后系统具备 24 小时自动定时刷新的能力，不再需要人工刷新提示与控制。
2. **重构卡片头部右侧 (Restructure Header Actions)**：
   - 将原来纵向 3 层错位堆叠的区域，收纳为**单行水平对齐的两个极简气泡按钮**：
     1. **关联平台折叠按钮**：`[ ⚙️ 关联平台 ▶ ]`（带 `▶`/`▼` 折叠指示箭头），点击切换展开/收起下方的 4 个第三方平台关联状态卡片（Canvas、好课、智学盟、智慧树）。
     2. **账号下拉菜单**：`[ 👤 <username> ▾ ]`，点击或悬浮展开精致下拉菜单，收纳原本散落的 `📅 订阅苹果日历` 与 `🚪 退出登录`。
3. **保持传统结构与素雅风格 (Preserve Original Layout & Warm Theme)**：
   - `待完成 X 项` 与 `即将到期 Y 项` 统计栏保留在原始位置（输入框下方、分隔线上方）。
   - 维持 `#faf9f7` 浅色背景与优雅留白，去除所有炫目发光与高饱和度彩块。
4. **统一列表右侧栅格对齐 (Align Todo List Actions)**：
   - 优化 `templates/index.html` 中的待办事项列表右侧元素（截止日期、展开子任务箭头 `▶`、置顶 ⚑、隐藏 ✕、删除 🗑），使其右边界齐平整洁。

---

## 详细设计 (Detailed Design)

### 1. 结构变动 (`templates/index.html`)

```html
<!-- 原有混乱的三层结构 (Before) -->
<div class="header-right">
  <div class="header-info">
    <span class="last-updated" id="list-updated"></span>
    <button class="btn-refresh" id="btn-refresh" title="刷新">&#x21bb;</button>
  </div>
  <button type="button" class="login-trigger" onclick="toggleLoginCards()">
    <span id="login-trigger-label">系统登录</span>
    <span class="login-trigger-arrow" id="login-trigger-arrow">&#x25b6;</span>
  </button>
  <div class="account-row">
    <span>{{ username }}</span>
    {% if apple_calendar_enabled %}
    <a href="#" onclick="createCalendarSubscription();return false;">苹果日历</a>
    {% endif %}
    <a href="#" onclick="doLogout();return false;">退出登录</a>
  </div>
</div>

<!-- 重构后的单行平铺结构 (After) -->
<div class="header-right-actions">
  <!-- 关联平台折叠按钮 -->
  <button type="button" class="btn-pill-action" id="platform-toggle-btn" onclick="toggleLoginCards()">
    <span class="pill-icon">⚙️</span>
    <span>关联平台</span>
    <span class="pill-arrow" id="login-trigger-arrow">&#x25b6;</span>
  </button>

  <!-- 用户账号下拉气泡 -->
  <div class="user-menu-dropdown">
    <button type="button" class="btn-pill-action user-pill-trigger">
      <span class="pill-icon">👤</span>
      <span>{{ username }}</span>
      <span class="pill-arrow">&#x25bc;</span>
    </button>
    <div class="user-dropdown-menu">
      {% if apple_calendar_enabled %}
      <a href="#" class="dropdown-item" onclick="createCalendarSubscription();return false;">
        <span class="item-icon">📅</span> 订阅苹果日历
      </a>
      <div class="dropdown-divider"></div>
      {% endif %}
      <a href="#" class="dropdown-item danger-item" onclick="doLogout();return false;">
        <span class="item-icon">🚪</span> 退出登录
      </a>
    </div>
  </div>
</div>
```

### 2. 样式规范 (`static/style.css`)

```css
/* Header Right Actions */
.header-right-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.btn-pill-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-pill-action:hover {
  background: var(--border-light);
  border-color: var(--border);
}

.pill-arrow {
  font-size: 10px;
  color: var(--text-muted);
  transition: transform 0.2s ease;
}

/* User Dropdown Menu */
.user-menu-dropdown {
  position: relative;
}

.user-dropdown-menu {
  display: none;
  position: absolute;
  right: 0;
  top: 120%;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
  min-width: 140px;
  z-index: 100;
  padding: 4px 0;
}

.user-menu-dropdown:hover .user-dropdown-menu,
.user-menu-dropdown:focus-within .user-dropdown-menu {
  display: block;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  font-size: 13px;
  color: var(--text);
  text-decoration: none;
}

.dropdown-item:hover {
  background: var(--surface);
}

.dropdown-item.danger-item {
  color: var(--danger);
}

.dropdown-divider {
  height: 1px;
  background: var(--border-light);
  margin: 4px 0;
}
```

---

## 验证与测试计划 (Verification Plan)

### 1. 自动化回归测试 (Automated Tests)
运行已有 Playwright & API 单元测试，确保改动未破坏任何前端功能与路由：
```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_frontend_playwright.py -q
```

### 2. 手工 UI 验证 (Manual Verification)
1. **折叠展开**：点击 `[⚙️ 关联平台 ▶]`，确认能够平滑展开/收起下方 Canvas、好课、智学盟、智慧树登录状态卡片，且箭头指示符号由 `▶` 变为 `▼`。
2. **账号菜单**：悬浮/点击 `[👤 <username> ▾]`，确认能够正常弹出下拉菜单，且“订阅苹果日历”（已启用时）和“退出登录”功能可用。
3. **整体风格**：确认原有的定时/刷新逻辑在隐藏 DOM 元素后无 JS 报错，整体界面符合素雅极简外观。
