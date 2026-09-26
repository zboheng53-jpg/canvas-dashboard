# Canvas Dashboard 基础设计契约

## 视觉定位

面向个人学习、待办、课程、日程与长期项目管理的学习控制台：保持现有信息密度、柔和细线和圆角卡片，提供蓝白与苔绿两套外观，标题保留克制的编辑感衬线。

## 已确认原则

1. 保留总览页现有信息架构、卡片分区和整体密度。
2. 默认采用蓝白（冷灰背景与近白表面），可切换苔绿（浅灰米色背景、暖白卡片与导航）。苔绿以白色为主导，绿色用于主操作、边框与选中状态的点缀；保留现有布局与圆角。
3. 静态卡片保持平面；仅交互表面在 hover 时允许轻微抬升。
4. 保留现有控件、卡片与弹窗的圆角，不为统一皮肤而缩小圆角或改变组件轮廓。
5. 正文、控件、英文与数字使用 Geist；页面标题和内容标题使用 Noto Serif SC。
6. 两套配色的主操作均采用近白背景；边框、文字、hover 和 selected 随主题使用蓝色或苔绿色，避免整页铺绿。
7. 所有颜色、字体、间距、圆角、阴影、动效与焦点样式必须通过 `tokens.css` 使用。
8. 新组件至少覆盖 default、hover、active、focus-visible、disabled，以及适用的 loading、selected、error 状态。

## 外观与轻量动效

- 偏好设置提供“蓝白 / 苔绿”；选择以 `cda_appearance` 保存在当前浏览器的 localStorage，不跨设备同步。共享头部的 `appearance.js` 在样式加载前恢复选择；存储不可用时仍可切换，明确提示无法记忆。
- 默认变量和 `:root[data-theme="moss"]` 覆盖均维护在 `tokens.css`。主题只改变背景、正文、边框、主操作及焦点颜色；平台来源色与成功、警告、危险语义不随主题替换。`design-system.css` 不再在 body 或 dashboard-shell 重复定义全套颜色。
- 总览使用 `appearance.css` 的 280 ms 透明度渐入，分区相隔 40 ms，不位移、不缩放，不为每次数据重绘重播。系统启用“减少动态效果”时关闭入场动画。按钮等反馈使用共享时长和缓动变量。
- 手机端（宽度不超过 768 px）的新增表单默认收起，通过清单标题旁的“新增”展开；收起保留草稿，失败保留表单与输入，成功后收起并将焦点返回入口。桌面表单保持常驻。
- 手机是电脑完整工作台的补充，优先查看、新增、完成待办以及查看日程和当前行动。手机总览保留日期、教学周、校区与简要天气，省略湿度、秒钟和学期全称。任务主标题允许换行，隐藏课程副标题和重复来源标签，来源与截止／计划时间使用统一基线；详细信息经“更多 → 详情”访问。适配以 320–430 px 手机宽度及 768 px 边界验收，不以压缩所有桌面信息为目标。

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
