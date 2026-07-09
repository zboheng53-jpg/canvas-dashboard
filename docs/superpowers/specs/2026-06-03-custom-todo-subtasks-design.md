# 自定义待办折叠式细化清单设计

## Context

Canvas Dashboard 当前将 Canvas、好课、智学盟、智慧树和手动添加的自定义待办合并在同一个“待办清单”里展示。自定义待办已经支持标题、截止日期、标签、完成、标红和删除。

用户希望在待办清单中增加一个可折叠的细化清单，参考 `C:\Users\zhangboheng\Desktop\lftodo` 中人生清单的折叠/展开思路，但本功能只作用于当前项目里的手动自定义待办。

## Goal

为手动添加的自定义待办增加轻量 checklist，用于把一个父待办拆成多个可勾选的小步骤。

成功标准：

- 自定义待办可以展开/收起子任务区域。
- 子任务支持新增、勾选完成、删除、点击文字内联编辑。
- 子任务完成状态不自动改变父待办完成状态。
- 外部平台待办不提供子任务功能，只保留统一布局所需的三角占位。

## Non-goals

第一版不做以下功能：

- 不给 Canvas、好课、智学盟、智慧树条目添加子任务。
- 不支持子任务拖拽排序。
- 不支持新建父待办时批量输入子任务。
- 不持久化展开状态；刷新后全部收起。
- 不新增数据库或并发文件锁。（2026-07-09 之后的当前实现已为运行时 JSON 写入引入 `storage.py`：同路径进程内锁 + 临时文件原子替换；这条仅反映本功能初版设计约束。）

## User Experience

自定义待办仍显示在统一待办列表中，保留现有来源 badge、标题、标签、截止日期、标红、完成、删除等交互。

每个自定义待办新增一个轻量展开入口：

- 使用小三角作为展开/收起入口：收起为 `▸`，展开为 `▾`。
- 点击入口展开或收起。
- 外部平台待办可渲染无功能的三角占位，用于保持日期和右侧操作图标对齐，但不提供子任务功能。

展开后，在该自定义待办行下方缩进显示子任务面板：

- 每行子任务包含 checkbox、文字和删除按钮。
- checkbox 只修改该子任务的 `done` 状态。
- 点击子任务文字进入内联编辑，Enter 保存，Escape 取消。
- 面板底部显示“添加子任务...”输入框，输入后按 Enter 新增。
- 子任务按创建顺序显示。

父待办完成状态和子任务完成状态相互独立。即使所有子任务都完成，父待办仍需用户手动点击原来的完成按钮。

## Data Model

继续使用现有 `data/custom_todos.json` 存储自定义待办，不新增文件。

每个自定义待办新增 `subtasks` 字段：

```json
{
  "id": 16,
  "text": "高数作业",
  "done": false,
  "created_at": "2026-06-03T20:00:00+08:00",
  "due_date": "2026-06-05",
  "highlighted": false,
  "labels": ["数学"],
  "subtasks": [
    { "id": 1, "text": "看第 3 章", "done": false },
    { "id": 2, "text": "写 1-5 题", "done": true }
  ]
}
```

兼容旧数据：

- `_load_todos()` 继续补齐缺失的 `labels`。
- `_load_todos()` 额外为缺失 `subtasks` 的旧条目补 `[]`。

新建自定义待办时默认写入 `subtasks: []`。

子任务 id 只在父待办内部唯一：

```text
newSubtaskId = max(existing subtask ids, default=0) + 1
```

## API Design

复用现有自定义待办 API，不新增 nested routes。

| Method | Route | Change |
|---|---|---|
| GET | `/api/custom/todos` | 返回自定义待办时包含 `subtasks` |
| POST | `/api/custom/todos` | 新建待办时写入 `subtasks: []` |
| PUT | `/api/custom/todos/<id>` | 允许更新整组 `subtasks` |

前端在新增、勾选、编辑、删除子任务时，先更新本地 `customItems` 中对应父待办的 `subtasks` 数组，再通过一次 PUT 保存：

