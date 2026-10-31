# PathoReason 开发交接

## 通用开发规则（长期适用）

先读 [开发与能力验证规则](docs/DEVELOPMENT_PRINCIPLES.md)。开发目标是提升系统可复用的任务执行能力：从真实失败定位责任层，改进运行时、工具、Skill、上下文和恢复机制，再由目标引擎与基模验证。开发监控不代改研究 Agent 的项目脚本、数据处理结果、报告或成果来“完成”任务；用户另行明确要求的研究材料修复应独立标明人工来源，不能算模型验收成功。

工程测试、原生集成、模型行为和科学审核分层记录。保留失败、原始输出、预算和人工干预；调整步数等限制应有证据且保持有界。同范围既有授权可跨回合沿用。此规则适用于全部阶段、模型与项目，不限于本次 P5 调试；具体规范以上述文档为准。

## 用户已确认的范围

- 系统正式名称为 PathoReason；新项目根目录为 bxn-server:/home/bxn/projects/PathoReason。
- 2026-10-30 用户随后明确“开始进入 P0 实施”，已完成该阶段。用户随后授权继续 P1；已完成工程与真实 DeepSeek 验收。P2 已按用户后续要求完成独立合成 MIL 闭环；用户随后授权 P3，已完成双环境会话与上下文兼容；用户随后授权并完成 P4 领域 Schema 与历史兼容；P5 入口已交付，真实试验留给用户另开的窗口。
- 最新用户修订：服务器以 OpenCode + DeepSeek 开发验收；Codex 开发验收只在本机进行；服务器保留 Codex 登录接口，未登录不阻塞主线。该指令取代此前“服务器 Codex 优先”。
- 以计划 v0.8 和 docs/PLAN_REVISION_RUNTIME_20261030.md 为当前依据。P0 的路径与 auth_ref 尚需按环境适配，历史 Codex 样例不代表新主线验收。
- 后续用户明确要求开展某阶段时，以该请求和 EXECUTION_PLAN.md 为依据推进，不重复索取已经给出的授权。

## 界面设计规范（用户长期要求）

任何界面新增或样式修改前必须阅读根目录 [design.md](design.md)，以该文件为统一设计依据。保留固定导航、可折叠项目空间和主内容三列结构。正文至少 14px，元数据/说明标签至少 12px；不再使用过浅灰色降低阅读性。普通正文和辅助文字使用 tokens.css 的语义文字变量；卡片 24px、按钮/输入/徽标 18px 圆角。

状态采用 design.md 顶部更新优先规则：失败/取消/停止红色，进行中蓝色，完成/检查通过绿色，待审核/待处理琥珀色，未开始/未知灰色；保留文字与图标。统一通过 apps/web/src/status.ts 和 status.css 映射，不在各页面自行配色。基础色、字号、间距和圆角集中于 tokens.css。圆角卡片遵循 design.md 安全留白：主卡片内边距 28px／窄屏 24px，嵌套卡片 20px／16px，紧凑输入区域 20px；同级卡片间距 24px／16px。沿共用容器对齐，不以负 margin 抵消留白。新样式检查桌面/窄屏、折叠与正文对比度。

按 design.md 的文案与可访问性补充，优先删除冗余标签、常驻说明和 slogan，通过布局与按钮文案保持首次使用清晰度。补充信息优先使用可键盘访问的 info tooltip；保留表单标签、读屏名称和危险/不可逆操作的后果提示。

视觉显著性须服从信息逻辑层级与当前操作优先级，按 design.md 区分核心、支撑和辅助信息；用字号、字重、语义色与留白协调表达。保持同级一致、主次可辨，不通过降低可读性弱化次要内容。

当前界面层级实施与验证见 docs/p2/VISUAL_HIERARCHY.md；新增样式继续保持视觉主次、卡片安全留白和共用容器对齐。

## 工作入口

