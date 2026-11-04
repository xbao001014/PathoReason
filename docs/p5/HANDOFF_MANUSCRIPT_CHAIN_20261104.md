# PathoReason 论文生成链路优化交接

交给新的开发窗口。当前用户希望把工作重点转向论文生成链路的优化，继续修复公共机制并由研究 Agent 自主验证。本文状态核对时间为 **2026-11-04 16:50 香港时间（08:50 UTC）**；开始工作时必须重新读取实时状态。

**当前主线：方案已确认，Agent 已自动推进并提交初稿与图件，等待用户审阅。最新界面把审核放在输入框上方的可折叠栏。下一步应从真实初稿和审核回执检查论文链路，不重新做实验，也不代用户批准稿件。**

## 工作原则与已确认方向

- 优化 OpenCode + DeepSeek 的公共执行能力、Skill/工具、目标接续、上下文、审核及反馈机制。开发助手不直接改研究 Agent 的稿件、研究脚本、数据处理结果、实验结论来替它完成任务。
- 保留原失败、原始回复、已用额度、冻结配置、材料版本和人工干预记录。不重置消耗，不绕过训练执行器、作者审核或科学门禁。Agent 预算与训练预算独立；具体增加额度由用户决定。
- 用户明确：本次是后续链路推进测试，无论有无良好正结果都继续。不存在“必须再训练出正结果才能写论文”的前置要求。
- 审核应简洁直接：说明本次要决定什么、确认后做什么；保留自由输入。常规准备/修复由 Agent 完成，不让用户对每个机械步骤反复冻结确认。
- 工程测试、原生集成、真实模型行为和科学审核分层报告。用户已确认范围内的公共修复可直接完成；不能把开发任务授权解释为作者批准或新训练授权。
- 原项目 `/home/bxn/projects/auto-research` 可用于研究论文生成路径。修改、运行其代码或复用其实现前，先读其 `AGENTS.md` 和存储规则；不写旧研究数据。

用户已经在作者审核中确认的原文（须继承，不再重复询问）：

> 按现有实验结果整理稿件，不预设方法优势，保留非独立、非盲法等限制。H2 仅作为可选未来方向，不承诺开展，不新增实验。请据此更新写作方案并继续准备初稿。

## 环境与版本

| 项目 | 当前值 |
|---|---|
| 服务器 | `ssh bxn-server` |
| 正式源码 | `/home/bxn/projects/PathoReason`，正式分支 `PathoReason` |
| 数据根 | `/data/bxn/PathoReason` |
| 应用 / OpenCode | 8520 / 8522；本机已有 `http://127.0.0.1:8520` 转发 |
| 后端版本 | `/health` 为 `0.6.32-p5-review-efficient` |
| 最新功能提交 | `5841e4d` 审核移到输入框上方；`81393f2` 答复与方案一次确认 |
| Python | `/home/bxn/projects/PathoReason/.venv/bin/python` |
| Node | `/home/bxn/.nvm/versions/node/v24.22.1/bin` 加入 PATH |
| 核对时进程 | app PID `2309722`；OpenCode PID `3293916`。使用前重新核对身份 |

交接写入前正式源码工作区干净。此交接另作纯文档提交，不要求发布或重启。不要把本机 `/home/bbbxn/projects/PathoReason` 的旧状态视为服务器正式版本。远端没有 `rg` 时用 `grep`，本机优先 `rg`。

先读服务器仓库 `AGENTS.md`、`docs/DEVELOPMENT_PRINCIPLES.md`、`EXECUTION_PLAN.md`；改界面先读 `design.md`。历史段落是当时快照，后文和用户最新要求优先。

## 当前项目与执行状态

| 对象 | 标识或状态 |
|---|---|
| 项目 | `prj_f07d49680a6b475d91f2451260ca2040`，GIST 风险分级相关实验 |
| 当前稿件对话 | `conv_f57f523200354fe2bd64ebd464039c6c` |
| 旧创新/混合对话 | `conv_e37b7a0fd1cc4cb28a3701e495905a27`，仅作为历史来源 |
| 当前目标 | `goal_cd9d99373f964d04aead1b43dd52e958`，revision 6 |
| 目标状态 | `waiting_input` / `manuscript_review_pending`；已用 2 / 8 回合 |
| 项目研究阶段 | `manuscript`，active，stage revision 3 |
| 作者工作流 | revision 3，`draft` / 初稿与图件，`awaiting_review`；仅 blueprint 已批准 |
| 最新研究回合 | `turn_71cf1afbf3894c2b93848d6c6727836e`，completed，系统自动接续 |
| 待审材料包 | `mrv_turn_71cf1afbf3894c2b93848d6c6727836e` |
| 待审包 digest | `7054494c2770c4b7b9f900318797ab7650418696d59d090cd2d07fc579b6428c` |

