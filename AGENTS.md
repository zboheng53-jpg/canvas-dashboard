# Canvas Dashboard Agent Guide

Flask webapp for aggregating unfinished assignments and exams from Canvas, 好课, 智学盟, 智慧树, and custom todos.

`AGENTS.md` is the canonical project rule file. `CLAUDE.md` must point to the same content; prefer a symbolic link, and use a hard link on Windows when symbolic-link privilege is unavailable.

## 核心交互规则

1. **新建分支与意图说明**：每次面对一个新问题时，先新建一个 Git 分支，**用中文写清楚本次修改的意图**。
2. **本地效果验收**：在本地开发环境（http://127.0.0.1:5000/）完成修改与测试后，请用户进行效果验收。
3. **合并、推送与部署**：验收完成后，将分支修改合并到 `main` 分支，确认 `git push origin main` 成功后，再部署到服务器上。

## 开发原则与数据安全

- **小步修改**：根据需求做最小化精准修改，避免重构无关代码或无意义的大面积格式化。
- **数据保护**：`data/` 目录、平台凭据、缓存及生产配置属于敏感数据，未经明确授权不得随意覆盖、删除或迁移。
- **实事求是**：明确汇报命令与测试结果，若命令无法执行须说明具体原因。
- **核心语言**：Python 后端为主，前端为 Vanilla JS + Fetch API，保持代码直接简洁。

## 项目结构

```text
canvas-dashboard/
├── app.py                         # Flask 主路由与 API 接口
├── auth.py                        # 站点多用户系统、密码哈希与旧数据迁移
├── user_paths.py                  # 用户独立数据路径管理 (data/users/<username>/)
├── storage.py                     # 并发安全 JSON 读写与原子替换
├── tongji_timetable.py             # 一网通办课表 CDP 抓取与解析
├── schedule_store.py               # 课程与日程项存储
├── project_store.py                # 长期项目存储
├── canvas_auth.py                 # Canvas iCal 订阅抓取与解析
├── haoke_client.py                # 好课 API 客户端与缓存管理
├── zhixuemeng_client.py           # 智学盟客户端 (Token/课程/作业)
├── zhihuishu_store.py             # 智慧树缓存、状态与配置
├── zhihuishu_worker.py            # 智慧树后台多进程刷新 Worker
├── zhihuishu_browser.py           # 智慧树 Playwright 浏览器自动化
├── zhihuishu_login_sessions.py    # 智慧树短时 noVNC 登录窗口
├── templates/                     # 前端页面 (index.html 主控制台, auth_*, login_*)
├── static/                        # 静态样式 (style.css, dashboard-shell.css)
├── tests/                         # Pytest 单元测试与 Playwright 回归测试
├── deploy/                        # Nginx 与 systemd 部署参考配置
├── data/                          # 本地运行时数据 (不可随意篡改)
├── AGENTS.md                      # 规范指引 (本文件)
└── CLAUDE.md                      # 与 AGENTS.md 内容一致
```

## 常用命令

- **本地运行**：
  ```powershell
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
  .\local-preview.bat
  # 或在需要前台诊断时使用：
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1
  ```
- **自动化测试**：
  ```powershell
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
  # 单独运行特定测试：
  .\.venv\Scripts\python.exe -m pytest tests\test_p0_safety.py -q
  ```
- **生产部署**：
  ```powershell
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\.agents\skills\deploy-canvas-dashboard\scripts\deploy.ps1
  ```

## 架构与平台核心机制

- **存储与并发 (`storage.py`)**：
  - JSON 读写使用绝对路径加锁，写操作采用临时文件 + 原子替换 (`atomic replace`)。
  - 数据文件损坏时 `fail-closed`（备份 `.corrupt` 并抛出 `JsonFileCorruptionError`），切勿直接用空值覆盖。
  - 同一账户的自定义 Todo 更新必须通过 `locked_json_update()`。
- **用户隔离与路由**：
  - 所有 API 均需要站点 Session（除 `/healthz`、`/login`、`/register`、`/api/auth/*` 及 `/calendar/<token>.ics` 外）。
  - 用户独立数据存放于 `data/users/<username>/`，全局配置包含 `users.json`, `.flask_secret_key`, `.encryption_key` 等。
- **第三方平台特点**：
  - **Canvas**：解析 iCal feed，缓存于 `canvas_cache.json`。
  - **好课**：凭据加密存储，`/api/haoke/todos` 缓存优先，后台守护进程异步刷新。
  - **智学盟**：使用 `X-Access-Token`，支持课程与作业列表抓取。
  - **智慧树**：路由只读缓存/状态；后台通过 `zhihuishu_worker.py --all-users` 定时拉取；独立 Chromium profile 运行；支持 noVNC 远程登录窗口。
