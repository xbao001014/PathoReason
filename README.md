# PathoReason

PathoReason 是本系统的正式名称。

定位：以 Agent 对话驱动病理研究，以研究工作台追踪阶段并展示成果。

- 执行操作台：最左侧独立固定导航、第二列可折叠项目空间，右侧人与 Agent 的对话和执行历史。
- 研究工作台：阶段追踪、成果图表、预览与下载；与对话随时切换并保留上下文。
- 执行引擎：服务器优先 OpenCode + DeepSeek；Codex 开发验收在本机进行，服务器保留登录入口。
- 研究流程：先保持原流程和科研契约，由对话调用已有业务能力，后续按明确方案调整 Schema。

当前状态：**P0–P4 已完成。P2 已通过 OpenCode + DeepSeek 驱动独立 CPU 合成 MIL 任务的接入、方案修订、执行、恢复和成果闭环；旧真实项目保持只读。P3 已接通本机 Codex、压缩和快照交接；P4 已完成领域 Schema 与历史兼容；P5 服务器正式试验入口已交付，真实端到端试验待新窗口验收。**

当前访问：SSH 转发后的 http://127.0.0.1:8520/ 。服务已在 bxn-server 运行。本机 Codex 入口：http://127.0.0.1:8530/ 。

## 入口

- [开发与能力验证规则](docs/DEVELOPMENT_PRINCIPLES.md)：从真实失败提升系统能力，分层验收，不以人工代改研究结果替代模型验证。

- [P5 下一窗口交接](docs/p5/NEXT_WINDOW.md)、[正式试验操作说明](docs/p5/OPERATOR.md)、[入口验证](docs/p5/ENTRY_VALIDATION.md)、[Skill 迁移](docs/p5/SKILL_MIGRATION.md)、[发布与恢复](docs/p5/RELEASE_RECOVERY.md)。

- [P4 实施](docs/p4/IMPLEMENTATION.md)、[Schema 变更](docs/p4/SCHEMA_CHANGES.md)、[验收](docs/p4/VALIDATION.md)、[迁移与回退](docs/p4/MIGRATION.md)。
- [P3 实施](docs/p3/IMPLEMENTATION.md)、[验收](docs/p3/VALIDATION.md)、[开发与恢复](docs/p3/DEVELOPMENT.md)、[Schema 影响](docs/p3/SCHEMA_IMPACT.md)。

- [P2 实施记录](docs/p2/IMPLEMENTATION.md)、[P2 验收](docs/p2/VALIDATION.md)、[P2 开发入口](docs/p2/DEVELOPMENT.md)。

- [设计规范](design.md)：后续界面修改统一遵循；[样式与可读性优化](docs/p1/DESIGN_UNIFICATION.md)。

- [固定导航与项目空间折叠](docs/p1/NAVIGATION_LAYOUT.md)：对照原 demo 的三列布局。

- [P1 真会话与导航改版验收](docs/p1/LIVE_VALIDATION.md)。

- [P1 实施记录](docs/p1/IMPLEMENTATION.md)、[P1 启动与开发说明](docs/p1/DEVELOPMENT.md)。

- [运行环境与验收顺序修订](docs/PLAN_REVISION_RUNTIME_20261030.md)：服务器 OpenCode/DeepSeek、本机 Codex。

- [P0 实施交付](docs/p0/IMPLEMENTATION.md)：结果、证据和下一阶段条件。
- [架构与存储](docs/p0/ARCHITECTURE.md)、[源码复用清单](docs/p0/REUSE_MAP.md)。
- [开发与验证入口](docs/p0/DEVELOPMENT.md)、[Runtime/API 合同](docs/p0/RUNTIME_AND_API.md)。

- [执行计划](EXECUTION_PLAN.md)：阶段、交付物、验收和实施顺序。
- [原改造规划快照](docs/references/AGENT_CONSOLE_REFACTOR_PLAN_20261030.md)。
- [原 Schema 盘点快照](docs/references/SCHEMA_REVIEW_20261030.md)。
- [来源记录](docs/references/provenance.json)。

目录位于 bxn-server:/home/bxn/projects/PathoReason。
原项目 /home/bxn/projects/auto-research 当前仍是已有实现与研究记录的来源；P0 已建立独立契约代码与开发环境；P5 已选择性迁移原 Skill 和私有图像配置；未迁移旧实验数据，也未停用旧服务。
