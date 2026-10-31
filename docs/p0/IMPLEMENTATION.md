# PathoReason P0 实施交付

日期：2026-10-30。状态：**P0 完成；P1–P5 未开始。**

**后续修订：** 服务器 OpenCode + DeepSeek 为主线，本机承担 Codex 验收；服务器保留登录入口，Codex 未登录不再阻塞主线。见 [修订说明](../PLAN_REVISION_RUNTIME_20261030.md)。下面的预检/测试保持 P0 历史含义。

项目位置：bxn-server:/home/bxn/projects/PathoReason。P0 已将规划转为可验证的项目基线、公共契约和首轮来源映射；尚未启动新前后端或真实 Agent 会话。

## 交付清单

| P0 计划项 | 实际交付 | 结果 |
|---|---|---|
| 新旧源码关系、依赖与许可 | [复用清单](REUSE_MAP.md)，旧源码哈希/导入清单 | 明确选择性前端迁移、旧业务适配，未整仓复制；旧仓库无根许可文件的情况已记录 |
| 应用结构、包管理、Git、端口与数据 | [架构决策](ARCHITECTURE.md)、独立 .venv、依赖锁、Git main、配置模板和存储入口 | 独立数据根 /data/bxn/PathoReason；8520/8521/8522 检查可用但未启动 |
| 首轮字段流 | [CESC 字段流](FIELD_FLOW.md)、contracts/examples/cesc-reading.json | 3 个真实成果引用、1 个代表性旧实验观察；新会话为明确标注的离线样例 |
| 最小实体与事件契约 | src/pathoreason/contracts.py、contracts/v1/ | 16 个可导出模型 Schema；包括项目、Skill、调用、会话、回合、消息、绑定、上下文、成果、模型、两类事件、行动意图及验收包 |
| 旧身份与修订映射 | src/pathoreason/legacy.py | 保留原 adapter/resource_id；单文件哈希与观察 manifest revision 分开；旧冻结模板身份保持 |
| runtime、模型、认证与预算 | config/runtime-lock.json、[Runtime/API 合同](RUNTIME_AND_API.md) | CLI 版本固定、320 个协议文件重新导出、9 个必需方法存在；认证与真实调用条件明确 |

## 验证结果

- 最终 54 项测试全部通过（0.57 秒）：结构 Schema、Pydantic 跨对象校验、项目/会话归属、请求键去重、活动回合约束、模型未知限额、来源与 Skill 摘要、事件权威、文件变化/路径越界/符号链接、旧实验观察和存储拒绝条件。
- 14 项实机兼容检查全部通过：旧 Git HEAD/状态、选定源码字节、3 份成果、旧实验观察 manifest、原规划快照、旧服务同进程 ready 与空闲状态、3 个新端口。
- 新 Python 环境独立安装锁定依赖，editable 包构建/安装成功；旧虚拟环境未修改。
- 0 次推理、0 个训练任务、0 次旧业务变更请求。未建立新应用数据库，未重启旧工作台、未发布新页面。

证据目录：/data/bxn/PathoReason/acceptance/p0-20261030/。

主要文件：verification.json、pytest-final.xml、baseline.json、source-inventory.json、source-artifacts.json、legacy-experiment-observation.json、runtime-probe.json（账户信息已最小化）、protocol-check.json、codex-protocol-manifest.json、dependencies.json、package-install.log、ready-before.json、ready-after.json。

## 原 P0 交付时的 P1 设想（已被 v0.3 取代）

用户已明确选择“沿用服务器已有 Codex 登录”。本轮用应用将采用的 bxn 服务账户探测，account=null、requiresOpenaiAuth=true；当前登录不可用，model/list 目录可见不代表可推理。P1 开始真实会话前需要在该服务身份下完成登录/核验。未读取或复制其他机器凭据，未替换为付费 API。

首轮候选模型由本机 model/list 得到 gpt-6.1-sol、low effort。真实可用性尚未验证，上下文窗口保留未知。P1 验收配置已准备为最多 12 个显式回合、1200 秒墙钟、单并发、无自动重试；本轮没有执行该预算。

下一阶段按 P1 实施：搭建前后端与 SQLite 会话存储，接 Codex App Server，落 Skills 与模型选择、流式对话/取消/恢复、真实成果预览及引用。最先用已有 CESC 结果解读进行真实验收；P2 才接研究业务执行。

## 解释边界

这些测试证明 P0 契约与选定兼容路径，不证明所有旧数据库或科学结论正确。legacy bytes_verified 仅表示来源字节一致；CESC 开发准入、完整目标与作者审阅状态分别保留。原生 session 恢复、事件事务、运行隔离和真实模型质量均待 P1/P3 验证。

本目录已有独立 Git，未配置远端、未推送；P0 文件保留为可审阅的未提交变更。运行证据和本地配置不进入版本控制。
