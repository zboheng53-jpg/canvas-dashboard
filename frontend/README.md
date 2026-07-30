# 前端工作区

这里集中放置 Canvas Dashboard 的所有可视化界面文件，日常设计只需打开此文件夹：

- `templates/`：页面结构与内联交互（Jinja / HTML）。主控制台在 `templates/index.html`。
- `assets/css/`：样式。`dashboard-v103.css` 是当前界面主题，`dashboard-shell.css` 管理壳层与侧栏，`style.css` 保留登录与基础组件样式。
- `assets/js/`：浏览器端逻辑。`weather-icons.js` 提供统一的 Soft Monoline 描边天气图标。
- `assets/downloads/`：前端直接下载的文件。

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
- `assets/css/app.css` 是认证页和平台登录页的唯一入口。
- `assets/css/dashboard.css` 是控制台的唯一入口。
- `style.css`、`dashboard-shell.css`、`dashboard-v103.css` 作为 `legacy` layer 继续承载尚未迁移的旧组件与布局。

Cascade Layer 的固定顺序为 `legacy → tokens → foundation → components → patterns → pages → utilities`。新样式不得直接增加到三份 legacy 文件；组件迁移完成后再从 legacy 中删除对应规则。