核对时没有 queued/running/interrupt_requested/recovery_required 模型回合；项目已登记的 9 个训练实验状态均为 completed。不能仅凭此快照判断未来可重启。

当前审核没有 `author_questions`，没有标为 blocking 的 issue，尚无科学内容冻结或交付批准。这只说明平台可接受用户对初稿的审核动作，不代表稿件科学正确、可投稿或引用已全部达到全文支持层级。

### 额度与上下文

- 项目已用 **108 / 160 回合**，剩余 52 回合。
- Agent 预算 **14640 秒（244 分钟）**；计费预算消耗 `used_budget_seconds=12604.266447982285`，剩余约 **2035.73 秒 / 33.93 分钟**。
- `used_wall_seconds=18606.421447` 包含非 Agent 预算时间；`excluded_tool_seconds=6002.154999017715`。不要拿墙钟总量直接减 Agent 上限，误报额度耗尽。
- budget revision 4。不要恢复为早期 40/80 回合或 120/180 分钟，也不要由开发助手增加额度。
- 当前上下文约 `148744 / 1000000` tokens（运行时用量估计，约 14.9%）；项目压缩剩余 2 次。新开的是开发窗口，不意味着需重建研究对话或研究目标。
- 最新研究回合冻结为 OpenCode / `deepseek-v4-pro`，输出上限 32768。未来回合以其实际冻结配置为准，不能仅凭前端选择器默认值推断。

## 当前稿件材料

研究工作区：`/data/bxn/PathoReason/projects/prj_f07d49680a6b475d91f2451260ca2040`。

| 材料 | 工作区相对路径 | Artifact ID |
|---|---|---|
| 正文 v2 | `manuscript/gist-risk-mil-manuscript-v2.md` | `art_bf586a5d5c88d84fb1374d20c8ccb016` |
| 文献库 v2 | `manuscript/gist-risk-mil-references-v2.bib` | `art_266f094d94eb22265ea7ae885b10462e` |
| 引用核验报告 | `manuscript/citation-verification-v1.md` | `art_8cfe55348b52491827766a0ca8a1ad79` |
| 作者待办 | `manuscript/author-confirmation-checklist-v1.md` | `art_b04dd953fe9e2928570b26cc6953c905` |
| 图表清单 | `manuscript/draft-figure-manifest-v1.json` | `art_40f3070b2cb19d80c7df94918de3b167` |
| 图 1 | `figures/h1-slide-arms-v1.png` | `art_73577231eb940b08c2c7b988cf74732e` |
| 图 2 | `figures/gist-risk-blocks-v1.png` | `art_d46c866a31981ff95f3f1981d34b83b6` |

文献库已登记为成果/目标证据，但当前 draft 审核材料列表为正文、引用报告、作者待办、图表清单和两幅图，共 6 项。是否在初稿审核中加入文献库入口可作为通用展示优化评估，不能手改既有材料包摘要。

Agent 最新回复称它修正了 AGE-MIL、GroupMIL、Bonetti 的引用元数据，且 Christensen 引用实为会议摘要。**这些是模型报告的结果，开发窗口尚未独立复核原文。** 当前 issue 同时记录参考文献 1–7、11 仍是摘要级核验；不要把“逐条核验完成”写成“全文支持全部论点已确认”。

既定研究边界须保留：测试集已多次使用，材料目前记载 54 次曝光；非独立、非盲法；不同实验块的队列/评估范围/管线有差异，不能直接横向比较绝对数字。具体数字与推论以原实验账本和成果核验为准，不由开发窗口改成更好结论。

## 已上线的论文链路

研究五阶段：数据准备 → 基线方案与实验 → 创新方案与实验 → 结果分析与科学审核 → 稿件部分。显式阶段交接与同项目换窗已经实现；稿件内部五个作者节点不是五次强制换窗。

