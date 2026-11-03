# Ui — Style Reference
> clinical blueprint on frosted paper

> 2026-10-09 用户更新：全前端状态展示统一使用语义色，优先于本文默认单色约定。失败、已取消、已停止为红色；进行中为蓝色；已完成、检查通过为绿色；待审核/待处理为琥珀色；未开始及未知为灰色。保留状态文字与现有图标，不仅靠颜色区分。共享配色见 `apps/web/src/status.css`，状态映射见 `apps/web/src/status.ts`。


## 以推进任务节点为目标的交互

2026-10-31 用户补充，长期要求。

**一切交互都应帮助用户推进到下一个有效任务节点。** 对话、按钮、澄清、状态提示和错误恢复共同服务于这一目标。衡量交互的价值，要看它是否完成当前节点、消除下一步的关键障碍，或让用户能做出直接影响下一步的决定。回复变长、工具调用增多或显示“完成”，本身不代表任务推进。

任务节点是有实际结果和进入条件的工作环节，例如明确数据范围、形成方案修订、选定比较协议、准备试运行或审核结果；不把每条消息、每次工具调用机械地当作新节点。推进也包括补齐必要信息、修改方向、等待条件满足或按用户意愿停止，不以强行开始执行或跳过研究门禁为目标。

### 先判断下一步，再选择交互形式

- **方向清楚且条件已满足：直接推进。** 结合当前会话、相关成果与既有授权继承未变参数；可逆的合理默认简短说明并允许修改。用户已明确要求的操作，不再添加一个重复确认按钮或要求重写完整指令。
- **存在影响下一步的关键分岔：聚焦澄清。** 只询问会改变下一节点的信息，优先一次解决一个关键决定。能先完成的独立工作继续推进；不为问一个选择题先做全项目审计，也不一次索取后续所有阶段的参数。
- **条件未满足：给出可落实的补齐入口。** 说明当前阻碍和最近可达的一步，例如补充采集上限、设置试运行范围或完成适配。尚不能执行训练时，入口应指向这些准备工作，不把“开始训练”呈现为已经可用。
- **节点完成或操作失败：衔接下一步。** 简要呈现实际结果，并在确有后续动作时给出相关入口；失败时保留已有进展，提供针对失败原因的恢复路径。已完成、用户暂缓或没有合理后续动作时，不强行追加问题或按钮。

### 在明确分岔处提供适时引导

当可选方向已经明确且数量有限时，在相关回复或任务卡片附近提供按钮、单选项或轻量输入，帮助用户用一次选择完成澄清。通常展示 2–3 个与当前决定直接相关的选项；较多选项按决策层次渐进展开，不将整条研究流程变成常驻表单或固定向导。

- 选项文案直接表达动作与范围，例如“改为留出法”“保留交叉验证”“仅检查准备情况”“设置试运行范围”。避免“确认”“继续”“方案 A”等脱离上下文后无法判断后果的文案；必要差异用一句短说明表达。
- 主操作对应当前最明确、可执行的下一步。并列且未选定的科学方案使用同等强调；有依据的推荐可以标明理由，但推荐、默认高亮或预选不等于用户已经同意。
- 保留自由输入，允许用户补充条件、提出其他方向、修改先前选择或暂缓；按钮不是唯一合法的表达方式。点击选项和输入等价的自然语言，应进入同一任务决策与执行流程。
- 仅在需要决策时出现，解决后转为已选择/已处理的历史记录，不让旧选项持续抢占注意力。遵循现有单一主操作、状态语义色、圆角留白、窄屏布局及键盘/读屏规范；关键后果不能只藏在 tooltip 中。

### 让选择真正连接任务状态

按钮选择应绑定当前会话、具体提议、相关方案版本和操作范围，并记录为可追溯的用户决定。收到选择后，系统应更新相应状态并进入已具备条件的下一节点，不仅发送一句“收到”，再要求用户重复确认。对唯一明确提议的简短文字同意也按同样语义处理。

方案或执行状态变化后，旧按钮应失效或重新核对其适用范围；防止双击、刷新和重复发送造成重复执行。执行结果未知时先核对回执，不能用“再试一次”盲目重放。按钮及可执行状态应来自有明确动作语义的任务信息，不依赖从模型长回复中猜测动作或把任意文本直接拼成执行命令。

