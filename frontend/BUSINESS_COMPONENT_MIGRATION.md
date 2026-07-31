# Canvas Dashboard 业务组件迁移

## 组合映射

| 业务组件 | 基础组件组合 | 业务类只负责 |
| --- | --- | --- |
| 待办项 | `.ui-list-item.ui-list-item--interactive` + Source Badge + Tag + Button/Icon Button | 五列桌面网格、移动端区域排列 |
| 子任务 | `.ui-card.ui-card--subtle` + `.ui-list-item` + Checkbox + Date Input + Icon Button | 子任务行网格、展开区和新增行排列 |
| 项目项 | `.ui-nav-item` + Status/Count Pill | 项目名称、统计和拖拽信息排列 |
| 项目任务 | `.ui-list-item--contained` + Checkbox + Text/Icon Button | 任务名称、日期和操作区排列 |
| 日程项 | `.ui-list-item` + title/meta typography | 时间列与内容列排列 |
| 课程项 | token 化 Schedule Block + title/meta typography | 按时间定位、重叠列宽和紧凑高度 |
| 平台连接项 | `.ui-nav-item--source` + `.ui-source--*` + Status | 平台名称与状态左右排列 |
| 设置项 | `.ui-card-section` + Label/Control/Alert/Button | 标题列与内容列、危险操作表单排列 |
| 日历订阅操作区 | `.ui-card` + Count Pill/List Item + Control/Button/Feedback | 指引与凭据区双栏、操作按钮网格 |

## 新增业务专属样式

`assets/css/business.css` 是控制台业务组合层，位于 `pages` cascade layer。

- 待办桌面五列与移动端命名区域。
- 子任务、项目任务和设置项的响应式网格。
- 项目详情、连接详情、日历订阅的结构排列。
- 今日日程的时间列。
- 日程时间块的绝对定位承载样式。

该文件禁止使用 ID 选择器、`!important`、原始颜色、字体族、阴影和自定义交互状态。通用视觉必须回到 `components.css`。

## 无法通用化的例外

周课表中的课程、每周重复事项和单次事项需要同时表达时间占位与内容类型，因此保留 `.schedule-block` 业务组件。它的三组颜色来自 `tokens.css` 的 `--color-series-*`，不得借用 success、warning、danger 或平台来源色。

待办行的四个紧凑操作仍沿用已确认的桌面工具组例外；移动端保持至少 `36px`，其余移动控件由基础组件保证 `44px` 触控高度。

## 数据回归边界

- 长文本：预览数据包含长待办、长标签和长子任务，标题必须截断或自然换行，不得挤压操作区。
- 空数据：各模块继续使用 `.ui-empty`，正常空数据不得显示为错误。
- 大量数据：静态预览额外生成 12 条待办，用于检查滚动、分组和操作按钮稳定性。
- 错误数据：请求失败使用 `.ui-feedback--danger` 或 `.ui-alert--danger`；字段错误继续使用 `.ui-error`，不得改变已输入内容。

## 视觉验收

桌面检查宽度：`1440px`。移动端检查宽度：`390px`。两种宽度均需检查总览、长期项目、日程与课表、连接与同步、Apple Calendar、偏好设置，以及弹窗的长文本、空态、加载态和错误态。
