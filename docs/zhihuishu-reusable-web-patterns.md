# 智慧树式网页接入复用手册

本文沉淀 2026-07-02 智慧树接入中可复用的模式。目标不是只记录智慧树，而是让后续接入类似平台时，可以直接复用同一套网页结构、登录结构、后台刷新结构和验证方法。

适用场景：

- 平台没有稳定公开 API，需要浏览器登录态和动态页面。
- 登录依赖滑块、扫码、短信、人机验证，不能完全自动化。
- 作业入口藏在登录后的课程页里，需要先人工定位，再固化成 worker 抓取流程。
- 多个普通用户都要登录自己的第三方账号，不能接触服务器权限、SSH、裸 VNC 端口或共享浏览器桌面。

不适用场景：

- 平台有稳定 token/API，直接用 `requests` 就能拉取数据。
- 所有数据都是公开页面，无需用户级登录态。
- 第三方平台只允许单一管理员账号，并且数据不需要按站内账号隔离。

## 第一性原理

一个需要登录的动态网页，本质上有三件东西：

1. 登录态：cookie、localStorage、浏览器 profile、设备指纹等状态。
2. 页面入口：用户登录后从哪里进入课程、作业、考试列表。
3. 数据边界：哪些数据属于哪个站内用户，哪些缓存已经过期，哪些抓取失败只是暂时失败。

因此架构分成四层：

- Flask 请求层只读状态和缓存，不在请求里启动浏览器。
- Worker 层持有浏览器 profile，定时保活和抓取，写入小 JSON 缓存。
- 登录会话层给普通用户一个短期、隔离、可取消的远程浏览器窗口。
- Browser adapter 层把“人类找到的入口和动作”翻译成可重复执行的 Playwright 流程。

这四层的职责不能混在一起。混在一起会导致请求超时、多人 profile 串号、用户接触服务器权限、缓存状态无法解释。

## 当前智慧树实现映射

| 职责 | 智慧树实现 | 可复用到新平台时的命名 |
|---|---|---|
| per-user 状态/缓存/state | `zhihuishu_store.py` | `<platform>_store.py` |
| 后台刷新 worker | `zhihuishu_worker.py` | `<platform>_worker.py` |
| Playwright 页面操作 | `zhihuishu_browser.py` | `<platform>_browser.py` |
| 短期登录窗口 | `zhihuishu_login_sessions.py` | `<platform>_login_sessions.py` |
| 用户登录页 | `templates/login_zhihuishu.html` | `templates/login_<platform>.html` |
| noVNC 浏览器镜像 | `deploy/zhihuishu-login-browser.Dockerfile` | `deploy/<platform>-login-browser.Dockerfile` |
| noVNC 反代鉴权 | `deploy/canvas-dashboard.nginx` 的 `/zhs-vnc/<port>/<token>/...` | `/<platform>-vnc/<port>/<token>/...` |
| systemd worker | `deploy/zhihuishu-worker.service` | `deploy/<platform>-worker.service` |
| API 契约测试 | `tests/test_zhihuishu_api.py` | `tests/test_<platform>_api.py` |

每个站内账号的数据必须落在：

```text
data/users/<username>/
```

智慧树使用：

```text
zhihuishu_status.json
zhihuishu_cache.json
zhihuishu_state.json
zhihuishu_login_session.json
zhihuishu_chromium_profile/
```

新平台照这个结构替换平台前缀即可。

## 后台长连接刷新模式

前端看板不能等浏览器现场启动。正确模式是：

1. Worker 按站内账号遍历用户。
2. 对每个用户打开该用户独立 Chromium profile。
3. 先 `check_session(username)`，判断登录态是否仍有效。
4. 登录有效时 `keepalive(username)`，更新 `last_keepalive_at`。
5. 到抓取间隔或用户刚完成登录时，执行 `fetch_assignments(username)`。
6. 抓取成功后写 `cache` 和 `status`。
7. Flask 的 `/api/<platform>/todos` 只读 `cache/status/state` 并返回给前端。

智慧树当前间隔：

```python
KEEPALIVE_INTERVAL_SECONDS = 15 * 60
FETCH_INTERVAL_SECONDS = 45 * 60
MAX_FAILURE_DELAY_SECONDS = 60 * 60
```

可复用 API 返回形状：

```json
{
  "ok": true,
  "need_setup": false,
  "data": [],
  "hidden": [],
  "highlighted": [],
  "deleted": [],
  "stale": false,
  "fetched_at": 1782976751.8658469,
  "status": {
    "session": "active",
    "worker": "running",
    "last_keepalive_at": 1782976751.8658469,
    "last_fetch_at": 1782976751.8658469,
    "last_success_at": 1782976751.8658469,
    "last_error": ""
  }
}
```

空 `data: []` 不等于失败。只要 `session: active`、`stale: false`、`last_error: ""`，它表示当前没有未完成作业。

