# Benchmark 选型链路与联网检索

发布：`0.6.6-p5-benchmark`。目标是让 OpenCode + DeepSeek 从研究问题与数据条件出发，结合方法库和近期论文形成有说服力、可审核的比较方案。

## 修复的问题

现有 GIST vs 平滑肌瘤方案只选 MEAN_MIL、AB_MIL，主要依据受限执行器当前支持范围；两档 patch 数不能增加模型参照的多样性。库内实现存在与正式执行器可运行是不同事实，不能用执行便利替代科学选型，也不能把库目录齐全视为训练就绪。

## 新流程

研究问题/候选数据 → 方法库只读盘点 + 近期文献主动检索 → 有来源的候选池与选入/排除理由 → 公平比较协议 → 完整拟议矩阵与资源估计 → 实现缺口 → 用户确定最终范围后进入正常执行准备/训练门禁。

前端入口：病理 MIL 研究 → 基线研究 → Benchmark 选型与比较方案。原生 Skill：`benchmark-design`，源文件 `skills/benchmark-design/SKILL.md`；正式提示词对实验规划和基线选择自动要求加载。旧迁移 Skill 清单不变。

- 默认近年窗口为截至研究日期的最近三年起点（例如 2026 年以 2023 年起检索），标明此假设；经典参照独立保留。搜索近期方法和已有比较研究，扩展到相关模态/任务，不只限病种关键词。
- 用 websearch 发现来源，webfetch 阅读原论文和作者官方实现。检索不足或仅见摘要时明确证据等级；固定特征聚合器比较与更换编码器/端到端比较分轨。
- method_inventory.py 只枚举文件/目录并记录来源摘要，不导入、执行或改写旧引擎。依赖、输入兼容性和执行器验收需另行核实。
- check_plan.py 检查本地引用、候选/状态字段、经典/近期覆盖或理由、矩阵算术和计划不得批准训练。结构有效不代表来源真实、科学充分或执行准备完成。
- 由研究 Agent 在自己的 plans/、outputs/ 生成新版本并登记；开发助手只改公共能力，保留旧研究材料。

## 网络能力与权限

