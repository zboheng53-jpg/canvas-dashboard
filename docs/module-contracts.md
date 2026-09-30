# 架构与业务约束

本页保存当前模块边界与业务不变量；修改模块前阅读对应段落。开发和发布流程以 [development.md](development.md) 为准。业务约束变更同步本页，无需复制回 AGENTS.md。

## 项目结构

```text
canvas-dashboard/
├── app.py                         # Flask 组装、认证边界、账户/平台路由与导出
├── routes/                        # planning / agent Blueprint；保持既有 API URL
├── services/                      # workspace 共用操作/投影、academic 学期/节假日
├── web_common.py                  # HTTP 校验、错误与 Agent 认证工具
├── login_capacity.py              # 单 Web 进程共享的远程认证窗口容量限制
├── capacity_guard.py              # 上线前注册容量保护：准入阈值、fail-closed 判断与公开说明
├── auth.py                        # 站点多用户系统、密码哈希与旧数据迁移
├── user_paths.py                  # 用户独立数据路径管理 (data/users/<username>/)
├── storage.py                     # 并发安全 JSON 读写与原子替换
├── tongji_timetable.py            # 一网通办课表 CDP 抓取与解析
├── tongji_login_sessions.py       # 同济加强认证短时 noVNC 窗口
├── schedule_store.py              # 课程与日程项存储
├── project_store.py               # 长期项目存储
├── action_contract.py             # 事项字段校验、幂等与版本冲突
├── workspace_agenda.py            # 统一事项引用与日期范围议程
├── canvas_auth.py                 # Canvas iCal 订阅抓取与解析
├── haoke_client.py                # 好课 API 客户端与缓存管理
├── zhixuemeng_client.py           # 智学盟客户端 (Token/课程/作业)
├── zhihuishu_store.py             # 智慧树缓存、状态与配置
├── zhihuishu_worker.py            # 智慧树后台多进程刷新 Worker
├── zhihuishu_browser.py           # 智慧树 Playwright 浏览器自动化
├── zhihuishu_login_sessions.py    # 智慧树短时 noVNC 登录窗口
├── recurring_todo_store.py        # 原生重复待办系列、周期展开与独立完成状态
├── external_subtasks.py           # 外部平台作业子任务持久化与装配
├── ketangpai_client.py            # 课堂派客户端 (短信/密码/课程/作业)
├── tongji_oj_client.py            # 同济OJ竞教融合实训平台客户端 (统一身份认证/作业列表)
├── agent_auth.py                  # Agent API 独立安全凭据与 Token 管理
├── agent_mcp.py                   # 零依赖通用 MCP Server 脚本 (JSON-RPC stdio)
├── frontend/                      # 可独立打开的前端工作区
│   ├── templates/                 # index.html 壳层；dashboard 各视图独立模板
│   └── assets/                    # css、js 与 downloads；仍通过 /static/ 提供
├── tests/                         # Pytest 单元测试与 Playwright 回归测试
├── deploy/                        # Nginx 与 systemd 部署参考配置
├── data/                          # 本地运行时数据 (不可随意篡改)
└── AGENTS.md                      # 规范指引 (本文件)
```

## 架构与平台核心机制

- **小范围开放与维护**：账户各自独立，不提供团队共享。左侧「上手指南」先辨析待办、项目、日程与各入口的分工，再按功能逐段说明，附 Canvas 日历馈送截图与手机日历订阅教程，底部提供最近更新；用户可感知的变化同步 `CHANGELOG.md`，实际部署后才标注发布日期。容量与运营判断见 `docs/small-group-launch.md`。`CANVAS_DASHBOARD_REGISTRATION_ENABLED` 控制新注册；`capacity_guard.py` 在总账户 15、近 14 天活跃账户 10 或已连接平台合计 40 达到时自动关闭新注册（`CANVAS_DASHBOARD_CAPACITY_*` 覆盖，单条设 0 表示不限制），注册页左侧介绍不变、右侧改为说明，登录页同步提示，已有账户不受影响；两类 noVNC 窗口共享 `CANVAS_DASHBOARD_LOGIN_MAX_SESSIONS`（默认 1），满载返回可重试的 429。Canvas 馈送仅接受管理员信任域名的 HTTPS/443，禁止重定向。
- **文件边界**：`app.py` 保留全局 Session/CSRF/限流中间件；事项和 Agent API 分别注册到 `routes/`，共享操作位于 `services/`。`index.html` 仅组装视图与脚本；普通脚本仍共享全局，依赖顺序明确保留在模板中，启动统一在 `bootstrap.js`，不在业务视图重复初始化。

