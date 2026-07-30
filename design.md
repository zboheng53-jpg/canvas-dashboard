# Canvas Dashboard UI 设计规范

> 本文与 Figma 设计系统一一对应：Figma 负责可视化变量、组件和页面组合；本文记录变量含义、代码映射与开发约束。新增页面或组件应优先复用两者；若需求与本文冲突，以已确认的产品需求为准。

## 0. Figma 对应与同步规则

### 0.1 设计源职责

| 载体 | 职责 | 修改规则 |
| --- | --- | --- |
| Figma `Canvas Dashboard · Design System` | 变量、文字/效果样式、组件变体、页面组合和视觉验收 | 设计调整先在 Figma 变量或组件中完成。 |
| `design.md` | 设计意图、数值定义、Figma 名称与 CSS 映射、实现约束 | Figma 变量或组件变化后，同步更新本文件。 |
| `frontend/assets/css/dashboard-v103.css` | 生产环境实际样式 | 实现时优先引用已有 CSS token；缺失 token 需与 Figma 同名语义补齐。 |

Figma 文件建立后，应把文件链接填入此处；当前账号仅有查看权限，因此本轮只完成了可执行的对照结构，尚不能创建或写入该 Figma 文件。

### 0.2 Figma 页面结构

| Figma 页面 | 内容 | 对应本文 |
| --- | --- | --- |
| `00 · Overview` | 风格摘要、使用说明、链接至组件页 | 第 1、5 节 |
| `01 · Foundations` | 色彩、字体、间距、圆角、阴影变量与样式 | 第 2 节 |
| `02 · Components` | Button、Input、Card、Status Badge 等组件集 | 第 3 节 |
| `03 · Patterns` | 标题区、操作栏、列表、空状态和表单组合 | 第 4 节 |
| `04 · Screens` | 控制台各页面的实例与验收稿 | 第 4、5 节 |

### 0.3 Token 映射规则

- Figma 使用 `/` 分层命名，如 `color/text/primary`、`spacing/4`、`radius/button`；CSS 保留既有 `--` 命名。
- Figma 变量必须设置精确的适用范围，不能使用 `ALL_SCOPES`。
- 每项 Figma 变量需在说明中保留对应 CSS token；实现新样式时不能只写裸色值。
- 当前只提供 Light 模式。将来引入深色模式时，新增 `Light` / `Dark` 语义色模式；基础色和间距仍保持单一模式。

### 0.4 首版 Figma 变量对照

| Figma Collection / Variable | 类型 | 值 | CSS 对应 |
| --- | --- | --- | --- |
| `Color / background/canvas` | COLOR | `#F4F3EE` | `--bg-main` |
| `Color / surface/default` | COLOR | `rgba(255,255,255,.78)` | `--surface`、`--card-bg` |
| `Color / text/primary` | COLOR | `#2C3237` | `--text-primary` |
| `Color / text/secondary` | COLOR | `#5A646C` | `--text-secondary` |
| `Color / text/muted` | COLOR | `#8C969E` | `--text-muted` |
| `Color / border/default` | COLOR | `rgba(226,220,210,.85)` | `--border` |
| `Color / action/brand` | COLOR | `#2F6FE4` | `--color-primary` |
| `Color / action/secondary-text` | COLOR | `#3A5985` | `console-secondary-button` 文字色 |
| `Color / action/secondary-border` | COLOR | `#CBDCF6` | `console-secondary-button` 边框色 |
| `Color / action/secondary-hover` | COLOR | `#EDF4FF` | `console-secondary-button` 悬停底色 |
| `Spacing / 1…8` | FLOAT | `4, 8, 12, 16, 20, 24, 32` | 见第 2.3 节 |
| `Radius / control` | FLOAT | `6` | 默认按钮、输入框 |
| `Radius / card` | FLOAT | `12–14` | `--radius-card` |

每次增加变量时，都要在此表补充 Figma 路径、实际值和 CSS 映射；若 Figma 与代码存在不同值，先确认再修改，不能静默覆盖任一侧。

## 1. 整体风格

产品采用「克制、通透、工具优先」的后台工作台风格：接近 Linear / Vercel 的清晰层级，但保留温和的莫兰迪灰米色基调，避免强饱和、大面积渐变和厚重拟物阴影。

