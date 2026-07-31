# Canvas Dashboard 基础设计契约

## 视觉定位

面向个人学习、待办、课程、日程与长期项目管理的冷静学习控制台：高信息密度但规整，以近白表面、冷灰细线和小圆角为基础，标题保留克制的编辑感衬线。

## 已确认原则

1. 保留总览页现有信息架构、卡片分区和整体密度。
2. 页面采用低对比冷灰背景与近白表面；不使用大面积饱和蓝。
3. 静态卡片保持平面；仅交互表面在 hover 时允许轻微抬升。
4. 基础控件以 `6px` 圆角为迁移目标，弹窗与较大表面不超过 `8px`。
5. 正文、控件、英文与数字使用 Geist；页面标题和内容标题使用 Noto Serif SC。
6. 主操作优先采用候选 A：近白背景、浅蓝边框或文字；浅蓝弱背景只用于 hover、selected 或状态提示。
7. 所有颜色、字体、间距、圆角、阴影、动效与焦点样式必须通过 `tokens.css` 使用。
8. 新组件至少覆盖 default、hover、active、focus-visible、disabled，以及适用的 loading、selected、error 状态。

## CSS 责任边界

加载顺序由 Cascade Layers 固定为：

`legacy → tokens → foundation → components → patterns → pages → utilities`

- `tokens.css`：唯一的全局自定义属性定义源。`Legacy compatibility aliases` 仅供旧代码迁移期间使用，新组件禁止引用。
- `foundation.css`：文档级字体、标题、数字排版、基础焦点和选择文本；不得放置按钮、输入框、卡片或业务规则。
- `components.css`：交互控件、Badge、Tag、Status、Feedback、Alert、Loading、Empty 与 Disabled State 的唯一视觉和状态来源。
- `patterns.css`：已迁移控件进入业务上下文后的宽度、flex 与对齐桥接；禁止定义颜色、字体、边框、圆角、阴影和交互状态。
- `app.css`：认证页与平台登录页入口。
- `dashboard.css`：控制台入口。
- `component-lab.css`：组件实验室页面层与候选方案。
- `style.css`、`dashboard-shell.css`、`dashboard-v103.css`：隔离的 legacy 层。只允许删除或为迁移修正，不再新增视觉规则。

## Token 使用规则

- 新 CSS 必须使用语义 Token，例如 `--color-text-secondary`、`--color-border`、`--radius-control`，不得直接引用 `--text-secondary`、`--shell-border` 等兼容别名。
- 品牌或业务来源色只有在语义无法表达时才允许新增专用 Token；需要写明使用范围。
- 组件内部计算值可以使用局部自定义属性，但不得在 `:root` 重复定义全局 Token。
- 响应式布局中的几何计算、插画尺寸和浏览器兼容修复可以使用局部字面值。
- 禁止新增 `!important`、ID 视觉选择器、模板内联视觉样式、未加载字体名，以及依靠入口加载先后覆盖同层规则的写法。
- `focus-visible` 不得省略；焦点轮廓不能仅以颜色微调代替。

## 当前迁移状态

Button、Icon Button、Text/Password/Date Input、Select、Checkbox、Form Field、Label、Help Text 与 Error Text 已采用候选 A，并迁移到 `components.css`。业务页面只通过 `.ui-*` API获得这些视觉结果。

Badge、Tag、Status Dot、Count Pill、Success、Warning、Danger、Info、Alert、Inline Error、Loading、Empty 与 Disabled State 已迁移到同一组件层：

- `.ui-badge--source` 只表达平台来源，必须同时显示平台名称；来源色不得表达成功或失败。
- `.ui-status` 以“语义色点 + 文字”表达结果；只有已有可访问名称的紧凑位置可以单独使用 `.ui-status-dot`。
- `.ui-feedback` 用于页内短结果或进度；危险反馈增加克制的行内分隔，不扩展为大面积红底。
- `.ui-alert` 用于需要说明原因或下一步操作的完整提示块；阻断性错误使用 `role="alert"`，普通结果使用 `role="status"`。
- `.ui-empty` 提供默认与 `--compact` 两种密度；默认空状态允许一个不承载语义的几何装饰。
- Loading 必须有可读文案，并同步维护 `role="status"` 或更新区域的 `aria-busy`。
- 禁用状态优先使用原生 `disabled`；非原生元素必须同时提供 `aria-disabled="true"` 与 `.ui-disabled`。

控制台业务卡片、导航项和完整业务行已开始退出 legacy 层；迁移不得改变页面信息架构。

## 业务组合层

待办、子任务、项目项、项目任务、日程项、课程项、平台连接项、设置项和日历订阅操作区通过 `business.css` 组合基础组件。新业务类只定义模块特有布局；Surface、Card、List Item、Nav Item、标题/辅助文字、交互控件和反馈状态的视觉均来自 `components.css`。

完整映射、例外和数据回归边界见 `BUSINESS_COMPONENT_MIGRATION.md`。
