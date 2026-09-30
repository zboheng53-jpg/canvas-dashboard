# 开发、验收与发布

本文是日常流程入口；协作规则见 `AGENTS.md`，模块与业务约束见 `module-contracts.md`，运行拓扑见 `architecture.md`，生产操作以 `operations.md` 为准。

## 1. 明确结果并复现

从用户描述整理「当前现象 → 预期行为 → 验收步骤」，简单修改用会话说明即可，无需另建计划文件。先看 `git status` 和相关入口，保留用户已有改动；开发使用 `codex/` 分支。遇到问题先建立可复现案例，再修改；只询问无法从代码或可逆默认值解决的关键缺口。

### 一个人与多个 AI 的分工

用户决定目标、优先级和实质性产品取舍；AI 负责实现、验证和已授权范围内的交付。日常不要求 PR、第二个审批者、代码所有者审批或形式化审查记录。独立审查用于有具体风险的复杂变更；简单修复不自动扩成多代理任务。

**同一工作区只允许一个写入者。** 不同分支在同一目录里仍会共享文件，无法隔离 AI。存在另一个正在修改文件的任务时，新任务使用独立 worktree；串行的小任务可继续使用现有功能分支，不必每次创建工作树。

优先使用宿主提供的 worktree 工具；其他工具可用标准 Git，例如从已集成的 main 开始：

```powershell
git worktree add .worktrees/feature-x -b codex/feature-x main
cd .worktrees/feature-x
.\scripts\test.ps1 -ChangedOnly -Workers 2
.\scripts\dev.ps1 -Preview -Port 5001
```

worktree 不会复制未提交修改；有未合入依赖时明确指定其提交作为基线，不能假定文件已经带过去。已有混合改动先保持原位、按文件归属处理，不用 stash/reset/clean 或切分支替别的任务收拾工作区。只暂存自己的文件，避免 `git add -A` 将别的 AI 未完成工作带入提交。托管 worktree 用宿主归档功能回收；保留需要的证据后再清理。

`dev.ps1` 与 `test.ps1` 优先使用当前 worktree 的 `.venv`；不存在且两份 requirements 文件与主工作区一致时，自动复用主工作区已安装的包。源码、构建产物、测试结果和预览数据仍属于各自工作区。并行期间不向借用的环境安装/升级包；修改依赖的任务创建自己的 `.venv`。不复制或链接主目录的真实 `data/`。多个预览使用不同端口，多个定向测试按需用 1–2 worker，避免每个 AI 都开满 4 worker 跑全量。

**同一批交付由一个交付者收尾。** 各任务返回分支/提交、改动范围、已做验证和限制即可，不再生成专用交接报告。交付者按依赖顺序汇总，只在最终集成版本跑一次充分验证，再执行已授权的推送与部署。其他任务可继续在各自 worktree 开发，不改交付者正在验证的目录。无需新增中央调度服务、人工签字表或重复口头批准。

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

## 3. 两个验证时机，不叠加套件

开发中用能复现问题的最小测试；准备交付时，对最终改动运行一次足够的验证。`quick → ui → acceptance → all` 不是必走的流水线，完整回归已覆盖的检查不再重复。

| 目的 | 命令 | 说明 |
| --- | --- | --- |
| 复现与迭代 | `.\scripts\test.ps1 -PytestArgs tests/test_projects.py` | 指定文件或用例 |
| 未提交改动 | `.\scripts\test.ps1 -ChangedOnly` | 模块映射优先；无改动正常退出，不偷偷改测上次提交 |
| 整个分支改动 | `.\scripts\test.ps1 -BaseRef origin/main` | merge-base 到当前工作区，包含已提交、暂存、未暂存与未追踪文件；本地 origin/main 需按需更新 |
| 交付前：前端 | `.\scripts\test.ps1 -Suite ui` | 浏览器交互、布局与静态规则；有明确覆盖时也可指定受影响的浏览器文件 |
| 交付前：跨模块或安全边界 | `.\scripts\test.ps1 -Suite acceptance` | 账户、隔离、并发、接口与浏览器集成；平台内部修改可用对应模块测试 |
| 发布验证或广泛改动 | `.\scripts\test.ps1` | 一次完整回归，替代上述重叠套件 |
| 查看选择 | `.\scripts\test.ps1 -ChangedOnly -List` | 只收集，不算通过 |