- **存储与并发 (`storage.py`)**：
  - JSON 读写使用绝对路径加锁，写操作采用临时文件 + 原子替换 (`atomic replace`)。
  - 数据文件损坏时 `fail-closed`（备份 `.corrupt` 并抛出 `JsonFileCorruptionError`），切勿直接用空值覆盖。
  - 同一账户的自定义 Todo 更新必须通过 `locked_json_update()`。
- **用户隔离与路由**：
  - 所有 API 均需要站点 Session（除 `/healthz`、`/login`、`/register`、`/privacy`、`/welcome`、`/api/auth/*` 及 `/calendar/<token>.ics` 外）。
  - 用户独立数据存放于 `data/users/<username>/`，全局配置包含 `users.json`, `.flask_secret_key`, `.encryption_key` 等。
  - 生产 Session 必须校验不可变 `account_id` 与 `session_version`；永久删除必须经 `auth.delete_account()`，并保留不参与常规备份的删除账本以防旧备份复活账户。
- **统一待办状态**：
  - 平台缓存不得被本地完成、隐藏、标红、删除或标题/截止时间覆盖直接改写；统一通过各平台 `PlatformStateStore` 状态文件叠加，并允许恢复上游显示值。
  - 已完成且超过有效截止的普通待办自动永久删除，不可撤销或恢复；尚未截止则沉底，无截止则保留。纯日期按上海当日结束，重复待办只清理过期的已完成单次。
  - 待办清单只有一套分组与标色规则，与来源平台无关：固定「已逾期 → 今天 → 本周内（滚动 7 天）→ 无日期 → 更晚 → 已完成」，无日期固定在本周内之后，不设「明天」「此前未完成」分段；截止日期始终是同一枚胶囊标签（淡底色 + 圆角），只换字色与底色深浅：逾期和今天红色，3 天内截止黄色，其余灰蓝。行底色只区分逾期（红底）与今天（白底），近三天不铺黄底。
  - 普通 HTTP 平台通过 `http_sync.py` 共用全站有界预算（默认 2 个执行任务、32 个运行及排队任务），按账户、平台及任务类型去重；读取缓存后提交后台刷新。账户锁仅覆盖身份变更和最终关键写入，不覆盖整段读取或网络操作。
- **外部作业子任务 (`external_subtasks.py`)**：
  - 存储位于 `data/users/<username>/external_subtasks.json`，以 `source:item_id` 为稳定键，采用锁 + 原子写。
  - 支持 `canvas`、`haoke`、`zhixuemeng`、`zhihuishu`、`ketangpai`、`tongjioj` 6 大平台。各平台 `/api/<platform>/todos` 自动装配本地持久化子任务；提供 `PUT /api/external-subtasks` 供子任务增删改查。前端所有作业均共享子任务增删改、勾选、改期与展开交互，展开状态仅保留在前端内存。
- **平台同步元数据**：
  - `platform_sync_status.json` 只保存非敏感的连接、刷新、失败与日历资格状态；必须继续使用锁与原子写，并在损坏时 fail-closed。不得写入密码、Token、Cookie 或订阅地址。
- **长期项目 (`project_store.py`)**：
  - 存储位于 `data/users/<username>/projects.json` (v2)，采用锁 + 原子写。
  - 唯一主项目与 Next Action 原子维护，只要项目仍存在未完成的细分步骤，Next Action 永不为空（默认按分组与任务排序自动推选或顺延，用户可随时切换修改）；界面区分进行中/已完成/暂放；不设回收站。项目与任务删除后永久消失，不可找回；删除主项目后主项目重置为空。转资料在同一次项目锁内原子追加并物理移除原任务。
  - 新项目行动默认 `growth`，自定义待办默认 `obligation`；责任事项无日期也进入待办，成长行动不计入责任数量。既有未分类项目任务以 `legacy` 保留原有有日期才进入待办的行为，不能自动改写旧截止或批量迁移真实数据。
  - 行动标题与 `details` 分离，`planned_on` 是计划日期，`due_date` 是真实截止，项目级资料放 `materials`。旧长标题允许保留；缩短时保留 `original_name`。
  - Apple 日历使用独立投影，保留稳定 UID `project-task-...` / `project-due-...`；成长计划改分类后不因退出待办而丢失日历条目。
