# 同步可信度与浏览器资源生命周期修复报告 (2026-09-29)

本文档记录根据代码审阅报告（第二/三批：同步可信度与浏览器资源生命周期）在 `codex/review-sync` 分支上完成的核实、架构改进与测试验收。

---

## 一、问题核实与现状分析

对照审阅报告与基线提交（`ad7abad`），核实以下具体问题与风险：

1. **智慧树抓取失败覆盖正常缓存（核实属实）**：
   - 原 `_task_list_response_items` 在 JSON 解析异常或 payload 不是 dict 时返回 `[]`，将上游 500、网络中断或返回 HTML 登录页等错误直接当作“0 项待办”。
   - 抓取多个课程时，若个别课程因超时跳过，worker 仍将残缺的列表直接写入 `save_cache`，导致用户作业被清空。
2. **定时抓取间隔被绕过（核实属实）**：
   - worker 子进程由 `_run_user_subprocess` 启动，传参 `--once`，在 `_run_once` 中硬编码 `run_scheduled_cycle(username, force_fetch=True)`，导致每次心跳循环均强制抓取作业，绕过了 45 分钟周期的约束。
3. **失败退避全局化而非单账户独立（核实属实）**：
   - 原代码中全局 sleep 取所有用户失败退避的最小值，随后的下一轮再次遍历所有用户，导致一个频繁失败的用户把整个系统的重试周期打乱，健康账户与失败账户缺乏隔离。
4. **未连接智慧树的账户启动浏览器（核实属实）**：
   - 原 `_all_usernames()` 在生产环境扫描全体活跃用户，仅排除显式 `session == "disconnected"`；未配置智慧树或处于 `need_relogin` 状态的用户仍然启动 Playwright 进程。
5. **每轮次重复启动浏览器 context（核实属实）**：
   - 原 `check_session`、`keepalive`、`fetch_assignments` 各自独立调用 `_new_context()`，一次抓取轮次启动关闭 Chromium 达 3 次，开销大且容易累积内存泄漏。
6. **Chromium 活跃锁被误删（核实属实）**：
   - 原 `_profile_lock_is_stale()` 当 `not lock_target.startswith(prefix)` 时返回 `True`。在 Docker 容器或跨主机部署下，容器 hostname 与宿主机不同，导致宿主机清理逻辑将容器中正在运行的 Chromium `SingletonLock` 判定为陈旧锁并强行删除。
7. **无统一浏览器额度与 profile 跨进程互斥（核实属实）**：
   - noVNC 登录容器受 `startup_slot` 限制，但后台 worker 未纳入该限额，导致登录窗口与 worker 并发运行超出服务器承载；且两者未对同一用户的 Chromium profile 加独占锁。
8. **Docker 启停无超时与 starting 状态误杀（核实属实）**：
   - Docker 命令没有 timeout 限制；容器创建和会话元数据落盘之间存在时间差，未处于启动宽限期保护的容器会被 `cleanup_orphaned_containers` 误杀。
9. **Canvas/好课冷缓存同步阻塞请求（核实属实）**：
   - Canvas GET 接口直接同步请求上游 iCal feed；好课冷缓存时直接同步抓取；后台刷新为每个用户无节制创建线程。
10. **天气接口缺少共享缓存与合并（核实属实）**：
    - 每次前端请求天气均向外部天气 API 发起请求，同校区多用户并发时重复消耗网络配额且增加响应延迟。

---

## 二、修复方案与技术实现

### 1. HTTP 异步化与统一有界执行器 (`http_sync.py`)
- **有界并发**：设立 `ThreadPoolExecutor(max_workers=2)`，全站 HTTP 同步初始并发预算固定为 2。
- **请求去重**：以 `(username, platform)` 为键去重，正在排队或执行中的任务不会重复提交，返回已有任务状态。
- **身份一致性与断开防护**：
  - 任务提交时记录不可变账户身份（兼容 `auth.get_account_identity`、`session_identity` 与 `account_metadata`）。
  - 执行前与回写前两次校验账户身份和连接状态；若账户被删除、重建或用户断开平台连接，丢弃陈旧数据，绝不写回缓存。
- **冷缓存返回 pending**：
  - `/api/canvas/todos` 与 `/api/haoke/todos` 在无缓存（冷缓存）时立即返回 `{"ok": True, "data": [], "cached": True, "has_cache": False, "refreshing": True, "stale": True}`，触发后台异步刷新，避免阻塞 Web 线程。

