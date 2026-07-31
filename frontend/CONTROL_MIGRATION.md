# 交互控件 API 与迁移表

## 已确认方向

候选 A：桌面控件高 `36px`、触控环境至少 `44px`、`6px` 圆角、清晰冷灰边框、近白浅蓝主按钮，以及 `3px` 克制外扩 focus ring。

视觉和状态只由 `assets/css/components.css` 提供；`assets/css/patterns.css` 只允许处理业务布局。

## 新组件 API

| 组件 | 基础类 | 变体或状态 |
| --- | --- | --- |
| Button | `.ui-button` | `--primary`、`--secondary`、`--outline`、`--danger`、`--text`、`--choice` |
| Button 尺寸/布局 | `.ui-button` | `--sm`、`--block`、`--start`、`--heading` |
| Icon Button | `.ui-icon-button` | `--sm`、`--danger`、`--flag` |
| Text/Password/Date/Select | `.ui-control` | 原生 `type`；错误使用 `aria-invalid="true"` 或 `.is-invalid` |
| Password/Loading shell | `.ui-input-shell` | 密码操作按钮放在 shell 内；加载使用 `.is-loading` |
| Checkbox | `.ui-checkbox` | 原生 `checked`、`disabled`；错误使用 `aria-invalid="true"` |
| Checkbox Label | `.ui-checkbox-label` | 包裹 `.ui-checkbox` 与文字 |
| Form Field | `.ui-field` | 错误字段使用 `.is-error` |
| Label | `.ui-label` | 字段标题 |
| Help Text | `.ui-help` | 错误语义可叠加 `.is-error` |
| Error Text | `.ui-error` | 空内容自动隐藏 |

Button 和 Icon Button 的 loading 使用 `aria-busy="true"`；choice/flag 状态优先使用 `aria-pressed`，原有 JavaScript 状态类继续作为兼容行为钩子。

## 旧类到新 API

| 旧类/实现 | 新 API |
| --- | --- |
| `btn-primary`、`btn-accent`、`btn-submit`、`project-button-primary`、`btn-schedule-primary`、`calendar-panel-primary`、`connection-primary-action`、`subtask-add-btn` | `.ui-button.ui-button--primary` |
| `btn-secondary`、`btn-auth-secondary`、`project-button-secondary`、`btn-schedule-secondary`、`console-secondary-button` | `.ui-button.ui-button--secondary` |
| `project-button-danger`、`calendar-panel-revoke`、`connection-danger-quiet`、`settings-danger-button` | `.ui-button.ui-button--danger` |
| `connection-text-button`、`project-overview-all`、`project-task-name-btn`、`project-todo-link`、`project-due-editable` | `.ui-button.ui-button--text` |
| `project-tab-btn`、`todo-source-filter` | `.ui-button.ui-button--choice` |
| `btn-refresh`、`project-modal-close`、`schedule-modal-close` | `.ui-icon-button` 与适用的 `--danger`/`--flag` |
| 父容器或标签选择器实现的 text/password/date/select/textarea | `.ui-control` |
| 原生业务 checkbox | `.ui-checkbox` + `.ui-checkbox-label` |
| `connection-field-label`、`settings-field-label`、`account-delete-field` | `.ui-label`；字段容器使用 `.ui-field` |
| `setup-hint`、`form-note`、`connection-data-note` | `.ui-help` |
| `error-banner`、`connection-error`、`project-modal-error` | `.ui-error` |

旧类暂时保留作为 JavaScript、布局或回归钩子；其中颜色、字体、高度、圆角、边框、阴影和状态声明已经删除。

## 保留的例外

- `sidebar-nav-item`、`sidebar-footer-action`、`sidebar-user`、`sidebar-scrim`：属于完整导航模式，不是通用 Button。
- `login-card`：整张连接卡片承担选择和状态表达，后续随卡片组件迁移。
- `.subtask-toggle`、`.btn-flag`、`.btn-dismiss`、`.btn-delete`：待办行的紧凑工具组保留原有桌面尺寸；通用 36px Icon Button 与 24px 业务网格会产生宽高冲突。移动端仍使用 36px 触控尺寸。
- `project-choice-row`、`project-list-item`：属于可点击业务列表行，继续保留自身模式。
- Radio 和 file input：不在本轮 Checkbox/Form Control 范围内。
- `.hidden`、`.active`、`.is-active`、`.is-selected`、`.is-error` 以及既有 ID/data 属性：继续作为行为钩子，未更名。

## 最低状态覆盖

所有 Button、Icon Button 与 Control 覆盖 default、hover、active、focus-visible、disabled；Button/Icon Button 支持 loading，choice/flag 支持 selected，Control/Checkbox/Field 支持 error。移动端和粗指针环境的按钮、图标按钮及输入控件最小高度为 `44px`。
