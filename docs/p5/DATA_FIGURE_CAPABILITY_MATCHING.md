# 数据接口与生图能力匹配（2026-11-06）

## 结论

已将病理接口字段与现有图件路线匹配，并接入数据接入、图件路由和论文图件三个 Skill。
本次交付是能力匹配及输入检查规则，不是新增绘图 provider，也未生成或改写研究图表。
“接口可返回字段”“当前样本有数据”“已注册渲染器”“真实研究图件通过”分别记录。

| 图件方向 | 接口能力 | 项目匹配与当前缺口 |
|---|---|---|
| 地域/医院、年龄/性别、染色/标签分布、数据缺失 | 两个聚合接口及患者/标本/切片/富集列表有对应字段 | 通用确定性绘图可用于分析；专用 API→论文资产 provider 未注册，需整理口径及适配 |
| IHC/分子分布、相关性矩阵热图 | 定性/定量/单位等字段已定义 | 需要同标本关联、单位与缺失核验；抽样定量与单位为空，不能据此绘制定量图 |
| HE/WSI 概览、ROI | 提供 FilePath/SlideId/WsiId 等引用 | tissue_overview/roi_panel 已注册；本次普通 2 条及 HE 5 条记录的像素路径为空，尚不可取图 |
| Attention 热点图、Top patches | 不直接提供坐标、attention 或模型绑定 | attention_overlay/top_patches 已注册；需真实像素、坐标及特征顺序、推理分数、checkpoint/执行来源。图件工具存在，输入链未核验完成 |
| ROC/PR、混淆矩阵、回归图、基线比较/消融 | API 可能提供真值，未提供实验预测/指标 | 复用 task_diagnostics、condition_comparison 等对应 provider；必须接真实实验输出 |
| 生存 KM/HR、校准、决策曲线 | 文档未定义完整随访/删失契约 | 对应临床 provider 尚未注册；现有 survival 风险诊断不等于支持这些图 |
| 概念示意、方法说明图 | 不依赖患者像素或明细 | 现有 Seedream 路由可用作概念图；真实结构须绑定执行来源，不能替代组织图或统计图 |

具体字段、提供器、接入条件和下一步动作维护在
[Skill 能力匹配表](../../.agents/skills/pathology-mil-paper-figures/references/api-capability-matching.md)。

## 真实接口抽查

- 共 12 次有界 GET，覆盖文档中的 10 类端点；均 HTTP 200 / API code 200。这是样本与响应结构检查，不是全量采集。
- 首次字典 Keyword=胃肠道间质瘤 返回零行；改为 Keyword=间质 后，按字典确认 C_JZL / 间质瘤（DiseaseId=28），未根据模糊命中混用另一病种。
- 主明细每项首屏最多 2 条；患者富集只取已查询的一位患者，每项最多 2 条；两个聚合接口不分页。
- 额外查询 StainType=HE 的首屏 5 条。普通切片样本 2 条与 HE 样本 5 条的 FilePath、FeaturePath、ScanName 均为空；不假定两批记录互斥，不据此推断全库缺失率。
- 亚型/属性/分子/文本端点有非空响应。抽样分子 QuantitativeValue/QuantitativeUnit 为空，属性 NumericValue 为空；不能将“字段存在”当成可用数值。
- 未尝试根据 WsiId 猜路径，未递归遍历运行数据盘，未推断空值的根因。接口字段未列出的能力仍以已公开文档为边界，未声称发现隐藏端点。

原始响应、查询、时间、摘要和脱敏结构汇总保存在独立受限目录：

- /data/bxn/PathoReason/acceptance/data-figure-match-20261106T024553Z（初次字典空响应）
- /data/bxn/PathoReason/acceptance/data-figure-match-20261106T024603Z（病种身份）
- /data/bxn/PathoReason/acceptance/data-figure-match-20261106T024619Z（其余九类端点）
- /data/bxn/PathoReason/acceptance/data-figure-match-20261106T024658Z（HE 切片抽样）

凭据不写入查询或回执；患者记录只在数据盘证据中，未加入仓库或发送给图像模型。

## 实现核对与改动

- 只读核对 auto-research 的 manuscript_assets.figure_capabilities/prepare_assets、pathology_slide_assets 的 API 路径检查、WSI/H5 导出及 typed spatial 需求；旧仓库未修改。
- 已有 14 个注册图件标识，包括 context_residual_paper 的两个受限提供器；不能将它们概括为任意模型/临床图表支持。
- FXio 具备历史读片验证，但 export_wsi_region 实际使用 OpenSlide 或 opensdpc。需要 FXio 的文件仍须补齐兼容空间回执的桥接，不把环境安装当成提供器接通。
- 新增 api-capability-matching.md，并从 pathology-data-api、pathology-figures、pathology-mil-paper-figures 的入口按需加载。
- 图件 Skill 升至 1.1.1，当前清单只更新受影响文件 SHA 并登记新参考文件。原始迁移清单、旧冻结实验和稿件资产保持原样。
- 修正 OPERATOR.md 的当前数据入口说明，指向 2.0 分页 helper；历史 Limit 代码本次未改，不能宣称旧接口已修复。

## 优先后续工作

1. 对已知切片 ID 核实上游 FilePath/FeaturePath 为空的原因，或接入有明确身份映射的已授权文件清单。先恢复真实像素和特征来源。
2. 对显式指定的小批文件核对实际解码器、坐标/H5 元数据、特征行序与提取来源；不再递归扫描挂载目录。
3. 将对应真实模型的 attention/attribution 输出、采样索引和执行来源导入现有 spatial 契约，走最小真实样本生成及校验。
4. 若需要把 API 队列统计直接纳入论文资产包，再实现专用确定性 provider 与相应拒绝/来源测试。避免把通用 Skill 能绘图误报为该适配已完成。
5. 使用实际研究 Agent 验证选图、缺口判断和生成行为；本次没有消耗其模型或训练额度。

## 验证与发布

- 25 项数据接口与原生 Skill 生命周期回归通过。
- 三个 Skill 均通过 skill-creator quick_validate；真实引擎 validate_skills 校验当前清单和全部登记摘要通过，figure_capabilities 返回 14 个注册标识。
- 首次在应用 .venv 导入旧引擎校验器因缺 PyYAML 失败；改用已有旧引擎 .venv 执行只读校验后通过，未安装依赖或修改环境。
- 维护前应用无未决回合/压缩及阻塞目标；stop-app → refresh-native → start → check-native 完成。8 个绑定目录的原生 Skill 正文/路径核验通过，应用健康，OpenCode 进程身份不变。
- 发布前后 16 张研究/稿件/训练等业务表的行数与内容摘要一致。未对研究文件执行写入。
- 发布证据：/data/bxn/PathoReason/acceptance/data-figure-release-20261106T025241Z/，包含前后业务摘要、维护日志和 result.json。
- 回退仅恢复本次 Skill/当前清单/文档并在空闲窗口刷新缓存；不恢复数据库，不回放研究回合。
- 无研究模型、付费生图、训练或科学审核；原生加载成功也不等于模型已正确执行。
