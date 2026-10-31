# Ui — Style Reference
> clinical blueprint on frosted paper

> 2026-10-09 用户更新：全前端状态展示统一使用语义色，优先于本文默认单色约定。失败、已取消、已停止为红色；进行中为蓝色；已完成、检查通过为绿色；待审核/待处理为琥珀色；未开始及未知为灰色。保留状态文字与现有图标，不仅靠颜色区分。共享配色见 `apps/web/src/status.css`，状态映射见 `apps/web/src/status.ts`。


## 界面文案与可访问性（2026-10-30 用户补充，长期要求）

避免不必要的次要标签、说明文字、辅助文案、描述性文字和冗余的微文案。让布局、视觉层级、间距和清晰的主操作自己完成解释。

- 优先用强视觉层级和自解释的结构，而不是用文字去解释。
- 默认不要添加 slogan 式文字、教学段落，或在每个区块下都加“帮助说明”。
- 如果确实需要补充信息，优先使用 info 图标 + tooltip，而不是始终显示的次要文字。提示须支持键盘聚焦与读屏访问。
- 保留必要的表单标签和可访问名称（方便读屏软件）。界面清爽不能牺牲可访问性。
- 危险或不可逆操作（删除、支付、提交永久性变更）必须保留清晰的后果提示。
- 去掉说明文字后，第一次使用的人仍应能看懂：下一步点哪里、点了会发生什么。
- 重写已有界面时：先去掉冗余标签和说明，如果清晰度下降，再优化布局和按钮文案。

以上要求与状态语义色、正文可读性规范共同适用；状态事实、错误信息、必要操作后果不应当作冗余文案删除。

## 信息层级与视觉显著性（2026-10-30 用户补充，长期要求）

**视觉显著性应与信息的重要性、逻辑层级及当前操作优先级相匹配。** 先确定用户需要先看什么、再理解什么、最后采取什么行动，再决定元素的大小、字重、颜色、位置和留白；不能因组件类型或装饰偏好让次要内容抢占注意力。

- 在页面、区块和单张卡片内部，都应建立清晰的主次关系。通常使用“核心信息／主操作 → 支撑信息／次操作 → 元数据／补充信息”三个层次；按实际任务选择重点，不机械地让所有标题或所有数字都最大、最粗。
- 每个独立信息组应有明确的首要视觉焦点。同一操作组默认只有一个主操作；多个卡片并列时，其强调程度还须服从整个页面的任务优先级，避免所有局部重点同时争夺注意力。
- 核心信息可使用较大字号、较高字重、深色文字或更充分的独立留白；支撑信息使用常规字号与字重；元数据使用可读的次级文字样式。少量、协调地组合强调手段，不默认把放大、加粗、亮色和厚边框全部叠加。
- 用位置、分组、对齐和间距表达逻辑关系：相关内容靠近，不同层级适当拉开；阅读顺序应与理解和操作顺序一致。不要依赖反复添加标签或说明文案弥补层级不清。
- 颜色承担稳定的语义。重点优先通过字号、字重、深浅与留白建立；涉及状态时沿用共享语义色，不为吸引注意而给普通内容套用成功、失败或警告色。状态同时保留文字或图标，不能只靠颜色传达。
- 同等语义、同等优先级的元素使用一致样式；不同层级应有可辨认的差异。辅助图标、单位、时间和编号不得比它们所解释的核心内容更显眼。
- 次要信息可以弱化，但不能通过过浅颜色、过小字号或低透明度牺牲可读性与可访问性。沿用正文至少 14px、元数据至少 12px 的规范；关键错误和不可逆操作后果不能因被归入“辅助文案”而弱化。
- 验收时快速扫视页面和卡片：第一眼应看到核心信息或当前必须处理的问题，随后找到支撑信息和下一步操作。若所有内容同样醒目，或次要元素先吸引注意，应重新分配视觉权重；窄屏换行后也须保持该顺序。

## 圆角卡片留白（2026-10-30 用户补充，长期要求）

圆角卡片须给内容留足安全间距，避免文字、图标、按钮和底部信息贴近弧形边角。留白应随圆角和内容密度协调调整；本节优先于旧的紧凑卡片间距示例。

