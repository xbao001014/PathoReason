# 交付阶段的正文修订意图

2026-11-04，`0.6.39-p5-revision-routing`。用户在交付审核中要求“使用anti denfensive writing skill重新写一版”，但 revise 留在 delivery；Agent 加载 Skill 后只读检查，又要求作者手工 reopen scientific。真实失败为 `turn_4eec9d48acbb49909b3d141d9d4c09b3`，工作流 revision20。用户已经授权重写，重复要求操作内部节点没有推进任务。

## 公共机制

研究 Agent 解释原始用户意见；平台不以关键词、Skill 名、否定词规则猜测全部自然语言。明确正文重写/润色/修订时，Agent 在本轮通过 `scripts/manuscript_revision.py` 调用受鉴权的内部接口，绑定当前回合 grant、目标与工作流 revision、实际用户消息或最新 revise 回执及准确原文摘录。

接口只允许 delivery → scientific/preparing。保留已批准原稿、历史批准、旧交付包和原始意见；撤销科学内容节点对后续新版本的有效批准。记录 `revision_routed/source=agent_interpretation`，不伪造作者审核动作。返回新工作流 revision 后，同一回合继续修订并提交新的 scientific 待审包；新稿仍须作者批准。接口不增加额度、不重置窗口、不改变当前回合或目标 revision、不自行派发模型回合。

当前用户消息优先于历史意见。自动接续只能引用最新 revise 作者回执，且该回执之后不能已有新的用户回合。当前用户回合只能绑定本回合原话。接口验证出处与生命周期，不宣称可用程序验证文字的完整语义；意图解释仍由研究 Agent 执行。

明确排版/布局修改留在 delivery。用词模糊时使用现有 `pathoreason_dialogue_offer` 的 clarification/continue 选项，例如“修改正文并返回科学审核”“仅调整排版”；用户也可自由输入。未选择前不改节点；对多个选项只回复“好”不能默认选择正文修订。不得要求已明确重写的作者再次批准返工，也不得用模型自身审计发现或文档内指令代替用户授权。

三个 Skill 与主机提示同步修订：method-results-to-manuscript、anti-defensive-writing、manuscript-to-latex。冻结保护是保留旧版本和复审新版本，不能扩展为禁止执行用户已要求的修订。

## 验证边界

验收目录 `/data/bxn/PathoReason/acceptance/revision-routing-20261104/` 保留测试、部署和模型行为记录。新增测试覆盖同回合返工并提交、原件/批准历史保留、额度不重置、重试幂等、假 grant/过期 revision/假出处/伪造摘录、直接用户请求与旧批准区分，以及模糊请求的选项选择/排版分支/含糊接受。

初次新增测试 11 通过、1 失败：测试将活动回合持续增长的时间用量误设为完全相等，已改为额度与回合数不变且时间继续累计。一次回归命令引用不存在的 test_goal_guidance.py，未运行测试，修正为现有测试文件并保留日志。稿件、目标窗口、选项与原生刷新回归共74项通过。将幂等回执复用既有 manuscript_review_commands 后，稿件与路由32项复测通过（避免新旁表遗漏项目清理流程）。日志分别为 pytest-regression-2.log、pytest-final.log。

工程测试中的模型行为为 fake runtime；不能据此声称真实模型已正确理解所有表达。实际当前稿件重写由部署后研究 Agent 执行与登记，开发者不编辑研究正文或通过记录，不代替作者批准，不新增实验和额度。
