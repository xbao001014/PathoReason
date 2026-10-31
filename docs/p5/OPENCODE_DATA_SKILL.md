# OpenCode 步数与病理数据 Skill 适配（2026-10-31）

发布：0.6.3-p5-data-skill。目标是改善 OpenCode + DeepSeek 的系统执行能力，不代替研究 Agent 修改数据处理结果。

## 调试边界

用户明确本 session 用于运行时、基模、工具和 Skill 适配。研究 Agent 的错误用于构造回归场景和改进通用规则；研究数据处理、结果改写、成果登记仍由研究 Agent 完成。此前开发者生成的 profile-v3 和审计成果属于外部干预，不能计为模型端到端验收成功。保留这些历史记录，不将其改写为模型产出。

本次部署前后 1344 个当前项目/成果文件与 19 张数据库原表内容一致；无新增模型回合、数据请求、训练或图像调用。

## 步数判断

OpenCode steps 是单回合模型迭代上限；达到上限后工具禁用，转为文字总结。它不是项目回合数，也不是精确供应商请求数。官方依据：https://opencode.ai/docs/agents/#max-steps 。

实测最近正式回合达到 16 次 assistant 迭代，约 311 秒，数据分析收尾和登记未完成；项目合计 2/40 回合、673.56574/7200 秒，仍有预算。16 步不适合包含协议读取、采集、关联分析、检查和收尾的正式工作，故将 pathoreason-formal.steps 调为 64；普通受限 Agent 的 6 步保持。

64 是有界的初始调试值，给多阶段单回合留出余量，不代表已证明最优。项目累计墙钟与回合预算、训练和图像预算、权限配置继续独立约束。后续观察真实回合：若频繁触顶且仍有实质进展，再评估；若反复空转则修复工具/策略而非继续提高上限。不得用开发者代做结果掩盖失败。

## 新 Skill

路径：skills/pathology-data-api/SKILL.md。原生名称 pathology-data-api；前端“病理 MIL 研究 → 数据与任务定义 → 病理接口数据接入”。使用原有 skills.paths 发现，无需复制到研究项目。

内容包括：
- 病种身份、接口版本和默认诊断过滤；2.0 的 PageIndex/PageSize/X-AiData-Key 与历史 Limit 协议分开。
- 患者/标本/切片层级、病人级富集的跨病种过滤、同患者同标本联合关联。
- 行数与唯一患者数、HE/非 HE、路径存在与全量可训练等口径区分。
- 原始响应字节、独立合并数组摘要、完整查询清单、中断结果核对。
- 已授权同一范围跨回合继续，预留核验/成果登记步骤，不机械重复请求批准。

scripts/fetch_pages.py 只负责可复用接口传输；研究 Agent 提供项目内查询计划，再按权限调用。每页保留 request/response/receipt，完成后写 rows.json/complete.json；同计划只复用摘要验证通过的完成组。中断不自动重发，触及页数上限不声明完成，非 2xx/API 错误保留响应证据。真实凭据只在进程中读取，不写入 Skill、计划或回执。重复分页放进批量计划，不让每页消耗一次模型思考步骤。

Skill 注册与历史 13 个迁移 Skill 分开，旧迁移清单不改。SKILL、参考和 helper 的 SHA 一并进入公开 SkillDefinition，证据范围仍为 contract_only，不能宣称真实研究已通过。

## 验证与部署

- skill-creator quick_validate 通过。
- 后端全量 133 passed、1 skipped（既有 Starlette 警告）；随后补全 HTTP 错误响应保存，最终 helper/目录检查 7 passed。
- 原生 OpenCode 1.18.33 在 runtime 目录和现有正式项目目录均实际返回 steps=64，并发现新 Skill。
- API Skill 目录、数据阶段导航、健康接口与正式入口版本一致；无需修改前端组件或样式。
- 空闲检查后通过 service.py 仅重启自有运行时和应用。旧科研服务与任务不操作。
- 本轮无真实 DeepSeek 推理；Skill 是否改善模型行为、64 步是否足够，要在后续真实前端回合观察。工程检查不代替模型行为验证。

证据：/data/bxn/PathoReason/acceptance/opencode-data-skill-20261031T054912Z/。
恢复时仅回退此次源文件/配置并在空闲后重启；不得覆盖研究数据库或回放回合。
