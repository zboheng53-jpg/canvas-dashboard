# Canvas Dashboard 交互控件审计

审计范围：`frontend/templates/**/*.html`、`frontend/assets/js/**/*.js`、`frontend/assets/css/*.css`。下表只统计真实业务页面和动态 HTML；组件实验室类单独标记，不计入业务迁移数量。

> 本文保留迁移前快照。候选 A 已确认并完成迁移；当前 API、旧类映射和保留例外见 `CONTROL_MIGRATION.md`。

## 数量概览

| 元素 | 源码实例 | 无自身组件类 |
| --- | ---: | ---: |
| `button` | 151 | 14 |
| `input` | 57 | 52 |
| `select` | 5 | 2 |
| `textarea` | 1 | 1 |
| `label` | 36 | 21 |
| `form` | 15 | 1 |

“无自身组件类”表示其视觉来自父容器、标签选择器、ID 选择器或内联样式，不代表元素没有 ID。

## 当前按钮类名

### 通用与旧公共类

`btn-accent`、`btn-auth-secondary`、`btn-cancel`、`btn-delete`、`btn-dismiss`、`btn-primary`、`btn-refresh`、`btn-schedule-action`、`btn-schedule-primary`、`btn-schedule-secondary`、`btn-secondary`、`btn-sm`、`btn-submit`、`btn-wide`。

### 连接、日历与设置

`action-button`、`calendar-panel-primary`、`calendar-panel-revoke`、`connection-clear-button`、`connection-danger-quiet`、`connection-primary-action`、`connection-text-button`、`console-secondary-button`、`console-stateful-button`、`login-card`、`settings-danger-button`、`sync-status-button`。

### 长期项目

`project-button-danger`、`project-button-primary`、`project-button-secondary`、`project-choice-row`、`project-due-editable`、`project-empty-create`、`project-group-add-task-btn`、`project-modal-close`、`project-next-action-btn-choose`、`project-next-action-btn-complete`、`project-overview-add`、`project-overview-all`、`project-tab-btn`、`project-task-action-btn`、`project-task-name-btn`、`project-todo-link`。

### 日程

`schedule-import-button`、`schedule-modal-close`、`schedule-nav-btn`、`schedule-refresh-button`、`schedule-return-default`。

### 待办与内容内操作

`item-course`、`item-due`、`last-updated`、`mobile-action-trigger`、`subtask-add-btn`、`subtask-delete`、`subtask-toggle`、`todo-source-filter`。

### 导航与侧栏

`mobile-menu-toggle`、`sidebar-collapse-toggle`、`sidebar-footer-action`、`sidebar-logout`、`sidebar-nav-item`、`sidebar-scrim`、`sidebar-user`。

### 组件实验室专用

`candidate-button`、`candidate-icon-button`、`context-nav-item`、`lab-button`、`lab-button-danger`、`lab-button-ghost`、`lab-button-primary`、`lab-button-secondary`、`lab-icon-button`、`lab-list-item`、`password-toggle`。

### 状态与结构类

`active`、`hidden`、`is-active`、`is-current`、`is-danger`、`is-focus`、`is-hover`、`is-loading`、`is-selected`。

这些类不是稳定的视觉 API，其中部分被 JavaScript 直接切换。

## 当前表单类名

### Input

`date-input`、`schedule-file-input`、`subtask-add-due-input`、`subtask-add-input`、`subtask-due-input`。

组件实验室：`candidate-control`、`lab-input`、`is-error-control`、`is-active`、`is-focus`、`is-hover`。

### Select

`logged-in-select`、`todo-source-select`。

组件实验室：`candidate-control`、`lab-select`、`is-error-control`、`is-active`、`is-focus`、`is-hover`。

### Form 与布局容器

`account-delete-form`、`add-todo-form`、`auth-card`、`auth-form`、`connection-form`、`connection-form-inline`、`mb-s`、`project-modal-form`、`schedule-modal-form`。

### Field 与 Label

