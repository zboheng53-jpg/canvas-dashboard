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

## 暂缓项

按钮、输入框、卡片、导航项和业务组件仍由 legacy 层维持现状。它们会在组件实验室逐项确认后迁移，不在基础架构阶段批量改写。
