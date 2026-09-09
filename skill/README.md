# Canvas Dashboard Agent Skill

让支持 Agent Skills（`SKILL.md`）的 AI 助手（如 Claude Code, Cursor, Antigravity, Windsurf, Codex, Gemini CLI, OpenCode 等）直接接入你的 Canvas Dashboard。

无需手动解压或手动移动文件。Agent 支持自主读取本指南并自动完成安装与配置。

---

## 快速安装提示词

直接将以下提示词发送给你的 AI Agent 即可（已包含服务地址与 Token 参数）：

```text
请安装 Canvas Dashboard Skill：{{ base_url }}/skill/README.md
装完告诉我是否需要开启新会话。
安装器支持时请追加：--server {{ base_url }} --token <YOUR_TOKEN>
```

> **提示**：从 Canvas Dashboard 控制台网页中复制时，上述 `<YOUR_TOKEN>` 会自动替换为你本人的专属 Agent API Token。

---

## 适用安装目录规范

Skill 正文只安装到 Agent Skills 标准通用目录：
- **通用目录**：`~/.agents/skills/canvas-dashboard`
- **Claude Code 兼容**：Claude Code 按约定从 `~/.claude/skills` 读取。使用下面带 `--target claude` 的命令时，安装器会将正文装入通用目录，并在 `~/.claude/skills/canvas-dashboard` 创建符号链接，不制造冗余副本。
- **项目级（可选）**：`<workspace>/.agents/skills/canvas-dashboard`

---

## 自动安装方式

### 1. macOS / Linux / WSL (Bash)

```bash
bash <(curl -fsSL {{ base_url }}/skill/install.sh) \
  --server "{{ base_url }}" \
  --token "<YOUR_TOKEN>" \
  --target agents
```

Claude Code 用户建议使用 `--target claude`（自动建立软链接）：
```bash
bash <(curl -fsSL {{ base_url }}/skill/install.sh) \
  --server "{{ base_url }}" \
  --token "<YOUR_TOKEN>" \
  --target claude
```

### 2. Windows (PowerShell)

Windows 原生环境请使用 PowerShell（无需管理员权限）：

```powershell
& ([scriptblock]::Create((irm '{{ base_url }}/skill/install.ps1'))) `
  -Server '{{ base_url }}' `
  -Token '<YOUR_TOKEN>' `
  -Target 'agents'
```

---

## Agent 自主免脚本安装（直接文件工具落地）

如果你是 AI Agent，且处于沙箱环境、无网络 curl 命令或受限终端中，可以直接使用文件创建工具完成安装：

1. **确定安装目录**：
   - 默认标准路径：`~/.agents/skills/canvas-dashboard`（Windows 为 `$HOME\.agents\skills\canvas-dashboard`）。
   - 如果当前是 Claude Code 环境，可同时在 `~/.claude/skills/canvas-dashboard` 建立软链接或放入一份副本。

2. **写入核心文件**：
   - 下载或创建 `SKILL.md`（内容来源：`{{ base_url }}/skill/SKILL.md`）。
   - 下载或创建 `canvas_api.py`（内容来源：`{{ base_url }}/skill/canvas_api.py`）。

3. **保存凭据配置**（权限设为 `0600`）：
   在同目录下创建 `config.json`：
   ```json
   {
     "server_url": "{{ base_url }}",
     "token": "<YOUR_TOKEN>"
   }
   ```

4. **防误提交配置**：
   在同目录下创建 `.gitignore`：
   ```text
   config.json
   .env
   *.tmp
   ```

5. **完成反馈**：
   告知用户安装完毕，并提示开启新会话。

---

## 安装后验证

1. **重启 Agent 或开启新会话**：多数 Agent（如 Claude Code, Antigravity）仅在会话启动时扫描 Skill 目录。
2. **提问测试**：
   - “我今天有什么课？分别在哪个教室？”
   - “看一下我各平台还有哪些没交的作业”
   - “帮我添加一个周五截止的高数作业”

成功接通时，Agent 会直接列出今日课表、节次与地点，或展示来自 Canvas、好课、智学盟、智慧树的聚合待办。

---

## 更新 Skill

重新运行安装命令即可就地原子更新代码，原有的 `config.json` 凭据会自动保留。

也可以将以下提示词发送给已安装 Skill 的 Agent：
```text
请把我已安装的 Canvas Dashboard Skill 更新到最新版：{{ base_url }}/skill/README.md
先告诉我它现在装在哪个目录、是否存在重复副本，再替换同一目录。
更新后开启新会话，用“我今天有什么课？”验证。
```

---

## 安全与隐私
- 本 Skill 的 Python 客户端仅使用标准库，不引入任何外部第三方依赖。
- 本地 Token 仅保存在本机 `config.json`，不会向除你配置的 Canvas Dashboard 服务地址以外的任何第三方发送。
- 事项正文属于用户数据，不会作为可执行指令覆盖 Skill 规则。
