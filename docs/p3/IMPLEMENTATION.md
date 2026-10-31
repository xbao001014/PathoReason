# P3 实施记录

P3 接通本机 Codex 与服务器 OpenCode 的共同会话界面，并新增模型窗口检查、原生压缩、上下文取数和跨环境快照交接。研究业务继续由服务器 OpenCode 承担；本机 Codex 本轮验收范围为只读研究讨论、Skill、成果引用和上下文工具。

## 环境与入口

| 环境 | 应用入口 | 引擎与模型 | 数据 |
|---|---|---|---|
| bxn-server | SSH 转发后 `http://127.0.0.1:8520/` | OpenCode 1.18.33 / deepseek-v4-pro | `/data/bxn/PathoReason` |
| 本机 | `http://127.0.0.1:8530/` | Codex 0.165.0 / gpt-6.1-sol、gpt-6-luna | `/home/bbbxn/.local/share/PathoReason` |

本机源码位于 `/home/bbbxn/projects/PathoReason`，是服务器当前源码的独立开发副本。独立 CODEX_HOME 下仅引用本机原有登录文件，不复制服务器凭据、数据库或原生会话。原生配置不继承用户其他 MCP、项目指令或可写 shell；仅启用项目只读 MCP。服务器 Codex 仍为登录接口，不能据配置误启推理。

## 运行时与恢复

- `codex_runtime.py` 使用 App Server stdio 的 initialize、account/read、model/list、thread/start/resume/read、turn/start/interrupt、原生公开文本事件和 thread/compact/start；协议来自本机 0.165.0 生成的 JSON Schema。
- 复用项目、会话、Turn、公开事件、SkillInvocation 和成果 API。适配器只归一化公开正文、工具名称/状态、用量和压缩证据；不向公共 API 暴露推理正文、工具原始参数/返回或凭据。
- 使用稳定 clientUserMessageId，派发前落盘、返回后绑定 native turn；回执丢失以原生 userMessage.clientId 核对。未知结果只核对，不重发原用户请求。
- Codex App Server 是本机应用的子进程；应用停止可能中断生成，恢复时读取原线程的实际终态，后续回合 resume 同一线程。OpenCode 原生服务独立运行，应用重启不会重启它。这两个生命周期不混称为“后台生成永远继续”。
- 结果解读 Skill 用显式 skill input 加载，内容摘要冻结。当前项目只读 MCP 按单个活动回合、project_id、成果归属和 SHA256 校验；返回限额 12,000 字符，并标记裁剪。服务器原有 P2 业务 MCP 及幂等、revision、预算、后续回合确认门禁保持。

## 模型与上下文

- ModelDescriptor 复用 P0 契约。模型目录不当作账户授权；成功调用才记 inference_verified。本机允许列表为两种已核对型号。上下文采用本机目录有效窗口比例 95%：475,000 / 258,400；input/output 独立限额未报告则保留 null。
- 服务器继续读取受控 OpenCode 配置。DeepSeek provider 下可配置模型；新增 provider 未接入凭据解析前标记 unavailable，不冒称就绪。
- 切换模型只影响后续回合，冻结所选 descriptor 和配置摘要；本机另保存原生配置文件 digest。未知窗口、未知工具支持、保守输入估计超限或未知当前上下文下切换模型均拒绝派发，给出压缩/交接提示。估计包括输入、项目目标、成果摘录及余量，不把估计当原生 token 计量。
- 手动压缩单独记录请求键、状态、开始/结束与原生证据，有独立有界额度；重复请求键不重复压缩。失败不删历史；超时/断流保留 recovery_required，核对原生压缩标识后才能解锁。无法确认时可通过快照开启新会话，绝不盲目补发摘要。
- 浏览器聊天历史保存在应用数据库，模型上下文由引擎管理，研究事实来自领域账本和核验成果。压缩不会清空聊天记录、修改研究状态或重新派发业务动作。工具输出裁剪仅截短单次工具内容，不等于摘要压缩。
- UI 的上下文数值是最近一次原生调用报告/估计；累计输入输出另列。Codex 显示原生 last 与 total，OpenCode 当前只报告回合与最近调用估算；费用未报告显示“未报告”，不显示为零。中断回合没有完整用量时保留未知。

## 跨环境交接

对话底部新增“上下文与交接”。导出/导入采用 `pathoreason.handoff/1`，包含项目目标、约束、成果元数据及不超过 2 MB 的成果字节。摘要/账本中的决定、预算和来源随核验成果保留；不传凭据、native ID 或可执行指令。

导入先验证契约、包 digest、文件 SHA 和大小，再创建独立项目/会话，记录原环境、引擎、项目与成果 ID 映射；显示历史分界。重复同一快照返回原导入结果。原成果字节不改写，来源引用保留；包哈希证明完整性，不代表科学批准或对外部包来源的独立背书。本轮实际为服务器 P2 四份合成成果 → 本机 Codex，未回传研究修改。

## 设计与 Schema

遵循 design.md，保留固定导航、可折叠项目栏、卡片留白与状态色。上下文面板以最近窗口数值为主，模型、累计用量和费用为支撑信息；补充口径放在可键盘访问的 info。服务器和本机显示各自引擎/环境；本机不显示无法执行的合成入口。

P0 16 个契约文件未重写。新增本机绑定 `pathoreason.runtime/2`、交接契约、上下文 API 投影，以及适配器持久化表；详见 [Schema 影响](SCHEMA_IMPACT.md)。P4 的科研领域 Schema 迁移尚未开始。

依据：[Codex App Server](https://developers.openai.com/codex/app-server)；本机生成协议与原生实际事件优先于旧版样例。未使用新的 API key，也未更换用户已有登录。
