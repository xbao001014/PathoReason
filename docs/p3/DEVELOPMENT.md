# P3 开发和恢复

服务器继续使用 P1/P2 启动方式。前端、上下文入口和既有业务从 `http://127.0.0.1:8520/` 访问；服务器原生 OpenCode 8522 仅 loopback，Codex 只留登录接口。

## 本机

源码 `/home/bbbxn/projects/PathoReason`；Python 3.14 独立 .venv，依赖锁与服务器一致。`scripts/setup_local.py` 检查已有本机 Codex 登录，创建 `~/.local/share/PathoReason`，引用本机 auth.json，初始化独立配置、Skill 和项目 MCP；再次运行不会重写已有原生配置。

```bash
cd /home/bbbxn/projects/PathoReason
.venv/bin/python scripts/setup_local.py
PYTHONPATH=src .venv/bin/python scripts/service.py start
PYTHONPATH=src .venv/bin/python scripts/service.py status
```

本机应用 `http://127.0.0.1:8530/`。`restart-app` / `stop` 只处理拥有的 PID+启动身份。Codex App Server 随本机应用退出；活动回合应先停止，未知派发仅核对。不能删除 codex_calls、应用 Turn 或原生 session 文件让动作重跑。

本机配置 `config/pathoreason.local.json` 被忽略，不能同步覆盖服务器同名文件。不要同步本机 auth.json 到服务器。服务器 credential_file 与本机登录引用互不替代。默认数据根校验在服务器仍要求独立 `/data` 挂载；本机仅允许专属 `~/.local/share/PathoReason`，没有放宽服务器规则。

## 上下文和模型

对话底部“上下文与交接”可查看最近原生窗口、累计用量、手动压缩记录，或导入/导出快照。压缩产生模型请求；停止/错误/费用未知均按实际记录。压缩结果未知时点“核对压缩结果”，只读核对原生标识，不再次调用模型；仍未知可导出快照并在新会话继续。

本机模型允许列表在 local config 的 codex.models；目录与有效窗口来自本机 model/list、models_cache，新增型号须重新核对权限、工具和窗口。OpenCode 的 DeepSeek 模型在 config/opencode.json 配置；不可把 unknown 限额填为猜测值。新增 provider 还需要独立的凭据适配，目前不会因 DeepSeek 已配置就自动开放其他 provider。

模型切换只影响下一回合。跨环境用导出/导入，不复制数据库或 native ID。文件最大 3 MB（成果字节总额 2 MB），只承载目标、约束及成果，不是业务授权。重复导入同一快照返回同一个导入结果。

## 验证与回退

```bash
PYTHONPATH=src .venv/bin/python scripts/export_web_types.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q
npm run build --prefix apps/web
PYTHONPATH=src .venv/bin/python scripts/verify_p3.py
```

最后一条只读取已存在的验收数据，不发起推理、压缩或研究。不要把 acceptance 目录中的 live.py/server_live.py 当作日常检查反复运行。

服务器升级前备份位于 `acceptance/p3-20261030/before-p3-source.tar.gz` 与 `before-p3.sqlite3`；SQLite 备份不等于完整运行时备份。恢复必须同时保留 P3 新增原生存储、应用状态、成果与研究账本，不可直接覆盖活跃数据退回旧数据库而丢失新增回合。回退界面/应用源码前先停止拥有的应用并保留 P3 新数据；OpenCode 与旧真实服务均不因 UI 回退而重启。

服务器验收额度现已 12/12；下一阶段如需新增模型调用，应按新阶段明确并记录预算，保留累计账本。P3 不提前实施 P4 的领域迁移或扩展真实科研计算范围。