点击“生成方案”只覆盖方案生成；点击明确范围的执行提议可表达对应授权，仍须满足实际输入、资源和研究门禁。不得通过模糊按钮扩大数据采集、计算预算或改变已冻结测试边界；同范围已经给出的授权也不应因换成按钮交互而重复索取。

### 设计示例与验收

| 当前情境 | 合适的交互 | 推进结果 |
|---|---|---|
| 用户说“留一部分验证就行”，现有参数足够 | 沿用其余参数直接生成可修改的新方案，简述默认 | 进入方案审阅节点，无重复选择 |
| 上文给了两个未选方向，用户说“按你说的来” | 简短询问，并展示“改为留出法 / 保留交叉验证” | 明确协议后生成对应修订 |
| 用户说“先跑一下”，检查与训练范围不明确 | 展示“仅检查准备情况 / 设置试运行范围”，保留文字补充 | 进入准备检查或范围确定节点，不把模糊表达当完整训练授权 |
| 用户选择已明确范围的方案生成提议 | 接收选择并生成、检查、登记新版本 | 交付结果并衔接实际存在的后续节点 |

验收须同时观察对话、界面和实际任务行为：用户能否看懂下一步及其后果；一个有效选择是否真正解除障碍并推进；是否重复澄清已有信息；自由输入是否与按钮一致；旧选项、重复点击和失败恢复是否正确。结合节点到达情况、无效澄清轮次、无助于决策的工具调用及等待时间判断质量，不以按钮数量、回复长度或回合 completed 状态代替任务成功。

本节确立通用设计要求与后续实现验收口径，不代表上述引导控件已经实现或通过模型行为验证。

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

2026-11-02 用户确认预览：对话输入框底部的模型、思考、模式、权限、显卡入口统一使用 18px 线性图标 + 14px 简短标签，透明背景，悬停或键盘聚焦时显示浅色圆角底与清晰焦点。具体当前值通过悬停/键盘提示及可访问描述呈现，点击后在原菜单或设置弹窗中查看和修改；简短触发器省略常驻数值及箭头。仅对话底部使用这一形式，弹窗内表单下拉保留当前选项与箭头。展开菜单、选项圆角及安全留白仍遵循上文规范，选中项保留勾选标记。窄屏自动换行，并为发送/停止按钮保留独立位置，避免设置入口挤成单列或与主操作重叠。

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


## 持久目标的交互

正式研究对话以目标为单位持续推进。输入框设置内保留“持续/单步”；紧邻输入框显示紧凑目标卡片，突出状态、当前进展和可执行操作，目标全文、验收条件与下一步可展开。系统自动接续明确标注来源，不能显示为用户发言。

方向明确且范围覆盖时直接进入下一节点；仅对影响行动的缺口提供澄清选项，并保留自由输入。暂停、调整和取消均须有可见状态，暂停后普通聊天不隐式恢复；调整保存后由用户继续。取消保留成果与预算记录，外部作业停止另有入口。完成状态应表述为 Agent 已报告完成，并明确证据核验和科学审核的边界。旧历史不得因升级自动开跑；真实能力未接通时显示实际阻塞。实现见 [目标推进](docs/p5/GOAL_CONTROL.md)。


2026-11-02 用户补充：持续任务进度面板依附于对话输入框上方，两者各自保留完整圆角框，中间留 12px 间距，不共用边线（按用户随后修订）。默认折叠，仅保留状态、回合数及右侧上拉箭头；展开时详情向上展开，箭头反向用于收起。折叠是展示控制，不能改变任务执行状态或清除编辑草稿；详情可独立滚动，状态行和输入入口保持可达。


## 上下文阻塞恢复交互

阻塞入口应说明实际原因并直接对应解除条件；不能只显示上一节点的成功摘要或提供会再次失败的普通继续按钮。上下文不足时展开压缩/同项目换窗操作，主操作在窄屏首屏可见，次要调整入口后置。压缩调用模型的后果、已用额度不变和未知结果先核对均应可见。恢复确认后接续原目标，暂停和取消保持优先；额度不足时说明其独立限制，不把换窗包装成新增预算。

## 额度设置交互