`-ChangedOnly` 是快速反馈，不承诺动态依赖的完整覆盖：CSS 先跑静态规则，JS/模板走 UI，已映射后端模块先跑对应测试；账户/存储核心保留 acceptance，未知或删除路径保守全量。共享夹具、依赖、CI 改动跑全量。映射唯一实现为 `scripts/recommend_tests.py`；发现跨模块影响时主动补充对应测试，不靠继续增加文档门禁解决。

`-PytestArgs` 显式覆盖自动选择；与 `-Suite` 同用取交集。PowerShell 多参数用数组：`.\scripts\test.ps1 -PytestArgs @('tests/test_projects.py', '-q')`。默认 4 worker、`--dist loadfile`，可用 `-Workers` 或 `CANVAS_TEST_WORKERS` 调整；缺 xdist 会提示并串行。`-Suite quick` 是全部非浏览器测试，默认首个失败停止，不是固定秒数的快速检查。

既有本机基线约 3 分钟全量，不能外推为 CI 承诺。看本次实际时长和最慢用例；不为追求“绿色”自动重试失败测试，不为少跑测试删除有效行为断言。新测试优先复现故障、验证接口或用户行为，避免只断言脚本中出现某段文本。

### 环境与证据

首次安装在项目 `.venv` 中执行 `python -m pip install -r requirements-dev.txt` 和 `python -m playwright install chromium`。需要解释器路径时用 `$Python = & .\scripts\resolve-python.ps1`，再用 `& $Python scripts/check_test_env.py` 等命令；它只定位环境，不安装包。正常开发不反复运行环境诊断，只有解释器、权限、临时目录或浏览器异常才用 `scripts/check_test_env.py`。

测试和预览在导入应用前隔离数据目录，不接触真实账户。浏览器测试复用 `tests/conftest.py` 的 `live_app`、`browser` 和 `FIXED_NOW`；特殊日期用 `@pytest.mark.now(...)`。失败保留截图和最终 DOM，通过不录制；截图生成不等于视觉验收。真实第三方认证和同步仍需对应环境验证。

`test-results/<时间-随机标识>/` 保存 `run.json`、JUnit、日志与失败浏览器证据。schema 2 记录完整执行标记、运行前后提交/工作区状态和 Python/包版本/相关环境变量指纹；pytest 开始前写入未完成记录，中断不会伪装成成功。只有标准完整调用（无 `-List`、自动筛选、自定义 pytest 参数、`PYTEST_ADDOPTS` 或 `PYTEST_PLUGINS`）、始终干净且提交未变、环境一致、退出码与 JUnit 均通过，才可用于发布。指纹仅保存摘要，不记录环境变量原文。

这是可信本机的防误用检查，不是抵抗篡改的签名证明。脏工作区测试仍有诊断价值，但不能代表已提交发布版本。相同提交最新一次完整运行失败或中断时，不能采用更早成功结果；修复后重跑。旧格式证据保留供排错，不作为发布免重跑凭据。

自动轮转复用 `scripts/clean_test_artifacts.py`，只读运行元数据，不再每次递归统计所有产物大小。保护当前/最新轮次，保留最近 10 次成功、30 次失败及全部无法判断的轮次；手动清理默认 dry-run。只清理严格命名且确认位于 `test-results/` 下的目录，跳过链接。旧 ACL 异常残留不属于本次变更；搜索优先指定源码目录或用 `git ls-files`，不反复遍历运行数据和产物。

## 4. 按结果类型验收

UI/交互修改先由执行者实际核验隔离预览，再给出地址、2–5 个操作及预期结果，方便用户查看。只有用户要求验收后继续、存在关键产品分歧，或动作尚未获授权时，才等待用户决定；已经授权的交付不因每次 UI 修改追加一次批准。已确认过的相同结果不重复询问。纯后端、测试、规范与交付工具改动以自动化和可审查差异验收，不强制启动 UI，也不机械地追加一轮“用户批准”。用户已授权完整交付时沿用授权；仅新出现的实质性不可逆动作或未解决的关键分歧需要确认。

说明实际改动、检查结果和剩余限制即可。小任务不用计划文件、额外审计报告、反复截图或多模型评审；审查聚焦数据边界、回归风险与行为正确性。行为变化只同步负责该约定的当前文档，历史计划不作为门禁。

## 5. 本地集成与发布

日常以本地检查作为交付证据。`.github/workflows/verify.yml` 仅保留手动 `workflow_dispatch`：需要验证干净安装环境、排查“本机正常”或依赖更新时按需触发；普通 push/PR 不自动再跑一遍完整测试。CI 只有 `contents: read`，不放生产 SSH/备份密钥，固定 Actions 提交，复用依赖缓存、取消过时运行、保留 14 天证据。触发与权限机制见 [GitHub Actions 官方工作流语法](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)。

