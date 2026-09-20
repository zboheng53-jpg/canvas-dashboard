# 开发、验收与发布

本文是日常流程入口；架构约束以 `AGENTS.md` 为准，生产操作以 `operations.md` 为准。

## 1. 明确结果并复现

从用户描述整理「当前现象 → 预期行为 → 验收步骤」，简单修改用会话说明即可，无需另建计划文件。先看 `git status` 和相关入口，保留用户已有改动；开发使用 `codex/` 分支。遇到问题先建立可复现案例，再修改；只询问无法从代码或可逆默认值解决的关键缺口。

## 2. 选择本地环境

```powershell
# 使用现有本地账户数据；连接第三方平台时使用此模式
.\scripts\dev.ps1

# 日常 UI / 交互验收优先使用独立示例数据
.\scripts\dev.ps1 -Preview -Scenario normal
.\scripts\dev.ps1 -Preview -Scenario empty
.\scripts\dev.ps1 -Preview -Scenario dense
```

默认打开 http://127.0.0.1:5000/preview-login 自动进入示例账户。`normal` 包含待办、项目、关联排程和重复日程；`empty` 用于空状态；`dense` 增加 30 条长标题待办（含逾期和未来日期）及 12 条当天项目计划。日期相对启动当天生成。每次启动创建新的系统临时目录，不覆盖上一次预览；输出会给出该目录。需要保留手动操作状态时：

```powershell
.\.venv\Scripts\python.exe scripts/preview_action_workspace.py --scenario dense --data-dir <上次输出的目录>
```

只允许复用带正确前缀、场景相符的临时目录。跨日复用保留原始日期；需要今天的场景时重新启动新的预览。端口被占用时先确认已有服务来源，不随意停止进程；可加 `-Port 5001`。统一默认验收地址仍为 5000。

预览使用真实 Flask 页面与存储，天气和节假日为离线示例；它不证明第三方认证、实际同步或生产连接正常。不要在预览账户输入真实凭据。静态设计预览另见 `frontend/README.md`，不能替代真实 API 验收。

`CANVAS_DASHBOARD_DATA_DIR` 是统一数据目录覆盖项，必须在导入应用前设置；不设置时仍使用项目 `data/`。测试自动覆盖为临时目录，预览也在导入前设置；会话密钥、平台加密密钥、浏览器 profile、worker 锁与日志均遵循该目录。它不执行迁移或复制现有数据。

## 3. 按阶段验证

| 阶段 | 命令 | 覆盖范围 |
| --- | --- | --- |
| 修改中 | `.\scripts\test.ps1 -PytestArgs tests/test_projects.py` | 指定模块；优先选能复现问题的测试 |
| 快速反馈 | `.\scripts\test.ps1 -Suite quick` | 不依赖 browser fixture 的测试，首个失败即停止 |
| 本地验收前 | `.\scripts\test.ps1 -Suite acceptance` | 浏览器交互/布局、前端规范及账户、安全、统一事项、并发与流程检查 |
| 最终回归 | `.\scripts\test.ps1` | 完整 tests/；部署脚本也执行此入口 |
| 查看选择 | `.\scripts\test.ps1 -Suite acceptance -List` | 仅列出用例，不算测试通过 |

`-PytestArgs` 后可传多个 pytest 参数。与 `-Suite` 同用时，选择的是指定路径和套件的交集。套件筛选定义在 `tests/conftest.py`；新增浏览器测试使用共享 `browser` fixture，不自行启动 Chromium。quick 并非承诺固定秒数，输出的最慢十项用于发现实际瓶颈。

共享 `live_app` 提供独立账户目录、模拟平台响应和固定服务端日期；`browser` 使用同一天及上海时区。默认日期只在 `FIXED_NOW` 定义；特殊场景用 `@pytest.mark.now("2026-03-02T12:00:00+08:00")` 同时覆盖前后端日期，不在各测试粘贴 Date 模拟代码。真实平台集成问题仍需单独验证。

每次脚本运行产生独立的 `test-results/<时间-随机标识>/`：

- `run.json`：提交、工作区是否有改动、参数、退出码和是否仅收集；它是追溯记录，不是免测凭证。
- `results.xml`、`pytest.log`：测试结果和日志，末尾显示耗时最慢的用例。
- 浏览器用例失败时，在以用例散列命名的子目录保存用例名、控制台错误，并尽力保存仍打开的页面截图和 trace。已在测试中关闭的上下文可能无法捕获；不要为了截图掩盖原失败。

查看 trace：`.\.venv\Scripts\python.exe -m playwright show-trace <trace.zip>`。这些产物不提交 Git；仅保留本次排错需要的证据，避免上传含凭据的诊断文件。

布局测试验证具体几何与交互约束，截图供人工检查；当前没有像素基线自动比较，不能把「截图生成」表述成「视觉验收通过」。小范围视觉改动无需创建新的测试体系。

## 4. 交给用户本地验收