- 主卡片（24px 圆角）默认内边距 28px，窄屏使用 24px；标题、正文、操作区和底部信息沿同一内侧边线排列。
- 嵌套卡片和紧凑交互区域默认内边距 20px；嵌套卡片在窄屏可降至 16px，输入操作台保留 20px。不要为挤入一行而让内容贴边，应优先换行。
- 同级卡片之间默认留 24px，窄屏留 16px；保持共用内容容器和已经统一的左右边界。
- 内容与边框的距离用 padding 控制，卡片之间的距离用 gap / margin 控制；不要通过子元素负 margin 或单独偏移破坏对齐。
- 图片或装饰背景允许铺满卡片，但图表中的文字、可交互内容以及覆盖文字仍须位于安全内区。
- 检查四角附近的标题首行、角落按钮、末行文字和底部操作；兼顾长标题换行、窄屏及键盘焦点轮廓，不能用裁切掩盖拥挤。

统一使用 tokens.css 中的 --card-padding、--card-padding-compact、--card-padding-input 和 --card-gap，避免各组件自行缩小。

## 下拉选择与菜单（2026-10-30 用户补充，长期要求）

所有下拉选择与菜单类控件统一遵循圆角和安全留白规范，覆盖主界面、弹窗、表单及工具栏，不因业务场景或实现方式不同而出现另一套样式。本节是通用要求，具体组件说明只补充其差异。

- **触发框与展开面板都使用圆角。** 触发框沿用交互控件的 18px 圆角，展开菜单沿用容器的 24px 圆角，选项的悬停、选中及键盘活动背景使用 18px 圆角。菜单边框、背景、滚动区域与内容裁切须匹配外轮廓，不能只把触发框做圆而展开后仍为直角框。
- **指示箭头必须留有独立的边缘安全距离。** 箭头在触发框内垂直居中，其可见右边缘距框内侧默认 16px；紧凑及窄屏布局不得少于 12px。文字与箭头之间至少保留 8px，文字区域须预留箭头宽度、间隔及右侧留白，不能让长文字覆盖箭头或将箭头挤到边缘。采用逻辑方向布局时，同样约束末端留白。
- **留白服务于内容和形状。** 展开菜单内部须保留统一内边距，使首末选项、选中标记及滚动条不贴住圆角。空间不足时调整菜单位置、宽度或滚动高度，不通过压缩安全留白、拉伸箭头或负 margin 挤入内容。
- **共用组件与设计 token。** 圆角、箭头尺寸、文字间隔及末端留白在共用下拉组件和 tokens.css 中统一维护，沿用既有圆角与间距 token；不要逐页硬编码箭头位置。系统原生控件若无法保证展开面板圆角和箭头留白，应使用统一的可访问下拉组件，不能把平台默认外观视为符合规范。
- **样式与可访问性同时验收。** 保留可访问名称、展开状态、选中及禁用状态、键盘导航和可见焦点。检查桌面与窄屏、弹窗内、长选项文字，以及展开菜单的四角、首末项和箭头留白；菜单不得被父容器裁切或超出可用视口。

## 悬浮式界面框架（2026-10-30）

- 固定导航栏、可折叠项目栏和主内容区使用独立的 24px 圆角面板；与背景保持间距，不以贴边直线分隔构成界面外框。
- 背景使用 Canvas，导航与研究页面使用 Surface Alt，对话使用 Paper；面板使用细边框和轻阴影，保持正文对比度与状态语义色。
- 外侧留白与面板间距统一使用 `--shell-inset`、`--shell-gap`：桌面均为 12px，窄屏均为 8px。内部卡片继续遵循安全留白，不为增加外侧间距压缩内容内边距。
- 导航保持固定，内容区独立滚动；项目栏折叠后主内容填充空位。窄屏项目栏以圆角抽屉展开，固定导航仍可操作。
- 不重复展示左侧导航及项目空间已经表达的页面名称和项目路径，右侧不设独立路径／状态栏。主内容区与左侧面板顶部对齐；项目空间收起后的展开入口放在固定导航栏中。
- 项目空间桌面默认宽 320px，中等屏幕宽 280px；窄屏抽屉不超过可用宽度。展开与折叠使用约 280ms 的平滑过渡，内部内容保持宽度，避免收起过程中文字反复换行；收起后禁用隐藏内容的交互和键盘聚焦。
- 项目及子对话标题保留完整可访问名称。超宽时默认省略，悬停或键盘聚焦后平缓往返滚动，首尾停留；短标题保持静止。触屏可横向滑动查看，减少动态效果模式关闭自动滚动和折叠动画。子对话通过缩进及选中态表达层级，不添加前置圆点。
- 根据主内容区的实际可用宽度调整内部排列，避免展开项目栏后文字挤成竖排；不为每个内部列表额外叠加圆角框。

