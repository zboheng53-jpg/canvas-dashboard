# 前端工作区

这里集中放置 Canvas Dashboard 的所有可视化界面文件，日常设计只需打开此文件夹：

- `templates/`：页面结构（Jinja / HTML）。`index.html` 只保留壳层；`dashboard/` 按总览、项目、日程、连接、日历、Agent、设置、指南分别维护视图，`_placeholder_views.html` 仅汇总 include。
- `assets/css/`：样式。`dashboard-v103.css` 是当前界面主题，`dashboard-shell.css` 管理壳层与侧栏，`style.css` 保留登录与基础组件样式。
- `assets/js/`：浏览器端逻辑。`weather-icons.js` 提供统一的 Soft Monoline 描边天气图标。
- `assets/downloads/`：前端直接下载的文件。
- `assets/guide/`：上手指南里的界面截图（Canvas 日历馈送三步）。第三张的私有订阅链接已打码，重新裁剪时必须保留打码，流程见 `scripts/prepare_guide_shots.py`。

控制台脚本按职责拆分：`core/utils.js` 放公共工具，`core/shell.js` 管导航和手机菜单，`core/context.js` 管时间、天气、学期；`features/todos.js`、`projects.js`、`features/schedule.js`、`features/integrations.js` 分别负责待办、项目、日程和平台请求，其他管理页有各自脚本，`bootstrap.js` 统一启动。当前仍是共享全局的普通脚本，模板中的加载顺序是依赖约定：`integrations.js` 必须先于待办事件绑定，启动脚本最后加载。没有引入打包器或改成前端框架。

Flask 从该目录加载前端，但浏览器 URL 仍是 `/static/...`：例如 `assets/css/dashboard-v103.css` 对应 `/static/css/dashboard-v103.css`。调整目录或文件名时，请同步修改模板中的 `url_for('static', filename=...)`。

## Open Design 预览

Open Design 不会执行 Flask 或 Jinja，因此不要直接导入 `templates/index.html`。在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\export_open_design_preview.py
```

它会将真实首页（含 Jinja `include` 与模板变量）渲染为 `open-design-preview/index.html`，并复用同一份 `assets/` CSS 与 JavaScript。将整个 `frontend/` 文件夹导入 Open Design，打开 `open-design-preview/index.html` 即可预览。这个目录是可再生的本地文件，不提交到 Git；每次模板结构变化后重新运行导出命令即可。

在 Open Design 中请把视觉修改落实到 `templates/` 或 `assets/` 中的真实源码；不要把 `open-design-preview/index.html` 当作需要维护的页面。导出文件会加载 `assets/js/open-design-mock.js`：它在浏览器中拦截所有 `/api/` 请求，提供待办、长期项目、日程、天气和学期的演示数据。因此总览、项目、日程与导航切换都能使用，同时不会访问真实账户或接口。

## 组件实验室

登录本地站点后访问 `/component-lab`，可以在隔离页面中检查基础组件、交互状态和候选视觉方案。实验室使用独立的 `component-lab.css` 与 `component-lab.js`，不会进入生产导航，也不会改写控制台现有样式。

需要生成无需登录的静态预览时运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\export_component_lab_preview.py
```

然后打开 `frontend/open-design-preview/component-lab.html`。该文件同样是可再生预览，不提交到 Git。

## CSS 加载结构

- `assets/css/tokens.css` 是全局设计变量的唯一来源。
- `assets/css/foundation.css` 只包含文档级字体与基础行为，不定义按钮、表单或业务组件外观。
- `assets/css/components.css` 是交互控件、字段文本、标签、状态、反馈、加载、空状态与禁用状态的唯一视觉来源。
- `assets/css/patterns.css` 只处理这些控件进入待办、子任务、项目和连接表单后的宽度、flex 与对齐。
- `assets/css/app.css` 是认证页和平台登录页的唯一入口。
- `assets/css/auth-pages.css` 经 `app.css` 的 pages 层加载，专门处理登录／注册展示页；`guide.css` 经控制台入口加载。
- `assets/css/dashboard.css` 是控制台的唯一入口。
- `style.css`、`dashboard-shell.css`、`dashboard-v103.css` 作为 `legacy` layer 继续承载尚未迁移的旧组件与布局。

Cascade Layer 的固定顺序为 `legacy → tokens → foundation → components → patterns → pages → utilities`。新样式不得直接增加到三份 legacy 文件；已迁移控件的视觉规则不得回到业务类或 `patterns.css`。

可执行约束见 `DESIGN_SYSTEM.md`；现状审计与迁移映射分别见 `STATUS_COMPONENT_AUDIT.md`、`STATUS_COMPONENT_MIGRATION.md`。

## 本地交互验收

使用真实 Flask API 与隔离示例数据：在项目根目录运行 `scripts/dev.ps1 -Preview -Scenario normal`，访问 http://127.0.0.1:5000/preview-login。空状态用 `empty`，密集内容用 `dense`。测试分层、失败截图与 trace 说明见 [开发流程](../docs/development.md)。静态预览不能代替此交互验收。
