# 执行计划 v0.3：按环境分配运行时与验收

日期：2026-10-30。依据：用户要求服务器主要进行 OpenCode + DeepSeek 开发验收，Codex 开发验收只在本机进行，服务器保留登录接口。本轮只修改计划与配置约定，未开始 P1。

## 环境责任

| 环境 | 引擎与模型 | 任务 | 验证状态 |
|---|---|---|---|
| bxn-server | OpenCode + DeepSeek | P1 真实对话、Skills、持久化/恢复/取消、成果引用；P2 研究业务闭环 | 待实施；型号、endpoint、凭据、工具支持与窗口需接入核对 |
| 本机 /home/bbbxn | Codex CLI App Server + 本机可用模型 | Codex 适配开发与真实兼容验收 | 待实施；本机版本、认证与模型权限未核对 |
| bxn-server 的 Codex 入口 | 保留适配和登录入口 | 登录状态、发起登录、取消/失败提示与重新检查 | 不要求服务器 Codex 登录/推理成功才能通过主线验收 |

两个环境使用同一套应用契约和对应版本的源码；凭据、native session、运行数据库各自隔离。测试证据必须注明环境、引擎、模型和版本，不能互相替代。

## 阶段变更

- P0 已完成，历史协议预检、离线 Codex 样例与测试结果保持原义，不改写成 OpenCode 验收。
- P1 改为服务器 OpenCode + DeepSeek 真会话与 Skills。原 P3 的持久 session、模型元数据、基础上下文用量/压缩配置与错误反馈提前至 P1；同时保留服务器 Codex 登录入口。
- P2 保持对话驱动原研究流程，使用服务器 OpenCode + DeepSeek 验收，不依赖服务器 Codex 登录。
- P3 改为本机 Codex 兼容、自选基模与上下文增强。在本机完成 Codex 真会话、恢复、取消、Skills 验收；多模型切换、压缩压力场景和跨引擎交接分别验证。
- P4/P5 的 Schema 调整、历史兼容与正式切换范围不变；最终按环境列出已验证能力。

## 实施时必须处理的差异

1. OpenCode 接入时核对固定版本的实际 Server 协议；DeepSeek 精确 model ID、endpoint、密钥引用、工具调用和窗口限额不得按名称猜测。
2. 服务器使用持久 session 存储，绑定 project/conversation；不继承旧单次 runner 的临时 HOME/XDG。
3. P1 包含基础上下文管理：用量来源、未知窗口提示、原生压缩配置与错误可见、研究事实可重新取数。长历史/多模型/跨引擎增强验证在 P3。
4. 服务器 Codex 登录入口按实际 CLI 支持的登录方式实现。未登录或暂不可用时说明状态，不阻止 OpenCode 会话，不显示 Codex 已可执行。
5. 当前 storage.py 的 /data/bxn 限制、服务器二进制路径和 RuntimeBinding.auth_ref 的 server 命名是 P0 基线。本机适配需独立配置、数据目录和认证引用；不能直接运行远端配置或宣称本机已兼容。
6. 本机 Codex 使用有清单/哈希的选定成果副本或明确的只读成果接口，不整库复制服务器数据，不搬运凭据或复用跨环境 native session ID。

## 预算与证据

本轮 0 模型调用。首轮建议仍为单并发、最多 12 个显式回合、1200 秒墙钟、无自动重试。回合数不是服务商请求次数；后台压缩也可能产生费用。DeepSeek 不沿用此前 Codex 场景的 paid_api_calls=0 假设；实际账号计费和费用上限在接入时核对，配置金额 null 表示未配置，不表示免费或无限额度。

当前配置默认服务器 OpenCode/DeepSeek，但 model、endpoint、credential_ref 留空待核对；没有写入密钥或启动服务。P0 数据盘证据和 docs/references 快照不变，后续验收使用新目录。当前计划以 EXECUTION_PLAN.md v0.3 为准。
