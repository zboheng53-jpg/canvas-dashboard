# 专项规则与 API

按本次操作读取对应章节。HTTP 路径相对于 `/api/agent/v1`；字段与方法签名见 skill 根目录 `canvas_api.py`。客户端未封装的接口使用 HTTP，服务端字段以返回提示为准。

## 查询与普通待办

| 操作 | HTTP 接口／客户端方法 | 关键参数 |
|---|---|---|
| 课表 | `GET /schedule/today`、`/schedule/date`、`/schedule/timetable` | 指定日期传 `date` |
| 查询、创建待办 | `GET/POST /todos`；`get_todos`、`add_todo` | 查询：`source`、`status`；创建：`text`、`due_date`、`planned_on`、`details`、`request_id` |
| 完成待办 | `POST /todos/<id>/complete`；`complete_todo` | `source` |
| 统一议程 | `GET /agenda`；`get_agenda` | `start`、`end`，最多 63 天 |

## 重复作业

- 用 `create_recurring_todo_series` 创建系列：`first_due_date` 确定基准，`interval_weeks=1|2`，范围明确时传 `end_date`。节奏不确定则只录本次普通待办，周期原文放 `details`。
- 待办清单中每个系列只展示最近一次未完成、未跳过的期次（7 天内或已逾期），今天页保留其中今日到期／逾期的截止提醒；完成或跳过后推进，旧次未完成不阻止后续期次产生。
- 不默认推演整个学期的普通任务。用户明确要求逐条录入且范围、各次截止可确定时，可批量创建普通待办；数量不改变归属。

| 操作 | HTTP 接口／客户端方法 | 关键参数 |
|---|---|---|
| 查询、创建系列 | `GET/POST /recurring-todos`、`GET /recurring-todos/<id>`；`get_recurring_todo_series`、`create_recurring_todo_series` | 创建：`title`、`first_due_date`、`interval_weeks`；可选：`end_date`、`details`、`request_id` |
| 修改、完成、跳过期次 | `update_recurring_todo_occurrence` | `series_id`、`date`，以及修改字段、`done` 或 `skipped`；完成和跳过分别调用，只作用于具体期次 |
| 停止系列 | `stop_recurring_todo_series` | `series_id`、可选 `stop_date` |

## 排程

- 用 `action_ref` 引用已有事项，不复制同名事项。`schedule_action(kind="recurring")` 是重复时间安排，不能代替重复作业提醒；仅在用户明确给出重复节奏时使用，并传起止日期。
- 排程期次完成只完成一次安排，`update_action(done=...)` 完成整个事项；取消排程不删除事项。

| 操作 | HTTP 接口／客户端方法 | 关键参数 |
|---|---|---|
| 单次／重复排程 | `POST /schedule/one-off`、`/schedule/recurring`；`schedule_action` | 单次：`action_ref`、`date`、`start_time`、`end_time`、`location`、`request_id`；重复：另传节奏及起止日期 |

## 项目、资料与纠错

| 操作 | HTTP 接口／客户端方法 | 关键参数 |
|---|---|---|
| 项目与今日行动 | `GET /projects`、`GET /actions/focus`；`get_projects`、`get_project_focus` | 返回项目／任务 ID、资料、版本或今日行动分类 |
| 添加项目行动 | `POST /projects/<project_id>/tasks`；`add_project_task` | 行动字段、`request_id` |
| 行动读写 | `GET/PUT /actions/<ref>`；`get_action`、`update_action` | 修改字段及 `expected_updated_at` |
| 永久删除项目／任务 | `POST /projects/<project_id>/delete`、`/projects/<project_id>/tasks/<task_id>/delete`；`manage_project_record` | `expected_updated_at` |

项目的已有下一步完成后，自动按最早 `planned_on` 推进已有未完成步骤，无日期最后；不会自动生成新步骤。有效手动指定继续保留。项目步骤仅在计划日已到、截止已到或今天有未完成时间块时进入待办；错过计划日的步骤持续显示为今天的原计划未完成，直到完成或明确改期。未来时间块和单次完成不消除这个状态，计划日不作为真实截止。

### 纠错与整理

- 用户纠正归属或日期时，回到原始要求重判类型、范围和截止，不能沿用误分类只修日期。
- 先读回误建记录，只修正本次授权且能确认的部分，保留原文和用户后续改动。整理旧数据先列出逐项变更，不猜测相似事项的关联。
- `delete` 永久删除、不可恢复。

`GET /projects/trash` 仅保留兼容，返回空列表，不代表删除可恢复。
