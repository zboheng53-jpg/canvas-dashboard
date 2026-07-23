# Documentation Index

## Current

- `../README.md`: project entry point and local quick start.
- `architecture.md`: runtime architecture, data boundaries, refresh flows, and release layout.
- `operations.md`: production deployment, rollback, services, health, TLS, and incident commands.
- `backup-and-restore.md`: encrypted backups, key ownership, recovery drills, corruption handling, and production restoration.
- `zhihuishu-reusable-web-patterns.md`: reusable browser-worker/login-window design.
- `../deploy/zhihuishu-login-tunnel.md`: concrete 智慧树 and Tongji browser-login production runbook.
- `../AGENTS.md`: coding-agent rules and current implementation contracts.

## Historical

`superpowers/plans/` and `superpowers/specs/` preserve dated design and implementation context. They are not task trackers or current runbooks. Unchecked boxes record the drafting state, not the current completion state. Each plan with superseded operational assumptions has a status note at the top.

The external-platform-subtask plan is an unimplemented proposal. Current editable subtasks belong only to custom todos.

When behavior changes, update the current document that owns the contract and add or update matching tests. Keep historical records unchanged except for a short status boundary when they could mislead an operator.
