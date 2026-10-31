# P2 实施记录

2026-10-30。P2 以独立 CPU 合成 MIL 任务完成对话驱动研究闭环。服务器仍使用 OpenCode 1.18.33 + deepseek-v4-pro，未执行服务器 Codex 推理。

## 已交付

- 通过本地 stdio MCP 的 `pathoreason_research` 工具接入任务、生成方案、反馈修订、执行、核对、恢复和停止信号。仅讨论回合不能变更业务；旧项目绑定的真实来源始终只读。
- 每次业务变更绑定项目 target、expected_revision、幂等键和当前活动回合。应用私有桥接令牌与限回合能力分别校验；模型不能跨项目、使用过期回合或自行批准同一回合生成的方案。
- 原 `RepairController / RepairJournal / RepairRegistry` 管理计划、批准、执行回执、幂等和核对；原 `LoopController / LoopStore` 管理完整矩阵、租约、预算、失败重试和评估。未启动第二个旧实验调度器。
- `business_job.py` 明确选择原 Landlock + seccomp CPU 隔离后端，复用原输入投影、受保护训练器与独立输出评估器；服务器没有 bubblewrap，未采用无隔离回退。
- 后台研究进程独立于模型回合。生成或修订方案后，后续用户回合才能执行；停止生成与停止研究任务分别处理。
- 工作台只展示业务事实、阶段、完整矩阵、预算、修订与成果；操作通过对话完成。固定导航、可折叠项目列保持不变。
- 每个运行结果索引 JSON 账本、CSV 指标、SVG 矩阵图与 Markdown 报告。按项目、run、结果摘要保存不可变版本；可从模型引用打开、下载，再引用到对话。重新核对或恢复不覆盖旧证据。
- 领域事件以项目内单调 seq、action_id、turn_id 关联原回合；RuntimeEvent 仍独立。回合完成、工具成功、执行状态、开发目标和科学审核分别展示。

## 实际开放范围

数据接入、MIL 基线和恢复三个 Skill 仅开放合成验证；结果解读沿用 P1。机制研究、论文和图件排版 Skill 继续标记未接入。P2 不是任意真实数据训练的开放授权，也未重启或修改旧 CESC 实验。

每个独立项目当前只有一个合成任务、一个冻结运行。固定 4 个开发个体、2 候选、2 折、种子 17/29、1 epoch，基线学习率 0.0002；候选学习率可在 0.00001–0.001 修订。预算 600 秒、每假设最多一次修复、无 GPU、无额外模型规划调用；保留原完整矩阵与独立科学审核边界。已停止任务不自动恢复；未明派发只核对，需明确恢复操作。

真实数据接入、任意训练配置、多运行研究项目和完整论文/机制工作流仍须后续单独接入及验收，不能把合成范围验收当作这些能力已开放。

## 源码、数据与契约

- 桥接：`src/pathoreason/business.py`、`business_worker.py`、`business_job.py`、`mcp_bridge.py`。
- 前端：`apps/web/src/BusinessPanel.tsx`、App 与共享状态/样式。
- 原代码固定清单：`config/p2-legacy-source.json`，582 个 Python 源文件 SHA256；发现变化拒绝执行。
- 独立存储配置：忽略版本管理的 `config/p2-compute.local.json`。保留旧存储校验，所有新输出位于 `/data/bxn/PathoReason`。
- 研究任务/回执/冻结方案/原 LoopStore：`research/<project_id>/`；行动库：`research/journal/repairs.sqlite3`。
- 私有桥接令牌：`runtime/control/business-token`，权限 600；不进入模型上下文。限回合 grant 会过期失效，公开输出会脱敏。
- P0 的 16 个 v1 领域 Schema 未更改。新增 `WorkflowRef`（pathoreason.business/1）及 `BusinessArtifact`（pathoreason/2），明确当前系统运行来源，避免伪装成旧 LegacyResourceRef。
- API 的成果列表接受旧/新两类对象；类型生成输出 `contracts/api-p2.openapi.json` 和前端 generated.ts。P1 DTO 另存 api-p1.openapi.json；全面 Schema 重构仍属于 P4。
- `business_turns` 以增量表保存回合执行模式和业务快照；原表及历史事件未迁移。P2 开始前已通过 SQLite backup 保存一致性备份。

## 界面规范

用户补充已写入根 design.md，并同步 AGENTS：去掉 slogan、重复标签和常驻教学说明，以结构与操作表达用途；必要解释使用可键盘聚焦的 info 提示。保留输入标签、可访问名称、状态文字与必要操作后果。

## 工程参考

OpenCode 的本地 MCP、权限及工具注册参照官方文档，并通过已安装版本实际核验：[MCP](https://opencode.ai/docs/mcp-servers/)、[权限与工具](https://opencode.ai/docs/tools/)。最终权限还需在原生 session 层允许工具；不能仅修改全局配置。