## 滑块验证登录模式

滑块登录不能交给后台自动硬闯。正确流程是让用户在隔离浏览器里自己完成验证，然后保存 profile 给 worker 复用。

智慧树用户流程：

1. 用户先登录 Canvas Dashboard 的站内账号。
2. 打开 `/login/zhihuishu`。
3. 点击“打开智慧树登录窗口”。
4. Flask 创建短期 token、分配本地端口、启动 Docker/noVNC 浏览器容器。
5. nginx 只允许通过 `/zhs-vnc/<port>/<token>/...` 访问该 noVNC。
6. nginx 每次访问前用 `auth_request` 调 Flask 的 `/api/zhihuishu/login-session-auth`。
7. 用户在 noVNC 窗口内完成智慧树滑块、扫码或密码登录。
8. 用户回到 `/login/zhihuishu` 点击“我已完成登录”。
9. Flask 停掉容器，并强制跑一次 worker refresh。
10. 看板读取新 cache。

关键安全约束：

- noVNC 容器端口只绑定 `127.0.0.1:<port>`。
- 公网只能走 nginx token-gated 路径。
- token 有 TTL，智慧树当前是 10 分钟。
- 普通用户不能看到 SSH、服务器桌面、裸 `6080`、Docker 命令或服务器密码。
- 每个用户只能有一个活跃登录会话；新会话会停止旧容器。
- 容器只挂载该用户自己的 `zhihuishu_chromium_profile/` 到 `/profile`。

复制到新平台时，先保留这套 API：

```text
GET    /api/<platform>/config
GET    /api/<platform>/todos
GET    /api/<platform>/state
POST   /api/<platform>/state
POST   /api/<platform>/login-required
POST   /api/<platform>/login-session
DELETE /api/<platform>/login-session
GET    /<platform>/session/<token>/
GET    /api/<platform>/login-session-auth
POST   /api/<platform>/login-session/<token>/complete
DELETE /api/<platform>/login-session/<token>
```

前端也保持同一结构：

- 状态表：登录状态、worker、上次保活、上次抓取、上次成功、错误。
- 主按钮：打开登录窗口。
- 次按钮：我已完成登录。
- 取消按钮：取消当前登录会话。
- 所有错误显示在同一个 message 区域。

## 本地登录探路到自动抓取

这部分是智慧树接入中最值得复用的流程。

第一步：不要先写爬虫。先让用户在真实浏览器里登录并找到作业页。记录三类事实：

- 从首页到课程页的入口选择器或链接模式。
- 从课程页到作业/考试页的 URL 变化。
- 页面实际请求的接口 URL 和返回字段。

智慧树中已验证的事实：

```text
课程入口 host:
ai-smart-course-student-pro.zhihuishu.com

课程链接形态:
/singleCourse/knowledgeStudy/<course_id>/<class_id>

作业页链接形态:
/singleCourse/taskAndExam/<course_id>/<class_id>

未完成作业接口片段:
kg-run-student.zhihuishu.com/student/gateway/t/task/taskList
```

第二步：把用户找到的入口固化成纯函数。智慧树是：

```python
smart_course_task_url(href)
```

它把：

```text
/singleCourse/knowledgeStudy/<course_id>/<class_id>
```

改写成：

```text
/singleCourse/taskAndExam/<course_id>/<class_id>
```

这种 URL 改写要写单元测试，避免平台页面文案变化时全部依赖点击文字。

第三步：把 UI 操作降级成多重兜底：

1. 优先找直接包含目标 URL 的 `a[href*="..."]`。
2. 找不到时点击页面上的“任务/作业/考试”文本或关键词组合。
3. 再不行时用已知 URL 规则直接 `page.goto(...)`。
4. 到达目标页后监听真正的数据接口 response。
5. 接口拿不到时才退回 DOM 文本提取。

第四步：统一 item shape。智慧树 item 形状：

```json
{
  "id": "zhs_123",
  "title": "第六章作业",
  "course": "课程名",
  "due_str": "2026-07-03 23:59",
  "due_ts": "2026-07-03T23:59:00",
  "type": "作业",
  "url": "https://..."
}
```

新平台也应转换成同一字段，前端 unified list 才能保持统一。

## 复现清单

接入新平台时，按这个顺序做：

1. Store 层
   - 新建 `<platform>_store.py`。
   - 提供 `load_status/save_status/load_cache/save_cache/load_state/update_state`。
   - 所有文件写入 `data/users/<username>/`。

2. Worker 层
   - 新建 `<platform>_worker.py`。
   - Flask 请求路径里不能启动浏览器。
   - 实现 `--username`、`--all-users`、`--once`、`--dry-run`。
   - systemd 用独立 service 管理。

3. Browser adapter 层
   - 新建 `<platform>_browser.py`。
   - 只暴露 `check_session`、`keepalive`、`fetch_assignments`。
   - 所有页面结构猜测都写成可测试的小函数。