当前不要求配置分支保护、第二人审批或等待远端检查；CI 是诊断入口。发布仍由本机脚本核验来源、测试和备份，不能把用户没看过的任意 JSON 或未实际运行的 CI 配置当成功证明。

仅在任务包含合并/推送/发布时继续对应动作。保持短期功能分支，允许时优先 fast-forward 保留已测试提交；合并冲突或新提交改变内容则重新验证最终版本。确认 `git push origin main` 成功后运行已有部署入口：

```powershell
.\.agents\skills\deploy-canvas-dashboard\scripts\deploy.ps1
```

脚本自动执行：

1. 要求干净 main（包括未追踪源码），与实时远端 main 一致，固定发布提交。
2. 默认核验并复用本机该提交的完整测试证据；没有有效证据就运行一次全量，再核验证据。`-ForceLocalRegression` 强制重跑；兼容的 `-SkipLocalRegression` 表示必须有有效证据，绝不是关闭门禁。
3. 编译 tracked Python、加密备份、下载校验与隔离恢复演练；再次检查源码及远端没有改变。
4. 打包固定提交，通过固定 SSH 主机密钥上传；原子激活、服务与健康检查、失败回滚仍由服务器安装器负责。

传输和只读探测可重试；**激活不自动重试**。SSH 中断不能证明服务端未执行，先按 `docs/operations.md` 查实际活动版本和状态，避免重复解包、重启或覆盖回滚关系。日常发布不再执行旧应用退役脚本；退役是独立运维动作。

按当前规模，先保持“本地集成验证 → 固定提交发布”。不为消除一次本地回归引入整套远端签名、制品仓库和审批链。跨平台依赖锁定仍有价值，但不能把 Windows 的 `pip freeze` 直接当生产 Linux 锁文件；调整生产依赖应在对应平台解析并验证。只有实际出现多机发布、本机环境无法维护或发布构建成为瓶颈时，再扩展 CI 构建与制品推广。备份/恢复演练与最终健康检查继续保留。

## 功能定位索引

| 功能 | 前端入口 | 后端与存储 | 优先检查 |
| --- | --- | --- | --- |
| 待办 | `features/todos.js`、`dashboard/_overview.html` | `routes/planning.py`、`services/workspace.py`、`platform_state.py` | `test_custom_todo_subtasks.py`、`test_platform_state.py`、`test_frontend_playwright.py` |
| 项目 | `projects.js`、`dashboard/_projects.html` | `routes/planning.py`、`services/workspace.py`、`project_store.py` | `test_projects.py`、`test_project_todos.py` |
| 事项与排程 | `features/workspace.js`、`features/schedule.js` | `action_contract.py`、`workspace_agenda.py`、`schedule_store.py` | `test_action_workspace.py`、`test_schedule.py`、`test_workspace_layout.py` |
| 账户与数据 | 设置、认证模板 | `auth.py`、`user_paths.py`、`storage.py` | `test_account_lifecycle.py`、`test_p0_safety.py`、`test_concurrent_writes.py` |
| 平台同步 | `features/connections.js` | 各平台 client/store/worker、`platform_sync.py` | 对应平台测试、`test_session_and_platform_sync.py` |
| Agent | `features/agent.js` | `agent_auth.py`、`agent_mcp.py`、`routes/agent.py`（接口）、`app.py`（下载） | `test_agent_api.py`、`test_agent_mcp.py` |
| 新手与公开展示 | `dashboard/_guide.html`、`_auth_landing_showcase.html` | `app.py`、`login_capacity.py`、`settings.py` | `test_release_onboarding.py`、`test_login_capacity.py` |
| 样式与响应式 | `frontend/assets/css/` | `frontend/DESIGN_SYSTEM.md` | `test_control_components.py`、`test_visual_regression.py` |
| 开发与发布 | `scripts/dev.ps1`、`scripts/test.ps1` | `scripts/check_release.py`、`scripts/check_test_env.py`、`scripts/clean_test_artifacts.py`、`scripts/recommend_tests.py`、部署 skill 脚本 | `test_development_workflow.py`、`test_scripts.py`、`test_deploy_configs.py` |

表内 JS 路径相对 `frontend/assets/js/`，测试路径相对 `tests/`。变更行为时同步负责该约定的当前文档；历史计划保留，不作为新任务清单。