| 作者节点 | 内容与下一步 |
|---|---|
| blueprint | 事实、写作主线、论点边界、图表计划；批准后准备初稿 |
| draft | 初稿、引用核验、作者待办、实际图件；批准后做完整性检查和模型辅助审稿 |
| review | 对审稿意见逐项裁定并给理由；完整性阻塞先修复，不伪造完整评审 |
| scientific | 修订稿、回应表、文献库、确切版本的核验；明确批准科学内容后才能冻结排版 |
| delivery | PDF、源包、页面 QA 与交付清单；明确确认交付，不授权投稿 |

公共机制在 `src/pathoreason/manuscript.py`。材料来源、发布副本、审阅快照和有效上游版本都校验；CAS、幂等回执、返工撤销下游批准、历史原文与预算保留已经实现。作者批准、独立科学批准与投稿授权分别记录。

0.6.32 修复了“输入意见仍不能确认方案”：只有 blueprint 允许显式 `approve + confirm_answers=true + 非空comment` 一次提交答复与方案确认。回执 `question_response` 保存原问题与作者原文；并非任意文字自动批准。后续内容节点缺必要事实仍应更新材料后再审；完整性阻塞不可跳过。默认 false 不进入旧命令摘要，保留历史幂等兼容。

当前真实历史证明：用户在 08:26:50 UTC 提交了组合答复确认，平台在约 2 秒后自动接续同一目标；Agent 生成 v2 并在 08:31:25 UTC 提交 draft 待审。这里只证明这一次 blueprint→draft 实际接续发生，不等于后续三节点或科学核验已通过。

## 最新界面要求

最新要求取代“正文末尾独立审核卡片”的旧方案：

- 标题行的阶段浮层保留稿件生成阶段、研究五阶段、上下文及交接记录。
- **输入框上方的可折叠栏**承接稿件审核，提供“稿件审核 / 任务进度”；当前稿件会话不挂载训练模块、不显示旧训练完成提示。
- 其他阶段继续使用原任务/训练方案/预算/执行记录；研究工作台的历史训练数据保持。
- 新待审材料可自动展开审核；标题入口及普通“继续”定位此处，不自动批准。
- 收起或切换标签保留意见和逐条裁定。出现额度/上下文/执行阻塞时显示任务恢复，保留暂停、目标调整等控制。
- 当前节点先说明确认后的动作，再展示必要问题和输入；两个直接操作为确认/按意见修改。材料及非阻塞核对项在详情。科学内容和交付确认保留明确勾选。

关键前端：`GoalPanel.tsx`（承载与阶段分流）、`ManuscriptReview.tsx`（审核表单）、`ResearchStageContext.tsx`（共享状态/旧轮询保护）、`StagePanel.tsx`（概览）、`App.tsx`（自然输入路由）。旧 `ManuscriptConversation.tsx` 已删除。不要恢复重复审核卡片或把训练页重新塞回稿件栏。

## 下一窗口优先处理的内容

1. **先读当前 draft 内容和核验报告，确定后续真实链路的风险点。** 优先看“论文论点—实验/文献证据”的支持关系，区分元数据、摘要、全文核验。若存在影响当前论点的完整性问题，不应一律推迟到投稿前；事实性核验由 Agent 执行，公共机制提供能力与约束。
2. **让审核提供有效信息而非只有文件列表。** 评估通用“本版改动、关键结论与限制、需要用户决定的事项、确认后动作”展示，以及正文/图件的就近查看。保持简洁、直接反馈与版本绑定，不把每个机械检查变成作者确认。
3. **观察 draft→review→scientific→delivery。** 必须等用户真正批准相应版本；确认后检查同目标自动接续、作者原文继承、审稿逐项裁定、返工后下游批准失效、额度停止与上下文恢复。没有用户批准就做工程/只读诊断，不替用户点确认。
4. **验证工具和 Skill 的实际使用。** 重点为 `method-results-to-manuscript`、`peer-review`、`manuscript-to-latex`；路径在 `.agents/skills/`。目录发现、正文加载、模型调用、输出质量分别留证。已有 hosted binding 应作为权威，不让旧 auto-research 门禁文件代替平台回执。
5. **排版交付必须核对实际产物。** 工具链在 `.tools/manuscript`，PATH 由 `.tools/manuscript-path.json` 加载。编译成功不等于 PDF 页面、图表、引用、源包正确；内容变动须重新取得相应版本批准。投稿仍另行授权。
6. **处理已观察到的表达问题。** 最新 Agent 回复开头混有英文过程话术，末尾直接显示 `<pathoreason_title>…</pathoreason_title>`；可检查公共回复/标题处理责任层。目标 `next_action` 还保留旧的“在对话正文审阅”表述，当前 UI 的提示已指向审核栏；后续统一未来提示，不改写历史回执。

