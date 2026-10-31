# P0 架构与运行基线

日期：2026-10-30。决策版本：2（按计划 v0.3 调整环境）。范围：PathoReason 新会话层及旧研究系统的适配边界。P1–P5 尚未实施。

## 已定决策

| 项目 | 决定 |
|---|---|
| 源码 | 独立目录、独立 Git 主分支 main；不整仓复制、不做旧仓库子模块、不改旧工作树 |
| Python | 3.14.4；独立 .venv；uv 0.13.6；pyproject.toml 与带 SHA256 的 requirements.lock；P0 只安装契约与验证依赖 |
| 应用服务 | P1 在 src/pathoreason 下建立 FastAPI 服务、会话服务、runtime/legacy adapter；FastAPI 0.141.1、Uvicorn 0.54.0 为已核对基线，P1 加入依赖锁 |
| 前端 | P1 建 apps/web，React 18.3.1 / TypeScript 5.7.3 / Vite 6.4.3；npm 11.19.1，npm ci + package-lock.json；完整版本在 config/runtime-lock.json |
| 公共类型 | src/pathoreason/contracts.py 为新数据模型权威，导出 contracts/v1 JSON Schema。P1 建前端时从这些 Schema 生成类型，不再手写镜像；关系校验仍由服务端实施 |
| 状态存储 | P1 使用 /data/bxn/PathoReason/state/pathoreason.sqlite3，单机 SQLite WAL + foreign_keys；短事务，不在模型调用期间持有写事务；schema_migrations 独立版本 |
| 运行数据 | /data/bxn/PathoReason，配置入口 config/pathoreason.local.json；示例配置可提交，local 文件忽略 |
| 项目粒度 | 一个 ResearchProject 容纳多个会话、多个旧实验与稿件；不把 conversation 当实验 |
| 原系统 | /home/bxn/projects/auto-research 保留运行；已有实验 ID、冻结模板、预算和研究判定不迁移、不改写 |
| 模型认证 | 服务器 OpenCode + DeepSeek 服务端凭据；本机 Codex 登录；服务器保留 Codex 登录接口。凭据独立，不写入消息或模板 |
| 产品 Skills | 首版内置 7 类一层场景目录；P1 首先接结果解读；其余显示具体未就绪原因，不按文件存在判为可执行 |

## 模块分工

- src/pathoreason/contracts.py：公共契约和关系不变量，P0 已实现。
- src/pathoreason/legacy.py：精确文件来源映射、字节核验、旧实验只读观察，P0 已实现；不导入旧业务模型进行补默认值回写。
- src/pathoreason/storage.py：新输出目录检查与分配，P0 已实现；数据盘不可用则失败。
- P1 新增 api/、services/、persistence/、runtime/opencode.py、apps/web，并保留服务器 Codex 登录入口；P2 增 legacy 业务桥；P3 在本机开发与验收 runtime/codex.py 兼容。
- 浏览器只访问 PathoReason API。原生 thread/session ID、服务器凭据和文件绝对路径由服务端管理。前端预览/下载用 artifact ID，不接受任意磁盘路径。
- P1 通过固定文件清单提供只读旧成果。P2 的写操作通过受控旧业务接口保留权限、revision、幂等、预算与门禁；不由新服务直接改旧 SQLite 或 state.json。

## 端口和目录

| 用途 | 路径或地址 | P0 状态 |
|---|---|---|
| 后端及正式同源前端 | 127.0.0.1:8520 | 空闲检查通过；未启动 |
| Vite 开发 | 127.0.0.1:8521，转发 /api 至 8520 | 空闲检查通过；未启动 |
| OpenCode 内部服务 | 127.0.0.1:8522 | P1 主线，启动前再检查 |
| Codex | 应用托管 stdio 子进程 | 已做短生命周期握手预检；无常驻服务 |
| state/ | 应用数据库与迁移记录 | P0 未建数据库 |
| runtime/ | 应用管理的 runtime 命名空间/恢复元数据 | P1 定义实际 native 存储绑定 |
| projects/ | 每项目受控工作区 | 不链接整个旧数据根目录 |
| artifacts/ | 新会话报告、图件及导出 | 与只读旧成果引用分离 |
| acceptance/、scratch/、cache/、releases/ | 验收、临时测试、可重建缓存、发布 | 数据盘独立保存 |

端口是配置约定，不是系统预留；每次启动检查占用并失败退出，不能杀占用进程或自动改端口。本轮旧服务 8002、8513、8514 保持原状态。默认通过 SSH 转发访问；正式 VPN 入口留待部署阶段。

服务器 P1 使用 OpenCode 持久 session + DeepSeek，本机 Codex 使用本机登录与精确 thread ID；服务器 Codex 登录不阻塞主线。两边均不依赖临时 HOME 保持会话，不扫描操作者其他线程。runtime/ 的应用绑定元数据不等于已迁移原生全部状态。跨引擎/跨环境新建会话并交接上下文。

本机验收是用户最新指令允许的开发环境；以上路径表仅适用于服务器。当前存储校验与 auth_ref 需按环境扩展，见 [修订说明](../PLAN_REVISION_RUNTIME_20261030.md)。

## 持久化约束（P1 实施合同）

表域：research_projects、project_resources、conversations、runtime_bindings、turns、message_parts、skill_definitions、skill_invocations、context_snapshots、artifacts、runtime_events、domain_events、execution_intents、schema_migrations。

- 资源与会话以 project_id 外键约束；native identity 唯一键为 runtime + storage_namespace + native_session_id。
- 同会话只有一个 active/recovery_required 回合；request_key 在会话内唯一。复发同键同内容返回原 turn，不再调用模型；同键不同内容返回 409。
- 事件分 runtime 与 domain 流；数据库按流原子分配 seq。source_event_key 在流内去重；先提交再推 SSE。Last-Event-ID 为 stream + seq；缺失保留窗口时返回需获取快照的明确错误。
- 崩溃后的未知派发结果进入 recovery_required；先 query/resume 旧 native turn，不能盲目重发 turn/start 或业务命令。
- RuntimeEvent 只存公开回复、工具摘要、用量和错误；不要求存储原始推理。DomainEvent 由实际业务观察/回执产生，模型说“完成”不产生科研状态更新。
- ExecutionIntent 幂等键按 project + target + operation + key 唯一，expected_revision 与业务当前版本核对。数据库请求收据与派发使用 outbox/reconciliation 方式，P2 以故障注入验证。
- 停止回合为 interrupt_requested，收到原生终态才变 interrupted。停止后台研究作业是另一类带目标的业务操作。
- 旧数据与新数据库分别备份。P0 无数据迁移，回退只需停用未来新入口，旧系统仍保留。

## P0 验证边界

离线样例校验、真实证据文件哈希与协议预检不代表 P1 服务、真实推理、断线恢复、数据库事务或操作系统读写隔离已经通过。本轮不开放网络监听，不调用训练，不使用封存数据。
