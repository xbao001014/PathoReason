# 第五阶段稿件生成与作者审核

2026-11-04，目标版本 `0.6.30-p5-manuscript-review`。对应用户要求：研究 auto-research 的论文生成路径，尤其人工审核门禁，并体现到第五阶段稿件部分。仅改公共系统、工具契约、Skill 适配和界面；不代写 GIST 研究材料，不新增模型调用、训练、额度或作者批准。

## 旧路径调查

只读来源仓库 `/home/bxn/projects/auto-research`，调查时提交 `55a19217f9c7ad89f1fc390d9dbb64bc44c30890`。主要依据：

- `packages/core/experiment_agent/manuscript_workflow.py`：`PHASES`、`AUTHOR_GATES`、`review_manuscript_gate`、`reopen_manuscript_phase`、批准哈希与完整性阻塞校验。
- 同目录 `manuscript_pipeline_runner.py`：阶段运行和回执；`manuscript_author_context.py`：原始作者事实跨阶段保留；`manuscript_context.py`：工作阶段上下文。
- `apps/web/src/components/ReviewAdjudication.tsx`、`manuscriptReviewGuidance.ts`：审核材料、逐条裁定和提交语义。
- `docs/MANUSCRIPT_AUTHOR_HANDOFF.md`、`docs/PATHOLOGY_MIL_TASK_EXTENSION_P3_MANUSCRIPT_IMPLEMENTATION.md`、`docs/MANUSCRIPT_STYLE_POLICY.md` 和旧返工测试。

旧顺序是 intake → planning → literature → draft → integrity → review → revision → final_integrity → final_approval → freeze → delivery_approval。其中 8 个作者节点为 intake_author_confirmation、blueprint_author_confirmation、narrative_author_confirmation、integrity_blocker_disposition、review_adjudication、revision_author_confirmation、final_author_confirmation、delivery_author_confirmation。文献完整性、最终完整性与实际冻结/排版不是额外作者批准。

值得保留的机制：批准绑定所审材料哈希；最终核验针对确切修订稿，不能沿用旧报告；高风险完整性问题不能靠批准跳过；审稿意见逐条接受/调整/拒绝/暂缓并写理由；事实保留原始作者文字与来源；返工撤销受影响节点及下游批准，保留旧版本。生成 PDF、review_delivery_ready 与投稿就绪是不同事实。

## 五个作者节点，仍属于研究第五阶段

| 新节点 | 合并/衔接的旧节点 | 提交的审核材料 | 用户动作 |
|---|---|---|---|
| 事实与写作方案 blueprint | intake + planning | 事实清单、测试使用记录/冲突、写作方案、论点边界、图表计划 | 确认方向；必要时补充事实或退回 |
| 初稿与图件 draft | literature 自动核验后接 narrative | 初稿、引用核验、作者待办、图件清单和实际图件 | 看原稿与图件后确认 |
| 审稿意见裁定 review | integrity 自动检查 + review_adjudication | 绑定初稿版本的完整性报告、模型辅助审稿及逐项问题 | 逐条裁定并说明理由；完整性阻塞退回初稿 |
| 修订稿与科学内容冻结 scientific | revision + final_integrity + final_approval | 修订稿、文献库、逐条回应、图件及清单、绑定修订稿 SHA 的新核验报告 | 明确确认本版内容，允许冻结排版 |
| 最终交付 delivery | freeze/排版/页面 QA 后接 delivery_approval | PDF、源包、页面 QA、交付及未决事项清单，引用已批准科学材料包摘要 | 明确确认交付；不含投稿授权 |

没有新增研究阶段，也不要求每个节点换会话。用户在标题行中右侧“5/5 · 稿件部分”展开查看当前节点、材料、意见与历史。待审核自动展开。主按钮按节点表明后续动作；退回、补充事实和返工入口保留。后两节点确认框默认不勾选。

普通“继续/同意/确认”等短句打开待审材料，不自动批准。自由输入的详细反馈以作者原文保存，通过公共 clarify 动作让原目标继续准备该节点。真正批准依赖当前版本的显式审核动作，工具自动批准不替代它。未决当前事实或完整性阻塞会禁用批准，但允许补充或返工。模型辅助审稿不标为独立外部同行评审。

早期事实与写作方案合并、修订与最终内容确认合并，避免逐步冻结确认的重复负担。作者、伦理、资助等投稿必需但不影响当前决策的缺口保留在待办，允许内部预览；不能猜填，也不能据此称为投稿就绪。负结果和探索性研究允许继续稿件链路。

## 公共契约与持久化

