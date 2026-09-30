# Canvas Dashboard Agent Guide

Flask webapp for aggregating unfinished assignments and exams from Canvas, 好课, 智学盟, 智慧树, 课堂派, 同济OJ, and custom todos.

`AGENTS.md` is the canonical project rule file. `CLAUDE.md` must point to the same content; prefer a symbolic link, and use a hard link on Windows when symbolic-link privilege is unavailable.

## 开发流程与验收

日常命令、测试映射与多 AI 协作见 `docs/development.md`；生产操作见 `docs/operations.md`。

1. **范围与复现**：先查工作区和相关入口，保留已有修改；使用 `codex/` 功能分支。简单任务用会话明确结果，不强制计划文件或多代理评审。并行写入使用独立 worktree；同一工作区同一时间只有一个写入者，不替其他任务切分支、stash、清理或全量暂存。
2. **迭代验证**：优先复现用例、指定文件或 `scripts/test.ps1 -ChangedOnly`；已提交的分支改动用 `-BaseRef origin/main`。快速选择不等于完整依赖分析，按实际影响补充检查。默认 4 worker；复用共享测试夹具和统一日期。
3. **一次充分验证**：交付前验证最终版本。前端用 UI 或明确覆盖的浏览器文件；账户/存储/跨模块用 acceptance；依赖、共享测试基础设施及发布用全量。它们是替代选择，不是逐层必跑。完整检查通过后，不因“提交前、验收前、发布前”这些阶段名称重复运行相同检查。
4. **验收与授权**：UI/交互先实际核验隔离预览并提供操作步骤；纯后端、规范、测试及工具改动用自动化与差异验收。除用户要求逐步验收或存在未解决的产品分歧，不以等待用户点击作为默认关卡。延续已有交付授权；仅任务包含合并/推送/部署时执行，不把局部修改扩展成生产发布。
5. **发布与交付**：同批交付只由一个交付者汇总、验证和发布。发布要求干净 main 等于实时远端 main；部署入口自动复用同提交、同环境的有效完整测试证据，无有效证据则全量一次。保留备份/恢复演练、固定提交打包、原子切换、健康检查和失败回滚。修改或合并改变结果则复验。交付说明实际结果、证据和限制，行为变化同步负责该约定的文档。

测试证据保存在忽略的 `test-results/`；浏览器只在失败时保存截图与 DOM。测试收集、截图、哈希和日志存在不等于正确性。正常工作不重复环境诊断；异常时用 `scripts/check_test_env.py`。产物轮转统一使用 `scripts/clean_test_artifacts.py`，保护最新、失败保留配额及无法判断的记录。日常不要求 PR、第二人审批或远端 CI 通过；可手动运行 CI 检查干净环境。禁止把任意 JSON 当作可信发布证明。

## 开发原则与数据安全

- **小步修改**：根据需求做最小化精准修改，避免重构无关代码或无意义的大面积格式化。
- **环境隔离**：`CANVAS_DASHBOARD_DATA_DIR` 必须在导入应用前设置；默认仍为项目 `data/`。测试与验收预览使用临时目录，不复制真实数据或凭据。真实平台登录/同步另行在对应环境验证。
- **数据保护**：`data/` 目录、平台凭据、缓存及生产配置属于敏感数据，未经明确授权不得随意覆盖、删除或迁移。
- **实事求是**：明确汇报命令与测试结果，若命令无法执行须说明具体原因。
- **核心语言**：Python 后端为主，前端为 Vanilla JS + Fetch API，保持代码直接简洁。

## 按需阅读

- 改动具体模块前，阅读 `docs/module-contracts.md` 对应段落；存储/隔离、统一事项状态、平台只读边界等业务约束继续有效。
- 文件定位、测试命令与开发环境：`docs/development.md`。不要每次任务通读全部架构、历史计划、运维手册或技能。
- 只有生产操作才读取 `docs/operations.md` 和部署 skill；备份恢复另见 `docs/backup-and-restore.md`。
- JSON 必须用存储层锁与原子写，损坏时 fail-closed，禁止空值覆盖；保持账户隔离。平台缓存和用户本地状态分离；同济 OJ 只读作业列表，不打开题目详情或提交作业。
- 用户可感知的变化同步 `CHANGELOG.md`，实际部署后才标注发布日期。流程规则只维护在本文件及负责该流程的当前文档，避免复制出多套门禁。