4. 登录会话层
   - 新建 `<platform>_login_sessions.py`。
   - token、端口、TTL、Docker command、stop/cleanup 都在这里。
   - 容器 profile 只挂载当前用户目录。

5. Flask API
   - 添加 `/api/<platform>/config`、`/todos`、`/state`、`/login-session` 系列路由。
   - `/complete` 里必须先停登录容器，再强制跑一次 worker refresh。
   - `/todos` 里要区分 `need_setup`、`stale`、空数据成功。

6. 前端
   - 添加平台卡片。
   - 添加 `login_<platform>.html`。
   - unified item 使用统一字段。
   - state 操作沿用 hide/highlight/delete。

7. 部署
   - Dockerfile 构建登录浏览器镜像。
   - nginx 加 token-gated VNC 反代。
   - systemd 加 worker service。
   - 文档写明验证命令和常见错误。

8. 测试
   - Store 测缓存过期和 state。
   - API 测登录态、login session、VNC auth、complete 后刷新 cache。
   - Browser 纯函数测 URL 改写、item normalization、入口候选提取。
   - Worker 测 fetch 间隔、强制 fetch、登录失效状态。

## 验证命令模板

本地单元测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_<platform>_api.py tests/test_<platform>_worker.py tests/test_<platform>_store.py tests/test_<platform>_browser.py -q
```

Python 编译检查：

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py <platform>_store.py <platform>_worker.py <platform>_browser.py <platform>_login_sessions.py
```

服务器服务状态：

```bash
systemctl is-active canvas-dashboard <platform>-worker.service nginx
journalctl -u <platform>-worker.service -n 100 --no-pager
```

服务器手动检查登录态：

```bash
cd /home/ubuntu/canvas-dashboard
env <PLATFORM>_CHROMIUM_EXECUTABLE=/usr/bin/google-chrome-stable .venv/bin/python <platform>_browser.py check --username <site_username>
```

服务器手动抓取：

```bash
cd /home/ubuntu/canvas-dashboard
env <PLATFORM>_CHROMIUM_EXECUTABLE=/usr/bin/google-chrome-stable .venv/bin/python <platform>_browser.py fetch --username <site_username>
```

强制 worker 跑一次并写 cache：

```bash
cd /home/ubuntu/canvas-dashboard
.venv/bin/python <platform>_worker.py --username <site_username> --once
```

检查 cache 是否新鲜：

```bash
cd /home/ubuntu/canvas-dashboard
.venv/bin/python -c 'import json, <platform>_store as s; print(json.dumps(s.load_cache("<site_username>"), ensure_ascii=False))'
```

## 常见失败解释

`Docker 运行时没有准备好`

含义：运行 Flask 的用户找不到 `docker` 命令，或者 Docker Desktop / Docker daemon 没启动。先解决运行时，不要改爬虫逻辑。

`502 Bad Gateway nginx`

含义：nginx 反代到了一个还没准备好的 noVNC 端口，或容器没启动成功。检查 Docker 容器、端口绑定、nginx `auth_request` 和 Flask 服务。

VNC 能打开但登录后看板仍显示缓存过期

含义：登录完成路由没有强制刷新 cache，或者用户点完登录后没有调用 complete。`/complete` 必须跑一次 `run_scheduled_cycle(..., force_fetch=True)`。

`session: active` 且 `data: []`

含义：登录成功，抓取成功，但当前没有未完成作业。不要把空列表当成失败。

Chrome profile lock

含义：同一个 profile 被另一个 Chrome 或 Docker 容器占用。必须保证同一用户同一时间只运行一个登录容器或 worker context，并清理已确认过期的 `SingletonLock`。

## 不要做的事

- 不要把服务器裸 `6080` 端口暴露给普通用户。
- 不要让普通用户 SSH 到服务器。
- 不要多个用户共享一个 Chromium profile。
- 不要在 Flask `/api/<platform>/todos` 里启动 Playwright。
- 不要因为一个用户登录失效而删除旧 cache。
- 不要把“没有未完成作业”显示成“抓取失败”。
- 不要只靠页面文字定位；能用 URL 和接口 response 就优先用 URL 和接口 response。

## 统一网页结构约定

新增平台时保持这些用户可见结构一致：

- 看板卡片：平台名、连接状态、点击进入 `/login/<platform>`。
- 登录页：状态表 + 打开登录窗口 + 完成登录 + 取消当前登录会话。
- 待办列表：来源 badge、标题、课程、截止时间、隐藏、标红、删除。
- 状态语义：`not_logged_in`、`need_relogin`、`active`。
- 缓存语义：`stale: true` 表示缓存过期；`data: []` 本身不表示失败。

这样后续平台虽然内部抓取方式不同，外部网页结构和用户理解成本仍然一致。
