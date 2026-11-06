# 病理接口与图件能力匹配

适用：从病理接口选择论文图表、评估“能否画热点图”、准备空间图件输入。
先读取项目已有来源与范围，再使用 [病理接口 2.0](../../../../skills/pathology-data-api/references/api-v2.md)；接口查询走该 Skill 的分页 helper。
本表是输入与实现的匹配规则，不代表任意病种已具备完整数据。

## 分开记录三个状态

- **接口输入**：字段未开放／返回为空／存在引用／实际数据已校验。FilePath 或 FeaturePath 非空只证明引用存在。
- **执行实现**：已注册 provider／已有通用绘图 Skill 但缺专用适配／依赖或适配待补。Skill 文案不是已实现 provider。
- **本次图件**：待取数／待关联／待文件核验／缺模型输出／待实现适配／可尝试生成／已生成待审。只有所需输入与执行条件均核验后才能标“可尝试生成”；生成后仍需实际图像和来源验证。

这些是图件清单的描述字段，不改变平台任务/审核状态，也不由此授予执行权限。

## 按数据来源匹配

| 图件 | 接口直接提供 | 额外输入与核验 | 当前执行路径与限制 |
|---|---|---|---|
| 地域／医院样本分布 | 两个 disease 聚合接口的省市/医院及 PatientCount、SpecimenCount、SlideCount | 相同病种、DiagnosisStatus、CurrentOnly 口径；按返回分组解释，跨中心人数不默认可加总 | scientific-visualization 可作确定性柱图；尚无专用“病理 API 聚合图”注册 provider；论文绑定需补适配 |
| 年龄、性别、染色、亚型、属性分布及缺失概览 | patients/specimens/slides/subtypes/attributes | 完整分页、患者/标本/切片去重口径、多病种过滤、多标签重叠与缺失保留 | 通用确定性绘图；outcome_coverage 需要其研究证据格式，不能直接传 API JSON |
| 队列筛选流程图 | 主列表及实际纳入材料 | 纳排规则、逐步排除原因、唯一患者及实际 split 清单 | study_design 支持已执行协议；原始列表数量不能冒充筛选或训练划分 |
| IHC/分子指标分布、相关性矩阵热图 | molecular-results + 同标本映射；属性接口可能提供任务标签 | PatientId/SpecimenNo 联合关联、单位、定量解析、重复检测选择、缺失与任务定义 | 通用统计绘图，未注册专用接口适配；定性结果可作类别图，不能擅自转为连续测量或填零。矩阵热图不是组织热点图 |
| 文本命中／核验状态分布 | text-disease-matches 的来源和核验字段 | 去重、否定状态、核验状态、明确分母 | 数据质量描述图；Confidence 是文本匹配置信度，不是肿瘤概率或模型性能 |
| 真实 HE/WSI 概览 | slides.FilePath、SlideId/WsiId 等引用 | 实际像素可读、patient/slide 身份、像素 SHA、level-0 尺寸、原点、level/downsample、导出回执 | spatial 包 tissue_overview 已注册；无需 attention/patch 坐标。物理比例尺另外要求 X/Y MPP 证据 |
| ROI 组织局部图 | 同上 | 声明的 level-0 ROI 和选择依据；真实解码像素与映射 | spatial 包 roi_panel 已注册；ROI 选择不等于病理专家肿瘤标注 |
| Attention 热点图／Top attributed patches | 仅切片/特征路径引用，不提供空间归因值 | 与特征行序绑定的 patch_id、level-0 x/y/width/height，真实模型分数、checkpoint、执行源码、预处理、feature manifest、inference receipt、归一化范围 | spatial 包 attention_overlay/top_patches 已注册；缺任一必要绑定则阻塞对应图，不阻塞已有证据的其他图件 |
| ROC/PR、混淆矩阵、回归预测/残差图 | 患者与标签可能构成部分真值来源 | 实际病例预测、真值、类别/阳性类或单位、决策规则、split/fold/seed、checkpoint 与执行回执 | task_diagnostics 已注册；API 记录本身不是预测。使用已有执行结果，不为补图自动训练 |
| 基线比较／消融／训练曲线 | 无实验指标或训练历史 | 真实指标、匹配协议/划分/种子、消融配置和运行记录；训练曲线需要实际 epoch 日志 | condition_comparison 已注册；development_summary 仅限明确选择的单回归开发证据。训练监控有曲线展示，不等于已有论文曲线 provider |
| KM/HR、校准、决策曲线及临床效用 | 文档未定义随访时间/事件/删失/时间原点契约 | 真实随访与任务定义、验证预测、统计方法及不确定性；不能用 DiagnosisDate/ReportDate 替代生存时间 | 相应临床 provider 尚未注册；现有 survival 风险诊断不能替代这些图 |
| 概念示意／方法图 | 无需患者明细 | 与研究主体一致的说明；涉及真实方法结构时要绑定执行源码/配置 | 概念插图走配置的 Seedream 与 image 回执；精确拓扑走已有受限结构 provider 或可编辑代码图。概念图不补造真实像素、空间证据或数值 |

