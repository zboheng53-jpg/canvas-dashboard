# Canvas Dashboard 信息表达组件迁移

## 语义映射

| 语义 | API | 典型场景 |
| --- | --- | --- |
| 中性 | `.ui-status--neutral` / `.ui-feedback--neutral` | 未配置、尚无结果 |
| 信息 | `.ui-status--info` / `.ui-feedback--info` / `.ui-alert--info` | 检查中、同步中、使用说明 |
| 成功 | `.ui-status--success` / `.ui-feedback--success` / `.ui-alert--success` | 已连接、保存完成、项目任务全部完成 |
| 警告 | `.ui-status--warning` / `.ui-feedback--warning` / `.ui-alert--warning` | 部分同步失败、即将到期、需要注意 |
| 危险 | `.ui-status--danger` / `.ui-feedback--danger` / `.ui-alert--danger` | 连接失败、字段外的阻断错误、不可逆操作 |

短结果与运行进度使用 `.ui-feedback`。包含标题、原因或下一步操作的完整反馈使用 `.ui-alert`。内容区域没有数据时使用 `.ui-empty`，不得用红色 Alert 代替正常空状态。

## 组件 API

| 组件 | 基础类 | 变体 |
| --- | --- | --- |
| Badge | `.ui-badge` | 平台来源叠加 `.ui-badge--source .ui-source--{platform}` |
| Tag | `.ui-tag` | 选中 `.is-selected`；禁用 `.is-disabled[aria-disabled=true]` |
| Status | `.ui-status` | `--neutral / --info / --success / --warning / --danger` |
| Status Dot | `.ui-status-dot` | 与 Status 相同的语义后缀；只用于已有文字或可访问名称的位置 |
| Count Pill | `.ui-count-pill` | 紧急计数 `.ui-count-pill--danger` |
| Inline Feedback | `.ui-feedback` | 与 Status 相同的语义后缀 |
| Alert | `.ui-alert` | `--info / --success / --warning / --danger`；紧凑型叠加 `--compact` |
| Loading | `.ui-loading` / `.ui-spinner` / `.ui-skeleton` | 内容区加载叠加 `.ui-loading--block`；Spinner 必须有可读文案；Skeleton 所在区域设置 `aria-busy=true` |
| Empty State | `.ui-empty` | 紧凑型 `--compact`；错误内容区可叠加 `--danger` |
| Disabled State | `.ui-disabled` | 非原生控件同时设置 `aria-disabled=true` |

## 平台来源色边界

平台色只回答“数据来自哪里”，当前覆盖 Canvas、好课、智学盟、智慧树、长期项目与自定义待办。来源 Badge 始终保留平台文字，小色点仅作快速定位。

全局 success、warning、danger、info 只回答“当前结果如何”。平台断开时，来源 Badge 仍保持平台色，旁边另加带文字的 warning/danger Status；不得把 Canvas 蓝当作 info，也不得把某个平台色当作成功色。

日程中的课程、固定事项与每周重复色属于数据系列色，不进入全局状态映射。

## 旧类迁移

旧业务类保留为 JavaScript 或布局钩子，视觉声明已经移除：

| 旧实现 | 新视觉来源 |
| --- | --- |
| `.login-card-status`、`.status-badge`、`.connection-state-connected`、`.login-session-message` | `.ui-status` |
| `.connections-manager-status`、`.project-manager-status`、`.schedule-manager-status`、`.calendar-subscription-status` | `.ui-feedback` |
| `.error-banner`、`.connection-error`、`.account-delete-warning`、`.project-all-done` | `.ui-alert` |
| `.item-source-badge` 内的 `.src-*` | `.ui-badge--source .ui-source--*` |
| `.label-badge`、`.project-tag-pill`、`.calendar-privacy-badge` | `.ui-tag` / `.ui-count-pill` / `.ui-status` |
| `.empty-state`、`.rail-empty-state`、`.project-*-empty`、`.subtask-empty` | `.ui-empty` |

已删除的重复视觉包括旧平台 Badge 配色、两套连接状态胶囊、项目状态和标签色、页级反馈红绿字、空状态字号与边框、日历私密标签、账户删除警告块，以及覆盖所有 `[class*="status-"]` / `[class*="tag-"]` 的高权重通配规则。

## 无障碍最低要求

- 状态不能只靠颜色：`.ui-status` 必须有文字；单独的 `.ui-status-dot` 必须由相邻文字或容器的可访问名称解释。
- 需要立即宣读的错误使用 `role="alert"`；进度和非阻断结果使用 `role="status"` 或 `aria-live="polite"`。
- 加载状态同时维护可见文案与 `aria-busy`，不能只显示旋转图形。
- 平台来源色、状态色和空状态装饰均为辅助信息；核心含义必须保留在文本中。
- 禁用交互优先使用原生 `disabled`；自定义交互必须有 `aria-disabled="true"`，并阻止实际操作。