- 页面背景温暖、低对比；内容卡片以半透明白色承载信息。
- 信息层级依靠留白、细描边、字号和字重建立，不依赖高饱和底色。
- 操作反馈轻量直接：悬停只改变背景、边框和文字颜色，不做明显位移或反白。
- 默认使用浅色界面；危险、警告、成功只用于状态和对应操作，不能当作普通装饰色。

## 2. 设计 Token

### 2.1 色彩

| 用途 | Token / 色值 | 说明 |
| --- | --- | --- |
| 页面底色 | `#F4F3EE` | 全局暖灰底色。 |
| 卡片表面 | `rgba(255,255,255,.78)` | 主卡片、面板；可配合轻微毛玻璃。 |
| 悬停卡片表面 | `rgba(255,255,255,.92)` | 卡片需要悬停反馈时使用。 |
| 主文字 | `#2C3237` | 标题、正文和主要数值。 |
| 次级文字 | `#5A646C` | 说明文、表单标签。 |
| 弱化文字 | `#8C969E` | 辅助信息、空状态、时间。 |
| 常规边框 | `rgba(226,220,210,.85)` | 卡片、分隔线、输入框默认边界。 |
| 弱边框 | `rgba(215,208,195,.45)` | 次级分隔或嵌套区域。 |
| 品牌蓝 | `#2F6FE4` | 导航选中、链接、非按钮强调。 |
| 品牌蓝浅底 | `#EAF2FF` | 导航选中、标签等非按钮选中态。 |
| 按钮黛蓝文字 | `#3A5985` | 默认操作按钮文字，低饱和且不刺眼。 |
| 按钮浅蓝边框 | `#CBDCF6` | 默认操作按钮边框。 |
| 按钮悬停底色 | `#EDF4FF` | 默认操作按钮 hover / focus。 |
| 危险色 | `#DC2626` | 删除、永久操作；背景使用 8% 透明度。 |
| 警告色 | `#D97706` | 注意或需处理状态；背景使用 9% 透明度。 |

不要为普通操作使用深蓝实底和白字。蓝色实底仅可用于有明确业务优先级且经过产品确认的极少数场景。

### 2.2 字体

```css
--font-sans: "MiSans", -apple-system, BlinkMacSystemFont, "PingFang SC",
  "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif;
--font-serif: "Tiempos Text", "Noto Serif SC", "Source Han Serif SC",
  "Songti SC", "SimSun", serif;
--font-mono: "Geist", var(--font-sans);
--font-number: "Geist", "MiSans", "Inter", "SF Pro Display", -apple-system,
  BlinkMacSystemFont, "Segoe UI", sans-serif;
```

| 场景 | 字体 | 字号 / 字重 |
| --- | --- | --- |
| 页面主标题 | `--font-serif` | 27–32px / 500–600 |
| 区域标题 | `--font-sans` | 16–20px / 600 |
| 正文 | `--font-sans` | 13–14px / 400–500 |
| 表单标签、辅助标题 | `--font-sans` | 12px / 500 |
| 辅助说明 | `--font-sans` | 11–12px / 400 |
| 按钮 | 系统无衬线 | 12px / 500 |
| 日期、时间、计数 | `--font-number` | 11–13px / 400–500 |

正文行高使用 `1.5–1.65`；紧凑的标题与按钮使用 `1.2–1.4`。中文排版不额外添加较大的字距。

### 2.3 间距与圆角

采用 4px 基础网格。除紧凑图标按钮外，间距应从下列档位中选择：

| Token | 数值 | 常见用途 |
| --- | --- | --- |
| `space-1` | 4px | 图标与文字、紧凑列表内部。 |
| `space-2` | 8px | 同组控件间距、表单字段小间距。 |
| `space-3` | 12px | 按钮内边距、普通列表项。 |
| `space-4` | 16px | 卡片内边距、小节间距。 |
| `space-5` | 20px | 卡片内容分组。 |
| `space-6` | 24px | 页面区块、常规卡片内边距。 |
| `space-8` | 32px | 主内容区块间距。 |

