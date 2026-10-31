# P4 领域 Schema 与历史兼容

2026-10-30。P4 已完成；不扩大 P2 的合成研究执行范围，也不进入 P5 正式切换。服务器继续使用 OpenCode + DeepSeek，本机继续使用 Codex。

本阶段新增版本化领域投影、统一来源引用、上下文和交接来源契约。旧 TaskSpec、ExperimentConfig、实验状态、冻结流程及成果文件继续作为原始依据，按原字节保存。新视图完整保留 `source_payload` 和逐文件 SHA256；结构化字段只用于解释和展示，`execution_authority=false`，不能据此获得执行或科学批准权限。

## 权威关系

- 存在 TaskSpec 时，任务类型、目标、标签、选择指标、优化方向、聚合口径和目标变换来自 TaskSpec。ExperimentConfig 的兼容字段若冲突，在 `issues` 中指出，状态为 `conflict`；不静默覆盖原字段。
- 没有 TaskSpec 的旧配置保留旧字段，指标标为 unresolved，不从 `primary_metric` 猜测验证/测试口径。JSON Schema 来自固定旧源码，版本和源码 SHA 见 `contracts/legacy/source.json`。它用于结构检查及本次权威关系核对，不替代原执行端的完整语义验证器。
- 计算设置与协议放在 `compute`；旧 Codex 调用时限放在 `invocation_settings`；研究预算保留名称、来源、作用范围与单位。GPU 秒、worker 墙钟秒、总墙钟秒、调用次数分别表达，不互相换算。
- 新模型回合独立冻结 `RuntimeConfiguration`，包括模型描述、运行环境和有界调用策略。服务器禁止 Codex 推理；预算账本、重试规则和 P2 方案确认门禁保持原实现。
- Workflow v1 的定义与 workspace 展示节点分离，节点顺序、阶段、门禁提示保留。TaskProjectBlueprint v2 另行投影，不能把 v1 增加字段后冒称 v2。原始完整对象仍保存在 source_payload 中。

## 接口与界面

`/api/v2/research-projects/{pid}/domain` 提供领域视图；`legacy-history` 提供带 legacy_import 标记的旧审阅；`artifacts/{aid}` 提供成果身份、原始来源及交接链；`/api/v2/turns/{tid}/context` 提供版本化上下文。既有 v1 项目、对话、成果和业务接口继续可读。

工作台来源流程由领域投影提供；成果预览增加可展开的来源详情，旧项目增加可展开的历史审阅。快照中报告保留原始字节，旧 artifact 引用按当前项目内的来源链解析；跨项目查找和歧义匹配拒绝。固定导航、折叠项目空间和 design.md 的间距、层级规则保留。

新 handoff/2 保存逐件成果 provenance；导入仍接受 handoff/1，P3 已导入成果从原 handoffs 映射只读推导来源。文件校验、项目归属和重复 ID 检查先完成，再在一个 SQLite 事务中创建项目、对话、成果、来源及交接记录。失败清理新目录，不留下部分业务记录；不搬运原生会话，也不重放历史操作。2 MB 成果总量上限保持。

## 历史兼容与边界

上下文来源采用 legacy/business/artifact 联合类型。历史转换只读取原 ContextSnapshot 和当时冻结的 runtime_config.business_context，不用今天的研究状态补造过去的决定。原摘要和原配置 digest 不重算；投影另外携带 origin_digest 和自身 digest。

真实旧实验的两条审阅记录已只读展示。旧 repair importer 按 owner + target 精确筛选，只产生 `LegacyHistoryEntry`，`native_session_id=null`、`executable=false`。预期旧 repair SQLite 不存在，因此修复记录适配采用隔离夹具验证；没有宣称完成不存在的真实排障历史导入。Workflow v2 同样是契约夹具验证，当前真实绑定案例仍为 v1。

不启动新的模型调用、压缩或训练。数据证据和迁移回执位于两环境各自 `acceptance/p4-20261030`，详见 [验收](VALIDATION.md)、[逐项变更](SCHEMA_CHANGES.md)、[迁移与回退](MIGRATION.md)。
