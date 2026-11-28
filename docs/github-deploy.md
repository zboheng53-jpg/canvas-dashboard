# GitHub Actions 生产部署

合并到 `main` 后由 GitHub Actions 自动部署到生产服务器 `124.222.188.101`。协作者只需要仓库 Write 权限，不需要服务器账号、SSH 私钥或 sudo。

部署沿用现有的 release 机制：固定提交打包、上传、在服务器上原子切换 `current`、健康检查、失败自动回滚。workflow 不在服务器上执行 `git pull`，也不直接拼接 `systemctl restart` 命令。

## 组成

| 文件 | 作用 |
| --- | --- |
| `.github/workflows/deploy.yml` | PR 和 `main` 推送跑完整测试；`main` 上测试通过后进入 `production` 环境部署 |
| `.github/workflows/rollback.yml` | 手动回滚到 `.previous-release` 或指定 release |
| `.github/workflows/verify.yml` | 手动干净环境诊断，不参与部署 |
| `.github/CODEOWNERS` | `deploy/`、`.github/`、`.agents/` 和运维文档必须由仓库所有者 review |
| `deploy/github-deploy/canvas-deploy` | 服务器上 root 所有的部署入口，只接受校验过的 release 包 |
| `deploy/github-deploy/setup-deploy-user.sh` | 一次性创建受限 `deploy` 用户、sudoers 和 wrapper |

## 一次性准备

### 1. 生成部署密钥（维护者工作站）

```powershell
Set-Location -LiteralPath 'C:\DesktopFiles\canvas-dashboard'
ssh-keygen -t ed25519 -C 'github-actions-deploy' -f "$HOME\.ssh\canvas-deploy"
```

在两次口令提示时按 Enter，供 Actions 无交互登录。私钥 `canvas-deploy` 写入 GitHub environment secret，公钥 `canvas-deploy.pub` 交给下一步。

### 2. 服务器创建受限用户（root，只做一次）

把 `deploy/github-deploy/` 目录和公钥复制到服务器，然后：

```bash
sudo bash setup-deploy-user.sh /path/to/canvas-deploy.pub
```

脚本会：

- 创建 `deploy` 用户（锁定密码、仅公钥登录），家目录下只有 `incoming/`；
- 安装 root 所有的 `/usr/local/sbin/canvas-deploy`；
- 写入 `/etc/sudoers.d/canvas-deploy`，只允许 `deploy` 以 root 运行这一个命令；
- 确认 `/home/ubuntu/canvas-dashboard/incoming` 存在。

验证：

```bash
ssh -i ~/.ssh/canvas-deploy -o StrictHostKeyChecking=yes -o UserKnownHostsFile=deploy/known_hosts \
  deploy@124.222.188.101 'sudo -n /usr/local/sbin/canvas-deploy status'
```

该命令只读：打印 `current`、`.previous-release`、各 unit 状态和本地健康检查。

### 3. GitHub 仓库设置

1. **Settings → Environments → New environment** `production`
   - **Deployment branches and tags** 选 **Selected branches and tags**，添加类型为 **Branch**、名称为 `main` 的规则。
   - **Required reviewers** 留空，让合并后的测试通过即可部署。
2. **Environment secret** `DEPLOY_SSH_KEY`：粘贴 `canvas-deploy` 私钥全文。
3. **Repository variable** `DEPLOY_HOST`：`124.222.188.101`。
4. **Settings → Branches → main 保护规则**：
   - Require a pull request before merging
   - Require approvals ≥ 1
   - Require review from Code Owners
   - Block force pushes
   - Restrict deletions
   - 首个部署 PR 的 `Full regression` 有运行记录后，将该检查设为必过。
5. **Settings → Collaborators**：队友给 Write；不要给 Admin 或 Maintain。
6. 可选：建 Organization 并把仓库转过去，用 Team 统一授权；转移后 environment、secret、变量和协作者需要重建。

### 4. 网络

GitHub Actions 的 runner 需要能连服务器的 22 端口。如果服务器防火墙或云安全组只放行了你的 IP，需要放行 GitHub 的出口地址（<https://api.github.com/meta> 的 `actions` 段），或改用 self-hosted runner。也检查 `sshd_config` 没有 `AllowUsers ubuntu` 之类的限制把 `deploy` 排除在外。

## 日常流程

1. 队友从 `main` 开分支，提 PR；`Full regression` 自动运行。
2. 至少一次批准后合并。触及 `deploy/`、`.github/` 等路径时，需要由所有者批准。初次引入 `CODEOWNERS` 的 PR 仍由 `main` 当时已有的规则控制。
3. `main` 上的同一次运行先跑完整测试，通过后部署该提交。开始部署时工作流会核对 `main` 最新提交，避免重跑旧工作流覆盖生产版本。
4. PR 的合并记录显示合并者，Actions 的 `Deploy` job 显示运行日志和最终 release 状态。

## 回滚

- **一键回滚到上一个 release**：Actions → *Roll back production* → Run workflow（留空）。
- **回滚到指定 release**：填 `release-YYYYMMDDTHHMMSSZ-xxxxxxxxxxxx` 或 `/home/ubuntu/canvas-dashboard/releases/...`。
- 命令行等价物：

```bash
ssh -i ~/.ssh/canvas-deploy deploy@124.222.188.101 \
  'sudo -n /usr/local/sbin/canvas-deploy rollback'
```

回滚是 release 目录切换，不是 `git revert`。回滚后 `main` 仍指向新代码；修复应走新的 PR。

## 备份策略

- 自动部署在激活前调用 `deploy/run-backup.sh`，在服务器上创建加密快照（停服、备份、恢复服务）。
- **不再**每次部署下载备份并做隔离恢复演练。离机副本和演练仍由维护者在工作站定期执行：

```powershell
.\scripts\pull-production-backup.ps1 -CreateBackup -RecoveryDrill
```

这是有意的取舍：把备份私钥放进 GitHub 的风险高于把演练改为定期执行。需要每次部署都演练时，再单独讨论密钥托管方式。

## 安全模型

- **能部署 = 能以 root 安装代码。** `deploy` 私钥能触发的 wrapper 最终会执行合并后的 `install-release.sh`，和现有手动部署的权限相同。真正的边界是“谁能合 PR”，所以 main 保护、CODEOWNERS 和批准数比密钥本身更重要。
- 私钥只存在于 `production` 环境的 secret 中；`Deployment branches` 限制为 `main`，其他分支的 workflow 拿不到它。
- 公开仓库的 Actions 日志对所有人可见：不要打印密钥、`.env`、备份内容或用户数据。
- 泄露处理：删除服务器 `authorized_keys` 中对应行（或重跑 setup 脚本换钥），再在 GitHub 更新 secret；两步都做完才恢复部署能力。
- 不要给协作者服务器账号、`ubuntu`/`root` 密码、sudo 或私钥。

## 故障处理

- **SSH 超时/断线**：激活只尝试一次。先跑 `canvas-deploy status`，看 `current`、`.previous-release` 和健康检查，再决定是否重新触发；不要盲目重跑。
- **安装器失败**：它已经自动切回上一个 release；修复后重新合并。
- **测试失败**：部署不会发生，生产不变。
- **完全手动兜底**：本地 `deploy.ps1` 仍是完整路径（含离机备份与恢复演练），需要 `ubuntu` 账号。它和 Actions 共用同一套 release 机制，不会互相冲突。
