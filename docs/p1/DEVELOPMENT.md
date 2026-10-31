# P1 运行与开发说明

服务器源码：`/home/bxn/projects/PathoReason`。运行状态、成果、原生会话与日志：`/data/bxn/PathoReason`。仅监听服务器回环地址，当前使用 SSH 转发访问。

## 启动和访问

```bash
cd /home/bxn/projects/PathoReason
.venv/bin/python scripts/service.py start
.venv/bin/python scripts/service.py status
```

本机建立转发后访问 `http://127.0.0.1:8520/`：

```bash
ssh -N -L 127.0.0.1:8520:127.0.0.1:8520 bxn-server
```

本次已在当前本机建立该转发。8520 同时提供生产前端和 API；8522 为受 HTTP Basic 保护的 OpenCode 私有服务，不需要转发；8521 保留为前端开发端口。没有切换或停止旧工作台。

服务管理只针对自己的 PID 与进程启动标识：`restart-app`、`restart-runtime`、`stop`。应用重启时原生引擎继续运行，启动后核对已有回合；不应在推理中主动重启原生引擎。设置页重载会先拒绝存在活动回合的情况。服务当前是独立后台进程，未注册机器重启自动启动。

## DeepSeek 凭据

当前凭据已配置并通过真实调用。后续更换时，将 `DEEPSEEK_API_KEY=...` 写入服务器 `/home/bxn/.config/pathoreason/credentials.env`，文件权限设为 `600`；模板为 `config/credentials.env.example`。当前文件已存在且权限为 600。不要将真实值提交进仓库或贴入对话。

文件是简单的 KEY=value 格式，不执行 shell 展开；也兼容服务启动环境中的同名变量。随后在设置页点“重新检查连接”，或执行：

```bash
.venv/bin/python scripts/service.py restart-runtime
```

界面显示已连接且凭据已加载后，才可开始真实验收。主线固定为 `deepseek-direct/deepseek-v4-pro`。配置存在不代表供应商认证/余额/型号已通过验证，本次真实调用已通过，记录见 LIVE_VALIDATION.md。

配置见 `config/opencode.json`。1M 上下文基于供应商模型文档，output 8192 为本应用限制。初轮 `p1_test_limits` 为数据库全局累计 12 回合、1200 秒、并发 1；不是每会话各 12 回合。无自动应用请求重试，原生 retry 状态会中止。尚未配置金额限制；费用按供应商账单核对。遇到额度耗尽，应检查记录后显式调整配置，不能删除历史绕过检查。

## 工具分类

左侧三入口固定保留。修改 `config/skill-navigation.json` 可增加研究类别与流程阶段；`skill_ids` 必须指向真实目录项，跨阶段支持项用 `cross_stage` 标记。该文件只管理导航，不推进业务状态；新增分类后同步生成 API 类型并检查浏览器布局。

## 开发与测试

```bash
cd /home/bxn/projects/PathoReason
export PYTHONPATH="$PWD/src"
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python scripts/export_web_types.py
.venv/bin/python -m pytest -q --basetemp=/data/bxn/PathoReason/scratch/<唯一测试目录>
```

测试 basetemp 必须使用全新目录，pytest 会清理该目录。依赖锁为 `requirements.lock` 与 `apps/web/package-lock.json`，不要更新旧项目环境。Python 环境恢复方法沿用 P0 DEVELOPMENT。

```bash
cd /home/bxn/projects/PathoReason/apps/web
export PATH="/home/bxn/projects/auto-research/.venv/bin:$PATH"
npm ci
npm run build
cd /home/bxn/projects/PathoReason
.venv/bin/python scripts/service.py restart-app
```

OpenAPI 在 `contracts/api-p1.openapi.json`，前端类型在 `apps/web/src/generated.ts`。服务源码、Skill 和权限改变后，重新生成相关契约、测试与构建，并在没有活动回合时更新原生服务。不要在活动回合中编辑运行配置或 Skill。

浏览器自动检查脚本与截图位于验收目录的 `browser/`；当前脚本在本机使用已有 Playwright/Chromium，通过 SSH 转发访问。后端 FakeRuntime 测试使用独立 SQLite 与假凭据，测试数据不进入正式应用。

## 状态与恢复

- 应用：`state/pathoreason.sqlite3`，保存项目、会话、回合、事件、配置快照、上下文、SkillInvocation、原生绑定和成果索引。
- 原生引擎：`runtime/opencode/{config,data,cache,state}`。它与应用数据库需要成对保留；不能仅复制一个文件并假设会话完整恢复。
- 生成报告：`artifacts/<project_id>/<turn_id>.md`；原始 CESC 只记录引用与哈希。
- 运行日志和服务回执：`runtime/control/`。凭据不会通过应用 API 返回。
- 模型派发结果不明确时，回合标记“需要核对连接”，点击“核对并恢复”只查询原生状态，不再提交同一用户消息。若仍无法确定，保持该状态直到人工核对；不要直接重发。
- 备份应用数据库时使用 SQLite backup API，或先停服务再备份完整状态；备份应同时覆盖原生存储、生成报告与有效配置。恢复后检查绑定、原生成果哈希及活动回合，再开放发送。P5 会补正式备份/发布流程。

## 外部协议依据

- [OpenCode Server API](https://opencode.ai/docs/server/)，本机安装版本 `/doc` 快照另存验收目录。
- [DeepSeek 模型说明](https://api-docs.deepseek.com/quick_start/pricing/)，实际型号可用性待真实凭据验证。
- [Codex App Server](https://learn.chatgpt.com/docs/app-server)：服务器仅接认证方法；本机真会话在 P3。

最新 P1 真验收：docs/p1/LIVE_VALIDATION.md。当前共 6 个真实应用回合，71 项后端回归通过；无推理首轮证据继续保留。原生事件订阅丢失时以已保存内容及最终快照核对，不凭断流重发用户请求。