`account-delete-field`、`connection-field-label`、`kind-option`、`project-check-option`、`settings-field-label`。

组件实验室：`candidate-field`、`candidate-field-label`、`candidate-checkbox`、`checkbox-state`、`compact-state`、`lab-checkbox`、`lab-field`、`lab-field-inline`。

### Help、Error 与状态文本

帮助：`connection-data-note`、`connection-setup-hint`、`form-note`、`schedule-login-note`、`setup-hint`。

错误：`connection-error`、`error-banner`、`project-modal-error`。

混合状态：`calendar-subscription-status`、`login-session-message`、`connections-manager-status`、`console-manager-status`、`project-manager-status`、`schedule-manager-status`。这些类同时承担布局、颜色和 JavaScript 状态输出，不应直接作为统一 Error Text API。

## 已确认的重复实现

### 1. 主按钮重复

以下业务类最终落到高度、蓝色、边框、圆角和 hover 近似相同的主按钮实现：

`btn-primary`、`btn-accent`、`btn-submit`、`subtask-add-btn`、`btn-schedule-primary`、`calendar-panel-primary`、`connection-primary-action`、`project-button-primary`、`project-group-add-task-btn`、`project-next-action-btn-complete`。

其中 `btn-primary` 目前有 19 组视觉规则，横跨 `style.css` 与 `dashboard-v103.css`；`project-button-primary` 有 14 组规则。

### 2. 次按钮重复

`btn-secondary`、`btn-auth-secondary`、`btn-refresh`、`btn-schedule-secondary`、`project-button-secondary`、`console-secondary-button` 都在重复实现“白色或弱背景 + 细边框 + 中性文字”。

`btn-secondary` 目前有 20 组视觉规则，分布于三份 legacy CSS。

### 3. 危险按钮重复

`project-button-danger`、`calendar-panel-revoke`、`connection-danger-quiet`、`settings-danger-button` 是同一危险变体的四种实现。

### 4. 无边框文字／图标按钮重复

`project-due-editable`、`sync-status-button`、`connection-text-button` 都是无边框文字操作；`btn-delete`、`btn-dismiss`、`project-modal-close`、`schedule-modal-close`、`sidebar-collapse-toggle` 又分别实现了图标按钮。

### 5. 输入框重复

- 认证与平台登录输入框大多没有类，依赖 `.add-todo-form input`。
- 连接页使用 `.connection-form input`、`.logged-in-select`。
- 项目弹窗依赖 `.project-modal-form input/select/textarea`。
- 日程弹窗依赖 `.form-group input/select`。
- 设置页使用父容器和 ID 选择器。
- 新增待办与子任务分别使用 `date-input`、`subtask-*`。

它们都重复定义了高度、padding、边框、圆角、背景、placeholder、focus 和 disabled。

### 6. Field、Help 与 Error 语义不稳定

`setup-hint`、`form-note`、`connection-data-note` 都可表达帮助文本；`error-banner`、`project-modal-error`、带 `.is-error` 的 status 元素都可表达错误。当前没有统一的 Field → Label → Control → Help/Error 结构。

## JavaScript 依赖，迁移时必须保留

- `.project-tab-btn` + `.active`
- `.project-modal-form`、`.project-modal-backdrop`、`.project-modal-error`
- `.login-card`、`.login-card-status.attention`、`.connection-detail-section`
- `.hidden`、`.is-active`、`.is-selected`、`.is-error`
- 所有现有 ID、`data-*` 属性和提交行为

这些类可以继续作为行为钩子，并与新的视觉类同时存在；在 JavaScript 改为明确的 `data-*` 钩子之前，不直接删除。

## 结论

推荐的新组件 API 最终只需要一套 Button、一套 Icon Button、一套 Control、一套 Checkbox 和一套 Field 文本结构。业务类保留布局、宽度、排列和行为钩子，不再定义颜色、字体、边框、圆角、阴影或状态。具体视觉值等待组件实验室 A/B/C 方向确认后制定。