先阅读 EXECUTION_PLAN.md；原改造规划与 Schema 盘点快照在 docs/references/。
已确认的产品要求与仍待定稿的技术建议分别见计划，不能把建议当作已经实现或已经批准的迁移。

## 项目边界

- 原项目 /home/bxn/projects/auto-research 保留。修改、运行或复用其代码前，阅读该仓库当时的 AGENTS.md 和存储规范，核对活动任务。
- 不因名称变更自动迁移数据库、复制原始数据/特征/检查点、重启旧实验或修改冻结配置与证据。
- /home/bxn/projects/PathoReason 存源码与轻量文档。未来运行数据、环境、发布端口及计算配置在 P0 明确；不得擅自复用旧实验的可写目录。
- 不在 Skill 目录中把“存在说明文件”表述为“当前可执行”；能力、环境就绪和验收证据分开。
- 新会话层区分产品 project/conversation/turn 与引擎 thread/session；科研状态由业务服务和账本更新。
- 每个阶段完成后更新计划状态和验证记录；记录实际实现范围及剩余问题，不用静态协议检查替代真实引擎验收。

## P0 已实施基线

先读 docs/p0/IMPLEMENTATION.md 和 docs/p0/DEVELOPMENT.md。新代码在 src/pathoreason；contracts/v1 由代码生成；真实来源引用在 contracts/examples，明确为离线样例。P0 54 项测试、14 项兼容检查通过，证据在 /data/bxn/PathoReason/acceptance/p0-20261030。

数据配置为 config/pathoreason.local.json（忽略）；用 scripts/storage.py 检查/分配新输出，不写回旧数据根。Python .venv 独立，锁 requirements.lock；旧工具只读引用，版本在 config/runtime-lock.json。P1 已使用 8520（应用）和 8522（原生引擎），8521 仍保留；修改服务前核对所属进程。不要因 P0 完成而宣称真会话、数据库恢复或业务执行已通过。

## P1 当前交接

用户已提供凭据并修订导航，P1 已完成。先读 docs/p1/LIVE_VALIDATION.md、IMPLEMENTATION.md 与 DEVELOPMENT.md。最左侧固定窄图标导航（执行操作台/研究工作台/工具）独占一列，项目空间另占可折叠一列，折叠按钮在其右上角，详见 docs/p1/NAVIGATION_LAYOUT.md；工具按研究类别 → 流程展示，当前病理 MIL 7 个 Skill，仅结果解读可执行。新增类别使用 config/skill-navigation.json，不硬编码到前端。

71 项后端测试、浏览器检查和 6 个 DeepSeek 真回合通过（5 完成、1 停止）。证据在 acceptance/p1-live-20261030，旧无推理证据不覆盖。凭据文件权限已修正 600，原生引擎已加载，后续不要因旧记录重复要求配置。不要输出凭据，不发起未经请求的服务器 Codex 推理；本机 Codex 在 P3。

原生 /event 文本增量与 /message 最终快照分开处理；普通 user.summary 不是压缩。停止保留部分正文，未知派发结果只核对、不重发。全局验收预算 12 回合/1200 秒，P1 当时消耗 6 回合；P2 结束时总计 11 回合；P3 后服务器累计 12/12，见 P3 交接。禁止自动启动旧真实实验。

## P2 当前交接

P2 已完成独立 CPU 合成 MIL 范围验收。先读 docs/p2/IMPLEMENTATION.md、VALIDATION.md、DEVELOPMENT.md。3 个业务 Skill 仅标记“合成验证”，结果解读沿用 P1；其他能力不能提前宣称可执行。

当前真验收项目 prj_57554f8fde2048909209b6c0648aff66，4 个业务成功回合完成接入/方案、反馈修订、确认执行、成果引用；另保留 1 次原生 session 权限错误导致的业务失败回合。8/8 单元，4 份成果，累计 worker 墙钟时间 42.042 秒，科学审核/独立验证/投稿就绪未通过。恢复真验收保留失败预算，只重试一个单元；首次恢复竞态失败记录与修复重验均保留。