### 2. 天气共享缓存与合并 (`app.py`)
- **TTL 缓存**：按校区（`siping`、`jiading` 等）缓存天气数据，有效期 15 分钟（`WEATHER_CACHE_TTL_SECONDS = 900`）。
- **请求合并（Coalescing）**：按校区分片互斥锁，多请求并发时仅首个请求穿透至上游，后续请求等待锁释放后直接复用新鲜缓存。
- **超时与降级**：上游请求设置 5 秒超时；失败时降级返回已有缓存，不影响主页待办渲染。

### 3. 智慧树抓取可靠性与安全合并 (`zhihuishu_browser.py`, `zhihuishu_worker.py`)
- **严格区分空结果与失败**：
  - `_task_list_response_items`：对 HTTP 非 200、JSON 错误、非字典 payload、code 非 200/0、data 非列表均返回 `None`；仅当上游明确返回 `{"code": 200, "data": []}` 时返回合法空列表 `[]`。
  - `_fetch_unfinished_homework_items`：请求失败或未收到有效响应时返回 `None`。
- **部分成功与失败合并策略**：
  - `fetch_assignments` 返回 `AssignmentFetchResult`，携带 `ok`、`partial`、`succeeded_courses` 与 `failed_courses`。
  - **完全失败**：绝不调用 `save_cache`，完整保留旧缓存，标记平台状态为 `error`，更新 `last_error`。
  - **部分失败**：从旧缓存中保留属于 `failed_courses` 的未完成事项，与本次 `succeeded_courses` 抓取到的最新事项合并后存入缓存，更新状态 `partial_fetch=True`。
  - **完全成功**：以最新抓取列表替换缓存。

### 4. 浏览器生命周期与配额治理 (`login_capacity.py`, `zhihuishu_login_sessions.py`, `tongji_login_sessions.py`)
- **共享全站浏览器配额**：
  - `worker_browser_slot` 与 `startup_slot` 共享 `settings.LOGIN_MAX_SESSIONS`。当存在活跃 noVNC 登录会话或 worker 租约时，超过额度的后台任务自动让出并等待下轮。
- **Profile 跨进程独占锁**：
  - `account_profile_lock(data_dir, username)`：在 `users/<username>/.zhihuishu_profile.lock` 上建立独占文件锁，禁止同一用户的 noVNC 窗口与后台 worker 同时使用 Chromium profile。
- **修复 SingletonLock 误判**：
  - `_profile_lock_is_stale`：当 lock target 中的 hostname 与宿主机不一致时返回 `False`，避免删除 Docker 容器内 Chromium 的活跃锁。
- **Docker 命令预算与宽限期**：
  - Docker 命令加入 30 秒超时（容器停止与列表命令 15 秒超时）。
  - 创建会话前预先写入 `status: "starting"`；`cleanup_expired_sessions` 与 `cleanup_orphaned_containers` 增加 60 秒启动宽限期（`STARTUP_GRACE_PERIOD_SECONDS`），杜绝启动竞态下被误杀。
- **超时进程树清理**：
  - worker 子进程在 Windows 下创建新进程组（`CREATE_NEW_PROCESS_GROUP`），Linux 下创建新 session（`start_new_session=True`）。
  - 超时时通过 `taskkill /F /T /PID`（Windows）或 `os.killpg`（Linux）递归终止子进程及其所有 Chromium 孙进程，确保配额释放前资源已完全回收。

### 5. 定时调度与公平调度 (`zhihuishu_worker.py`)
- **分离单次执行与强制抓取**：
  - 增加 `--force-fetch` CLI 参数；普通定时周期轮询传 `force_fetch=False`，严格尊重 45 分钟 `FETCH_INTERVAL_SECONDS`。
- **独立每账户 `next_attempt_at` 退避**：
  - 状态中独立保存各账户的 `failure_count` 与 `next_attempt_at`；未到重试时间的失败账户在轮次中直接跳过，健康账户保持正常调度。
- **筛选已连接账户**：
  - 生产环境 `_all_usernames()` 仅收录 `session == "active"` 的账户，未配置或处于 `need_relogin` 的账户不唤醒浏览器。
- **公平调度**：
  - 按各账户最旧的 `last_fetch_at` / `last_keepalive_at` 排序，避免慢账户饿死其他账户。
- **单 Context 复用**：
  - 新增 `run_user_cycle`，在单次 Playwright Context 内按需完成 session check、keepalive 与作业抓取，将单轮 Chromium 启停次数由 3 次降为 1 次。

