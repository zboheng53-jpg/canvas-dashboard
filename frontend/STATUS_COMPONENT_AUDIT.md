# Canvas Dashboard 信息表达与反馈组件审计

> 审计范围：待办、长期项目、日程、平台连接、Apple Calendar、偏好设置与认证页。  
> 本文件记录迁移前现状；组件实验室候选不代表最终 API。

## 1. 页面中的现有实现

### 待办

| 用途 | 当前实现 | 表达方式 | 主要问题 |
| --- | --- | --- | --- |
| 待完成与即将到期计数 | `.stat-pill`、`.stat-count`、`.urgent` | 文本 + 数字；紧急项仅改变文字颜色 | 名称是 pill，但视觉更接近散排文字；紧急语义依赖颜色 |
| 平台来源 | `.item-source-badge` + `.src-canvas/.src-haoke/.src-zhixuemeng/.src-zhihuishu/.src-project/.src-custom` | 各平台独立文字色、背景色与边框色 | 平台身份色与全局状态色混在 legacy CSS；尺寸与项目标签不同 |
| 课程或分类 | `.label-badge` | 中性弱背景标签 | 与来源 Badge、项目 Tag 的高度、圆角和字重不同 |
| 到期状态 | 待办行 `.urgent.is-overdue/.is-today/.approaching/.remote` | 整行背景、边框或截止时间颜色 | 同一时间语义在列表与项目页使用不同红/黄值；部分状态只靠颜色 |
| 手动标红与完成 | `.manual-flagged`、`.dismissed` | 标题色；整行透明度与删除线 | `dismissed` 兼具业务状态与 disabled 观感，需要保留行为类但拆出视觉语义 |
| 加载与空状态 | `.empty-state` | 单行居中文字；加载也复用空状态 | “加载中”和“没有待办”没有结构差异，也没有 `role=status` 的统一契约 |
| 子任务空状态 | `.subtask-empty` | 小号弱化文字 | 是第三套空状态排版 |

### 长期项目

| 用途 | 当前实现 | 表达方式 | 主要问题 |
| --- | --- | --- | --- |
| 标签组合 | `.project-tag-pill` + `.status-tag/.due-tag/.progress-tag/.main-project-tag` | 多个胶囊标签 | 后三个变体主要靠上下文理解；状态值没有统一 success/info/neutral 映射 |
| 项目状态 | `.project-status-badge.is-active/.is-completed/.is-archived` | 三种独立浅色背景 | 与 `.project-tag-pill`、连接状态重复，且实际模板主要渲染另一套 Tag |
| 主项目/下一步 | `.project-main-badge`、`.project-next-badge`、总览标题内裸 `span` | 绿色弱背景小标签 | 三个选择器共享硬编码值，但命名与结构不统一 |
| 创建成功/全部完成 | `.project-created-notice`、`.project-all-done` | 浅绿色整块提示 | 两个结构相同；视觉和按钮规则仍写在业务 CSS |
| 错误 | `.project-manager-status.is-error`、`.project-modal-error`、`.project-detail-empty.is-error` | 红色文字或只把标题染红 | 同一错误在页头、弹窗、内容区有三套结构 |
| 空状态 | `.project-list-empty`、`.project-detail-empty`、`.project-task-empty`、`.rail-empty-state`、`.project-next-action-card.is-empty` | 单行、标题+说明、卡片等多种结构 | 合理的尺寸差异与重复视觉实现混在一起；缺少统一的 compact/default 变体 |
| 加载 | 右栏初始 `.rail-empty-state.is-loading`；工作区依赖 `aria-busy` | 文案或容器忙碌状态 | 没有统一 Spinner/Skeleton 与可见加载文案 |

### 日程

| 用途 | 当前实现 | 表达方式 | 主要问题 |
| --- | --- | --- | --- |
| 日程类别图例 | `.legend-dot` + `.legend-course/.legend-recurring/.legend-weekly` | 色块 + 文字 | 这是“数据类别色”，不应映射为 success/warning/info；同一颜色在 CSS 中有两套定义 |
| 保存/导入反馈 | `.schedule-manager-status.is-error` | 普通提示文字或红色文字 | success/info/loading 仅靠文案，没有语义类 |
| 右栏空/错误/加载 | `.rail-empty-state` + `.is-error/.is-loading` | 标题 + 说明 | 结构相对完整，可作为统一 Empty/Feedback 的基础，但错误仍只改变标题颜色 |
| 列表空状态 | `.schedule-list-empty` | 小号弱化文字 | 与右栏空状态重复但密度不同，应转为 compact 变体 |

### 平台连接

