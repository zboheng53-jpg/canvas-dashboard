# 前端工作区

这里集中放置 Canvas Dashboard 的所有可视化界面文件，日常设计只需打开此文件夹：

- `templates/`：页面结构与内联交互（Jinja / HTML）。主控制台在 `templates/index.html`。
- `assets/css/`：样式。`dashboard-v103.css` 是当前界面主题，`dashboard-shell.css` 管理壳层与侧栏，`style.css` 保留登录与基础组件样式。
- `assets/js/`：浏览器端逻辑。`weather-icons.js` 提供统一的 Soft Monoline 描边天气图标。
- `assets/downloads/`：前端直接下载的文件。

Flask 从该目录加载前端，但浏览器 URL 仍是 `/static/...`：例如 `assets/css/dashboard-v103.css` 对应 `/static/css/dashboard-v103.css`。调整目录或文件名时，请同步修改模板中的 `url_for('static', filename=...)`。
