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
