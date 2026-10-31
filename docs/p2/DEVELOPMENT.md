# P2 开发与恢复入口

服务启动、SSH 转发、凭据管理沿用 ../p1/DEVELOPMENT.md。访问 http://127.0.0.1:8520/ 。新建独立项目，选择“合成验证”，接入任务并生成方案；后续回合确认或反馈修订，再执行。旧成果项目不能开启合成执行。

`docs/p2/BUSINESS_SKILL_POLICY.md` 是当前三个合成能力入口的共用规范，摘要写入 SkillDefinition，并注入已授权回合；不是未经实际加载却声称“原生 skill 工具已调用”。业务实际通过 MCP 执行。

```bash
cd /home/bxn/projects/PathoReason
PYTHONPATH=src .venv/bin/python scripts/export_web_types.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q --basetemp=/data/bxn/PathoReason/scratch/<新的唯一目录>
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:/home/bxn/projects/auto-research/packages/core /home/bxn/projects/auto-research/.venv/bin/python -m pytest tests/test_p2_adapter.py -q --basetemp=/data/bxn/PathoReason/scratch/<另一个新的唯一目录>
PYTHONPATH=src .venv/bin/python scripts/verify_p2.py
```

最后一条只核对已有 P2 验收记录，不发起模型调用或训练。真正故障注入脚本在验收目录中，会创建新的合成任务，不应把它当作普通只读检查反复执行。

业务动作入口 `/internal/business` 仅供持私有令牌的本地 MCP 使用；公开 `/api/v1/research-projects/{pid}/business` 为工作台投影。不要从前端绕过对话直接发研究执行请求。

所有业务源码变更后先验证，再在没有活动模型回合时 restart-app。修改原生配置另需 restart-runtime；不要重启活动引擎。旧业务源码被固定 SHA 校验，升级须有明确版本和兼容验证，不能在失败时自动刷新固定清单。

恢复前核对原任务、回执、job outcome、LoopStore 预算及进程启动标识；未知派发只核对。应用重启不会重发研究执行。不要删 task.json、started 标记、行动或 LoopStore 数据库来强行重跑。

完整备份需同时覆盖应用 SQLite、research（含行动和 LoopStore）、artifacts 和原生 OpenCode 数据；仅复制应用数据库不足以恢复研究任务。
