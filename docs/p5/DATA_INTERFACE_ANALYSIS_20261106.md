# 数据接口与病理图表接入分析

日期：2026-11-06。目标仓库：bxn-server:/home/bxn/projects/PathoReason。
源码基线：PathoReason 分支，431559d；检查前工作区干净。
本次为开发侧接口分析和工程检查，不是研究 Agent 或科学验收。

## 当前结论

接口传输、WSI 读取、模型 attention 输出及图件来源规则已有部分基础，但尚不能认定真实空间图表链路已完整接入。本 session 按“业务接口 → 文件与空间元数据 → 模型输出 → 图表与成果引用”继续核验。

## 已核验的实现

| 层级 | 证据 | 缺口或限制 |
|---|---|---|
| 业务数据接口 | skills/pathology-data-api/references/api-v2.md 列明 10 类 GET，覆盖疾病、两种聚合、患者、标本、切片、亚型、属性、分子结果、文本追溯 | 文档没有独立 WSI 像素/瓦片、坐标、attention 端点；实际额外服务能力未探测 |
| 新版传输 | skills/pathology-data-api/scripts/fetch_pages.py 校验允许字段、查询范围、分页、HTTP/API 状态、原始响应 SHA、完成回执及中断不重放 | 仅传输，尚非统一跨表/空间数据校验；本次未发起真实 API 请求 |
| 历史入口 | src/pathoreason/study_io.py:32 及 config/p5/data-source.json 仍使用 DiseaseName/Limit；请求未加新版鉴权头，未校验 API code/data 成功语义 | 与 2.0 并存，存在误选入口和错误响应被记为 downloaded 的风险；不能作为完整采集依据 |
| 原始切片 | docs/p5/FXIO.md 记录 ZYP/MRXS 各一例历史读取验证；当前 .venv 可发现 wsi、openslide、numpy | 本次未重新验证真实切片；历史少量样例不证明全数据覆盖 |
| 特征与空间坐标 | 切片记录含 FilePath/FeaturePath；模板 WSI_Coord_Dataset 支持 H5 coords | 实际文件格式、坐标所在位置、单位、层级、patch 大小与特征行序尚待核验 |
| attention | 模板 vendor/modules/AB_MIL/ab_mil.py:46 可选返回 WSI_attn；该值为 softmax 前 A_ori | 必须明确 raw score/归一化权重语义、模型适配及 patch 索引，不可假定所有模型均一致；未证明真实实验已导出 |
| 占位坐标 | 模板 vendor/utils/wsi_utils.py 的 SC_MIL 数据集在缺少 H5 时可回退 dummy coords | 不能作为真实空间坐标用于组织热点图；这是模板路径风险，不表示当前真实任务使用过该分支 |
| 图件约束 | .agents/skills/pathology-mil-paper-figures/references/evidence-and-provenance.md 已要求像素、坐标、模型与 attribution 来源绑定 | 规则存在不等于读取、对齐、渲染和审核全部有实现及真实验证 |

## 环境和本次验证

- 使用服务器项目 .venv 执行 tests/test_data_api_skill.py：7 passed（0.23 秒）。
- 模块发现：wsi/openslide/numpy 可发现，torch/h5py 不可发现；仅针对应用 .venv，其他训练环境未核验。模块发现也不等于完整运行检查。
- 对已有项目 inputs JSON 的只读目录抽查遇到 I/O 等待；未取得有效内容结果。已核对探针进程身份并终止，随后确认进程不存在。
- 不把该等待判定为数据缺失、文件损坏或整个数据盘不可用；后续采用已知文件白名单和单文件隔离超时，避免递归遍历挂载目录。
- 未调用研究模型、付费图像服务或训练，未修改研究成果、额度或服务状态。本次不宣称真实数据全量完整或热点图端到端通过。

## 接入顺序与完成判据

1. **统一接口入口**：将新版分页、凭据加载、业务状态校验和回执作为公共传输能力；为历史入口制定明确兼容/引导，避免静默按旧协议采集。保留历史回执。
2. **限定样本核验**：选取已有项目中已知来源的小批切片记录，检查患者—标本—切片关联，保留原路径；逐文件核对可读性、格式、特征形状、坐标及元数据。未通过不能推断全数据可用。
3. **建立空间输入契约**：至少绑定 slide/WSI 身份、像素来源、feature/coords 摘要、patch ID 与行序、原点/单位、level/downsample、patch 宽高、X/Y MPP、编码器及变换。坐标不足时明确阻塞空间图，其他有证据的图表可继续。
4. **对齐模型输出**：绑定 checkpoint、实际推理配置、split/fold/seed、采样/重排索引、attribution 方法和数值来源；检查长度、唯一性、有限值、边界及归一化。明确区分 raw attention、归一化权重和其他 attribution。
5. **补齐图表适配**：真实 WSI 缩略图/ROI/高分 patch/attention overlay 使用真实像素和坐标；ROC/PR/混淆矩阵等走病例预测表；生存图需额外时间/事件字段。注意力不能自动解读为肿瘤标注或概率。
6. **成果链路验收**：渲染来源清单、代码与环境、图注、尺度/色条、检查记录绑定确切版本，通过已有 publish/图件登记和预览链路交付。工程夹具、真实文件读取、目标 Agent 行为、科学审核分层留证。

优先下一步：从已知来源记录定位一份真实切片及配套特征/坐标文件，完成最小空间输入盘点，再确定需补的是数据提供方字段、公共读取工具、模型导出，还是图件渲染适配。
