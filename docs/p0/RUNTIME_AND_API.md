# Runtime 版本、认证与 P1 接口合同

## 实机结果

Codex CLI 0.164.0，OpenCode 1.18.33，Node v24.22.1，npm 11.19.1，uv 0.13.6。P0 重新导出 320 个 Codex JSON Schema；必需方法验证通过，版本和 manifest 哈希在 config/runtime-lock.json。

对 Codex App Server 进行 initialize → initialized → account/read(refreshToken=false) → model/list 的短生命周期探测，未创建线程、未发起推理。account=null、requiresOpenaiAuth=true；服务器服务账户当前未认证。这是 P0 历史预检；用户后续改为服务器 OpenCode + DeepSeek、本机 Codex 验收，服务器只保留 Codex 登录入口，不再以认证成功作为 P1 前置条件。

model/list 的默认目录项为 gpt-6.1-sol、low effort，记为 P0 的 Codex 候选（不是当前服务器默认基模）；这是运行时目录结果，不是该账户已获模型访问的证明。真实调用前重新查询并核对可用性；目标不可用时报明确错误，不静默换模型。上下文限额未从此次探测取得，契约中保留 null。

官方 [Codex App Server 文档](https://learn.chatgpt.com/docs/app-server) 说明需先完成握手，并可由安装版导出对应协议。本文兼容性以本机 0.164.0 的导出和探测为准，避免把网站新字段直接当作旧版支持。

| 产品操作 | 固定版本方法 | 应用侧要求 |
|---|---|---|
| 新建/恢复 | thread/start、thread/resume | 持久绑定精确 ID；不使用全局 last |
| 发送/取消 | turn/start、turn/interrupt | request_key、实际派发状态、终态核对 |
| 模型/Skill | model/list、skills/list | 目录与产品 Skill 独立映射 |
| 压缩 | thread/compact/start | 能力声明；压缩不是领域数据迁移 |
| 授权/账户 | account/read 及原生 server requests | 原生工具授权与科研门禁分开 |

上述方法存在不代表每个行为均已端到端验收。OpenCode 本轮只核对版本，真实 Server/OpenAPI、持久会话与基础压缩改在 P1 接入，增强验证留在 P3；不复制 Codex thread ID 到 OpenCode。

## 当前环境与调用预算（计划 v0.3）

- 服务器 P1 主线为 OpenCode + DeepSeek。精确 model ID、endpoint、凭据引用、工具调用、窗口与用量需接入核对，P0 没有验证这些能力。
- Codex 开发验收只在本机开展，列为 P3 兼容项；服务器 P0 的版本/目录列表不能当作本机证据。
- 服务器保留 Codex 登录状态、发起登录、取消/失败提示和重新检查入口，登录方式按实际 CLI 支持实现。认证失败不阻止 OpenCode。
- OpenCode 持久 session、模型元数据与基础压缩从 P3 提前到 P1；P3 做长历史、多模型及跨引擎交接增强验收。
- P0 和本次改计划均为 0 推理、0 付费调用、0 GPU 作业。
- P1 建议单并发、最多 12 个显式回合、1200 秒墙钟、无自动重试。DeepSeek 计费账号/费用上限在接入时核对；不继承 paid_api_calls=0。配置金额 null 为未配置，不表示免费或无限额度。
- 回合不等于模型请求次数，压缩也可能产生用量；训练预算、科研门禁仍按旧业务合同。

## 应用 API（P1 实施，P0 尚未启动服务）

统一前缀 /api/v1，不覆盖原系统 /api/projects。服务器默认 runtime=opencode、provider=deepseek。Codex 登录/状态作为独立设置入口，路由与认证流程在 P1 根据实际协议细化；保留入口不代表服务器 Codex 推理已验收。

| 方法与路由 | 输入/输出合同 | 关键行为 |
|---|---|---|
| GET /skills | SkillDefinition[] | 平铺目录，显示实现/证据/当前就绪三维状态 |
| POST/GET /research-projects | 创建 title/objective；服务端分配 ResearchProject | resource binding 由服务器核验，不信任客户端已验证声明 |
| POST/GET /research-projects/{id}/conversations | Conversation | 项目归属核对 |
| GET /conversations/{id} | Conversation + messages + active turn | 恢复浏览器历史，不能触发推理 |
| POST /conversations/{id}/turns | request_key,text,skill_ref?,artifact_ids,model_selection | 先记录 queued；同键不同内容 409；未认证 503 auth_required；非就绪 Skill 422 |
| POST /turns/{id}/interrupt | turn ID | 幂等停止请求，不等价停止研究作业 |
| GET /conversations/{id}/events | SSE RuntimeEvent，支持 cursor | 服务端事件重放，不重派发动作 |
| GET /research-projects/{id}/events | SSE DomainEvent | 只更新业务状态视图 |
| GET /artifacts/{id}/content | 由 ArtifactIndex 解析 | 核对归属/清单/哈希；变化则 409 artifact_revision_changed；不接受绝对路径 |
| GET /models | ModelDescriptor[] | 未知窗口显式 null；可用与已验证分开 |

创建/行动请求 DTO 在 P1 落路由时细化，不能将整份服务端对象作为可任意写入的请求。P0 已定的关系和状态语义是其约束。

## 状态与错误

queued → running → completed/failed；running → interrupt_requested → interrupted。进程/网络状态不确定时进入 recovery_required，先核对原生状态；核对成功可恢复 running 或真实终态。只关闭浏览器不改变回合状态。

HTTP 404 资源不存在/不可访问，409 版本冲突或幂等内容不一致，422 输入或 Skill 前置条件不满足，503 runtime/auth unavailable。API 返回 code、公开说明、request_id、recoverable；日志不回传密钥或账户个人资料。

P1 在服务器 OpenCode + DeepSeek 上验收；P3 在本机 Codex 复用兼容用例并独立记录证据。P1 验收必须包含：真实回复、Skill 固定版本加载、停止真实回合、刷新与 SSE 重连、进程恢复、两项目隔离、成果定位、重复提交不重复派发。只通过 P0 这些静态合同不能勾选上述能力。
