# P4 Schema 逐项变更

所有新类型在 `src/pathoreason/schema_v2.py`，纯适配函数在 `schema_adapters.py`，读取/迁移在 `domain.py`。旧 `contracts/v1`、`runtime-v2`、api-p1/p2/p3 快照保持原字节；新增 api-p4、contracts/p4，前端 generated.ts 由同一 OpenAPI 生成。未挂公开接口的 RuntimeConfiguration 等另导出独立 JSON Schema。

| 对象 | 旧 → 新版本 | 生产者 → 消费者 | 读写位置 | 适配、迁移与回退 |
|---|---|---|---|---|
| 任务语义、配置、预算 | TaskSpec 1/2 + ExperimentConfig → research/1 只读投影 | 原执行端/P2 计划 → Domain/API | 读取旧 experiment/config.json 或 PathoReason research/{pid}/plans/{sha}.json；不写源文件 | experiment_definition / synthetic_definition；保留全量原对象、文件 SHA，回退只移除读投影 |
| 流程 | Blueprint 1 或 TaskProjectBlueprint 2 → workflow-view/1 | 冻结实例 → 工作台阶段 | 读取 blueprint/state/template/冻结实例；内存投影 | workflow / task_project_definition；不改旧版本、不重算旧冻结哈希，原 UI 可继续读 |
| 来源引用 | LegacyResourceRef / WorkflowRef → kind 区分的联合类型 | 历史上下文、业务快照、成果 → 新上下文/API/MCP | 新 ContextSnapshot 内嵌；历史记录保留 | reference；保留原 adapter、revision_kind、项目/资源 ID；不伪装类型 |
| 上下文 | pathoreason/1 → pathoreason.context/2 | submit / 历史适配 → 回合、MCP、API | 新回合写 context_snapshots；旧行不改；显式迁移仅写 p4_context_projections + p4_projection_batches | snapshot / new_snapshot；批次撤销只删除旁表；旧 digest 为 origin_digest |
| 模型调用配置 | 无版本 JSON → runtime-config/1 | submit → 调度、恢复、审计 | 新配置写 runtime_configs，digest 写 Turn；旧配置按原字典读取 | RuntimeConfiguration 校验；原有键保留，新增描述与调用策略；不回填旧配置或重算旧 Turn |
| 成果来源 | ArtifactIndex pathoreason/1、BusinessArtifact pathoreason/2 → artifact/3 包装 | 原成果 + handoff 记录 → API/预览/MCP | artifacts 旧行不改；新导入来源写 p4_provenance | Domain.artifact/resolve；P3 从 handoffs 只读推导，旧成果接口继续可用 |
| 交接包 | handoff/1 → handoff/2 | export → import | 外部 JSON，成功导入写新项目/成果、p4_provenance、handoffs | v1/v2 双读，新写 v2；无原生会话迁移；有新 v2 导入后不可仅删除 provenance，需保留 P4 读适配 |
| 历史记录 | state.review_messages / scoped jobs SQLite → legacy-history/1 | 冻结旧记录 → 只读 UI/API | 原始存储只读；投影在内存，不插入 conversations/turns | Domain.history / repair_history；旧记录 ID/摘要、origin=legacy_import；回退移除展示，无历史写回 |

`source_files` 是原文件字节 SHA；ResearchDefinition / WorkflowProjection 的 digest 是新视图规范 JSON 摘要。它们与旧 `blueprint_digest`、模板 instance_sha256、计划 digest 各自独立。相同字节表示完整性，不意味着来源签名、科学审核或执行授权。

`source_payload` 包含完整配置、计划、状态和未知字段。规范化视图只整理当前需要解释的字段；未识别字段不被丢弃或加入执行默认值。任务语义冲突拒绝隐式修正，后续若要更改必须经过原业务的显式修订链。
