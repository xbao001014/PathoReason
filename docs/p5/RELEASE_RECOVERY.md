# P5 发布、备份与恢复

发布标识：`0.6.0-p5-entry`。服务器源码 `/home/bxn/projects/PathoReason`；应用端口 8520、OpenCode 8522；仅监听 loopback。旧 8514 演示与 8002 研究服务保留，本窗口没有停用旧入口。用户经已有 SSH 转发访问 http://127.0.0.1:8520/ 。本机 Codex 8530 不在本次服务器发布切换范围。

## 可追溯发布

`/data/bxn/PathoReason/releases/pathoreason-0.6.0-p5-entry/` 包含 source.tar.gz 和 manifest.json；后者逐文件记录 SHA256 和压缩包摘要，范围含源码、生产前端、Skill 全资源、契约与文档。不含运行数据、私有配置、凭据、.venv 或 .tools。发布包在独立临时目录展开并逐文件核对。重建 Python 使用 requirements.lock；前端使用 package-lock.json；便携排版工具使用 config/p5/toolchain-lock.json 与 scripts/setup_manuscript_tools.py。原生版本以 config/runtime-lock.json 和 native-contract-observation.json 为证。

`release-verification.json` 单独记录发布包摘要、文件数、解包验证及私有配置排除，避免回执自引用。此版本标签说明入口发布，不表示完整真实科研验收通过。

## 开工前备份

`/data/bxn/PathoReason/acceptance/p5-entry-20261030/`：

- before-p5.sqlite3：无活动回合时 SQLite 一致性备份。
- before-p5-source.tar.gz：P4 源码、前端源、契约、配置、文档和原有 Skill。
- before-p5-config.json：旧应用配置；仅留服务器受控验收目录。

旧引擎数据未搬迁，新配置/工具与旧服务独立。Seedream 私有配置是从旧服务器快照复制出的新文件，源未改动；不要把私有配置加入源码发布包。

## 常规恢复

先确认应用回合、原生会话、研究账本和后台进程是否活动。不要仅凭浏览器断开判断任务已停止。核对 runtime/control 的 PID 与 /proc 启动身份，脚本只控制 PathoReason 自有进程：

```bash
cd /home/bxn/projects/PathoReason
.venv/bin/python scripts/service.py status
.venv/bin/python scripts/service.py restart-app
# 仅在已确认原生会话空闲或安排恢复时：
.venv/bin/python scripts/service.py restart-runtime
```

保留 `/data/bxn/PathoReason/state/`、runtime/opencode/、projects/、studies/、research/、artifacts/ 整个关联集合。原生 ID、权限派发记录、预算与来源链不能从不同时间点任意拼接。当前 P5 核对脚本 scripts/verify_p5_entry.py 假设尚未开始正式研究；新窗口开始后其中“零新回合/零正式项目”不再成立，不要为使它通过而删除记录。

## 版本回退

先冻结新动作并保存当前源包、配置和一致性 DB 备份；有实际研究时同时保存工作区、成果、原生持久目录和执行器账本/回执。将目标版本解包到独立目录、核对 manifest，再切换代码；不可直接在运行中的 checkout 上覆盖解包。

未产生任何 P5 正式数据时，可在核对原有行未变化后恢复开工前代码和配置、重建 P4 前端；P5 新增旁表可保留，避免无必要的 DB 回写。原私有配置与工具目录可保留，不影响 P4；不动旧研究服务。

若已有正式研究、正式成果或 context/3/handoff/3，**不得用 before-p5.sqlite3 覆盖当前数据库**。P4 不理解新的正式执行/成果类型，此时应保留 P5 数据与服务版本，停止新增动作并前向修复，或先实现可验证的兼容投影。代码回退不代表已经回退外部训练/图像请求；不得自动重放或抹掉消耗。