右上角刷新图标统一跟随本地查询、各平台请求和实际后台任务：任一仍在进行时持续旋转，不显示更新文案；全部结束后，成功不提示，确认失败时仅在图标旁按当前可见平台汇总「N 处连接失败」「N 处未同步」，点击可进入连接与同步查看原因。未配置、主动断开或仅缓存过期不计为确认失败，成功重试后清除错误提示。连接管理页使用同一份状态，不根据卡片文案猜测失败，也不提前报告同步完成。

同济 OJ 的 todos 接口只读取本地投影；`cache_only=1` 不启动同步，普通读取在缓存过期或缺失时启动后台同步，`refresh=1` 请求强制后台同步。所有请求立即返回缓存和 `sync.refreshing`，上游网络请求不占用 Waitress 请求线程。每账户最多一个同步任务，浏览器在同步中每 2 秒读取缓存，完成后停止轮询并自动更新列表；断开、清除或重新登录会使旧任务失效，禁止旧任务恢复凭据或缓存。等待与失败期间均保留已有作业，不另设 OJ 更新横幅。恢复的 Cookie 绑定 OJ 域名，续期后保存最新会话；顶层列表连接超时 8 秒，读取超时默认 45 秒（`TONGJIOJ_READ_TIMEOUT_SECONDS` 可覆盖），网络超时或临时网关错误最多重试一次，最终失败才记录失败状态。选定课程不绕过新鲜缓存，配置接口只读取已保存的课程；更新成功后课程选择框同步更新。共享 `live_app` 支持 `@pytest.mark.waitress`，以真实 WSGI 线程池验证上游挂起时刷新去重、普通请求可用及自动更新；真实平台网络耗时需在实际连接环境验证。

同济 OJ 只抓取顶层作业列表，不读取最终提交记录，也不按提交次数或分数推断完成；完成与撤销完成均由用户手动操作。继续使用原有 `tjoj_<assignment_id>` 标识及独立的 `tongjioj_state.json` 和外部子任务记录，刷新不重置勾选、撤销、隐藏、标红、删除、标题／截止时间覆盖或子任务。缓存版本 3 更新只让旧缓存过期并触发后台同步，等待和失败时仍显示旧投影，不删除本地状态；过去被最终提交记录过滤且没有手动完成的开放作业，会在成功同步后重新出现。

好课的 `sync.refreshing` 反映实际后台任务，而非缓存是否过期。`cache_only=1` 只读取投影，不重启失败的同步；浏览器每 2 秒轮询至任务结束，`refresh=1` 可强制刷新现有缓存。

Canvas、好课、智学盟、课堂派和同济 OJ 的冷缓存也立即返回 pending/refreshing，共用 `http_sync.py` 的有界执行器（`HTTP_SYNC_MAX_WORKERS=2`、`HTTP_SYNC_MAX_JOBS=32`；任务上限包括排队和运行）。按 `(username, platform, job_type)` 去重，平台内部按顺序抓取。发布缓存和错误状态前复核账户不可变身份及连接版本，断开后重连不会接收旧任务结果。浏览器隐藏时暂停缓存轮询和周期刷新，回前台按需恢复；轮询使用 `cache_only=1`，失败结束后不重新发起同步。

第三方短信、验证码、登录及临时浏览器启动／读取通过同一预算提交后台操作，原接口返回 202 与 `status_url`，`GET /api/operations/<token>` 只供原账户身份读取。网页 `csrf.js` 等待任务结果，接口本身不占着 Waitress 线程等外网。队列满或同类任务已有返回带 Retry-After 的 429。天气也采用缓存优先；节假日只读本地缓存，普通页面不再通过 CDP 创建浏览器标签。旧 `POST /api/schedule/refresh` 返回 410，不接收密码或启动浏览器。

普通请求绑定不可变账户身份，读取不持有账户独占锁；`storage.py` 的关键写入短暂获取账户锁并复核身份，锁顺序为账户锁后文件锁。删除、身份变化仍在账户锁中完成。跨模块验证包括旧后台任务遇到删除重注册不回写，以及同用户慢请求期间本地接口正常响应。

平台 GET 列表不再自动删除过期隐藏项。日期解析将无时区校园时间按上海时区处理，纯日期表示当天结束；过期判断使用本地覆盖后的有效截止。Canvas 新稳定 ID 区分 assignment/calendar_event，迁移包含本地状态、覆盖、子任务和排程引用；旧 ID 歧义保留原数据并记录诊断，不自动猜归属。

