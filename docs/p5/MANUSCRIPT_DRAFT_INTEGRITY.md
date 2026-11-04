# 初稿审核的信息与完整性门禁

2026-11-04，版本 `0.6.34-p5-figure-audit`。

## 真实失败与责任层

当前 GIST 稿件已停在 `draft / 初稿与图件 / awaiting_review`，没有作者批准。只读核对确认待审包与六项材料 SHA 未漂移，但材料之间存在可复现的不一致：Figure 2 图内使用 A–E 五个分块，正文、审核摘要和 figure manifest 多处使用 A–D；作者待办仍称 AGE-MIL 元数据待确认，而同版引用报告已标为解决。目标 `next_action` 还指向已移除的“对话正文审阅”。

这些问题不应由开发助手直接改稿，也不能一律推迟到投稿前。责任分为两层：平台要求版本绑定的跨材料完整性证据并把有效审核信息直接呈现给作者；研究 Agent 使用稿件 Skill 核对并生成新版本。作者是否接受稿件仍由公开审核动作决定。

## 公共机制

- draft 审核包新增必需角色 `references` 与 `integrity`。引用核验报告不能代替实际 BibTeX；完整性报告必须以 `audited_manuscript_sha256` 绑定同包正文的确切字节。
- draft、review、scientific、delivery 均要求明确 `audit_status`。不适用状态不能进入这些节点；阻塞问题仍禁止批准。
- blueprint 之后的审核请求必须给出非空 `changes`、`key_findings`、`key_limitations`。输入框上方审核栏直接显示“本版变化 / 关键结论与限制”，仍保留材料、问题、问题记录和自由输入。
- 非空 figure manifest 除 artifact ID 集合一致外，还必须逐图给出唯一编号、文件和图注。实际图件仍随同一审核包冻结。
- 非空图件包还必须有 `figure_audit` 材料。`scripts/setup_image_ocr.py` 按 SHA-256 锁定的 Debian 包安装用户态 Tesseract 到仓库 `.tools/`，不修改主机；`scripts/inspect_figure_text.py` 只接受当前正式项目的 `figures/` 或 `manuscript/` 栅格图，输出带图件哈希的 JSON。OCR 是跨材料检查证据而非科学结论；关键文字无法识别时必须阻塞审计。
- Agent 提示要求在 draft 前比较正文、文献库、引用报告、作者待办、figure manifest、图内标签/图注及分块定义。机械不一致由 Agent 自主修正；无法解决的事实冲突作为阻塞 issue 暴露。
- 新审核请求把目标提示更新为输入框上方“稿件审核”栏。历史目标和历史回执不回写。

## 边界

本次不新增训练、测试评估、测试集调用或实验额度，不重置既有消耗。工程完整性报告不是独立同行评审或科学批准。平台不生成作者签名，不代替作者确认 draft/scientific/delivery，也不授权投稿。旧待审包保留在 superseded 历史中；新包必须由研究 Agent 登记实际材料后才能替换。

## 工程验证

- 稿件专项：27 项通过。
- 完整回归首轮：549 项通过、3 项跳过；5 项因隔离 worktree 缺 Git 忽略的本地配置而在读取设置时失败。复制正式配置到隔离目录且不输出内容后，5 项独立复验通过。
- 完整回归最终：554 项通过、3 项跳过。
- TypeScript/Vite 构建通过；保留既有 bundle size 提示。
- 契约新增 `api-p5-manuscript-integrity.openapi.json` 与 `p5-manuscript-integrity/`，不覆盖历史快照。

首轮真实 Agent 修稿已把五项只获得摘要核验的参考文献降为准确的证据标签，并修复 AGE-MIL 待办，但因运行时没有视觉能力，未识别 Figure 2 的 A–E 与稿件 A–D 冲突。该失败直接促成上述公共图件审计机制；最终 Agent 修稿、线上只读状态和发布连续性在完成后补记。工程通过不代表稿件科学正确或作者已批准。