```json
{
  "subtasks": [
    { "id": 1, "text": "看第 3 章", "done": true },
    { "id": 2, "text": "写 1-5 题", "done": false }
  ]
}
```

错误处理保持轻量：

- 空子任务文本不提交。
- 保存失败时提示 `保存失败` 并重新拉取自定义待办，避免前端状态长期不一致。
- 初版不新增文件锁，沿用当时项目 JSON 文件写入模式。当前实现已改为通过 `storage.py` 对运行时 JSON 做原子写入；自定义待办的读改写路径使用 `locked_json_update()`。

## Frontend Structure

主要修改 `templates/index.html` 的统一列表渲染逻辑。

### State

新增前端内存状态：

```javascript
let expandedCustomTodoIds = [];
```

该状态不持久化。刷新页面后默认全部收起。

### Unified item data

`customItems.forEach` 构造 unified item 时增加：

```javascript
subtasks: item.subtasks || []
```

外部平台 unified item 不增加子任务功能。

### Markup

当前 `.unified-item` 是单行 flex。为了在行下方显示子任务，渲染自定义待办时使用 wrapper：

```html
<div class="unified-item-wrap">
  <div class="todo-item unified-item">...</div>
  <div class="subtask-panel">...</div>
</div>
```

只有自定义待办需要 wrapper 和 subtask panel。外部平台条目保持当前结构，除非实现时为了减少分支而统一包一层；无论哪种实现，外部平台视觉和行为必须保持不变。

### Functions

新增少量只操作自定义待办的 JS 函数：

- `toggleSubtasks(todoId)`：展开/收起。
- `addSubtask(todoId, text)`：新增子任务。
- `toggleSubtaskDone(todoId, subtaskId)`：勾选/取消勾选。
- `startSubtaskEdit(todoId, subtaskId, spanEl)`：子任务文字内联编辑。
- `deleteSubtask(todoId, subtaskId)`：删除子任务。
- `saveCustomSubtasks(todoId, subtasks)`：PUT 保存子任务数组。

现有 `saveInlineEdit`、`toggleTodoCheck`、`toggleCustomHighlight`、`toggleCustomDelete` 等父待办功能保持现状。

## Styling

主要修改 `static/style.css`，延续当前 dashboard 的米白、蓝灰、细边框风格。

新增样式目标：

- `.subtask-toggle`：与右侧操作图标同尺寸的小三角按钮，视觉弱化，不显示文字标签。
- `.subtask-panel`：在父待办下方缩进显示，使用淡边框或浅背景区分层级。
- `.subtask-row`：checkbox + 文本 + 删除按钮的横向布局。
- `.subtask-text.done`：灰色并添加删除线。
- `.subtask-add-input`：小号输入框，风格接近现有 inline edit 输入框。

移动端保持可读：子任务面板跟随父待办宽度，文本过长时换行或截断，不撑破列表。

## Verification

实现完成后验证以下场景：

1. 旧的 `data/custom_todos.json` 没有 `subtasks` 字段时页面正常加载。
2. 新建自定义待办后，数据文件中该条包含 `subtasks: []`。
3. 展开一个自定义待办，添加 2 个子任务，刷新后子任务仍存在且默认收起。
4. 勾选子任务后，子任务状态保存；刷新后保持。
5. 点击子任务文字编辑，刷新后修改保留。
6. 删除子任务，刷新后删除保留。
7. 所有子任务完成后，父待办不会自动完成。
8. Canvas、好课、智学盟、智慧树条目的渲染和操作不变。
9. 现有自定义待办标题、标签、截止日期内联编辑仍可用。

## Implementation Scope

预计修改文件：

- `app.py`
  - `_load_todos()` 补齐 `subtasks`。
  - POST `/api/custom/todos` 新建时写入 `subtasks: []`。
  - PUT `/api/custom/todos/<id>` 支持更新 `subtasks`。
- `templates/index.html`
  - 自定义待办 unified item 携带 `subtasks`。
  - 自定义待办渲染新增展开入口和子任务面板。
  - 新增子任务操作函数。
- `static/style.css`
  - 新增子任务相关样式。

该范围足够形成一个单独实施计划，不需要拆成多个子项目。