- `checkpoint.manuscript_review` 只提出审核请求，要求 `outcome=needs_input`、当前 stage/conversation、workflow revision、真实已登记成果和对应 checkpoint evidence。成功回合结算才呈现；失败/中断不生成可批准节点。
- `GET/POST /api/v2/conversations/{cid}/manuscript-review` 提供当前视图和用户决定。POST 使用 CAS revision 与幂等 request_key；动作是 approve/revise/clarify/reopen。不在模型 MCP 工具中暴露 approve。沿用现有本机应用访问边界；不声称在同一 OS 用户下构成进程级安全隔离。
- 三张追加账本 `manuscript_workflows`、`manuscript_review_events`、`manuscript_review_commands` 保存当前状态、历史和命令回执。原始材料快照在数据根 `manuscript_reviews/PROJECT/REVIEW/ARTIFACT`，不写研究工作区的批准文件。
- 校验项目来源、工作区原文件、发布副本和审阅快照。每次批准验证当前材料与全部有效上游批准；后续源文件修改必须返工重新登记，不以旧副本掩盖改稿。快照阅读独立于原文件，仍能查看当时批准的版本。
- draft/scientific 要求 JSON figure_manifest：`{"artifact_ids":[...],"no_figures_reason":"仅空列表时必需"}`，列出的图件必须以 role=figure 同时登记；不能用图件文字描述冒充实际图件。文件必须非空；PDF 检查头部仅是格式检查，不代表实际页面 QA。
- review 核验报告绑定已批准初稿 SHA；scientific 绑定确切修订稿 SHA；delivery 绑定已批准 scientific 材料包摘要。技术完整性报告是 Agent 提供的报告，平台验证引用/版本一致性，不替 Agent 做科学正确性判断。
- 审查前完整性失败时允许仅交 integrity 报告和阻塞问题，不捏造评审；退回修改自动回到 draft 并撤销 draft 之后的有效批准。一般返工由用户选择受影响节点和原因，下游批准失效而原件/决定保留。
- 成功决定沿用原 goal id、权限、已用额度和项目训练预算；正常目标接续走原调度器。额度耗尽仍停止；暂停不自动恢复；已完成/取消的旧目标不因审核动作复活。用户在对话发起后续稿件准备即可建立下一目标。
- 第五阶段 `stage_handoff` 要求五节点全过，交接结算再校验一次。`author_content_approved`、`delivery_approved` 与 `independent_scientific_approval`、`submission_authorized` 分离，后两者本机制不授予。
- 原作者事实/逐条决定进入后续提示和持久化恢复；普通批准不能清除旧事实。三项迁入 Skill 增加 PathoReason hosted binding，保留科学规则，替换旧门禁存储及重复确认。历史迁移清单不改写。
- 公共 publish_artifact 支持只读发布 `.tex/.bib` 文本和 `.zip` 源包；归档不会被执行或自动解压。源包通过附件下载；HTML 类内容不作为可执行页面呈现。

## 验证与发布记录

全部原始证据：`/data/bxn/PathoReason/acceptance/manuscript-gates-20261104`。发布状态和最终测试数字以该目录 `release.json`、`full-tests.log`、浏览器和原生核验结果为准。

工程夹具覆盖：五节点真实状态迁移、同目标接续/额度保持、重复提交与过期 CAS、外会话拒绝、普通 checkpoint/resume 不能越过门禁、失败回合、完整性阻塞与事实缺口、逐条裁定、精确稿件 SHA、实际图件引用、原稿变更/存档损坏、返工撤销与历史快照、暂停/额度耗尽和重启恢复、HTTP 契约/来源限制、源包发布。

最初工程测试发现：只核对发布副本会遗漏工作区原稿改写，已修复联合校验并保留失败。另有隔离 worktree 缺本机配置、假运行时结束后仍报告 busy、浏览器断言返回 DOM 导致序列化失败及等待错误提示词等验收配置问题；修正夹具，没有放宽公共校验。失败日志不覆盖。

浏览器使用模拟审核数据，所有非 GET 写请求留在浏览器 mock；检查桌面1440、手机390/320宽度、标题栏位置、滚动边界、重复点击、版本过期、模糊继续无批准、自由反馈、后两节点明确确认、逐条理由、事实/阻塞禁用。上线后只读检查真实项目，不能拿合成图件/PDF做真实论文验收。

原生验收只证明新的 checkpoint schema 可发现、相关 Skill 正文与目录加载一致。真实 OpenCode + DeepSeek 是否按顺序准备合格稿件、准确解释意见并产生有效排版，仍待用户启动下一研究目标验证。没有新增独立科学批准或投稿授权。

当前已有 GIST H1 草稿保留原样，旧 completed 目标也保留；不回填作者批准。新视图从第一个待准备节点开始。建议用户发起：“沿用现有 H1 草稿和实验结果，准备事实与写作方案审核；保留非独立、非盲法限制，不新增实验。”随后由 Agent 提交实际材料，用户在稿件栏按版本审核。

全量工程回归：519 通过、3 跳过（246.48 秒）；最终小修后再跑目标/阶段/稿件定向回归。前端构建通过；最终发布回执和在线只读浏览器记录另存验收目录。

## 并行主线兼容

发布前发现主线已上线 `0.6.29-p5-project-lifecycle`（5d7a87c），本功能合并该主线后使用 `0.6.30-p5-manuscript-review`。保留新项目归档/清理界面与 API；增加审核存档的项目独占资产归属，用户明确删除项目并清理资产时才清理对应存档，保留资产选项继续生效。项目归档继承只读，不能通过稿件批准接口绕过；恢复项目也不恢复暂停目标。所有这类操作只在隔离合成项目测试，真实项目不归档、不删除。

稿件审核合并验收：保留项目生命周期主线，版本为 0.6.30；完整合并版本 539 项通过、3 跳过，65 项相关回归及三宽度浏览器审核交互通过。工程、原生、模型和科学验证继续分层记录，发布回执见 acceptance/manuscript-gates-20261104。

发布核对补充：研究 Agent 已在本次开发期间另行交付完整 GIST 阴性结果/证据汇总初稿，历史稿件阶段已 completed。这属于旧流程成果，不能算新门禁验收。保留旧交接和目标，标题显示“待进入作者审核”，新作者工作流仍为 blueprint/preparing、零批准。首次发布因预期旧阶段 active 的断言中止在静态入口发布前；后端已健康，调整兼容显示后只补发前端，不重启原生或训练。下一任务应复用现有完整初稿、图件、文献与作者待办，不只复用早期 H1 草稿。