**Theme:** light

shadcn/ui is a monochromatic design-system workshop: pure white canvas, soft warm-gray surfaces, and large-radius cards floating on hairline borders. The interface is almost entirely achromatic — black text, white surfaces, gray secondary tones — with a single destructive red reserved for error states and nothing else. Typography leans on Geist's geometric neutrality with tight letter-spacing on display sizes, creating a quiet, code-adjacent feel that reads as developer infrastructure rather than consumer product.

## Tokens — Colors

| Name | Value | Token | Role |
|------|-------|-------|------|
| Canvas | `#f5f5f5` | `--color-canvas` | Page background, muted surface fills, secondary buttons |
| Paper | `#ffffff` | `--color-paper` | Card surfaces, popover backgrounds, primary button fills |
| Surface Alt | `#fafafa` | `--color-surface-alt` | Sidebar background, subtle card variant, input resting state |
| Ink | `#0a0a0a` | `--color-ink` | Primary text, headings, button labels, icon strokes |
| Ink Soft | `#171717` | `--color-ink-soft` | Filled button backgrounds, secondary text on light surfaces |
| Mid Gray | `#737373` | `--color-mid-gray` | Muted body text, placeholder text, helper labels, icon fills at rest |
| Hairline | `#e5e5e5` | `--color-hairline` | Borders, input outlines, card edges, badge outlines |
| Ember | `#e7000b` | `--color-ember` | Red decorative accent for icons, marks, and small graphic details. Use as a supporting accent, not as a status color |

## Tokens — Typography

### Geist — All interface text — body at 14px/400, headings ranging 24–48px/600, buttons at 13–14px/500. Geist's geometric letterforms and uniform stroke width create a developer-tool neutrality; weight 600 at 48px with -0.05em tracking produces tight, confident display headlines that feel engineered rather than editorial. · `--font-geist`
- **Substitute:** Inter
- **Weights:** 400, 500, 600
- **Sizes:** 12, 13, 14, 16, 18, 24, 30, 36, 48
- **Line height:** 1.10, 1.11, 1.20, 1.33, 1.43, 1.50, 1.56, 1.63, 2.00
- **Letter spacing:** -0.0500em at display (48px), -0.0250em at subheading (24–30px), 0.0500em at caption (12px uppercase). Tracking tightens aggressively at large sizes and loosens slightly at small uppercase labels.
- **OpenType features:** `"ss01" on, "cv11" on`
- **Role:** All interface text — body at 14px/400, headings ranging 24–48px/600, buttons at 13–14px/500. Geist's geometric letterforms and uniform stroke width create a developer-tool neutrality; weight 600 at 48px with -0.05em tracking produces tight, confident display headlines that feel engineered rather than editorial.

### Type Scale

| Role | Size | Line Height | Letter Spacing | Token |
|------|------|-------------|----------------|-------|
| caption | 12px | 1.33 | 0.6px | `--text-caption` |
| body | 14px | 1.43 | — | `--text-body` |
| body-lg | 16px | 1.5 | — | `--text-body-lg` |
| subheading | 18px | 1.56 | — | `--text-subheading` |
| heading-sm | 24px | 1.33 | -0.6px | `--text-heading-sm` |
| heading | 30px | 1.2 | -0.75px | `--text-heading` |
| heading-lg | 36px | 1.11 | -0.9px | `--text-heading-lg` |
| display | 48px | 1.1 | -2.4px | `--text-display` |

## Tokens — Spacing & Shapes

**Base unit:** 4px

**Density:** compact