交付：本地地址、涉及的场景、2–5 个操作与预期结果、已运行检查和仍存在的限制。自动化通过后再请用户判断体验。验收要求来自 `AGENTS.md`，用户已明确验收过的同一结果不要重复询问。修订后复验受影响部分。

## 5. 合并、推送与发布

用户验收通过后，将分支合并到 `main`，确认 `git push origin main` 成功，再运行既有部署脚本。解决合并冲突或产生新变更后，验证最终版本；功能或视觉结果变化时补充相应验收。

部署脚本自动执行：

1. 要求分支为 `main`，工作区干净（包括未追踪源码），HEAD 与实时读取的远端 `origin` 的 `main` 相同。
2. 记录固定提交并跑完整回归、编译、加密备份和恢复演练。
3. 再次核对工作区与本地/远端提交；变化则停止，不自动提交、推送或丢弃修改。
4. 以固定提交打包，发布名称带提交前 12 位；继续原有原子切换、健康检查和失败回滚。

只做来源检查：`.\.venv\Scripts\python.exe scripts/check_release.py`。该命令会读取 origin 的远端引用，不写远端，不执行部署，也不会代替用户验收。最终报告发布名、完整提交和实际健康检查结果。

## 功能定位索引

| 功能 | 前端入口 | 后端与存储 | 优先检查 |
| --- | --- | --- | --- |
| 待办 | `features/todos.js`、首页模板 | `app.py`、`platform_state.py` | `test_custom_todo_subtasks.py`、`test_platform_state.py`、`test_frontend_playwright.py` |
| 项目 | `projects.js` | `app.py`、`project_store.py` | `test_projects.py`、`test_project_todos.py` |
| 事项与排程 | `features/workspace.js`、`features/schedule.js` | `action_contract.py`、`workspace_agenda.py`、`schedule_store.py` | `test_action_workspace.py`、`test_schedule.py`、`test_workspace_layout.py` |
| 账户与数据 | 设置、认证模板 | `auth.py`、`user_paths.py`、`storage.py` | `test_account_lifecycle.py`、`test_p0_safety.py`、`test_concurrent_writes.py` |
| 平台同步 | `features/connections.js` | 各平台 client/store/worker、`platform_sync.py` | 对应平台测试、`test_session_and_platform_sync.py` |
| Agent | `features/agent.js` | `agent_auth.py`、`agent_mcp.py`、`app.py` | `test_agent_api.py`、`test_agent_mcp.py` |
| 样式与响应式 | `frontend/assets/css/` | `frontend/DESIGN_SYSTEM.md` | `test_control_components.py`、`test_visual_regression.py` |
| 开发与发布 | `scripts/dev.ps1`、`scripts/test.ps1` | `scripts/check_release.py`、部署 skill 脚本 | `test_development_workflow.py`、`test_scripts.py`、`test_deploy_configs.py` |

表内 JS 路径相对 `frontend/assets/js/`，测试路径相对 `tests/`。变更行为时同步负责该约定的当前文档；历史计划保留，不作为新任务清单。

## 长期项目的当前交互

项目今日行动通过 `/api/actions/focus`（Agent 对应 `/api/agent/v1/actions/focus`）读取，不另存任务。返回 `today`、`previous`、`candidates`、`overdue` 和上海日期；网页将 today 与 overdue 按原事项引用去重并入原待办清单，复用普通待办行、日期分组、来源筛选及完成／删除按钮；不再另设今日行动卡片或特殊分区。计划日期不冒充截止日期，具体安排时间保留在行内说明。两边操作同一项目任务，删除即永久删除；单次完成仍在排程详情中操作。previous 与 candidates 保留供 Agent 查询；网页在长期项目内查看，不自动滚入今天。

完成的步骤分组沉底折叠，项目主界面不再用任务总数显示进度。界面区分进行中、已完成与暂放（对应既有 `archived`），不设回收站，项目与任务删除后永久消失不可找回。转资料在同一次项目锁内原子追加并物理移除原任务。

网页 DELETE 项目/任务为永久删除。Agent 使用项目/任务路径下的 POST `delete`；任务还支持 `to-materials`。新写入携带 `expected_updated_at`，转资料同时校验 `expected_project_updated_at`，资料超长或冲突不会删除原任务。项目暂放、完成或删除后，关联排程从议程与日历投影退出，底层安排和原引用保留。

Agent 默认每项目只落实当前一步，先读取项目完整内容和 focus，再复用或最少量写入，最后回读；用户明确要求可扩展，服务端不设行动数量上限。代码更新不自动更新外部 Agent 本机的 Skill/MCP 脚本，用户需通过既有更新入口更新并重启会话。

normal 预览含今日行动、旧计划、可选下一步和已完成步骤；dense 验证多项可达性；empty 验证空态。新增回归位于 `test_project_focus.py` 与 `test_project_focus_browser.py`，均纳入 acceptance。
