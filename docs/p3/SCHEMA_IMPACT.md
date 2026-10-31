# P3 最小契约变更与 P4 输入

| 对象 | 变更/版本 | 读写者 | 兼容方式 |
|---|---|---|---|
| ModelDescriptor、Conversation、Turn、RuntimeEvent、ContextSnapshot | 保留 P0 pathoreason/1 | 共用 API、两运行时 | 历史记录原样读取；model descriptor 随 Turn 冻结 |
| RuntimeBinding | 服务器继续 pathoreason/1；本机新增 pathoreason.runtime/2 + local_codex_login | Codex 适配器、bindings 表 | 不给旧 server_codex_login 偷换含义；独立 Schema 在 contracts/runtime-v2 |
| ContextView / 手动压缩操作 | P3 API 投影，context_operations 新表 | 应用与上下文面板 | 旧 conversation 无压缩记录时为空；未知结果只核对 |
| codex_calls / codex_usage / codex_compactions | 本机适配器内部表 | Codex 适配器 | stable client ID / native turn 映射、原生用量与压缩证据；不复用 OpenCode session |
| handoffs / HandoffBundle | pathoreason.handoff/1 | 导出/导入 API、取数 MCP | SHA 校验后新建项目/会话；保留来源映射和历史分界，重复导入幂等 |
| Usage / RuntimeStatus | 新增可选累计用量/费用、环境/业务可用性字段 | API 与生成的 TS | 原字段不删；未知保持 null，服务器原配置默认值保持 |
| RuntimeConfig | JSON 新增 runtime/environment/context policy；Codex descriptor/config digest | submit 与恢复 | 既有 config digest/记录不重算；P4 再做完整版本化 |

公开类型由 `scripts/export_web_types.py` 生成 `contracts/api-p3.openapi.json`、`apps/web/src/generated.ts`。P1/P2 OpenAPI 快照和 P0 v1 Schema 未覆盖。

P4 待处理：ContextSnapshot 的 source/decision/run refs 仍为旧 LegacyResourceRef，不能伪装成 P2 WorkflowRef；当前新业务约束/决定由冻结 runtime_config.business_context 与核验成果账本保留。P4 应设计版本化统一引用联合类型，并明确计划、研究事实、运行时上下文与交接来源的生产者/消费者。

跨环境成果保留原始字节和 source_ref，同时分配当前项目 ID/成果 ID；后续需正式化 origin/provenance 类型。P3 没有改写 TaskSpec、ExperimentConfig、冻结流程或旧研究数据库。
