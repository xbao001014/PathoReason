# 首轮场景与字段流

首轮真实验收目标：用户在“结果解读与研究汇报”Skill 下，要求解释已有 CESC 结果、定位论文审阅稿并产生有来源引用的摘要。P0 只验证读取与契约，P1 才进行真实对话。

## 已核对的来源

1. /data/bxn/auto-research/acceptance/cesc_shared_context_replication_20261028_analysis/CONCLUSIONS.json。
2. /data/bxn/auto-research/acceptance/cesc_manuscript_delivery_20261029/53a69e70219c4a1ca00a43e6fda8752a/_manuscript_pipeline/pipeline_index.json。
3. 同交付目录 DELIVERABLES/CESC_manuscript.pdf。
4. 代表性旧实验 /data/bxn/auto-research/experiments/11e2e1f03fe84ca38bf34b6315c8e3da 的 state/config/blueprint/workflow_template 及冻结实例。该实验用来核对旧身份与流程映射，不将它伪称为上述独立后续研究/论文的唯一执行来源。

三份成果逐文件哈希、字节数和新 artifact ID 在 contracts/examples/cesc-reading.json。旧实验观察清单在数据盘 legacy-experiment-observation.json。只存引用，不复制 PDF/实验目录。

## 从输入到展示

| 环节 | 字段/来源 | 处理与持久化 | 展示或消费者 |
|---|---|---|---|
| 用户选项目 | ResearchProject.id/objective/resources | 应用保存新 prj ID；绑定原 adapter/resource_id/revision | 左栏项目；不改旧 ID |
| 选择 Skill | SkillDefinition.id/version/digest、required_inputs | 服务端解析目录可用性；SkillInvocation 固定版本 | 一层 Skills；未适配时说明原因 |
| 用户输入 | MessagePart(role=user,kind=text)、Turn.request_key | P1 先持久化 user message/queued turn，键去重后再派发 | 对话历史与状态 |
| 上下文取数 | ContextSnapshot.project_revision/source_refs/artifact_ids | 读取精确成果清单并核对哈希，摘要含来源，不遍历全数据盘 | 模型上下文与引用列表 |
| 旧实验读取 | store.py:230 get；state/config/blueprint/template | 旧接口仍用原验证链；P0 新侧只读 raw JSON 与文件 manifest | 旧阶段值 completed 仅表示该实例状态 |
| 旧 API 投影 | experiments.py:614 get_experiment → _record_to_dict、gate_policy.view、workflow_status.project | P1/P2 facade 保留不同状态维度 | 工作台动态阶段、审核与执行状态 |
| 调用引擎 | RuntimeBinding.native_session_id、Turn.model/config_digest | P1 服务器 OpenCode 创建/恢复指定 session；P3 本机 Codex 绑定 thread；回合配置固定 | 选择模型仅影响后续回合 |
| 接收回复 | RuntimeEvent(seq,source_event_key,payload)、MessagePart.id/ordinal | P1 先落事件再推 SSE；稳定 part ID 合并 delta | 流式回答、工具摘要、断线补读 |
| 新摘要产物 | ArtifactIndex.storage_root=pathoreason_artifacts | 新文件独立输出，索引来源；绝不覆盖 CESC 原件 | 预览/下载/引用回对话 |
| 切换工作台 | project_id、artifact ID、领域状态投影 | UI 保留会话 ID 与草稿；不重发已有请求 | 成果页与对话随时切换 |

## 事实与状态必须保留的差异

- CONCLUSIONS.execution.completed_cells=60：该后续研究矩阵完成 60 个单元；不能用论文跨轮 120 单元代替。
- CONCLUSIONS.performance.*.mean_cell_rmse：五折三种子的验证 RMSE 均值；单位取原任务目标变换/TaskSpec，未知时不标成百分比或百分点。
- frozen_decisions 中实例对照 status=accepted，但 goal_achieved_dev=false，scientific_status=not_assessed；这三个字段分别展示，不归并成“研究成功”。
- registered_comparisons 使用 patient-pooled RMSE 与条件配对区间，与 mean_cell_rmse 不是同一汇总口径。
- pipeline_index.status=review_delivery_ready、submission_ready=false、author_approved_exact_artifacts=false；预览稿可用不表示已投稿或科学批准。
- 旧演示 src/showcase/assets.ts:4–16 使用嵌入 base64 或 files/name，src/showcase/scenario.ts 是静态叙事。P1 改由 artifact ID 查询，不从这些演示文案反推真实研究状态。

## 新契约约定

- schema_version 固定 pathoreason/1；未知版本和字段拒绝。新语义使用新版本/适配，不给旧冻结文件补字段后写回。
- ID 为不带路径的稳定字符串；旧 resource_id 由 adapter 解释，允许保留原相对证据路径。日期为带时区 ISO8601，服务端生成统一 UTC。
- project.revision 为正整数修订；LegacyResourceRef.revision 为 SHA256，revision_kind 明确单文件字节或观察 manifest。两者不和旧 template revision/instance_sha256 混用。
- digest 为规范 JSON（UTF-8、键排序、紧凑分隔、无 NaN）的 SHA256；Skill/Context 排除自身 digest 后计算。哈希仅表示身份和完整性，不表示来源已获科学批准。
- size_bytes 为字节；*_tokens 为 token；null 表示未知，不填 0 来显示空上下文。窗口占用和累计用量使用不同 usage_scope。
- 终态回合必须有 finished_at；正在执行/恢复未知的回合没有终止时间。同一会话最多一个活动或待核对回合。
- RuntimeEvent 与 DomainEvent 使用独立 producer/scope 和序列；JSON Schema 检查结构，Pydantic/服务事务检查跨对象引用、摘要、唯一性与所有权。
- ArtifactIndex 的 bytes_verified 仅说明文件哈希核对。本轮 3 份成果 evidence_role 分别为 development/manuscript_review；不将训练目标提升为独立测试证据。

P0 离线样例固定 fixture_kind=contract_only、native_session_id=null、turn=queued，事件列表为空。样例用户消息是验收输入，不是已发生的真实会话，不能作为运行历史导入。