- **统一事项与排程 (`action_contract.py`, `workspace_agenda.py`)**：
  - `/api/actions` 和 `/api/agenda` 供网页及 Agent 共用；排程以 `action_ref` 引用原事项，标题与任务完成状态从原记录读取。取消安排不删除事项，单次完成不结束整个行动。
  - 创建支持 `request_id` 幂等，更新支持 `expected_updated_at` 冲突检查；使用各存储层锁和原子写，不绕过账户隔离。重复安排的单次修改须原子跳过原日期并创建例外，保留本次完成记录。
  - 今日总览保持现有左、中、右分区：中央为统一待办清单（今日与逾期项目行动由统一事项与议程投影去重后直接并入待办，不再另设独立行动卡片），右上长期项目、右下今日日程。可选下一步不自动排入今天。暂放、完成和删除项目的关联排程退出活动展示与订阅，但保留引用及历史。右下今天优先，有空间时接续未来日期；周视图使用全天、上午、下午、晚上四段并保留精确时间；桌面四段固定同屏，溢出项在格内入口展开。界面不展示“责任／成长”标签，表单以“同时加入待办清单”控制显示范围。
- **原生重复待办 (`recurring_todo_store.py`)**：
  - 存储位于 `data/users/<username>/recurring_todos.json`，采用锁 + 原子写。
  - 支持每周、隔周重复（以首次截止日期确定星期和隔周基准）。
  - 首页每个系列最多展示一条记录：按实际截止排序，取最早未完成且未跳过的单次；该次已逾期或截止距今不超过 7 天时进入首页，否则不占位。旧次未完成持续展示旧次，不阻碍后续次数在日程与全量展开中生成；完成或跳过旧次后顺延推选下一次。
  - 议程与 Apple 日历支持范围展开（UID 稳定前缀 `recurring-<series_id>-<orig_date>`），单次修改、跳过、完成与系列管理独立操作。
- **第三方平台特点**：
  - **Canvas**：解析 iCal feed，缓存于 `canvas_cache.json`。
  - **好课**：凭据加密存储，`/api/haoke/todos` 缓存优先，通过共享有界执行器异步刷新。
  - **智学盟**：使用 `X-Access-Token`，支持课程与作业列表抓取。
  - **智慧树**：路由只读缓存/状态；后台通过 `zhihuishu_worker.py --all-users` 定时拉取；独立 Chromium profile 运行；支持 noVNC 远程登录窗口。
  - **同济课表**：前端直接打开短时 noVNC 认证窗口；用户完成微信扫码或短信加强认证后，后端通过该窗口的 CDP 读取当前可见课表。只解析渲染中的表格并展开 `rowspan`/`colspan`，失败时保留上次成功缓存，认证结束或过期后删除临时 profile。
  - **课堂派**：凭据加密存储，支持短信验证码与账号密码双模式登录；动态获取当学期有效课程，按顺序抓取作业与随堂测验，自动滤除已交项；使用 `PlatformStateStore` 叠加本地状态。
  - **同济OJ**：凭据与会话加密存储，默认支持同济统一身份认证登录（`Unified_Certification`）并提供平台密码登录回退；仅只读抓取顶层作业列表，将每次作业作为一条待办事项导入，不读取提交记录或按分数判定完成，绝不打开题目详情或提交任何作业。完成与撤销由用户手动操作，沿用稳定作业 ID，并通过独立的 `PlatformStateStore` 叠加本地状态；同步与缓存版本更新不得重置这些状态或外部作业子任务。
- **Agent 接入与凭据 (`agent_auth.py`, `agent_mcp.py`)**：
  - 用户专属 Agent Token 采用独立高熵密钥生成（`cda_...`），在 `data/users/<username>/agent_token.json` 中仅存储 SHA-256 哈希，支持随时一键撤销与重置。
  - `/api/agent/v1/...` 接口采用 `Authorization: Bearer <token>` 认证，免受 CSRF 限制，提供统一事项与议程查询、待办和项目行动写入、关联排程、单次完成及项目资料更新等能力。写入规则由 `agent_mcp.py:WRITING_RULES` 与工具字段共同约束，Skill 与下载包同步验证。长期项目默认只落实当前一步，远期方向与方法写入资料；用户明确要求多步可扩展，不设服务端数量上限，不自动生成复盘或后续任务链。
  - `agent_mcp.py` 基于纯 Python 3 标准库（零外部依赖）实现 JSON-RPC 2.0 stdio MCP 协议，支持直接与 Claude Desktop、Cursor、Cline 等集成。
