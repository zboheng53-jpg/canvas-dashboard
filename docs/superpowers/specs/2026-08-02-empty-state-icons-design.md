# 空状态留白图案设计规范 (Empty State Icons Design Spec)

**日期**：2026-08-02  
**状态**：已由用户确认选择（方案 1：保守柔和浅蓝线框）  

## 1. 概述 (Overview)

当 Canvas Dashboard 界面中没有待办事项、长期项目或今日日程时，页面区域会出现较大面积的空白。为了提升界面的整体精致度与视觉丰富度，本设计为以下三个关键区域引入专属定制的空状态矢量图案（SVG）：

1. **待办清单 (Todos)**：待办事项为空/已全完成时的空状态图案。
2. **长期项目 (Projects)**：侧边栏“暂无长期项目”时的空状态图案。
3. **今日日程 (Schedule)**：侧边栏“今天没有日程”时的空状态图案。

## 2. 视觉风格定义 (Visual Style: 方案 1 保守柔和浅蓝线框)

整体风格采用**低明度、低饱和度的淡蓝色线框插画**，与 Canvas Dashboard 现有的白色卡片、`#f5f7fa` 背景及 `--ds-ink` 色系保持高度和谐：

- **背景浅晕 (Backdrop)**：淡冰蓝圆形 `#EFF6FF` (opacity 0.9)，提供轻微的区域视向收拢感。
- **轮廓线框 (Card Outline)**：虚线框线稿 `#93C5FD` (stroke-width 1.5px, stroke-dasharray "3 3")。
- **主元素线稿 (Main Element)**：莫兰迪蓝 `#3B82F6` / `#2563EB`（勾选框、里程碑节点、时钟表盘与挂钩）。
- **点缀装饰 (Sparkles)**：柔和多角微星 `#3B82F6` / `#60A5FA`，赋予细微的浮空灵动感。

---

## 3. 各模块矢量图案规范 (SVG Specifications)

### 3.1 待办清单 (Todos Empty SVG)
- **概念**：浮空虚线卡片 + 勾选框 wireframe + 柔和文本条 + 双角微星点缀。
- **尺寸**：`width: 72px`, `height: 64px`
- **SVG 代码**：
```xml
<svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/>
  <rect x="18" y="14" width="36" height="36" rx="6" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/>
  <rect x="24" y="22" width="8" height="8" rx="2" stroke="#3B82F6" stroke-width="1.5" fill="#FFFFFF"/>
  <path d="M26 26L28 28L30 25" stroke="#2563EB" stroke-width="1.5" stroke-linecap="round"/>
  <rect x="36" y="25" width="12" height="3" rx="1.5" fill="#60A5FA"/>
  <rect x="24" y="36" width="20" height="3" rx="1.5" fill="#BFDBFE"/>
  <path d="M54 14L55 17L58 18L55 19L54 22L53 19L50 18L53 17L54 14Z" fill="#3B82F6"/>
</svg>
```

### 3.2 长期项目 (Long-term Projects Empty SVG)
- **概念**：虚线文件夹轮廓 + 节点里程碑 (Milestone Nodes) 连线 + 浮空微星。
- **尺寸**：`width: 72px`, `height: 64px`
- **SVG 代码**：
```xml
<svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/>
  <rect x="18" y="18" width="36" height="30" rx="6" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/>
  <path d="M26 33H46" stroke="#BFDBFE" stroke-width="1.5"/>
  <circle cx="26" cy="33" r="3" fill="#FFFFFF" stroke="#2563EB" stroke-width="1.5"/>
  <circle cx="36" cy="33" r="3" fill="#FFFFFF" stroke="#3B82F6" stroke-width="1.5"/>
  <circle cx="46" cy="33" r="3" fill="#FFFFFF" stroke="#60A5FA" stroke-width="1.5"/>
  <path d="M22 18V15C22 13.8954 22.8954 13 24 13H30C31.1046 13 32 13.8954 32 15V18" stroke="#93C5FD" stroke-width="1.5"/>
  <path d="M52 14L52.7 16.3L55 17L52.7 17.7L52 20L51.3 17.7L49 17L51.3 16.3L52 14Z" fill="#60A5FA"/>
</svg>
```

### 3.3 今日日程 (Today's Schedule Empty SVG)
- **概念**：虚线日历页 + 挂钩 Pin + 内部表盘指针 + 浮空微星。
- **尺寸**：`width: 72px`, `height: 64px`
- **SVG 代码**：
```xml
<svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/>
  <rect x="20" y="16" width="32" height="34" rx="5" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/>
  <path d="M20 23H52" stroke="#BFDBFE" stroke-width="1.5"/>
  <line x1="28" y1="13" x2="28" y2="17" stroke="#3B82F6" stroke-width="1.5" stroke-linecap="round"/>
  <line x1="44" y1="13" x2="44" y2="17" stroke="#3B82F6" stroke-width="1.5" stroke-linecap="round"/>
  <circle cx="36" cy="35" r="7" fill="#FFFFFF" stroke="#2563EB" stroke-width="1.5"/>
  <path d="M36 31V35L39 37" stroke="#2563EB" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M52 38L52.7 40.3L55 41L52.7 41.7L52 44L51.3 41.7L49 41L51.3 40.3L52 38Z" fill="#3B82F6"/>
</svg>
```

---

## 4. 前端样式与模板修改点 (Implementation Touchpoints)

1. **`frontend/assets/css/design-system.css`**：
   - 移除限制空状态图标显示的 `.todo-list .ui-empty__art, .rail-card .ui-empty__art { display: none !important; }`。
   - 调整 `.ui-empty__art` 基础容器样式，消除默认伪元素 border/before/after 方块干扰，使其支持显示嵌入的真实 SVG。

2. **`frontend/templates/index.html`**：
   - 更新待办事项空状态渲染逻辑中的 `.ui-empty__art`，放入待办专属 SVG。
   - 更新日程渲染逻辑 `schedule_store.py` / 前端 JS 中日程空状态的 `.ui-empty__art`，放入日程专属 SVG。

3. **`frontend/assets/js/projects.js`**：
   - 更新长期项目空状态 `.ui-empty__art`，放入长期项目专属 SVG。

---

## 5. 验证计划 (Verification Plan)

1. **单元测试与 CSS Lint**：
   - 运行 `pytest tests/test_design_system_lint.py` 确保 CSS 修改符合设计系统规范。
   - 运行 `pytest tests/test_p0_safety.py` 确保页面无破坏性影响。
2. **浏览器视觉验收**：
   - 本地运行 `serve.py`（http://127.0.0.1:5000/），清除待办/开启空状态查看待办、项目与日程三处空状态图标的展示效果。