### Spacing Scale

| Name | Value | Token |
|------|-------|-------|
| 4 | 4px | `--spacing-4` |
| 8 | 8px | `--spacing-8` |
| 12 | 12px | `--spacing-12` |
| 16 | 16px | `--spacing-16` |
| 20 | 20px | `--spacing-20` |
| 24 | 24px | `--spacing-24` |
| 48 | 48px | `--spacing-48` |

### Border Radius

| Element | Value |
|---------|-------|
| cards | 24px |
| small | 6px |
| badges | 18px |
| inputs | 18px |
| nested | 10px |
| buttons | 18px |

### Shadows

| Name | Value | Token |
|------|-------|-------|
| subtle | `oklab(0.145 -0.00000143796 0.00000340492 / 0.05) 0px 0px ...` | `--shadow-subtle` |
| subtle-2 | `lab(2.75381 0 0) 0px 0px 0px 0px` | `--shadow-subtle-2` |

### Layout

- **Page max-width:** 1280px
- **Section gap:** 48-80px
- **Card padding:** 28px（窄屏 24px）
- **Element gap:** 8px

## Components

### Primary Filled Button
**Role:** High-emphasis action (Submit, Save, Create)

Background #0a0a0a, text #fafafa, border none, radius 18px, padding 0px 12px (compact) or 8px 16px (comfortable), font 14px Geist weight 500. Height ≈ 36–40px. The dark-on-light inversion is the only chromatic interaction in the system; the fully rounded radius (18px on a ~36px height) produces perfect pill geometry.

### Secondary Ghost Button
**Role:** Low-emphasis action (Cancel, Back)

Background #f5f5f5, text #0a0a0a, no border, radius 18px, padding 0px 12px or 8px 16px, font 14px weight 500. Soft gray fill reads as a tonal sibling to the primary rather than a muted alternative — both buttons share shape and type, differing only in lightness.

### Outline Button
**Role:** Tertiary action with visible boundary

Background transparent, text #0a0a0a, border 1px solid #e5e5e5, radius 18px, padding 0px 12px or 8px 10px. The hairline border defines the shape without weight — preferred when the button sits inside a card or alongside filled controls.

### Card
**Role:** Content container for blocks, previews, dashboard panels

Background #ffffff, radius 24px, border 1px solid #e5e5e5, shadow oklab(0.145/.05) 0 0 0 1px + rgba(0,0,0,0.1) 0 1px 3px + rgba(0,0,0,0.1) 0 1px 2px -1px, padding 28px (24px on narrow screens). The 1px hairline shadow stacks with a faint elevation layer — cards sit visually raised but remain flat and understated.

### Nested Card Header/Footer
**Role:** Header or footer strip inside a card

Asymmetric radius — top corners 24px on header, bottom corners 24px on footer. Padding 28px horizontal (24px on narrow screens), transparent fill. Provides a subtle tonal band within card boundaries without introducing a new color.

### Input Field
**Role:** Text entry, search, form controls

Background #f5f5f5 (resting) or transparent (inline), text #0a0a0a, border none at rest with 1px #e5e5e5 on focus, radius 18px, padding 8px 10px, font 14px weight 400. The soft gray fill differentiates the input from the card surface beneath it; focus replaces the fill with a 1px ring.

### 对话内容宽度与对齐

执行操作台的标题、对话内容、内嵌研究卡片与输入框共用同一宽度，最大为 `--page-max-width`（1280px）。左右安全距离统一使用 `--chat-gutter`（桌面 28px、窄屏 16px）；输入框内部继续保留 20px 留白。

Agent 头像放在消息标题行，输出正文沿输入框外侧左边线排列，不因头像额外缩进。用户消息气泡右边缘与输入框右边缘对齐，长内容可占满共同宽度；保留气泡内部留白。展开／折叠项目空间、窄屏和滚动条出现时均须保持共同边界。

### 对话模型与模式选择器

模型与模式使用可区分的中性底色：模型使用 Canvas，模式使用 `--color-control-fill`（#eaeaea），正文保持深色。触发框、展开菜单、选项圆角及指示箭头留白统一遵循上文“下拉选择与菜单”规范；选中项保留勾选标记，键盘活动项有可见边框。