| 用途 | 当前实现 | 表达方式 | 主要问题 |
| --- | --- | --- | --- |
| 列表连接状态 | `.login-card-status.connected/.attention` | 文字 + 伪元素圆点 | 是当前最接近“颜色 + 文字”的可访问方案 |
| 详情连接状态 | `.status-badge.connected/.attention` | 胶囊/文字 + 伪元素圆点 | 与列表状态内容、状态类和视觉定义重复 |
| 已登录状态 | `.connection-state-connected` | 单独绿色文字 | 第三套 success 表达 |
| 侧栏注意提示 | `.sidebar-attention-dot` | 单独红点，仅 `aria-label` | 折叠时有文本替代，但视觉完全依赖点色；应明确为 attention count/status dot |
| 刷新反馈 | `.connections-manager-status` | 普通文字 | loading、success、partial failure 与 error 共享一个外观 |
| 表单错误 | `.connection-error.error-banner.ui-error` | 红色错误块 | 同时叠加三套类；属于明确重复实现 |
| 智慧树会话反馈 | `.login-session-message.connected/.attention` | 绿/红文字 | 与连接状态、页级状态重复 |

### Apple Calendar 与设置

| 用途 | 当前实现 | 表达方式 | 主要问题 |
| --- | --- | --- | --- |
| 私密链接 | `.calendar-privacy-badge` | 中性小标签 | 可归入 neutral Tag，而不是独立业务 Badge |
| 操作反馈 | `.calendar-subscription-status.is-error` | 普通/红色文字 | 与项目、日程、连接的 manager status 重复 |
| 危险说明 | `.account-delete-warning` | 红色浅底 + 圆形感叹号 + 文字 | 结构完整，但色值和圆角硬编码；可迁移为明确的 danger Alert |
| 删除表单状态 | 复用 `.calendar-subscription-status.is-error` | 文案 + `role=status/alert` 动态切换 | ARIA 行为较好，但类名与业务不匹配 |
| Disabled/Loading | 原生 `disabled`、`aria-busy` + Button API | 控件状态 | 交互层已统一；信息反馈层还没有统一的邻接说明或 live region 规则 |

### 认证与独立登录页

| 用途 | 当前实现 | 表达方式 | 主要问题 |
| --- | --- | --- | --- |
| 表单错误 | `.ui-error.error-banner` | 红色块或文字 | `ui-error` 已有字段错误语义，`error-banner` 又提供整块反馈，职责重叠 |
| 检查/会话状态 | `.setup-hint`、`.login-session-message` | 帮助文字复用为运行状态 | 帮助文本、加载反馈和结果反馈未分离 |

## 2. 重复实现归并

1. `.login-card-status`、`.status-badge`、`.connection-state-connected` 和 `.login-session-message` 本质上都是 `Status`。
2. `.error-banner`、`.connection-error`、`.account-delete-warning`、`.project-created-notice`、`.project-all-done` 本质上都是不同语义与密度的 `Alert`。
3. `.empty-state`、`.rail-empty-state`、`.project-detail-empty`、`.project-list-empty`、`.project-task-empty`、`.schedule-list-empty`、`.subtask-empty` 本质上是 `Empty State` 的 default/compact/rail 变体。
4. `.stat-pill`、项目 Tab 内计数和项目进度数字可归为 `Count Pill/Count`，但不应把所有数字都做成胶囊。
5. `.item-source-badge`、`.label-badge`、`.project-tag-pill`、`.calendar-privacy-badge`、`.project-next-badge` 可共享 Badge/Tag 尺度；平台来源色和全局状态色必须使用不同 token 命名空间。
6. `.is-error` 目前同时用于字段、页级状态、空状态和业务容器。行为可以保留，视觉应由明确组件基类决定，避免裸 `.is-error` 产生跨组件副作用。
7. Loading 目前分散为按钮 Spinner、输入框 Spinner、`aria-busy` 容器、单行“加载中”和 `.rail-empty-state.is-loading`，需要统一可见文案与 live-region 行为。

## 3. 迁移时需要保护的行为契约

- 保留现有 ID、`data-*`、`.connected/.attention/.is-error/.is-loading/.hidden` 等 JavaScript 钩子，先叠加新基础类，再逐步收窄旧视觉规则。
- `role="alert"` 仅用于需要立即宣读的失败；普通进度和成功结果使用 `role="status"` / `aria-live="polite"`。
- `aria-busy` 必须继续落在真正被更新的区域或触发控件上，不能只显示 Spinner。
- 平台来源色只表达“数据来自哪里”；success/warning/danger/info 只表达“当前结果如何”，两者不得互相替代。
- 日程的 course/recurring/weekly 色属于数据系列色，不纳入全局 success/warning/info。