| 对象 | 圆角 |
| --- | --- |
| 图标按钮、小标签 | 4–6px |
| 默认按钮、输入框 | 6px |
| 选中导航项、紧凑面板 | 8px |
| 卡片、模态框 | 12–14px |

## 3. 基础组件

### 3.1 默认操作按钮（必须优先使用）

所有常规蓝色操作，例如“保存配置”“完成项目”“添加任务”“生成订阅链接”，默认使用以下次级按钮，而不是深蓝实底按钮。

```html
<button type="button" class="console-secondary-button">刷新状态</button>
```

```css
.console-secondary-button {
  flex: 0 0 auto;
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid #cbdcf6;
  border-radius: 6px;
  background: #fff;
  color: #3a5985;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 200ms ease, border-color 200ms ease, color 200ms ease;
}

.console-secondary-button:hover:not(:disabled),
.console-secondary-button:focus-visible:not(:disabled) {
  background: #edf4ff;
  outline: none;
}

.console-secondary-button:disabled {
  cursor: wait;
  opacity: .55;
}
```

规则：

- 主操作也沿用这套白底描边样式；通过位置、文案和分组表达优先级，不通过反白深蓝表达。
- 按钮文案用动词开头，如“保存配置”“添加任务”“刷新状态”。
- 不为 hover 添加上浮、缩放或浓重阴影。
- 纯白的取消、查看、更多菜单按钮保持中性灰边框和深灰文字，不强行染蓝。

### 3.2 危险按钮

删除、清除、撤销订阅等不可逆操作使用白底或极浅红底，红色文字与红色边框；禁止把危险操作伪装成默认蓝色操作。悬停可加深浅红背景，但不使用大面积纯红。

### 3.3 图标按钮

- 仅图标操作使用 28–32px 方形点击区，圆角 6px。
- 默认透明或白底，使用弱化文字色；hover 使用非常浅的中性色背景。
- 所有图标按钮必须有 `title` 或 `aria-label`。

### 3.4 输入框与选择器

- 默认高度：36px；紧凑场景可以为 34px。
- 内边距：`0 10–12px`；圆角：6px。
- 背景：白色或极轻的白色半透明；边框使用常规边框 token。
- `:focus` 使用品牌蓝描边或轻量 `0 0 0 3px rgba(47,111,228,.15)` 焦点环。
- 标签置于输入框上方，间距 6–8px；不要把 placeholder 当作唯一标签。

### 3.5 卡片、列表与分隔

- 卡片背景使用 `--surface`，边框使用 `--border`，圆角 12–14px。
- 常规卡片内边距 20–24px；紧凑卡片 12–16px。
- 阴影只用于区分悬浮层：`0 4px 20px -2px rgba(70,80,72,.04)`；普通卡片可无阴影。
- 列表行优先用细分隔线，不要给每行增加厚边框和强阴影。

### 3.6 状态标签

- 高度紧凑，内边距 `2px 6px`，圆角 4–6px，字号 10–11px，字重 500。
- 成功使用低饱和绿色，警告使用低饱和橙色，错误使用低饱和红色。
- 状态颜色只服务语义；与普通操作按钮保持区分。

## 4. 布局与响应式

- 桌面端工作区保持左侧导航 + 右侧主内容的结构；主内容以卡片和区块分隔。
- 页面标题区包含：kicker（可选）、标题、说明，以及右侧操作区；标题区下方使用细分隔线。
- 桌面端主卡片间距通常为 24–32px；移动端收至 12–16px。
- 宽度不足时，按钮组允许换行；不要压缩文字、截断关键操作或强行保持等宽。
- 移动端按钮可在需要时铺满容器，但保持 36px 高与相同的视觉 token。

## 5. 开发约束与检查清单

新增或修改 UI 前检查：

1. 是否复用了现有 token，而不是新增近似色值？
2. 常规操作是否采用白底黛蓝描边按钮，而不是深蓝实底？
3. 按钮、输入框、卡片的圆角和高度是否符合本规范？
4. hover / focus 是否有键盘可见的反馈，且没有突兀位移？
5. 文字层级是否通过字号、字重、留白建立，而不是靠颜色堆叠？
6. 在桌面端和移动端，操作是否仍可读、可点击、可换行？
7. 调整视觉规则后，是否同步更新相关 Playwright 视觉断言？