应用测试 84 通过，旧环境 adapter 测试 3 通过；最终证据在 /data/bxn/PathoReason/acceptance/p2-20261030。P2 结束时全局模型累计 11/12 回合，1200 秒额度未重置；P3 后为 12/12。合成执行预算每任务 600 秒、最多一次恢复；不自动扩展。P3 本机 Codex 随后已完成；P4 领域 Schema 与历史适配随后已完成。

新增业务数据在 research/；不要删除回执、started 标记或 LoopStore 强行重跑。原业务源码 582 文件 SHA 固定校验，不得因异常自动刷新固定清单。公开 API/界面不能绕过对话直接 dispatch。运行中的研究任务与模型回合分离；停止生成不会自动停止研究。

## P3 当前交接

P3 已完成，先读 docs/p3/IMPLEMENTATION.md、VALIDATION.md、DEVELOPMENT.md、SCHEMA_IMPACT.md。本机源码 /home/bbbxn/projects/PathoReason，应用 8530，独立数据 ~/.local/share/PathoReason；服务器应用 8520、原生 OpenCode 8522 不变。Codex 0.165.0 仅本机推理，已有本机登录以引用方式使用；不把服务器凭据/native ID 移到本机。

服务器模型累计 12/12 回合（P3 新增 1），禁止悄悄重置预算继续调用；本机独立 12 回合/1200 秒额度已用 6（5 完成、1 停止）。手动压缩另有界记录，服务器 1/2、本机 1/4；自动压缩验收共 4 次原生事件，测试用 12000 阈值已恢复默认。未知 token/费用不得写为 0。后续阶段若新增调用应明确并保存新预算，旧账本保留。

本机只开放结果解读与项目只读 MCP；P2 业务执行仍走服务器，不把本机卡片的存在当作能力已接通。原合成物理作业 34、旧真实任务保持不变。94 项应用测试与双环境浏览器检查通过；只读复核 scripts/verify_p3.py 不推理、不压缩、不启动任务。

压缩超时/断流为 recovery_required，先核对原生标识，不重发摘要。跨环境用有 SHA 校验的 handoff 包新建项目/会话，保留历史分界和原成果字节，不重放动作。公共契约最小增量：runtime/2 本机绑定、handoff/1；P0 v1 和 P1/P2 API 快照保留，全面科研引用/Schema 兼容随后在 P4 实施。

## P4 当前交接

P4 已完成，计划 v0.7；先读 docs/p4/IMPLEMENTATION.md、SCHEMA_CHANGES.md、VALIDATION.md、MIGRATION.md。新契约在 schema_v2.py，纯适配 schema_adapters.py，只读领域服务 domain.py；P0/P1/P2/P3 契约快照不覆盖，前端生成目标是 api-p4.openapi.json。新增 JSON Schema 来自 export_web_types.py。

TaskSpec 优先于 ExperimentConfig 的兼容字段；冲突只标记，不修正旧源。完整原字段/文件 SHA 留在 ResearchDefinition，execution_authority=false；计算设置、调用策略和不同预算单位分开。流程 v1/v2 分别投影，旧模板/冻结实例仍按原 manifest 校验。

新上下文写 context/2，新配置 runtime-config/1；旧上下文从当时冻结业务快照适配，不能用当前状态补造历史。显式 migrate_p4.py 写 p4_context_projections + batches，12/6 条已应用；原表不改。新 handoff/2，兼容 v1，p4_provenance 保存多跳来源；旧 artifact 引用按当前项目解析歧义拒绝。不得删除 provenance 来强行降级。

真实旧审阅两条只读映射，repair 数据库不存在，仅夹具验证；不得冒造原生会话。104 项回归、两环境源数据/事务回退和六布局浏览器通过，数据证据在各自 acceptance/p4-20261030。模型累计服务器 12/12、本机 6/12 不变，物理作业仍 34。P5 未开始。

## P5 当前交接（优先于前述阶段快照）