展开菜单使用统一组件，不依赖系统原生矩形选项窗口；按视口空间向上或向下展开，不能被输入框或对话容器裁切。保留可访问名称、方向键／首尾键导航、Enter 选择、Esc 关闭、Tab 离开及禁用选项行为；样式修改不能改变模型和执行权限的实际语义。

### Badge — Solid
**Role:** Tag, status pill, counter

Background #171717, text #fafafa, radius 18px, padding 2px 8px, font 12px weight 500. Pill-shaped at 18px radius — the minimum height creates a capsule tag.

### Badge — Soft
**Role:** Neutral label, category tag

Background #f5f5f5, text #171717, radius 18px, padding 2px 8px, font 12px weight 500. Same capsule geometry as solid badge, tonal variant.

### Badge — Outline
**Role:** Subtle tag with no fill

Transparent background, text #0a0a0a, radius 18px, padding 2px 8px. The lightest-weight tag — used when the label is informational rather than categorical.

### Sidebar Surface
**Role:** Left navigation panel

Background #fafafa, full-height, contained width. Sits one tonal step off the canvas (#f5f5f5) so the navigation reads as a distinct layer without introducing a divider line.

### Breadcrumb Trail
**Role:** Hierarchical path indicator

Inline text with chevron separators, font 14px weight 400, color #737373 for separators and #0a0a0a for the current segment. No background, no borders — purely typographic hierarchy.

### Stat Block
**Role:** Large numeric metric display

Label in 12–14px uppercase #737373, value in 30–48px weight 600 #0a0a0a with tight tracking. Progress bar or comparison text in 14px #737373. The block relies on typographic scale alone — no card chrome — to establish the metric.

### Search Trigger
**Role:** Command palette / search input

Background #f5f5f5, text #737373, radius 18px, padding 8px 10px, with a keyboard shortcut indicator (e.g., ⌘K) right-aligned. Functions as both a button and an input affordance.

### Destructive Action
**Role:** Delete, remove, revoke — error-adjacent interactions

Text or icon in #e7000b against the monochromatic palette. The red is the only chromatic hue in the system and appears exclusively in destructive or error contexts — it never decorates.

## Do's and Don'ts

### Do
- Use #0a0a0a on #ffffff for filled buttons — the dark inversion is the only primary action treatment.
- Maintain 18px radius on all buttons, inputs, and badges for perfect pill geometry; use 24px radius only on cards.
- Set display headlines at 48px/600 with -0.0500em tracking — Geist's geometric weight at this size with aggressive tightening produces the engineered headline voice.
- Reserve #e7000b exclusively for destructive states; never use it for decoration, branding, or non-error emphasis.
- Stack card shadows as 1px hairline + 1px + 2px offset — the combined effect is a barely-perceptible elevation that reads as 'card' without drama.
- Use #f5f5f5 for secondary surfaces and inputs; use #fafafa for sidebar and subtle card variants — the three-tone surface stack (canvas → soft → paper) creates layering without borders.

### Don't
- Do not introduce chromatic brand colors beyond #e7000b — the monochromatic palette is the system.
- Do not use border-radius values other than 18px (interactive) or 24px (containers); avoid square corners on any element.
- Do not skip the 1px hairline border on cards — the shadow alone does not define the card edge in this system.
- Do not set body text below 14px or above #737373 lightness — the type scale is deliberately compact.
- Do not apply gradients, colored shadows, or accent fills — every surface is a solid tone.
- Do not use letter-spacing wider than 0.05em or tighter than -0.05em; tracking outside this range breaks the typographic system.
- Do not mix filled and outline buttons of the same size in a single row without visual rhythm — alternate ghost or secondary variants.

## Surfaces

| Level | Name | Value | Purpose |
|-------|------|-------|---------|
| 0 | Canvas | `#f5f5f5` | Page background, broadest layer |
| 1 | Sidebar | `#fafafa` | Navigation surface, one step lighter than canvas |
| 2 | Card | `#ffffff` | Primary content container, brightest surface |
| 3 | Input Fill | `#f5f5f5` | Resting input field, matches canvas tone for subtle differentiation |

## Elevation

