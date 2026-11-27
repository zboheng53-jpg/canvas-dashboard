# 2026-09-29 安全入口、Agent、前端与健康检查修复报告

## 一、概述与基线

- **工作分支**：`codex/review-security`
- **基线提交**：`ad7abadfac75f99ab507af87f99a1720191c3618`
- **任务范围**：第五/六批问题核实与修复（安全入口、Agent 凭据与权限、前端交互与轮询治理、健康检查与探针、静态缓存策略）。
- **约束遵循**：
  - 未触碰 `auth.py`、`platform_state.py`、Canvas ID、各平台客户端/Worker/Browser、`login_capacity.py`。
  - 未触碰主代理负责的备份与发布测试脚本（`scripts/backup_data.py`、`deploy/`、`tests/test_backup_data.py`、`tests/test_deploy_configs.py`、`tests/test_release_rollback.py`）。
  - 未修改规范文件与开发文档（`AGENTS.md`、`CLAUDE.md`、`CHANGELOG.md`、`docs/development.md`）。
  - 所有测试运行于临时环境，无真实平台网络访问，无真实数据目录变更。

---

## 二、修复问题明细与核实证据

### 1. 限流器容量、可信 Host、代理头与生产配置断言

- **问题现象与风险**：
  - 原内存限流器仅在单个 IP/用户名达到上限时清理该 key，未清理过期 bucket，恶意扫描或爬虫可使内存字典无限制膨胀。
  - 原 Flask 应用盲目信赖请求 Host 头；未明确限制可信反向代理头范围。
  - 生产配置缺乏显式安全检查，可能在明文 Cookie 或非 HTTPS 下运行。
- **修复方案**：
  - `settings.py` 增加 `PUBLIC_BASE_URL`、`TRUSTED_HOSTS`、`ENV_MODE`、`IS_PRODUCTION`、`RATE_LIMIT_MAX_KEYS`（默认 10000）、`RATE_LIMIT_CLEANUP_INTERVAL_SECONDS`（60 秒）。
  - `app.py` 中 `_check_rate_limit` 引入全局 TTL 清理（清除 600 秒无活动 bucket）及最大容量淘汰（超过 10000 key 时基于最旧访问时间 LRU 淘汰）。
  - 使用 Werkzeug `ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_prefix=0)` 严格只信赖一层代理的客户端真实 IP 与协议，不伪造 `X-Forwarded-Host`。
  - 增加 `@app.before_request` 的 `_enforce_trusted_hosts` 拦截器：仅放行 `settings.TRUSTED_HOSTS` 或 `PUBLIC_BASE_URL` 允许的主机。
  - `settings.validate_production_configuration()`：在 `IS_PRODUCTION=True` 时断言 `CANVAS_DASHBOARD_COOKIE_SECURE=True` 且配置了 HTTPS 的 `PUBLIC_BASE_URL` 或明确的 `TRUSTED_HOSTS`；本地预览模式（`ENV_MODE=development`）保持无缝运行。

### 2. Agent Token 架构安全与细粒度权限

- **问题现象与风险**：
  - 每次 Agent 请求遍历读取用户 Token JSON 文件，成功后每次均落盘覆写 `last_used_at`，高并发下导致磁盘抖动。
  - 单用户仅支持单一 Token，无备注名称、有效期与权限区分；新 Token 具有无限制读写权限；删除操作仅依靠客户端自律，服务端未真实校验拒绝。
- **修复方案**：
  - **全局 O(1) 哈希索引**：在 `data/agent_token_index.json` 维护 SHA-256 哈希到 `{username, token_id, account_id}` 的快速映射，杜绝明文持久化，鉴权命中无需全量扫描。
  - **使用时间节流**：内存跟踪最近写入时间，同一 Token 至少间隔 300 秒才落盘更新一次 `last_used_at`。
  - **多 Token 与细粒度权限**：支持多 Token 列表，各 Token 独立包含 `id`、`name`、`scopes`、`created_at`、`expires_at`、`last_used_at`、`revoked`。
  - **服务端真实权限校验**：`require_agent_auth(scope=...)` 严格区分 `read`、`write`、`delete`。写操作拒绝只读 Token，项目/任务物理删除显式校验 `delete` 权限，不足返回 403 `insufficient_scope`。
  - **新 Token 默认只读与既有兼容**：Web 界面与 API 创建新 Token 默认 `["read"]`；既有老格式单一 Token 自动升级并赋予兼容权限，不得悄悄撤销老 Token。
  - **前端管理界面**：新增 Token 名称备注输入、权限单选（只读/读写/完整）、有效期选择（30天/90天/永不过期）、已激活 Token 列表展示及单凭据撤销按钮；样式全部合入 `business.css`，无任何模板内联 `style=`。
  - **MCP 友好报错**：`agent_mcp.py` 针对 403 `insufficient_scope` 与 401 返回明确的人类可读修复提示。

### 3. 前端网络安全、健壮性与轮询治理

