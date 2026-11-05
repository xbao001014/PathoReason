# 基线对比写作的显式执行

2026-11-05，`0.6.42-p5-baseline-writing`。

## 缺口与已有机制

用户要求检查写作 Skill 是否明确要求基线比较，缺失时参考相关领域高水平文章并形成可调用指导。只读核对发现：主 Skill 已要求区分 baseline/ablation/sensitivity，已有不确定性不能只报点估计；stage-execution 要求解释主要比较的目的，scientific-writing 要求证据与一致性。但缺少完整的比较对象选择理由、可比性检查、结果表、领域定位以及对应的实际执行记录，不能说此前完全没有要求。

开发修复前稿件评估只读发现：稿件已有算法对照、匹配控制和稳定性结果，但基线呈现较简略，且宿主选择与训练检查点选择的证据需要区分。这些是通用规则的动机，不将当前病种、数值或预期结论写成 Skill 答案。

## 公共改动

- 新增项目自有 `skills/baseline-comparison-writing/SKILL.md` 和 `references/paper-patterns.md`。参考 CLAM（Nature Biomedical Engineering 2021）、UNI（Nature Medicine 2024）、Fu 等 GIST（npj Precision Oncology 2023）、Bonetti/Le 等多中心 GIST（Cancer Research 2026）的相关正文，来源、实际阅读章节、未读补充材料边界在参考文件中列明。
- 明确六类证据角色、实际可比条件、实施忠实度、宿主/检查点/阈值选择、主指标/不确定性、同条件实验与文献定位分离。机制控制和交叉验证不可互相代替；不同任务/队列/指标不直接排名。
- 在主写作 Skill、scientific-writing 的宿主入口、stage-execution、M1/M4→M5/M6 工作流及主机节点提示中显式调用。新草稿/科学修订输出绑定正文 SHA 的 `baseline_review`，接入已有 integrity、skill_usage 与 checkpoint evidence。模型自评不等于平台或作者科学批准。
- 加入项目 Skill 目录和论文编写导航；原生发现仍使用既有配置目录，不改迁移来源清单。
- 不新增作者节点、实验、统计分析或额度，不追溯撤销已批准稿。旧稿交付/呈现调整仍按既有路由；缺少可选对照时收窄论断，不自动追加训练。当前论文由研究 Agent 在后续获授权的内容修订中处理。

## 验证与部署

工程与原生验证在独立工作区及 `/data/bxn/PathoReason/acceptance/baseline-writing-20261105/` 保存；发布记录完成后补充。Skill frontmatter 校验通过。只读检索包含期刊站点拒绝/重定向、PMC 间歇验证页，GIST 相关正文通过公开 Europe PMC fullTextXML 读取，未把摘要/搜索片段冒充全文。

本次不调用真实研究模型；工程/原生检查不能证明 Agent 已执行新写作要求，也不能认定当前 v13 已通过新核查。实际行为验收留待后续真实稿件修订，不占用或扩展既有研究预算。

部署采用已存在的安全维护流程：检查活动回合/目标与原生会话 → 停应用 → 刷新空闲原生实例 → 恢复应用 → 核对 Skill 正文与来源、健康及研究记录不变。原生引擎进程和训练控制器不重启。若存在活动或未决任务，不强行刷新。