完成待办的截止规则：已完成且超过有效截止后自动删除，不提供撤销或恢复；已完成但尚未截止继续沉底，无截止则保留。自定义待办物理删除，不因刚完成、幂等键或关联安排延长保留；平台通过独立状态文件记录永久删除标识，不修改上游缓存，旧完成／撤销／改期操作不能复活自动删除项。重复待办只删除已完成的过期单次，系列及后续次数不变。清理发生在本地列表读取时；只有日期按上海当日结束，未完成逾期保留并标红。长期项目及其步骤的存储规则仍见项目章节。

待办清单的分组与标色只有一套规则，与事项来自哪个平台无关：固定按「已逾期 → 今天 → 本周内（滚动 7 天）→ 无日期 → 更晚 → 已完成」排列，无日期固定在本周内之后，不设「明天」「此前未完成」分段。截止日期始终是同一枚胶囊标签（淡底色 + 圆角），只换字色与底色深浅：逾期与今天红色，3 天内（含今天之后第 1–3 天）截止黄色，其余灰蓝；行底色只区分逾期（红底）与今天（白底），近三天不铺黄底。分组与颜色共用同一个有效截止判断。

静态资源以 `frontend/assets/css`、`js` 为源；`scripts/build_assets.py` 展开分层 CSS import 并生成内容指纹与 manifest 到忽略的 `frontend/assets/built/`。开发启动和发布安装会构建。直接运行 app 或导出预览前若修改了 CSS/JS，应先运行构建脚本并重启进程，使加载的 manifest 与源码一致。源文件结构和普通脚本依赖顺序不变。

Agent 的所有新 Token 默认只读；测试需要写入时应显式申请 read/write/delete。旧单 Token 保留原兼容权限。名称、有效期、单凭据撤销与服务端权限检查由 agent_auth/routes 维护；只写客户端提示不能代替服务端拒绝。

## 长期项目的当前交互

项目今日行动通过 `/api/actions/focus`（Agent 对应 `/api/agent/v1/actions/focus`）读取，不另存任务。返回 `today`、`previous`、`candidates`、`overdue` 和上海日期；网页将 today 与 overdue 按原事项引用去重并入原待办清单，复用普通待办行、日期分组、来源筛选及完成／删除按钮；不再另设今日行动卡片或特殊分区。计划日期不冒充截止日期，具体安排时间保留在行内说明。两边操作同一项目任务，删除即永久删除；单次完成仍在排程详情中操作。previous 与 candidates 保留供 Agent 查询；网页在长期项目内查看，不自动滚入今天。

完成的步骤分组沉底折叠，项目主界面不再用任务总数显示进度。界面区分进行中、已完成与暂放（对应既有 `archived`），不设回收站，项目与任务删除后永久消失不可找回。转资料在同一次项目锁内原子追加并物理移除原任务。

网页 DELETE 项目/任务为永久删除。Agent 使用项目/任务路径下的 POST `delete`；任务还支持 `to-materials`。新写入携带 `expected_updated_at`，转资料同时校验 `expected_project_updated_at`，资料超长或冲突不会删除原任务。项目暂放、完成或删除后，关联排程从议程与日历投影退出，底层安排和原引用保留。

Agent 默认每项目只落实当前一步，先读取项目完整内容和 focus，再复用或最少量写入，最后回读；用户明确要求可扩展，服务端不设行动数量上限。代码更新不自动更新外部 Agent 本机的 Skill/MCP 脚本，用户需通过既有更新入口更新并重启会话。

Agent 写入先判断事项归属，再判断责任性质与重复范围：普通课程作业默认进自定义待办，跨学期或重复节奏不构成长期项目。默认每项仅录最近一次可靠截止并在 details 保留周期原文；明确要求批量录入时才展开。普通待办暂无自动续期，recurring 仅为每周时间安排，不支持隔周规则或生成下次待办。用户纠正时重新判断归属与范围；写入后从待办入口核对来源和各项截止。统一规则维护在 `agent_mcp.py:WRITING_RULES`，同步到 `skill/SKILL.md`，由导出与 MCP 初始化检查验证分发一致性；这些检查不代表模型一定遵循规则。

normal 预览含今日行动、旧计划、可选下一步和已完成步骤；dense 验证多项可达性；empty 验证空态。新增回归位于 `test_project_focus.py` 与 `test_project_focus_browser.py`，均纳入 acceptance。
