# 原 Schema 梳理与改造边界

日期：2026-10-30；对象为 bxn-server:/home/bxn/projects/auto-research 当前工作树。该文件是改造前盘点与建议，不是已经实施的新 Schema。

## 盘点范围

静态扫描 packages/core/experiment_agent、apps/api/app、apps/assistant_worker，并读取正在运行服务的 OpenAPI；前端扫描排除本轮 agent-demo 与既有 showcase 演示类型。没有执行数据库写入或迁移，也没有读取个人会话内容。

抽取结果：94 个相关 Python 文件，274 个有注解字段或模型/枚举的类，55 处 SQL 建表声明，79 个前端导出类型，133 条 OpenAPI 路径、125 个 OpenAPI schema。这些是扫描计数，不意味着 274 个独立业务 Schema，也不代表 55 张唯一运行数据库表。动态字典、代码验证和嵌套内联 JSON Schema 还需沿各改动路径人工核对。

机器清单及字段注解/源码行号/validator 名称在 /data/bxn/auto-research/acceptance/agent-console-planning-20261030/schema-inventory.json。OpenAPI 快照在同目录 openapi.json；运行时协议另存 codex-schema/，与应用业务 Schema 分开。

## 现状映射

| 层次 | 当前对象与源码 | 权威内容/存储 | 改造处理建议 |
|---|---|---|---|
| 实验入口 | schema.py:237 ExperimentConfig，store.py:33 ExperimentRecord | 目标、数据、配置、预算、runtime、stage、审核、成果路径；实验目录 config.json/state.json/blueprint.json 等 | 暂保留为旧运行配置；新会话通过版本化适配层访问 |
| 科研任务语义 | task_contracts.py:164 TaskSpec，TargetSpec/MetricSpec/SelectionSpec/PredictionRecord/MetricRecord | 分类/回归/生存、缺失策略、单位、评价分区、任务 digest；v1/v2 | 优先作为任务语义中心；旧字段映射需明确冲突处理 |
| 工作流定义 | blueprints/__init__.py ProjectBlueprint/WorkflowNode/GateSpec，state_machine.py Stage | schema v1；转换/门禁/节点展示；legacy_mil executor | 后续把执行定义与展示布局分层；首版仍用冻结定义驱动状态 |
| 场景模板 | workflow_templates/__init__.py TemplateManifest/TemplateBundle/TemplateReference | 五类 MIL 模板；四类 scope/profile；版本、哈希、冻结实例 | 作为 Skill 场景的工作流依赖，不等同于 Skill 本体 |
| 第二条项目路径 | projects/models.py TaskProjectBlueprint v2、SegmentationDataset；projects/service.py | operation/gate、ExecutionPlan、掩膜评估；workflow.sqlite3 中 project/decisions/project_origin | 新通用 ResearchProject 用独立命名；不要把 v1/v2 当同一对象升级链 |
| 能力与数据流 | capabilities/registry.py CapabilitySpec/PortSpec；capabilities/plan.py ExecutionPlan；compiler/bindings.py NodeBinding；capabilities/artifacts.py ArtifactContract | 能力 id/version、输入输出端口、节点绑定、内部 stage、相对文件契约 | 继续验证执行前后契约；从本体投影出目录与前端可读信息 |
| 能力就绪 | task_capabilities.py TaskCapability；method_engines/registry.py | contract_only/bounded_available/unsupported、evidence_scope、can_execute | 单独核验具体任务/模型/环境；不把 schema 支持当执行器支持 |
| 节点执行记录 | workflow/store.py NodeAttempt/NodeRunStore | execution_plans、node_attempts；attempt、状态、plan digest、artifact checks、authorization | 作为节点执行权威；会话只保存 run/attempt 引用 |
| 修复与反馈 | workbench/contracts.py/registry.py/controller.py/journal.py；routes/workbench.py Target/Bound/PlanRequest/ActionRequest | repairs/events；adapter/id、revision、plan_digest、角色与行动 | 复用目标绑定/冲突/幂等；runtime 工具确认与科研决定不混用 |
| 阶段任务/记忆 | task_supervisor/contracts.py StageTask/StageResult；store.py、journal.py、memory.py | current_context/snapshots/events、任务领取/租约；task_memory_sources/items/updates | 提供项目上下文取数来源，适配至新 ContextSnapshot；解释不等于授权 |
| 排障对话/执行 | apps/assistant_worker/workspace_jobs.py；workspace_events.py；API workspace_assistant.py | jobs/events/fault_sessions；目标与 owner 绑定；最近六条结果拼接；现有流只投影简短工具活动 | 可复用持久化经验，但新增通用 Conversation/Turn，不让新对话受 repair/diagnose 限制 |
| 摘要助手 | apps/assistant_worker/protocol.py DiagnoseRequest/Response；apps/api/app/assistant_history.py | turns；SafeContext；executable=false | 保留文本摘要用途，与具备工具的主 Agent 分开 |
| Agent 单次产物 | agent_runtime.py AgentRequest/ConfiguredAgentExecutor；agent_settings.py AgentSettings | prompt/output/schema、harness/provider/model、只读范围、最终回答验证、*.agent.json | 保留旧 runner；新增 StatefulRuntimeAdapter，避免破坏单次产物调用 |
| 研究循环 | performance_loop/contracts.py ResearchLoopContract/CandidateSpec/EvaluationBundle/AcceptanceDecision；store.py | 协议、候选、矩阵、原始基线、接受判定；loop/units/attempts/decisions/planner_calls 等 | 模型层与会话层引用，不重写已冻结协议 |
| 研究预算 | schema.py RunBudget；task_supervisor TaskBudget；performance_loop ResearchBudget；research_cycle/ledger.py CycleLedger | 阶段训练参数、阶段任务开销、研究预算、跨轮累计账本分别存储 | 命名和单位显式化；新增 usage/预算视图，不把不同总额直接相加 |
| 消融/封存确认 | performance_loop/mechanism_contracts.py MechanismStudy；confirmation_contracts.py ConfirmationInput/Approval | 配对、对照、来源、限定 evidence role、一次性确认协议 | 保留独立科研约束；聊天“好”不得脱离对应目标/修订被解释为通用批准 |
| 成果 | ArtifactContract、ExperimentRecord.artifacts、EvidenceRef、论文 pipeline/index | 相对路径、SHA256、data_scope、专用清单与原文件 | 新增可视化 ArtifactIndex，保存来源/run/revision/kind，原文件仍权威 |
| API 与前端 | apps/api/app/routes；apps/web/src/types.ts、outcomeTask.ts、performanceLoopApi.ts、workspace/* | FastAPI/OpenAPI、手写 TS、前端状态投影 | 为新稳定契约生成 TS，旧接口先通过 facade 兼容；减少重复定义 |

## 已确认的耦合与缺口

1. **新项目与旧实验不能一一硬绑。** 当前 ExperimentRecord 与 ProjectService 是不同入口。新左栏项目应是聚合研究容器，显式关联历史实验、稿件、数据接入和多个会话；旧 ID 原样保留。新项目 ID 使用独立命名空间，通过 LegacyResourceRef(adapter, id, revision) 引用旧对象。
2. **任务语义重复。** ExperimentConfig 中 task_kind/label_column/class_threshold/primary_metric 与 task_spec 同时存在。旧主评价字段不能被随手当作 checkpoint 选择指标；已有 TaskSpec 的 selection 明确只允许 val。需决定新建项目以谁为权威，并让冲突显式报错。
3. **预算与模型配置混层。** RunBudget 内有 codex_timeout_minutes，也包含折数/epochs/GPU 等训练参数；AgentSettings 又有 harness timeout。应分训练协议、计算预算、模型调用策略、原生窗口上限，而不是一个通用 budget 字典。
4. **显示与执行混层。** WorkflowNode 中 stages/gateStage/gateHint 与 ProjectBlueprint 转换相互验证。可以在后续分离 ViewProjection，但首版不能为了界面自由度绕过现有转换规则。演示里的十个 CESC 阶段不是系统全局常量；正式页面从冻结模板/实例映射，模板之间节点数量可不同。
5. **多个注册表语义不同。** CapabilityRegistry 管端口/版本，RepairRegistry 管恢复动作，TaskCapability 管支持组合，TemplateManifest 管场景配方，SKILL.md 管行为说明。需要产品级目录投影，不能直接合并为一个无类型 registry。
6. **状态词同名不同义。** node succeeded、StageResult.completed、job completed、workflow completed、AcceptanceDecision.accepted、goal_achieved_dev 和科学批准应分别保存。建议事件/展示包含 scope、status、reason，不用一个“成功”覆盖。
7. **当前对话不是原生连续会话。** fault_sessions 分组已有，但 runner 没有把 native thread/session ID 作为长期契约；历史通过限长文本拼接。新增绑定与上下文分层，不误称只是加一个 UI。
8. **来源契约粒度不齐。** artifacts 有纯路径列表，也有文件格式契约、哈希引用和论文专用清单。新 ArtifactIndex 负责索引和预览，不用“有路径”冒充已验证研究证据。
9. **类型与事件重复维护。** Python 模型、动态业务 JSON、OpenAPI 与 TS 手写定义不同步；workspace_events.py 当前有意不发布 agent_message/原始输出，因此新对话必须有自己的用户可见文本事件。原始推理不作为必备 UI 事件；显示回复、工具摘要和执行结果即可。
10. **单次自选模型缺少上下文元数据。** OpenCode 自定义 provider 目前仅写模型名，配合临时 XDG 存储不能作为持续会话配置；新 RuntimeBinding/ModelDescriptor 必须补 context/input/output、工具支持与可用性来源。

## 建议新增的最小契约（尚未实现）

| 对象 | 最小内容 | 关系/不变量 |
|---|---|---|
| ResearchProject | id、title、objective、resource_refs、created_at、revision | 聚合多个会话与 workflow；不覆盖旧 project/experiment 原记录 |
| SkillDefinition | id/version/digest、输入输出引用、模板/能力/说明文件引用、可用性 | 目录定义不可被聊天消息直接改写；SkillInvocation 固定版本 |
| Conversation | id、project_id、title、active_runtime_binding_id、selected_skill_refs | 一个会话可讨论多个项目内资源，目标行动必须显式绑定 |
| RuntimeBinding | runtime、version、native_session_id、storage_namespace、cwd_ref、model_policy | 绑定拥有者与项目；原生 ID 不能跨 runtime 复用 |
| Turn / MessagePart | turn_id、conversation_id、role、kind、text/ref、status、resolved_model | 流式部分有稳定 ID；一个回合固定调用配置，不随全局模型切换漂移 |
| ExecutionIntent / RunLink | request_id、target_ref、expected_revision、operation、arguments_ref、idempotency_key | 指向既有业务执行；再次发送相同请求不重复训练 |
| DomainEvent / RuntimeEvent | event_id、seq、scope、producer、correlation_id、payload_version、payload | 两类事件分开；workbench 依领域事件和状态快照更新，不依据模型措辞 |
| ContextSnapshot | project_revision、goal、constraint_refs、decision_refs、active_run_refs、artifact_refs、pending_items、digest | 压缩摘要可失真；快照必须能回到已绑定原证据 |
| ArtifactIndex | id、project_id、run_ref、stage_ref、kind、uri_ref、sha256、verification_scope | 预览/引用/下载共享身份；生成与科学验证状态分别保存 |
| ModelDescriptor | runtime/provider/model、context_limit、input_limit、output_limit、tool_support、usage_source | 未知限额显式 unknown；不据此显示虚假的精确上下文百分比 |

所有新公共契约使用独立 schema_version；前端从已定稿契约生成类型。示例接口只是规划：/api/skills、/api/research-projects、/api/conversations、/api/conversations/{id}/turns、/api/turns/{id}/interrupt、/api/events、/api/artifacts。现有 /api/projects 等保留，避免同名语义冲突。

## 实施顺序与迁移原则

先定会话与目录契约 → 用 facade 读取旧对象 → 接 Codex 真会话 → 业务工具/只读工作台 → OpenCode/压缩 → 有证据地修改领域契约。新增字段或默认值会改变 model_dump/digest，不能直接加载旧冻结对象后重写。

后续每项调整至少写明：旧对象、旧版本、所有生产者/消费者、读写路径、字段单位与状态含义、迁移/适配函数、旧数据行为、回退方式。涉及已有科研结果时，以只读映射或明确的新修订承接，原始来源与哈希继续保留。

对话历史迁移另列：旧排障会话只导入能确证的用户请求/已发布回复/执行记录，并标记 legacy_import；不能臆造原生 runtime session 或恢复完整上下文的保证。

## 下一轮需补的审计

- 按选定首轮场景追踪所有入口到持久化与前端的完整字段流；本轮为静态盘点，不是逐条历史数据一致性证明。
- 核对 blueprint/workflow_template 实际冻结版本与当前服务只读兼容，选取代表性旧实验作回归样本。
- 盘点动态 JSON Schema 与 dict payload 的关键消费者，决定生成类型的边界。
- 用显式测试账户完成原生持续会话、恢复与压缩验证，核验 native capability 与产品 Skill 的映射。

关联规划：AGENT_CONSOLE_REFACTOR_PLAN_20261030.md。