- **Card:** `0 0 0 1px rgba(23,23,23,0.05), 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px -1px rgba(0,0,0,0.1)`
- **Button (filled):** `none — relies on tonal contrast, not shadow`
- **Input (focus):** `1px solid #e5e5e5 ring, no offset shadow`

## Imagery

Minimal imagery — the system is almost entirely UI. No hero photography, no illustrations, no decorative graphics. Product showcases are rendered as component mockups (cards, inputs, buttons) in a grid, serving as both documentation and visual content. Icons are thin-stroke geometric marks (likely Lucide-derived) at 1.5–2px stroke weight in #0a0a0a or #737373, used sparingly as functional cues. The visual language IS the UI components themselves — the page functions as a living style guide where every visible element is a design token made visible.

## Agent Prompt Guide

**Quick Color Reference**
- Canvas/background: #f5f5f5
- Card/surface: #ffffff
- Primary text: #0a0a0a
- Muted text: #737373
- Border: #e5e5e5
- primary action: #171717 (filled action)
- Destructive: #e7000b

**Example Component Prompts**
1. Create a dashboard stat card: white (#ffffff) background, 24px radius, 1px solid #e5e5e5 border, shadow 0 0 0 1px rgba(23,23,23,0.05) + 0 1px 3px rgba(0,0,0,0.1) + 0 1px 2px -1px rgba(0,0,0,0.1), 20px padding. Label in 12px uppercase #737373, value in 36px Geist weight 600 #0a0a0a with -0.025em tracking.

2. Create a filled dark button: background #0a0a0a, text #fafafa, no border, 18px radius, padding 0px 12px, font 14px Geist weight 500. Height 36px. No shadow — tonal contrast only.

3. Create a ghost secondary button: background #f5f5f5, text #0a0a0a, no border, 18px radius, padding 0px 12px, font 14px weight 500. Same dimensions as the filled button for visual parity.

4. Create an input field: background #f5f5f5, text #0a0a0a, placeholder #737373, no border at rest, 18px radius, padding 8px 10px, font 14px weight 400. On focus: 1px solid #e5e5e5 ring with no offset.

5. Create a badge tag: background #171717, text #fafafa, 18px radius (full pill), padding 2px 8px, font 12px Geist weight 500.

## Design Philosophy

shadcn/ui is built on three principles visible in every token: (1) achromatic by default — color is absence, not expression; (2) radius defines hierarchy — 18px for interactive elements, 24px for containers, never anything in between; (3) elevation is whisper-quiet — the card shadow is barely perceptible, relying on 1px hairlines and tonal contrast rather than dramatic drop shadows. The system is designed to be copied, modified, and owned — every value is explicit, every token is simple, and nothing is locked behind abstraction.

## Similar Brands

- **Vercel** — Same monochromatic palette, same Geist/geometric sans pairing, same pill-shaped buttons with tight letter-spacing on display text
- **Linear** — Identical approach to monochromatic UI with single accent for destructive states, tight typographic tracking, and hairline-bordered cards
- **Radix UI** — Same developer-tool visual language — neutral surfaces, geometric type, and component-first documentation layout
- **Tailwind UI** — Matching restrained palette, identical border-radius scale (large radii on containers), and code-adjacent minimal chrome
- **Cal.com** — Same compact density, same pill-badge system, and the same achromatic-first approach with red reserved for errors

## Quick Start

### CSS Custom Properties

```css
:root {
  /* Colors */
  --color-canvas: #f5f5f5;
  --color-paper: #ffffff;
  --color-surface-alt: #fafafa;
  --color-ink: #0a0a0a;
  --color-ink-soft: #171717;
  --color-mid-gray: #737373;
  --color-hairline: #e5e5e5;
  --color-ember: #e7000b;

  /* Typography — Font Families */
  --font-geist: 'Geist', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;

  /* Typography — Scale */
  --text-caption: 12px;
  --leading-caption: 1.33;
  --tracking-caption: 0.6px;
  --text-body: 14px;
  --leading-body: 1.43;
  --text-body-lg: 16px;
  --leading-body-lg: 1.5;
  --text-subheading: 18px;
  --leading-subheading: 1.56;
  --text-heading-sm: 24px;
  --leading-heading-sm: 1.33;
  --tracking-heading-sm: -0.6px;
  --text-heading: 30px;
  --leading-heading: 1.2;
  --tracking-heading: -0.75px;
  --text-heading-lg: 36px;
  --leading-heading-lg: 1.11;
  --tracking-heading-lg: -0.9px;
  --text-display: 48px;
  --leading-display: 1.1;
  --tracking-display: -2.4px;

  /* Typography — Weights */
  --font-weight-regular: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;

  /* Spacing */
  --spacing-unit: 4px;
  --spacing-4: 4px;
  --spacing-8: 8px;
  --spacing-12: 12px;
  --spacing-16: 16px;
  --spacing-20: 20px;
  --spacing-24: 24px;
  --spacing-48: 48px;

  /* Layout */
  --page-max-width: 1280px;
  --section-gap: 48-80px;
  --card-padding: 28px;
  --card-padding-compact: 20px;
  --card-padding-input: 20px;
  --card-gap: 24px;
  --element-gap: 8px;

  /* Border Radius */
  --radius-md: 6px;
  --radius-lg: 10px;
  --radius-xl: 14px;
  --radius-2xl: 18px;
  --radius-3xl: 24px;

  /* Named Radii */
  --radius-cards: 24px;
  --radius-small: 6px;
  --radius-badges: 18px;
  --radius-inputs: 18px;
  --radius-nested: 10px;
  --radius-buttons: 18px;

  /* Shadows */
  --shadow-subtle: oklab(0.145 -0.00000143796 0.00000340492 / 0.05) 0px 0px 0px 1px, rgba(0, 0, 0, 0.1) 0px 1px 3px 0px, rgba(0, 0, 0, 0.1) 0px 1px 2px -1px;
  --shadow-subtle-2: lab(2.75381 0 0) 0px 0px 0px 0px;

  /* Surfaces */
  --surface-canvas: #f5f5f5;
  --surface-sidebar: #fafafa;
  --surface-card: #ffffff;
  --surface-input-fill: #f5f5f5;
}
```

### Tailwind v4

```css
@theme {
  /* Colors */
  --color-canvas: #f5f5f5;
  --color-paper: #ffffff;
  --color-surface-alt: #fafafa;
  --color-ink: #0a0a0a;
  --color-ink-soft: #171717;
  --color-mid-gray: #737373;
  --color-hairline: #e5e5e5;
  --color-ember: #e7000b;

  /* Typography */
  --font-geist: 'Geist', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;

  /* Typography — Scale */
  --text-caption: 12px;
  --leading-caption: 1.33;
  --tracking-caption: 0.6px;
  --text-body: 14px;
  --leading-body: 1.43;
  --text-body-lg: 16px;
  --leading-body-lg: 1.5;
  --text-subheading: 18px;
  --leading-subheading: 1.56;
  --text-heading-sm: 24px;
  --leading-heading-sm: 1.33;
  --tracking-heading-sm: -0.6px;
  --text-heading: 30px;
  --leading-heading: 1.2;
  --tracking-heading: -0.75px;
  --text-heading-lg: 36px;
  --leading-heading-lg: 1.11;
  --tracking-heading-lg: -0.9px;
  --text-display: 48px;
  --leading-display: 1.1;
  --tracking-display: -2.4px;

  /* Spacing */
  --spacing-4: 4px;
  --spacing-8: 8px;
  --spacing-12: 12px;
  --spacing-16: 16px;
  --spacing-20: 20px;
  --spacing-24: 24px;
  --spacing-48: 48px;

  /* Border Radius */
  --radius-md: 6px;
  --radius-lg: 10px;
  --radius-xl: 14px;
  --radius-2xl: 18px;
  --radius-3xl: 24px;

  /* Shadows */
  --shadow-subtle: oklab(0.145 -0.00000143796 0.00000340492 / 0.05) 0px 0px 0px 1px, rgba(0, 0, 0, 0.1) 0px 1px 3px 0px, rgba(0, 0, 0, 0.1) 0px 1px 2px -1px;
  --shadow-subtle-2: lab(2.75381 0 0) 0px 0px 0px 0px;
}
```