用户授权 P5，并明确本窗口只交付入口，下一窗口使用数据接口 + OpenCode + DeepSeek + Seedream 进行真实试验。入口已交付，完整 P5 仍待实际验收。先读 docs/p5/NEXT_WINDOW.md、OPERATOR.md、ENTRY_VALIDATION.md、RELEASE_RECOVERY.md。计划 v0.8，源码发布 0.6.0-p5-entry。服务器 8520 入口已更新；本机 8530 仍保留 P4 运行进程，不冒称本机 P5 已部署。

原仓库数据接口来自 data_api.png，非新造接口；Seedream 使用服务器旧稿件快照中的配置，安全迁入 /home/bxn/.config/pathoreason/image-generation.json（600）。不要打印或把凭据写入仓库/提示词。当前未进行真实数据拉取、付费生图或模型调用；服务器旧账本 12/12、本机 6/12、原合成 jobs 34 不变。

13 个原 Skill 的 2537 个原文件迁入 .agents/skills，原来源摘要 config/p5/skill-migration.json；现有 results-explanation 保留。两目录均注册于 OpenCode。20 项目录条目按研究类别/流程组织；“已迁移”仅指指令可加载，非真实任务验收或所有可选依赖已满足。Skill 适配和资源差异见 docs/p5/SKILL_MIGRATION.md。

正式项目通过 /api/v2/formal-studies 或项目“+”创建。每项目冻结独立回合/墙钟预算，旧预算不能重置。原生 bash/edit/webfetch 逐次确认；这是用户权限下的执行入口，不是 OS 沙箱。原研究执行器的隔离、矩阵、预算、作者/科学门禁不变。原生命令审批回执未知时保留 dispatching，核对原生状态，不重发。

新 workspace /data/bxn/PathoReason/projects/PROJECT_ID；新研究存储 /data/bxn/PathoReason/studies/PROJECT_ID。复用旧引擎时 PYTHONDONTWRITEBYTECODE=1 且 AUTORESEARCH_COMPUTE_CONFIG 指向新项目 compute.json。默认 real_training_authorized=false；实际训练前按具体协议和后续用户授权准备，不能复用旧可写目录。

scripts/study_io.py 提供 data/image/publish；来源回执、独占输出和 SHA 保留。正式成果用 formal/1 引用和 artifact schema pathoreason/3；包含此类成果的新上下文/交接用 context/3、handoff/3，旧上下文/交接/指纹不重写。新增契约快照 contracts/p5 与 api-p5.openapi.json；P4 快照保留。

排版工具独立安装于 .tools/manuscript，版本/下载摘要 config/p5/toolchain-lock.json。service.py 从 .tools/manuscript-path.json 加载 PATH；命令行手工运行也需加载对应路径。可选 WSI/PDF 工具依赖范围以 ENTRY_VALIDATION 为准。停止/重启仅限核对过身份的 PathoReason 服务，先检查活动回合和研究任务。不得把新发布回滚成旧数据库来抹掉新研究证据。

## 2026-10-30 会话权限设置（优先于 P5 入口的逐次确认限制）

用户明确要求并授权修改、部署 permission 设置。正式研究对话现在可选择逐次确认、自动批准、自定义 bash/edit/webfetch/external_directory 的 allow/ask/deny；范围仅当前对话的后续回合，执行中禁止保存。自动模式保留配置中的 deny。审批支持 once/always/reject，always 仅覆盖原生请求给出的匹配范围，既有 session 授权不会因切回逐次确认自动撤销。研究预算、执行器隔离和科学/作者门禁独立，不因工具模式切换而批准训练。

权限修订保存在 conversation_permission_settings，每回合 runtime_config 记录 permission_settings 和 permission_revision；旧记录不重写。OpenCode 1.18.33 PATCH session permission 实际追加规则，以末尾规则组核验并避免重复追加。旧 P5 契约快照保留，新增 contracts/api-p5-permissions.openapi.json 和 contracts/p5-permissions/。验证与发布详见 docs/p5/PERMISSIONS.md。