项目共享额度与当前目标回合上限统一放在对话输入框下方的“额度”设置窗口，和权限、显卡同级；目标卡片遇到额度不足时直接指向此窗口。上限编辑明确单位、作用范围和已用量，填写总上限而非追加量；不要求用户构造精确对话指令才能解除平台额度阻塞。

运行中允许修改后续回合额度，当前回合按启动时限额执行。保存保留消耗与审计，暂停/额度耗尽目标不自动恢复；明确展示下一步继续操作，其他阻塞保留对应入口。并发修改冲突时重新读取，不能静默覆盖。正文区域滚动，窗口标题、关闭和保存操作保持可达，窄屏输入按单列排列。


## 方案选择后的自主准备（2026-11-02）

用户提供数据和目标、选择基线方案后，Agent 在已有范围与预算内完成适配、依赖准备、内部检查和冻结，不为每个机械步骤要求确认。关键选择应直接接回原目标；只在科学取舍、数据/资源边界变化、缺失授权或无法自行解决的条件上询问。准备就绪且授权不足时提出一次具体启动清单，已有同范围“就绪后运行”授权不重复索取。冻结和合成检查是内部机制，不作为固定用户审批节点。

区分平台能力、工具权限、输入和资源阻塞，明确补齐责任。已知训练后端缺失时不提供会重复失败的普通继续入口，不让用户修改配置字段充当执行授权。旧权限、历史失败和消耗不因升级改变；上述目标体验不表示训练后端已接通。


## 权限模式（2026-11-03 用户确认）

自动批准为四项工具全部允许；逐次确认为四项询问；自定义按逐项允许、询问或禁止执行。修改单项自动切换自定义，选择预设统一更新四项，保存后才生效，不增加第二个全部放行按钮。旧混合模式以保留原行为的自定义展示，不因升级放宽权限。工具许可与研究范围、预算、训练授权和科学审核分别控制。

2026-11-03 用户进一步确认：四项工具选项仅在自定义模式显示；自动批准与逐次确认只保留模式选择，不展示可编辑的逐项控件。


## 独立训练预算节点（2026-11-03）

项目/目标的 Agent 额度与训练预算分开设置、计量和展示。基线选择后由 Agent 自主适配、检查和准备；正式启动前在“训练”入口一次呈现具体矩阵、评估范围、资源与累计预算，由用户确认后直接启动后台执行。无准备好的实验时显示空状态，不预造可执行方案。不得为每次内部冻结/合成验收要求确认。

训练预算包括累计执行时长、累计 GPU 时长、单元最长时间和最多重试次数。失败、修复、恢复共用原实验预算；上限不能低于已用量。保存预算与恢复训练是明确的两个动作，停止/未知状态不因保存而重放。工具自动批准与训练授权分离；Agent 时间用完不停止已授权训练。对应阻塞直接提供“训练设置”，不能诱导用户反复点击“继续推进”。实现及验收边界见 docs/p5/TRAINING_EXECUTOR.md。


## 训练方案确认位置（2026-11-03）

用户确认：训练方案和独立训练预算并入输入框上方已有的可折叠进度栏，收起显示待确认/执行状态，展开直接审阅和操作；不再放在模型、权限等工具栏设置中，也不另开模态确认窗口。折叠保留未提交输入，正文在栏内滚动，输入框始终可见。操作仍绑定具体实验修订，启动必须明确展示资源与预算的授权范围。


## 工作台实验实时进度（2026-11-03）

用户要求：实验完成数以执行器回执为依据；实时矩阵与历史报告分开展示。当前单元进度、损失/验证曲线、日志、失败重试和独立预算可直接查看；控制操作回原对话授权栏。未上报数据明确显示未知，不推测进度；更新中断保留最后记录和时间。矩阵及日志局部滚动，参数按需展开，窄屏曲线纵向排列。保留来源、冻结身份及科学审核状态，不以实验完成替代研究审核。


## 项目昵称字标（2026-11-03）

项目空间的 PathoReason 作为项目昵称，使用独立衬线文字标识：Patho 加粗直体、Reason 常规斜体，保持连续可选文本和完整读屏内容。字号 30px，360px 及以下视口为 25px；紧凑字距、深墨色与下方「项目空间」标签形成层级。此字体例外仅用于昵称，其余界面沿用 Geist 字体栈；不引入外部字体请求。字标与折叠按钮保留安全间距，不改固定导航与项目栏宽度。