- **问题现象与风险**：
  - `csrf.js` 盲目向所有 `fetch` 请求注入 `X-CSRF-Token`，存在向跨域请求泄露 Token 风险；对 `Request` 对象处理不当可能丢失原有 headers。
  - 请求缺乏超时取消机制；遇到网络波动、401 会话失效、409 冲突或 429 限流时缺少统一友好反馈。
  - 后台静默定时轮询在浏览器标签页隐藏时依然持续运行，且未配置的外部教学平台仍在盲目发起同步请求。
- **修复方案**：
  - `csrf.js` 增加 `isSameOrigin(input)` 校验，严格限制同源请求才附加 CSRF Token；完整克隆并保留 `Request` 实例的原有 method 与 headers。
  - `client.js` 基于 `AbortController` 实现请求超时（默认 25 秒可配置）；针对 401 提示会话过期，针对 409 提示版本冲突，针对 429 解析 `Retry-After` 给出可恢复重试提示。
  - 待办状态切换与标红（`toggleTodoCheck`、`toggleCustomHighlight`）真实附带 `expected_updated_at`，落实版本防覆盖机制。
  - `integrations.js` 与 `bootstrap.js`：基于 `document.visibilityState` 引入前后台感知的自适应任务调度器。标签页隐藏时暂停所有非必要轮询，切回前台时根据最后刷新时间按需触发一次增量同步；未配置平台（`isPlatformConfigured` 返回 false）不触发网络同步。

### 4. 健康检查分层、探针解耦与降级隔离

- **问题现象与风险**：
  - 原 `/healthz` 在第三方后台 Worker（如智慧树）异常时直接返回 HTTP 503，导致主站被负载均衡器剔除或整体不可用。
  - 原健康检查通过向数据目录写临时文件来探测写入能力，在高频探针下产生无效磁盘 I/O。
- **修复方案**：
  - 新增 `/livez`：纯 Web 存活探针，进程响应即返回 200 OK。
  - 新增 `/readyz`：本地核心存储就绪探针。检查核心目录存在性与写权限，检查关键数据（如 `users.json`）格式完好性，损坏时返回 503 `fail-closed`；不写临时探针文件。
  - 重构 `/healthz`：保持部署兼容。第三方 Worker 挂掉时将状态标记为 `degraded`，但整体仍然返回 200 OK，避免全站 503；仅在本地存储损坏或不可写等致命故障时才返回 503。
  - 诊断端点 `/api/diagnostics/workers`：展示 Worker 的心跳时间与新鲜度状态。

### 5. 静态资源与动态 HTML 缓存策略区分

- **问题现象与风险**：
  - 认证后动态页面与静态资源共用缓存头，可能导致用户数据被反向代理或浏览器错误缓存，或者静态资源无法长期利用客户端缓存。
- **修复方案**：
  - 在 `app.py` 的 `@app.after_request` 中区分响应类型：
    - 针对所有已认证页面及动态 `/api/*` 路由，强制注入 `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` 与 `Pragma: no-cache`。
    - 针对 `/static/*` 静态资源（CSS/JS/图标），注入 `Cache-Control: public, max-age=86400, stale-while-revalidate=604800`。
  - 字体回退：`tokens.css` 确保系统自带无衬线与等宽字体完整回退，不依赖外部 CDN。

---

## 三、修改文件清单与理由

| 文件 | 修改说明 |
|---|---|
| `settings.py` | 增加 `PUBLIC_BASE_URL`、`TRUSTED_HOSTS`、`ENV_MODE`、限流与 Agent 频率配置及生产断言 |
| `agent_auth.py` | 实现全局 O(1) 哈希索引、`last_used_at` 节流、多 Token 元数据、作用域与有效期管理 |
| `web_common.py` | `_get_external_base_url` 优先信赖可信 Host/固定公开 URL；`require_agent_auth` 增加服务端 scope 校验 |
| `routes/agent.py` | 在 Agent 项目/任务物理删除接口增加真实 `delete` scope 服务端拒绝检查 |
| `agent_mcp.py` | 增强 MCP 权限不足（403）和认证失败（401）的可读性错误与指引 |
| `app.py` | 配置 ProxyFix；增加受信 Host 中间件；动态/静态 Cache-Control 区分；限流器 TTL/容量淘汰；`/livez`、`/readyz`、降级版 `/healthz`、`/api/diagnostics/workers`；Agent Token Web 端点支持多 Token/权限/有效期 |
| `frontend/assets/js/csrf.js` | 增加 `isSameOrigin` 判定，同源才附加 CSRF Token；兼容 `Request` 对象与既有 Header |
| `frontend/assets/js/api/client.js` | 增加 `AbortController` 25s 超时取消；处理 401/409/429 可恢复错误 |
| `frontend/assets/js/features/todos.js` | 在勾选与标红操作中实际传递 `expected_updated_at` 落实版本冲突保护 |
| `frontend/assets/js/features/integrations.js` | 增加平台配置判定，未配置平台不触发后台同步 |
| `frontend/assets/js/bootstrap.js` | 增加基于 `visibilityState` 的自适应轮询调度器，隐藏暂停，前台恢复 |
| `frontend/assets/js/features/agent.js` | 多 Token 渲染、自定义权限/有效期生成、独立撤销按钮、无内联样式 |
| `frontend/templates/dashboard/_agent.html` | Agent 界面增加备注、权限单选、有效期及 Token 列表骨架；完全移除内联 `style=` |
| `frontend/assets/css/business.css` | 规范定义 Agent Token 选项面板、输入框、作用域与 Token 列表组件样式 |
| `tests/test_agent_api.py` | 增加多 Token Web 端点、权限分级测试 |
| `tests/test_agent_auth.py` | 增加索引、有效期、节流、老格式兼容性测试 |
| `tests/test_healthz.py` | 增加 `/livez`、`/readyz`、降级 `/healthz` 测试 |
| `tests/test_settings.py` | 增加生产配置断言与环境重置测试 |
| `tests/test_frontend_playwright.py` | 增加前端多 Token 生成、细粒度权限选择与单独撤销端到端测试 |

