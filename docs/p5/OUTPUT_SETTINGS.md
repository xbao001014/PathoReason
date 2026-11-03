# 单次输出设置与截断恢复

2026-11-03，`0.6.25-p5-output-settings`。

## 真实失败

用户选择「固化五阶段结论」后，DeepSeek Flash/high 的原生回执 `finish=length`，reasoning=8192、output=0，无工具调用。项目余量仍存在、上下文未耗尽；失败与预算均保留。旧固定 8192 单次请求限制与高思考任务不匹配。

## 已实现

- 输入框工具栏独立「输出」设置：8K / 32K / 64K（8192 / 32768 / 65536），默认保持 8K；选择按对话和基模保存在浏览器，发送时冻结到回合配置、模型描述与目标请求模板。恢复成功同步工具栏配置，避免实际接续用 32K 而界面仍显示 8K。选值本身不派发请求。
- 输入 token 预留随所选输出上限一起计算；超过上下文可用空间在建立回合前拒绝。未传新参数的旧调用保留原默认行为；其他引擎不冒充支持。
- 阻塞进度栏显示**最后一次模型响应**的思考 token、正文 token 和冻结上限，区别同一 Agent 回合多个模型响应的累计 token。新用量来自原生统计；历史失败通过只读原生回执补充显示，不改历史 usage。不可用显示「未记录」，不补零、不暴露思考正文。
- 恢复时一次选择输出上限和思考强度，再点击「按所选设置恢复」。沿用目标 revision/CAS，重复请求不重复派发；不自动降思考或提高上限，再次截断仍立即 blocked。恢复不重置目标回合、项目额度、失败、权限、训练预算或已冻结配置。
- 通用目标提示增加按可核验节点交付：只读所需证据、保存小型产物、提交 continue 检查点再接续；截断后先核对文件与工具回执，不重放已完成/未知操作。这是模型执行指引，是否遵循须另做真实模型验证。

## 原生适配与能力边界

配置 `config/output-limits.json` 区分上游能力上限（当前官方文档 393216）、平台开放的有界档位和默认值。配置能力不等于本项目上调已获授权的限额。

OpenCode 的请求上限由模型配置决定，普通 variant 不直接覆盖 maxOutputTokens。平台配置内部输出 profile，并通过 `id` 映射到相同上游基模；产品模型列表隐藏内部 profile。适配器核验已加载的 profile 上限与上游 ID，原生配置未加载时拒绝派发。

真实原生探针发现 OpenCode 额外默认截到 **32000**：初次 32768 探针失败。尝试 chat.params 插件在服务 `--pure` 模式无效，最终未引入插件、未放宽纯净模式。改用原生 `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX=65536` 作为**执行引擎天花板**；普通模型仍请求 8192，只有用户选定的 profile 请求更大值。服务启动记录保存已加载天花板，避免源码已改而引擎仍截断。

配置依据：
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://raw.githubusercontent.com/anomalyco/opencode/v1.18.33/packages/opencode/src/provider/transform.ts
- https://raw.githubusercontent.com/anomalyco/opencode/v1.18.33/packages/opencode/src/effect/runtime-flags.ts

契约为增量字段与只读接口 `GET /api/v2/models/output`、`GET /api/v2/turns/{tid}/output`；本次 OpenAPI/JSON Schema 在 `contracts/p5-output-settings/` 和 `api-p5-output-settings.openapi.json`，历史快照保持。

## 分层验证与发布

- 工程：最初 51 项定向通过；全量 447 通过、3 跳过；补充 HTTP 与上下文预留覆盖后最终定向 20 通过（包含部分既有定向，不能相加）。TypeScript/Vite 构建通过。
- 原生：独立 OpenCode 1.18.33、假凭据、loopback 模型端点捕获五组请求，确认两基模的 8K/32K/64K 与 high/low/none 按选择生效，基模 ID 不变，没有外部模型调用。保留 32000 天花板、重复夹具消息 ID 及 pure 插件无效的失败日志。
- 浏览器：1440/390/320 三宽度验证旧失败用量显示、默认 8K、显式选值恢复、保持 high、恢复后工具栏同步、修改偏好不发送、过期 revision 拒绝；真实 API 写请求为 0。保留一次 TypeScript 类型导出修正记录。
- 真实模型行为：**本次未新增调用**。分段交付效果及扩容后的完成率待用户选择数值后验证；不将工程/原生模拟端点通过称为模型或科学验收。
- 发布时核对全局模型回合、原生会话、权限和上下文操作空闲，再停应用、重载原生引擎并启动应用；训练执行器保持，原生会话 ID/数据库和原始产物保留。发布脚本记录前后身份、研究文件/表摘要和当前额度，原生目录/Skill 与输出 profile 均只读复核。

证据：`/data/bxn/PathoReason/acceptance/output-settings-20261103/`。发布及线上验证以该目录 release.json、browser-live.json 为准。当前目标保持 blocked，未自动恢复、未增加项目预算、未启动训练。
