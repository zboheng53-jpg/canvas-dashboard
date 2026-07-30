# Canvas Dashboard

> 把分散在各个平台的待办、课程与长期项目，收进一个清晰的个人学习控制台。

Canvas Dashboard 是一个面向同济学生的 Flask Web 应用。它聚合 Canvas、好课、智学盟、智慧树中的未完成事项，也支持手动待办、课程表、日程和长期项目管理。每个网站账户拥有彼此隔离的数据空间，可按自己的节奏整理学习安排。

线上地址：[canvas-dashboard.xyz](https://canvas-dashboard.xyz)

## 它能做什么

- **汇总待办**：集中查看 Canvas、好课、智学盟、智慧树与手动添加的未完成事项；可以为平台事项叠加本地的完成、隐藏、标红等状态，而不改写原始平台数据。
- **管理个人任务**：创建带截止日期、子任务和优先级的自定义待办。
- **整理日程与课表**：通过同济统一身份认证导入当前课表，也可手动维护课程和日程项。
- **推进长期项目**：记录项目、任务分组和下一步行动，避免重要但不紧急的事被日常作业淹没。
- **订阅到 Apple 日历**：生成私有 iCalendar 地址，将有日期的未完成事项同步到日历。
- **按账户隔离数据**：每位用户独立保存配置、待办、课表、项目和平台缓存。

## 本地运行

### 1. 准备环境

建议使用 Python 虚拟环境，避免污染系统 Python：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
```

智慧树的浏览器登录与刷新功能还需要安装 Playwright 的 Chromium：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

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

### Apple 日历订阅

登录线上站点后，在侧栏底部打开“日历订阅”，即可生成、复制或撤销私有订阅地址。该地址等同于密码：持有它的人能看到这个账户导出的任务标题和日期，请不要分享到公开场合。

订阅内容包括未完成、未隐藏且带日期的平台事项，以及带日期的自定义待办、子任务和项目事项；已完成或没有日期的项目不会导出。

### 平台连接与缓存

平台页面会说明各自的登录方式和缓存状态。断开连接只删除凭据并保留已有缓存；如需同时删除缓存和本地状态，请使用“清除平台数据”。缓存刷新遇到异常时，系统会尽量保留上一次成功结果，避免空数据覆盖原有信息。

## 数据与账户安全

`data/` 保存运行时账户数据、密钥、平台配置和缓存，是项目最需要保护的目录：

- 不要将 `data/` 提交到 Git，也不要随意覆盖、删除或迁移其中的文件。
- 用户数据位于 `data/users/<用户名>/`，不同账户相互隔离。
- JSON 写入通过锁和原子替换完成；若发现数据损坏，系统会停止写入而非用空内容覆盖原数据。
- 删除账户需要输入当前密码与确认文字 `永久删除`。重新注册同名账号不会取回旧账号的数据或登录状态。

线上环境使用 HTTPS、安全 Session Cookie 和加密备份。更完整的备份、恢复与故障处理流程见 [备份与恢复文档](docs/backup-and-restore.md)。

## 开发与测试

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