---

## 四、验证证据

### 1. 快速回归套件（Quick Suite）

- **命令**：
  ```powershell
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Suite quick
  ```
- **退出码**：`0`
- **运行结果**：`401 passed, 1 skipped, 131 deselected in 65.55s`
- **测试证据目录**：`test-results/20260929-122909-923d2e21/`

### 2. 核心安全与 Agent 专项测试

- **命令**：
  ```powershell
  C:/DesktopFiles/canvas-dashboard/.venv/Scripts/python.exe -m pytest tests/test_p0_safety.py tests/test_security_auth.py tests/test_settings.py tests/test_healthz.py tests/test_agent_api.py tests/test_agent_auth.py tests/test_agent_mcp.py -q
  ```
- **退出码**：`0`
- **运行结果**：`53 passed in 2.88s`

### 3. Playwright 前端 Agent 与核心待办端到端测试

- **命令**：
  ```powershell
  C:/DesktopFiles/canvas-dashboard/.venv/Scripts/python.exe -m pytest tests/test_frontend_playwright.py -k "agent or core_todo or subtasks" -q
  ```
- **退出码**：`0`
- **运行结果**：`5 passed, 64 deselected in 24.36s`
  - `test_frontend_agent_integration_page` PASSED
  - `test_frontend_agent_multi_token_and_scopes` PASSED
  - `test_frontend_v2_preserves_core_todo_actions` PASSED
  - `test_frontend_custom_todos_subtasks_platform_cards_without_ocr` PASSED
  - `test_frontend_external_platform_subtasks_lifecycle_and_badge` PASSED

### 4. 设计系统与组件规范 Lint

- **命令**：
  ```powershell
  C:/DesktopFiles/canvas-dashboard/.venv/Scripts/python.exe -m pytest tests/test_design_system_lint.py tests/test_css_architecture.py tests/test_business_components.py -q
  ```
- **退出码**：`0`
- **运行结果**：`18 passed in 0.14s`

---

## 五、兼容性风险与适用条件

1. **Agent Token 兼容性**：
   - 既有用户的 `agent_token.json` 自动平滑升级为带有兼容 `scopes: ["read", "write", "delete"]` 的结构，现有活跃 Token 保持完全有效，不会静默撤销。
   - 代码层直接调用 `agent_auth.create_token(username)`（如老脚本或老测试）默认保持全部权限；而在 Web API 与用户交互界面创建新凭据时默认 `["read"]` 只读。
2. **反向代理部署要求**：
   - 生产环境经 Nginx 反向代理时，Nginx 应配置 `X-Forwarded-For`、`X-Forwarded-Proto`；若启用 `IS_PRODUCTION=True`，必须在环境变量中提供 HTTPS 的 `CANVAS_DASHBOARD_PUBLIC_BASE_URL` 或在 `CANVAS_DASHBOARD_TRUSTED_HOSTS` 列举域名。
   - 本地开发与预览模式（`CANVAS_DASHBOARD_ENV=development`）无硬性要求，直接兼容 `127.0.0.1` 预览。
3. **健康检查端点**：
   - 容器编排层（K8s/Docker Swarm）可将 liveness probe 指向 `/livez`，readiness probe 指向 `/readyz`。原 `/healthz` 保持完全兼容既有监控探针。

---

## 六、未完成项与原因说明

1. **邀请码注册体系**：
   - 依据任务指示：“注册受控可采用既有关闭开关，不凭空强制新邀请产品”。当前项目已有成熟的 `CANVAS_DASHBOARD_REGISTRATION_ENABLED` 环境变量开关，若需停止开放仅需置为 `false`，未凭空创造额外的邀请码数据库表或邀请码输入产品流。
2. **全局 CSS 物理合并构建**：
   - 仓库内既有测试 `tests/test_css_architecture.py` 明确断言 `dashboard.css` 必须包含 `@layer` 和 `@import url("./...") layer(...)` 分层引用结构。若用脚本将所有 CSS 暴力打平成单文件，会破坏既有架构约束。因此本批采取了标准规范的做法：在 HTTP 响应头区分静态资源强缓存策略（`max-age=86400, stale-while-revalidate=604800`），既不违背既有架构测试，又大幅提升了资源加载性能。