OpenCode 原生 Exa 搜索已通过服务启动环境 `OPENCODE_ENABLE_EXA=1` 启用，使 DeepSeek 提供商能使用 websearch。官方依据：[OpenCode Web Search](https://opencode.ai/docs/tools/#websearch)。服务器已实测 Exa 初始化与搜索成功，Europe PMC/Crossref/arXiv 也可访问；后者通过已有 paper-lookup Skill 作备选。

websearch 与 webfetch 共用现有“网络访问”设置；ask/auto/custom 和显式 deny 同步映射，每回合冻结既有权限修订。没有新增网络权限开关或更改现有会话设置。不得向搜索服务发送患者明细或凭据。

## 工程验证

- skill-creator quick_validate 通过；后端全量 177 passed、1 skipped。覆盖网络 deny、结构盘点不执行代码、引用越界、矩阵算术、候选状态冲突及目录注册。
- 自有服务空闲检查后更新；原生发现新 Skill、DeepSeek tool schema 包含 websearch，正式 steps 仍为 64。
- 更新后、真实调用前，比对当前项目 1662 个文件的 SHA，均未改变。
- 真实行为验证使用现有项目与 DeepSeek Flash/high，通过正常应用回合提交；原 40 回合/7200 秒预算保留，调用前已用 4 回合/2955.623755 秒。结果见本文件后续记录及验收目录。

证据目录：`/data/bxn/PathoReason/acceptance/benchmark-chain-20261031/`。备份只用于源码回退和核对；不能恢复旧数据库抹掉新增研究证据。发布包使用独立版本目录，回退源码后须在空闲时重启自有运行时和应用。

## 真实模型行为验证与再次修复

使用同一个正式项目 `prj_f07d49680a6b475d91f2451260ca2040`、同一原生 session、DeepSeek Flash/high，通过正常应用入口完成 3 个回合。开发者没有写研究方案、候选表或改统计结果；研究目录的新文件与登记全部来自目标 Agent。开发干预包括公共层修复、提交验证任务，以及 5 次仅针对新方案/日志文件的 once 编辑批准；会话权限修订仍为 1。

| 回合 | 原生迭代 / 工具数 | 结果 |
|---|---:|---|
| turn_e62ad1223f764c7490d6ba008d783838 | 22 / 34 | 实际 4 次 websearch、10 次 webfetch，盘点 58 个方法，形成 v2：7 个选入候选。首次回答自报 8 次 webfetch 不准确，以原生记录 10 次为准。发现原文/代码等级混淆。 |
| turn_5fb9f0c3324a4ab88a0c6d2fbcd546b5 | 12 / 14 | 补读 4 篇 arXiv HTML，按收紧后的分级规则输出 v3；自行撤回“R2T 需要绝对坐标”的判断，将其纳入。仍明确 ABMIL/MEAN/MAX 正文未读、无源码级核验。 |
| turn_4636b18a7dd847bdbd48edd23ab47032 | 11 / 11 | 使用新 PDF helper；PMLR 下载超时保留失败回执，改用 arXiv 成功提取 16 页并读取方法段；补读 PMC 全文，输出 v4，并保留整数余数。 |

64 步本轮足够，没有增加步数。项目预算保持 40 回合 / 7200 秒；验证前 4 回合 / 2955.623755 秒，验证后 7 回合 / 3674.083527 秒。本次新增约 718.46 秒，包含权限等待与网络等待；费用未知，不记为 0。

### 公共层补强

1. 明确 `paper_access`（元数据/摘要/正文）与 `code_access`（未读/仓库首页/实现文件）。paper_and_code 需同时申报正文与实现文件级证据；附具体 evidence_notes。`source_review_complete` 仅汇总申报级别，仍需与原生轨迹核对。
2. 对输入需求的推断要求原论文/官方接口证据，不以“Transformer/位置编码”等名称推断需要额外坐标。
3. 新增 `fetch_paper.py`：完整下载过程限时 60 秒、20 MB；解析限时 30 秒、200 页、1 GiB 地址空间；独占新输出目录，保留 PDF/逐页文本/SHA/失败回执，无自动重试或覆盖。平台独立增加并锁定 pypdf 6.21.4，其余依赖版本不变。扫描件无文本时失败，不伪装为 OCR 成功。
4. 新增 `split_counts`：cohort=development+locked_test，各折 OOF 人数总和等于开发集。此人数检查不替代后续患者 ID 不重叠/全覆盖检查。
5. 修正盘点 helper 中门禁源码路径；初次验证快照原样保留，不代改研究快照。

PDF 卡点对应 OpenCode 1.18.33 上游实现：超时包围请求阶段，读取 response.arrayBuffer 在其后，PDF 随后被 TextDecoder 当文本返回；本次观测到原生请求长时间等待并返回二进制，不能作为正文阅读。采用通用 Skill 路由到有界下载/解析 helper，未修改上游二进制；并非宣称原生所有网络读取的超时问题已修复。来源：[上游 webfetch 实现](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/tool/webfetch.ts)、[pypdf 文本提取](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)。

### 最终证据与范围

v4 由 Agent 选入 MEAN、MAX、ABMIL、CLAM-SB、TransMIL、DTFD、MambaMIL、R2T；开发集 206、锁定测试 52，各折 OOF 为 42/41/41/41/41。拟议 120 次 CV 拟合 + 24 次最终拟合，24 次锁定测试推理另列；smoke 与敏感性实验另列。它是本项目的拟议方案，不是写入系统的固定模型名单。

- 结构检查通过；申报主矩阵论文均已读到正文，原生记录包含相应 HTML/PMC 内容、PDF 提取及正文检索。代码级别保持 repository_page/not_checked，没有冒称源码复现验收。
- 所有 8 个模型仍为 needs_adaptation。第三方实现一致性、输入/序列/采样适配、依赖、训练配置、公平调参和实际执行门禁仍需后续核验；检索不宣称穷尽领域，不能据此宣布论文科学审核通过。
- 原有 1662 个项目文件 SHA 未变化；v2、v3 结束时记录的文件 SHA 均未变化。`compute.json` 未变，real_training_authorized=false，无训练或新患者数据提取。
- 最终全量 183 passed、1 skipped（既有 Starlette 警告）；随后针对响应体停滞而非仅连接停滞细化夹具，2 个 PDF 测试通过。通用 PDF 工具另在独立验收目录完成真实公开 PDF 下载/15 页提取验证；Skill 最终 quick_validate 通过。
- 完整请求、源文件版本、原生工具证据、回合结果、测试记录、完整性与预算核对保存在验收目录。旧账本和失败证据均保留。

最终工作台成果：

- JSON 方案：`art_a7f7ee0245a13124dd83fb67f034c896`（outputs/benchmark-plan-v4.json）
- 可读方案：`art_77077e59294c4901afb067854fa21880`（outputs/benchmark-plan-v4.md）
- 来源日志：`art_46f34e8f50bb002e538b74abd2602d14`
- 库快照：`art_93d602bd6d1c51d6fe1d6bb2c34eebdc`

前端后续应先查看 v4，再推进官方实现核验和执行器适配；实际训练矩阵与预算需单独确定。当前没有将拟议 144 次拟合或 GPU 预算变为执行授权。