### 6. 前端 UI 适配 (`integrations.js`, `todos.js`)
- 适配 `sync.refreshing` 状态，在冷缓存或后台刷新期间以 2 秒间隔轮询 `/api/canvas/todos?cache_only=1`。
- 刷新期间显示“同步中…”，并完整保留展示已有缓存数据，避免界面闪烁或空态抖动。

---

## 三、测试与验证

### 1. 自动化测试套件运行结果
运行全套单元测试及集成回归（通过隔离临时环境 `$env:TEMP`，不访问真实数据与网络）：

```powershell
$env:TEMP = "C:\Users\zhangboheng\AppData\Local\Temp\canvas-test-temp"
& "C:/DesktopFiles/canvas-dashboard/.venv/Scripts/python.exe" -m pytest tests/test_sync_remediation.py tests/test_canvas_auth.py tests/test_haoke_api.py tests/test_haoke_client.py tests/test_dashboard_localization.py tests/test_tongji_login_sessions.py tests/test_zhihuishu_login_sessions.py tests/test_login_capacity.py tests/test_zhihuishu_api.py tests/test_zhihuishu_browser.py tests/test_zhihuishu_worker.py tests/test_zhihuishu_store.py -q --basetemp="$env:TEMP/bt"
```
- **结果**：85 passed in 2.65s (退出码: 0)。

### 2. 覆盖的专门场景 (`tests/test_sync_remediation.py`)
1. `test_zhihuishu_response_validation`：响应结构校验，验证空列表 `[]` 与各类异常/500/畸变数据返回 `None`。
2. `test_zhihuishu_complete_failure_preserves_old_cache`：全失败时不写回 cache，旧缓存 100% 留存，平台同步记为错误。
3. `test_zhihuishu_partial_failure_merges_failed_courses_from_old_cache`：部分失败时，保留失败课程旧事项并合并成功课程新事项。
4. `test_foreign_chromium_lock_not_stale`：异构主机/容器 hostname 锁不被误删。
5. `test_shared_browser_quota_and_profile_lock`：跨进程 profile 锁互斥；noVNC 窗口与 worker 额度共享互斥。
6. `test_login_session_starting_grace_period`：starting 状态 60s 宽限期保护，防清理器误杀。
7. `test_http_sync_deduplication_and_bounded_executor`：同账户同平台并发请求去重与有界调度。
8. `test_http_sync_aborts_writeback_on_identity_change`：同步途中用户注销/断开/重建，写回自动中止。
9. `test_weather_shared_cache_and_coalescing`：校区天气缓存与并发在途请求合并。

---

## 四、文件修改范围与兼容性说明

### 修改文件
- `http_sync.py` (新增)：统一有界 HTTP 执行器、去重与身份校验。
- `login_capacity.py`：全站浏览器配额共享租约与 profile 互斥锁。
- `canvas_auth.py`：冷缓存返回、后台刷新与写回安全校验。
- `haoke_client.py`：后台异步刷新接入 `http_sync`，写回安全校验。
- `zhihuishu_browser.py`：响应校验、上下文复用 `run_user_cycle`、非本地锁防护。
- `zhihuishu_worker.py`：分离强制抓取、退避与公平调度、安全缓存合并、进程树终止。
- `zhihuishu_login_sessions.py`：Docker 超时、starting 状态与宽限期。
- `tongji_login_sessions.py`：Docker 超时、starting 状态与宽限期。
- `app.py`：天气共享缓存与合并；Canvas/好课冷缓存待办响应适配。
- `frontend/assets/js/features/integrations.js`：适配后台刷新与轮询。
- `frontend/assets/js/features/todos.js`：适配待办列表异步刷新状态与缓存留存。
- `tests/test_sync_remediation.py` (新增)：第二/三批专项测试。
- `tests/test_haoke_api.py`：适配冷缓存 pending 状态断言。
- `tests/test_zhihuishu_browser.py`：更新容器锁测试断言。
- `docs/reviews/2026-09-29-sync-remediation.md` (本文件)：详细审阅修复与验证报告。

### 兼容性语义
- 严格保持现有 API URL 及返回结构不变；冷缓存时通过已有 `cached=True` 与 `refreshing=True` 表达状态，前端与 Agent 均可无缝消费。
- 未修改任何禁止触碰的身份与数据文件（`auth.py`、`platform_state.py`、`external_subtasks.py`、Canvas ID 提取函数等保持原样）。
- 既有测试用例保持 100% 通过。
