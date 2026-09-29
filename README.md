# Canvas Dashboard

> 给一小群同学使用的个人工作台：汇总作业，推进项目，安排今天。
>
> 🌐 **在线网址**：[https://canvas-dashboard.xyz](https://canvas-dashboard.xyz)

Canvas Dashboard 面向同济学生，聚合 Canvas、好课、智学盟、智慧树、课堂派、同济OJ 中的事项，也支持手动与重复待办、课表、日程和长期项目。每个账户拥有独立的数据空间，目前不提供团队共享或协作编辑。保持 Flask + Vanilla JS + JSON，适合小范围使用和个人维护。

## 第一次使用

注册并登录后，打开左侧 **上手指南**：先分清待办、项目、日程，再按功能逐段看，附常见问题和 GitHub 开源入口。也可以先从今日总览写下一个待办，再按需连接教学平台。

| 想做什么 | 使用哪个功能 |
| --- | --- |
| 记住「要交实验报告」 | 待办；截止日期填真实要求，无日期也可以 |
| 持续推进「完成课程设计」 | 长期项目；目标和资料分开，先确定下一步 |
| 计划「今晚 19:00 写报告」 | 日程；关联已有事项，不必重复创建 |

在这里勾选完成不会向教学平台提交作业；重要截止和提交结果请核对原平台。上游不可用时保留旧缓存，最近成功时间可在「连接与同步」查看。

## 使用定位

电脑端是完整工作台，承载平台配置、项目整理、排程管理等全部功能。手机端是补充入口，优先方便查看待办与临近截止、快速新增和完成事项、查看日程及项目当前行动，不追求把完整电脑界面压缩到小屏。

手机首屏优先呈现任务主标题、来源及截止／计划时间，完整管理和上手指南可从菜单进入。

## 它能做什么

- **汇总待办**：集中查看 Canvas、好课、智学盟、智慧树、课堂派、同济OJ 与手动添加的未完成事项；可以为平台事项叠加本地的完成、隐藏、标红等状态，而不改写原始平台数据。
- **管理个人任务**：创建带截止日期、子任务和优先级的自定义待办。
- **整理日程与课表**：通过同济统一身份认证导入当前课表，或导入浏览器导出的课表文件，手动创建单次与周期日程。
- **推进长期项目**：记录项目、任务分组和下一步行动，避免重要但不紧急的事被日常作业淹没。
- **日历订阅（Apple / Google 等）**：生成私有 iCalendar 地址，将有日期的未完成事项同步到日历。
- **AI Agent 接入 (MCP & Skills)**：支持 Claude Desktop、Cursor、Cline、Claude Code、Antigravity 等 AI 助手通过专属安全 Token 直接接入控制台，自主查询课表日程、聚合待办、添加待办和管理项目。
- **按账户隔离数据**：每位用户独立保存配置、待办、课表、项目和平台缓存。

## 本地运行

### 1. 准备环境

建议使用 Python 虚拟环境，避免污染系统 Python：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
```

普通待办、项目和日程不需要浏览器服务。智慧树后台刷新需要 Playwright 的 Chromium：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

智慧树和同济课表的远程登录窗口还依赖 Docker/noVNC、对应镜像及反向代理，单独安装 Chromium 不足以启用；见 [登录窗口配置](deploy/zhihuishu-login-tunnel.md)。仅体验界面时可运行 `scripts/dev.ps1 -Preview -Scenario normal`，无需真实平台凭据。

### 2. 启动开发服务

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

然后访问 <http://127.0.0.1:5000/>。默认只监听本机；如需指定地址或端口，可传入参数：

```powershell
.\scripts\dev.ps1 -HostName 127.0.0.1 -Port 5001
```

也可以直接运行入口程序：

```powershell
.\.venv\Scripts\python.exe app.py
```

## 常用功能说明

### 同济课表导入

在“日程与课表”中点击“统一身份认证登录”，完成微信扫码或短信加强认证，等待个人课表出现后回到控制台，点击“我已完成认证，导入课表”。系统只读取该临时浏览器会话中已经渲染出来的课表；认证结束或过期后，临时浏览器配置会被清理。导入失败不会覆盖上一次成功保存的课表。

### 日历订阅

提供通用 iCalendar（.ics）订阅。Apple 日历可直接打开；Google 日历需在电脑网页版通过“其他日历 → ＋ → 通过网址”添加 HTTPS 链接，再在安卓端使用同一账号查看。安卓其他日历需支持网址订阅；导入文件不会持续更新，订阅刷新频率由日历客户端决定。

登录线上站点后，在侧栏“管理”中打开“日历订阅”，即可生成、复制或撤销私有订阅地址。该地址等同于密码：持有它的人能看到这个账户导出的任务标题和日期，请不要分享到公开场合。

订阅内容包括未完成、未隐藏且带日期的平台事项，以及带日期的自定义待办、子任务和项目事项；成长行动的计划日期也会导出，不会因未加入待办而丢失；完成、暂放或删除项目后，其关联日程退出订阅。

### 平台连接与缓存

平台页面会说明各自的登录方式和缓存状态。断开连接只删除凭据并保留已有缓存；如需同时删除缓存和本地状态，请使用“清除平台数据”。缓存刷新遇到异常时，系统会尽量保留上一次成功结果，避免空数据覆盖原有信息。

### AI Agent 接入 (MCP & Skills)

在侧边栏【管理】中打开“Agent 接入”，可一键生成专属 Agent API Token。用户可下载零外部依赖的通用 MCP Server 脚本（`canvas_mcp.py`）与一键配置包，直接接入 Claude Desktop、Cursor、Cline 等工具；也可以下载 Agent Skill 包供终端 Agent（如 Claude Code、Antigravity）直接调用。Token 采用 SHA-256 哈希存储（不保存原始 Token），随时可以独立撤销与重新生成。

## 数据与账户安全

`data/` 保存运行时账户数据、密钥、平台配置和缓存，是项目最需要保护的目录：

- 不要将 `data/` 提交到 Git，也不要随意覆盖、删除或迁移其中的文件。
- 用户数据位于 `data/users/<用户名>/`，不同账户相互隔离。
- JSON 写入通过锁和原子替换完成；若发现数据损坏，系统会停止写入而非用空内容覆盖原数据。
- 删除账户需要输入当前密码与确认文字 `永久删除`。重新注册同名账号不会取回旧账号的数据或登录状态。

线上环境使用 HTTPS、安全 Session Cookie 和加密备份。更完整的备份、恢复与故障处理流程见 [备份与恢复文档](docs/backup-and-restore.md)。

## 开发与测试

完整工作流、场景选择、测试分层、失败证据和功能定位见 [开发、验收与发布](docs/development.md)。

```powershell
.\scripts\dev.ps1 -Preview -Scenario dense
.\scripts\test.ps1 -Suite quick
.\scripts\test.ps1 -Suite acceptance
```

独立预览默认访问 <http://127.0.0.1:5000/preview-login>；示例数据不会写入原有 `data/`。

运行完整测试：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

只运行某个测试文件：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_healthz.py -q
```

前端代码位于 `frontend/`。若要在 Open Design 中预览真实首页结构，可导出一份不访问真实账户的静态预览：

```powershell
.\.venv\Scripts\python.exe .\scripts\export_open_design_preview.py
```

随后将整个 `frontend/` 文件夹导入 Open Design，并打开 `open-design-preview/index.html`。请将最终视觉修改落实到 `frontend/templates/` 和 `frontend/assets/`，不要修改可再生的预览文件。详细约定见 [前端工作区说明](frontend/README.md)。

## 反馈与维护

问题反馈见 [GitHub Issues](https://github.com/zboheng53-jpg/canvas-dashboard/issues)，请提供操作步骤、平台和时间；不要上传密码、订阅链接、Token 或未脱敏的个人数据。忘记站点密码时联系维护者获取一次性重置凭据。项目与任务删除后没有回收站。

[更新记录](CHANGELOG.md) · [开放容量与维护说明](docs/small-group-launch.md)。当前部署为单 Web 进程；JSON 锁是进程内的，不能直接启动多个写进程扩容。

## 项目文档

| 想了解什么 | 文档 |
| --- | --- |
| 组件、数据流和刷新机制 | [架构说明](docs/architecture.md) |
| 线上部署、回滚、日志与健康检查 | [生产运维](docs/operations.md) |
| 加密备份、恢复演练与 JSON 损坏处理 | [备份与恢复](docs/backup-and-restore.md) |
| 智慧树与同济浏览器登录窗口 | [登录隧道运维说明](deploy/zhihuishu-login-tunnel.md) |
| 界面风格、Figma token 与组件约束 | [UI 设计规范](design.md) |
| 文档的当前版本与历史记录 | [文档索引](docs/README.md) |
| 代码修改约定 | [AGENTS.md](AGENTS.md) |

## 部署

生产部署请使用已验证的脚本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\.agents\skills\deploy-canvas-dashboard\scripts\deploy.ps1
```

该流程会执行测试与编译检查、加密备份和隔离恢复演练，然后以原子方式切换版本；失败时自动回滚。部署前请先阅读 [生产运维文档](docs/operations.md)，并确认没有把本地 `data/` 当作可随意覆盖的项目文件。
