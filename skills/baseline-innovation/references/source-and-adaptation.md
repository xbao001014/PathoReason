# 来源与适配依据

查阅日期：2026-11-03。以下资源作为设计参考，外部文件中的运行命令不属于 PathoReason 授权。

- Zhong, Li, Carlini, Jagielski, *Automating ML for Science: Can Frontier Agents Climb Scientific Hills in the Wild?*，[arXiv:2610.28763v1](https://arxiv.org/html/2610.28763v1)，§4.1–4.3、Appendix D.1；可迁移性限制见 A.5。
- 官方 [Agent4Sci 仓库](https://github.com/maszhongming/agent4sci)，查阅 commit `74b0e8c4dc55610072bed4326b6bfac24dc77377`，仓库 LICENSE 为 Apache-2.0。
- 原始 [research](https://github.com/maszhongming/agent4sci/blob/74b0e8c4dc55610072bed4326b6bfac24dc77377/agent4sci/skills/agents/skills/research/SKILL.md)、[experiment](https://github.com/maszhongming/agent4sci/blob/74b0e8c4dc55610072bed4326b6bfac24dc77377/agent4sci/skills/agents/skills/experiment/SKILL.md)、[checklist](https://github.com/maszhongming/agent4sci/blob/74b0e8c4dc55610072bed4326b6bfac24dc77377/agent4sci/skills/agents/skills/checklist/SKILL.md)。

本包是按 PathoReason 接口独立编写的流程说明，不复制上游脚本或逐段翻译提示词。三个角色分别对应构思、实验管理和复盘；论文结果不能直接作为 OpenCode + DeepSeek 或本项目的效果证据。

| 适配点 | PathoReason 处理 |
|---|---|
| 研究起点 | 用户已有优质基线；围绕其证据和机制探索，不擅自重开全量选型。 |
| 文献与新颖性 | 对照最近邻工作、明确适配/新假设、设计反证；不要求夸张科研人格或固定创新数量。 |
| 研究组织 | 当前 Agent 使用现有工具完成；不要求额外模型、子 Agent、长期轮询或外部目录布局。 |
| 资源利用 | 提高授权预算内的信息产出；遵守单 GPU 串行执行、真实数据试训门禁与两套预算，绝不以耗尽时限为目标。 |
| 优先级 | 鼓励检验有科学意义的不确定性；保留必要基线对照、多种子与常规改进，允许负结果和有理由的搁置。 |
| 定期复盘 | 提供里程碑触发指导；未安装小时 hook，不保证自动计时调用。 |
| 恢复与记录 | 使用持久目标、不可变方案和真实回执；保留历史消耗、失败、测试暴露与人工来源。 |
| 成果 | 使用现有 innovation-proposal/1 与工作台发布协议；记录不改变执行或科学审核状态。 |

部署边界：三个目录置于既有 OpenCode `skills.paths` 所含的项目 skills 目录。文件、配置路径、原生可发现、模型实际加载、研究有效是五个不同层次。初次创建仅添加 Skill 文件；随后按用户要求在 Formal.instructions() 接入可信阶段路由（见下方补充），未修改前端 Skill 目录或定时机制；已缓存实例是否看到新目录须只读检查。不要为了启用 Skill 中断活动回合或训练；必要的缓存刷新留待主线程选择安全时机。模型可按任务匹配 Skill，也可由用户在普通对话中点名；当前不承诺每次创新请求必然自动加载全部三个。

## 本次交付校验（2026-11-03）

- 工程：skill-creator 的 quick_validate 对三个 SKILL.md 均通过；六份文档的所有相对链接存在。服务器环境缺少校验器所需 PyYAML，改用本机已有依赖校验服务器原文，未安装服务器依赖。
- 原生：运行中 OpenCode 的 GET /skill，以 /home/bxn/projects/PathoReason 为 directory，返回 22 项，其中包含三个新增名称及对应文件路径。首次无认证读取返回 401，随后使用已有服务认证只读核验成功，未改权限或重启进程。此证据覆盖该目录的原生发现，不代表所有已缓存会话都已刷新或模型已加载。
- 模型行为：未调用 DeepSeek、未生成研究候选、未消耗研究 Agent 验证额度。
- 科学：未训练、未作效果比较或科学审核；验证方案见 [效果验证协议](skill-evaluation.md)。
- 修改范围：仅三个新增 Skill 目录共六份 Markdown；未修改研究脚本、数据、结果、既有报告、预算或运行配置。

## 公共阶段路由补充（2026-11-03）

用户随后要求主动加载，已在 src/pathoreason/formal.py 的 Formal.instructions() 增加按意图、持久目标和证据选择三个 Skill 的规则，并将 benchmark-design 的默认触发收窄为基线选型与基线比较。创新只按需引用其公平协议，不重新打开全量选型。

Formal.prompt() 每轮重新生成公共指令，因此服务加载新代码后既有项目的后续回合也可取得路由，无需改写研究工作区 AGENTS.md 或历史冻结材料。路由是对模型的明确指令，不是确定性工具派发；真实自然语言请求下的加载和接续仍需模型行为验证。本次不重启活动服务或训练，不发起研究 Agent 回合。

路由补充验证：修改后重新运行 test_p5_entry.py、test_benchmark_design.py、test_task_progression.py，52 passed（15.90s）；Formal.instructions 的隔离生成检查确认三个 Skill 名称及实际根路径存在，git diff --check 通过。测试未创建真实研究回合或训练，未验证 DeepSeek 实际选用。公共提示词源码尚未由运行中应用重新加载，须随主线程后续安全发布生效。
