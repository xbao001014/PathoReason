# 固定留出法的方案支持（2026-10-31）

发布：0.6.7-p5-holdout。benchmark-design Skill 版本 0.2.0。

用户在原项目对话将 v4 改为固定留出法，目标 Agent 已生成 v5，但原检查器只接受 CV：folds 至少 1、OOF 人数必须覆盖开发集。本次修复公共契约、Skill 和检查器，再由同一目标 Agent 重新验证；不代改 v5 或研究输出。

## 协议与兼容性

新方案使用 pathoreason.benchmark-plan/2，validation.method 明确选择 holdout 或 cross_validation。历史版本 1 保持原 CV 解释，不自动迁移/覆写；实际 v4 复核仍通过。

| 检查 | 固定留出法 | CV（版本 2） |
|---|---|---|
| folds / cv_runs | 均为 0，不是单折 CV | folds≥2，按模型×折×种子×设置计算 |
| 拟合次数 | final_fit_runs=模型×训练种子×预先确定的设置；total 同值 | total=cv_runs+final_fit_runs |
| 测试推理 | test_inference_runs=final_fit_runs，独立计数 | 与最终拟合对应，不混同 OOF 评估 |
| 人数 | train+validation=development；development+locked_test=cohort | 各折 OOF 总和=development，开发/锁定测试之和=cohort |
| 过期字段 | 拒绝非空 CV/OOF 统计与冲突的旧人数别名 | 保留折级人数 |
| 划分 | 一个 split_seed，fixed_split=true；训练种子不重新划分患者 | 折分配对所有模型/训练种子固定 |

validation 同时记录分组单位、分层说明、proposed/frozen 状态。frozen 必须提供当前工作区名单引用与匹配 SHA256；计数或文字不能冒称冻结。文件存在/摘要匹配并不验证名单内容、患者不交叉或冻结授权，实际训练前仍须核对这些证据。

只修订验证协议时，允许引用已有候选、方法库与文献证据，不重复采集患者数据或做完整联网检索。Skill 提供对话修订顺序、固定留出法示例、CV 兼容规则、种子语义和局限。新增参考文件 skills/benchmark-design/references/validation-protocols.md。正式提示词与目录条目同步更新。

本次支持固定留出法与普通 CV 的方案生成/检查；重复留出法、嵌套 CV、额外合并训练集重训等协议需独立建模，不能自动降级。实际模型适配、训练 runner、资源与训练授权独立，本次没有执行训练。

## 验证

- 最终 199 passed、1 skipped；既有 Starlette 警告。新增 16 项覆盖留出法次数/人数、固定数据划分与训练种子区分、禁止单折伪装、过期 CV 字段、未支持协议、冻结清单 SHA 与越界引用，以及两个 CV 契约版本兼容。
- skill-creator quick_validate 通过；API 目录返回 benchmark-design 0.2.0、7 个指令/资源摘要引用；应用健康版本为 0.6.7-p5-holdout。只在空闲时重启 PathoReason 自有应用，原生运行时无需重启。
- 同一 GIST vs 平滑肌瘤项目、DeepSeek Flash/high，通过正常应用入口提交 1 回合：turn_22a86a84a4fa441c8c5c037710fbe362；原生 5 次迭代、5 次工具调用，自行加载新 Skill、读取协议、生成/检查/登记 v6，无额外工具审批。
- 本轮约 23.74 秒；项目累计由 8/40 回合、3713.896105/7200 秒变为 9/40 回合、3737.631704/7200 秒，未重置/扩展预算。训练授权 false；权限 revision=1 未变。
- 本轮之前的 1689 个项目文件 SHA 均未变化；公共验证源码也未被研究 Agent 改写。保留 v5 的失败记录。开发助手只做公共层修改、提交验证任务和只读检查。

## 真实结果

Agent 自行登记 benchmark-plan-v6：schema /2、method=holdout、folds=0、cv_runs=0；8 模型×3 训练种子×1 设置=24 次拟合，24 次测试推理另列。拟议人数为 train 165 / validation 41 / locked test 52；split_status=proposed，未生成患者划分名单或冻结回执。

检查结果 structure_valid=true、validation_method=holdout；source_review_complete=true 沿用已申报的论文正文证据，仍非第三方科学审核；保留 8 条 executor not validated。没有数据重拉、依赖安装、smoke、训练或 compute.json 修改。

成果：
- JSON：art_b0f02db8d88f3bba0c25092f0136d522（outputs/benchmark-plan-v6.json）
- 可读方案：art_2ac606bef339c8f0d9b140d123023080
- 变更与校验记录：art_e23226ba41d025ff9021c28fdfaaa1d4

用户可在原对话继续提出协议、比例或种子修改，审核新版本差异；后续划分冻结、模型接入和实际训练按各自授权推进。v6 的拟议训练预算没有转化为执行授权。

## 证据与恢复

证据目录：/data/bxn/PathoReason/acceptance/holdout-support-20261031/，包含前置源码/数据库备份、原文件 SHA、实际请求/回合/原生工具摘要、测试和兼容核对。发布包为 releases/pathoreason-0.6.7-p5-holdout，按文件 SHA 核验。

恢复只回退此次公共源码/Skill，并在空闲后重启应用；不能恢复旧数据库抹掉 v6 或重放调用。旧检查器不能理解 /2 新方案，回退时应明确该兼容边界。原有 OPERATOR.md/FXIO.md 用户工作目录变更保留。