## Git 与工作目录维护（2026-10-31）

当前版本使用 Git 维护，正式版分支为 `PathoReason`；`main` 保留本次初始化基线。后续修改优先在该仓库内使用分支与提交记录，不再为每次样式或功能修改在 `/home/bxn/projects` 下创建同级项目副本。确需独立构建验证时使用专用临时目录，确认无独有修改且无进程引用后及时清理。凭据、本机配置、运行数据、依赖和构建产物继续排除在版本控制之外。正式分支命名不表示真实科研全流程已经验收通过。

## 2026-10-31 系统适配实施记录（通用规则见文首）

本 session 及后续同类验证以 OpenCode + 基模的适配为目标：判断/调整步数上限、抽象接口读取 Skill、改善工具与上下文。模型的数据处理错误应作为系统改进证据，不由开发助手代改研究脚本/输出或发布修正成果来替代模型验收。此前外部修正的研究文件保留来源，不能算模型自己完成。

正式 Agent steps 已从 16 提高到 64，旧普通 Agent 为 6；项目独立预算不变。新增原生 pathology-data-api Skill（skills/pathology-data-api），前端数据与任务定义入口可选。接口 2.0 使用该 Skill 的分页 helper，旧 study_io.py data 仍只支持历史 Limit 协议。正式提示词沿用同范围既有授权，权限设置和科研预算独立。发布 0.6.3-p5-data-skill；证据与行为验证局限见 docs/p5/OPENCODE_DATA_SKILL.md。本轮只验证工程和原生加载，未调用模型或更改研究项目文件。

## 2026-10-31 会话生命周期

服务器应用发布 `0.6.4-p5-conversations`，见 [会话归档与删除](docs/p5/CONVERSATIONS.md)。归档可恢复；显式删除清除在线聊天、会话上下文和 OpenCode 原生 session，并保留项目文件/成果、来源和预算。不得把共享项目目录当成会话独占记忆目录清空。清理失败/中断保留删除状态并显式核对；不可通过恢复旧数据库让已删除内容复活。本机 Codex 原生删除未支持，本次不部署 8530。

## 2026-10-31 执行过程摘要

服务器应用 `0.6.5-p5-process`，见 [回合执行过程摘要](docs/p5/PROCESS_SUMMARY.md)。每轮工具过程独立显示，开始输出和结束时自动折叠；展开区限高，连续同类成功调用合并，失败单列。摘要来自原生元数据与固定模板，不导出内部推理/原始参数输出，不改写模型回答；历史缺字段不补造。仅服务器部署，本机未更新。

## 2026-10-31 Benchmark 链路

服务器 `0.6.6-p5-benchmark`，见 [Benchmark 选型链路](docs/p5/BENCHMARK_CHAIN.md)。正式研究基线规划加载 benchmark-design，先研究问题/数据协议，再方法库与近期文献候选，再公平协议、完整矩阵和执行器适配缺口。不得以当前 runner 白名单代替科学选型。OpenCode 原生 Exa websearch 已启用，与 webfetch 共用网络访问设置，显式 deny 保留；禁止把患者明细发送到公开搜索。通用检查不构成科学/训练授权。真实验证由研究 Agent 自行生成新方案，开发者不改其输出。

本次以同一 DeepSeek Flash/high 正式项目完成 3 轮原生验证（22/12/11 次迭代），目标 Agent 自行登记 benchmark-plan-v4；8 模型拟议 144 fits，全部执行准备未验收。新增 PDF 有界提取 helper、论文/代码独立证据等级、各折人数检查；平台锁定 pypdf 6.21.4，未安装训练依赖。项目累计 7/40 回合、3674.083527/7200 秒，旧文件不改，训练标志 false。后续先做官方实现核验与 adapter，再按研究授权准备训练；不能把本次来源/结构验证写成训练或论文完成。