具体 provider 和输入以当前只读引擎的 manuscript_assets.figure_capabilities()、prepare_assets 路由及 [集成说明](auto-research-integration.md) 为准。当前还注册 context_residual_paper 包的 linear_context_residual_architecture 和 verified_regression_summary；它们仅用于对应已执行方法/已有结果，不能作为任意模型的通用适配。

## 热点图的最小接入链

1. 从已授权切片范围取得真实 FilePath；空值先记缺失，不用 FeaturePath 代替图像，不根据 WsiId 猜文件。允许接入有可追溯映射的其他已授权存储来源。
2. 用实际解释器探测解码器和具体样本。PathoReason 的 FXio 有历史 ZYP/MRXS 样例，而已注册 export_wsi_region 使用 OpenSlide/可选 opensdpc；**FXio 可读不代表该导出器已接通 FXio**。若需 FXio 桥接，须产生等价 typed mapping/导出回执并通过 spatial 校验；不能只保存 PNG 冒称集成完成。
3. 获取真实坐标源和提取元数据。export_h5_coordinates 支持含 coords 和几何 attrs 的 H5，输出保持原始行序；相同行数不是与任意 PT 特征一一对应的证明。坐标数组的原点/单位/层级必须来自提取契约。禁止把 dummy/grid 坐标作为组织定位。
4. 获取已执行推理的 patch 分数及实际采样/重排索引；部分采样需显式 patch IDs，未采样区域透明。ABMIL 模板的 WSI_attn 为 softmax 前 A_ori，不应当成归一化概率；如转换分数，记录公式、归一化范围及采样对象，不冒称复现了另一种输出。
5. 对齐 patient/slide、像素、坐标、特征、checkpoint、执行配置与 attribution binding；检查有限值、唯一 patch IDs、范围、等长/已声明子集及共同色标。
6. 通过 provider='spatial' 的 typed request 生成候选，沿 validate_assets、实际视觉检查、bind_assets 和宿主作者审核交付。Attention 是模型归因，不是肿瘤边界、因果解释或校准概率。

## 采集、环境与交付

- 字典精确身份先于病种过滤；别名查询为空不是该病种不存在。列表满页不等于全量；零行样本与字段未开放分开。
- 聚合统计和患者列表的默认过滤不同；回执中保留实际查询。真实患者明细、文件路径和凭据不进入图像生成服务。
- 检查将要执行脚本的解释器；应用 .venv、图件环境、训练环境的依赖分别核验。缺 torch/h5py 不代表所有环境都缺，也不要求为概念图安装这些包。
- 图件 inventory 逐项记录：figure_id、用途、API 查询回执、所需字段、已有证据引用/摘要、缺失输入、provider/package、实际解释器、输入状态、实现状态、候选状态、下一动作。
- API 描述性统计在普通分析阶段可由 scientific-visualization 输出可复现图表；进入严格 prepare_assets/bind_assets 的论文包时，未注册适配必须明确记录待实现，不能伪称是已注册 provider。
- 沿宿主稿件规则登记生成文件、源代码、图注、来源及 QA，保留不可变版本；此匹配本身不触发训练、数据扩采、付费生成或作者批准。

样本级联通与缺口记录见项目 docs/p5/DATA_FIGURE_CAPABILITY_MATCHING.md；实际覆盖率须由本次完整查询及文件核验重新计算，不能把历史样本结论固定为全库能力。