以上为下一窗口的建议检查顺序，不表示要立即把所有问题都改掉。先复现真实失败，再做相称的公共修复；不要为了“优化链路”重新启动已完成实验或消耗模型去重做已确认方案。

## 证据与验证边界

服务器 `docs/p5/` 的主要文档：

- `MANUSCRIPT_AUTHOR_REVIEW.md`：auto-research 路径调查、五门禁、快照/返工/科学边界。
- `MANUSCRIPT_EFFICIENT_REVIEW.md`：组合答复确认、直接反馈、原文继承和测试失败记录。
- `MANUSCRIPT_COMPOSER_PANEL.md`：最新审核栏布局，优先于 `MANUSCRIPT_INLINE_REVIEW.md` 的旧位置说明。
- `STAGE_CONVERSATION_ENTRY.md`、`RESEARCH_STAGE_HANDOFF.md`：显式换窗与阶段交接。
- `SKILL_LIFECYCLE.md`、`OUTPUT_SETTINGS.md`、`EXECUTION_EVIDENCE.md`、`RELEASE_RECOVERY.md`：工具发现、输出恢复、证据链和发布维护。

运行证据在 `/data/bxn/PathoReason/acceptance/`：

- `manuscript-gates-20261104`：初始作者审核，合并版本539通过/3跳过等历史工程记录；不是本轮重跑结果。
- `review-efficient-20261104`：60项相关覆盖（最终59项通过，隔离目录问题的1项独立复验通过）；组合答复、返工、幂等、预算、HTTP与浏览器证据，失败日志保留。
- `review-composer-20261104`：最新构建、4种宽度夹具与真实只读线上检查；意见保留、可点击性、任务恢复、其他阶段训练、版本/重复提交保护。发布 `5841e4d`，服务进程未变，无审核写请求。
- `handoff-manuscript-20261104/state.json`：本次交接时的只读 API 快照（含最新回复和作者原文），不含凭据配置。它不是当前状态的替代品。

开发窗口未替用户修改稿件或批准审核。该阶段的真实模型进展来自用户批准后的 Agent 自动执行。完整稿件生成、科学核验和最终交付仍待后续验证，不得因 UI/单元测试通过就宣称论文链路全部成功。

## 新窗口的第一步

先 SSH 服务器读本文件及根目录规范，再查看以下只读接口。研究会话可能已被用户推进，禁止用这里记录的 revision 直接提交动作。

```bash
curl -fsS http://127.0.0.1:8520/health
curl -fsS http://127.0.0.1:8520/api/v2/conversations/conv_f57f523200354fe2bd64ebd464039c6c/stage
curl -fsS http://127.0.0.1:8520/api/v2/conversations/conv_f57f523200354fe2bd64ebd464039c6c/manuscript-review
curl -fsS http://127.0.0.1:8520/api/v2/conversations/conv_f57f523200354fe2bd64ebd464039c6c/goal
curl -fsS http://127.0.0.1:8520/api/v2/conversations/conv_f57f523200354fe2bd64ebd464039c6c/budget-settings
```

若 stage 指向新 conversation_id，应跟随拥有者。完整会话/上下文用 `/api/v1/conversations/{cid}`；审核快照材料用 `/api/v2/conversations/{cid}/manuscript-review/{review_id}/materials/{artifact_id}`。只读诊断不需要用户逐次确认。

修改优先用仓库分支/临时 worktree。静态前端可保留旧哈希 assets 并原子替换 index，不重启服务；后端改动须先核对活动目标/回合/训练、备份并按发布规范实施。不得重启 OpenCode 或训练来验证一个 UI 改动。旧验收发布脚本含特定基线断言，只能阅读/适配，不能直接重放。不要把服务配置或凭据打印到输出/交接里。
