# 新旧源码复用清单

旧仓库 HEAD：55a19217f9c7ad89f1fc390d9dbb64bc44c30890，存在先前未提交变更。实际复用必须绑定当前文件 SHA256，不能只写 HEAD。P0 源码哈希与直接导入清单见数据盘验收目录 source-inventory.json；本轮没有复制旧应用源码。

| 旧模块 | 依赖与职责 | 新项目处理/阶段 | 允许修改边界 |
|---|---|---|---|
| apps/web/src/agent-demo | React；showcase scenario/assets；浏览器模拟状态 | P1 选择性迁移布局与交互组件，替换模拟消息、模型与阶段数据 | 仅新副本；原演示保持 |
| apps/web/src/showcase/ResearchResults.tsx | 静态 JSON 与资源 URL | P1/P2 复用图表呈现方式，改 artifact API 与项目事实 | 不把静态 CESC 十阶段或结果写为全局状态 |
| apps/web/src/types.ts 与 workspace | 手写类型、原 API 和排障交互 | 只参考业务字段；新类型从新 Schema 生成 | 不整体携入旧全局 store |
| apps/api/app/routes/experiments.py、projects.py | AppState、Store、workflow_status、gate_policy | P1 只读映射，P2 为明确操作建立服务 facade | 不整包启动第二个旧 orchestrator |
| packages/core/experiment_agent/store.py | ExperimentConfig、Blueprint、templates、storage、历史元数据 | 旧服务继续权威；新 LegacyResourceRef 保留原 ID/修订 | 新侧不调用 save/update 来归一化旧结果 |
| schema.py、task_contracts.py | Pydantic、字段验证、任务版本与选择分区 | P0 明确权威，P4 再评估拆分 | 不自动改旧配置及 digest |
| blueprints、state_machine、workflow_templates | 冻结流程、门禁、节点与 profile | 读取实例用于展示；P2 调用原执行路径 | 不把 UI 顺序改成执行顺序 |
| capabilities、compiler、task_capabilities | 能力端口、绑定、有限模型/任务支持 | 投影为 Skill 的依赖与就绪检查 | 不把 contract_only 标成可执行 |
| agent_runtime.py、agent_settings.py | 子进程、隔离、输出 Schema、原子发布 | 保留旧单次 runner；P1/P3 新建有状态 adapter | 不给旧调用强加 thread/session |
| workbench/{contracts,registry,controller,journal} | 目标绑定、revision、行动回执、修复幂等 | P2 通过业务工具桥复用 | 沿用授权与门禁，不直接运行任意聊天命令 |
| task_supervisor/{memory,store,journal} | 来源、约束解释、租约与审计 | ContextSnapshot 按需取来源；不整库迁移 | 记忆不是执行授权 |
| performance_loop、research_cycle、engines/auto_mil | Torch/科学计算、隔离、预算与冻结源码 | 保持原执行端；P2 用独立合成任务接桥 | 不安装到轻量会话进程，不动旧训练 |
| manuscript_pipeline、manuscript_assets、research_reporting | 科研来源、图件、排版工具链 | 先引用已有产物；后续再接生成场景 | 不因能预览就认定能生成或投稿 |
| .agents/skills | 13 个 Markdown 技能目录及各自依赖 | P1 建 7 类产品目录映射；按版本复制所需说明 | 逐项核对输入/工具，不直接批量启用 |
| storage_paths.py | 旧 compute.local.json 与 /data/bxn/auto-research | 原路径继续有效；新项目独立 storage.py | 不修改旧配置来指向新数据根 |

## 依赖与许可记录

- 旧仓库根目录未发现 LICENSE/COPYING/NOTICE 文件，不据此推断公共开源许可。本次为同一用户本机系统演进，未对外发布、未重新授权旧代码。实际迁移的每个文件记录来源路径、源哈希、修改摘要；后续公开分发时补齐来源与许可信息。
- 旧前端锁文件声明 React/ReactDOM/Vite/plugin-react/Vitest 为 MIT，TypeScript 为 Apache-2.0。react-markdown、remark-gfm 在该锁条目没有 license 字段，P1 引入时读取对应包的 LICENSE，不能填猜测值。
- P0 新环境只含契约/测试依赖，包版本及完整校验哈希见 requirements.lock，安装元数据许可记录见 acceptance/p0-20261030/dependencies.json。
- Codex、OpenCode、Node/npm/uv 暂引用服务器已安装工具，版本与解析路径记在 runtime-lock.json；未复制二进制。升级或旧目录调整需要重新校验协议，不能悄悄切换版本。
- 旧数据、特征、检查点、数据库、凭据、node_modules 和 .venv 不迁入新 Git；成果引用保持原路径与字节哈希。

## Schema 权威与后续调整清单

| 概念 | 当前权威 | 本次处理 | 后续边界 |
|---|---|---|---|
| 通用项目 | 新 ResearchProject | 聚合容器独立 ID | 不取代两条旧 project/experiment 路径 |
| 任务语义 | 旧 TaskSpec；兼容 ExperimentConfig | 引用原配置；冲突不得静默覆盖 | P4 给出字段级迁移 |
| 阶段和门禁 | 冻结 workflow/template + 状态与账本 | 新工作台只读投影 | 不能由聊天完成更新 |
| 科研预算 | 各原预算/累计账本 | 原单位、原任务范围保留 | 模型调用预算单列 |
| 上下文 | 新快照 + 原始来源 | 摘要仅供模型理解 | 原生压缩不修改业务事实 |
| 成果 | 原文件与内容哈希 | ArtifactIndex 增检索与访问身份 | 索引验证不等于科学验证 |
| 对话与 native session | 新应用与 runtime | 独立绑定，不导入虚构历史 | 旧排障文本若迁移标 legacy_import |

旧 Schema 全量静态盘点保留在 docs/references/SCHEMA_REVIEW_20261030.md；本轮是首个场景的细化，没有声称完成全部历史数据库审计。
