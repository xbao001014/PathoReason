# P4 验收记录

2026-10-30，服务器与本机应用均已运行 P4（API 0.5.0）。本阶段新增模型调用 0、压缩 0、训练作业 0；服务器模型账本仍 12/12，本机仍 6/12，已有合成物理作业仍 34。

- 应用回归：原 94 项与新增 10 项通过，共 104 项；1 项环境条件跳过。P4 覆盖历史上下文转换、调用策略冻结、事务迁移故障回滚/幂等、v1/v2 多跳交接、来源/项目校验、文件及数据库故障清理、历史引用解析、旧排障隔离、流程版本/顺序、TaskSpec 权威冲突、公开 API。
- 两端 TypeScript 检查与 Vite 构建通过；公开类型与 7 个领域 JSON Schema 已生成。
- 服务器实际旧实验 `11e2e1f03fe84ca38bf34b6315c8e3da`：完整原配置、状态、流程、模板和冻结实例可读；TaskSpec 回归目标和 val RMSE/minimize 口径保持；节点顺序不变；两条原审阅标记 legacy，只读展示。
- P2 实际合成项目：plan/task 源字段完整保留；GPU 秒、总墙钟秒、worker 墙钟秒及 planner 调用分开；未修改原方案、研究状态或科学门禁。
- 本机 P3 导入的 4 份原成果可推导来源，旧 artifact ID 可在当前项目解析。报告不改写原始字节；新版多跳链用夹具验证。
- 两端全部 P4 前原表逐行一致，12/6 条上下文均可投影；所有成果 SHA/长度校验通过。原科研源码清单、实验 manifest 与冻结来源不变；旧服务 ready 且仍为同一 PID/instance，无活动实验/后台作业。
- 真实库的隔离副本：中途失败零投影残留，apply 幂等，rollback 后所有原表一致。生产侧只应用新增旁表投影。
- 浏览器六种组合：两环境 × 桌面展开、桌面折叠、390px 窄屏。检查历史审阅、成果来源、旧引用实际点击跳转、无横向溢出；无页面异常、无 POST、无模型调用。截图已人工查看。

证据：服务器 `/data/bxn/PathoReason/acceptance/p4-20261030/`，本机 `~/.local/share/PathoReason/acceptance/p4-20261030/`；分别含 before-p4.sqlite3、migration-receipt.json、p4-verification.json。浏览器结果与截图在 `/home/bbbxn/outputs/PathoReason/p4/`，同步到服务器本阶段验收目录的 browser/。

范围限制：旧 repair SQLite 未找到，repair importer 仅完成 owner/target 精确筛选和 legacy 标记的夹具验收；真实历史验证是旧实验两条审阅。Workflow v2 用契约夹具验收，未新建分割研究。TaskSpec 结构投影不替代旧执行端完整语义验证。成果完整性和来源链不等于科学审核或来源签名。P5 正式切换尚未开始。
