# P4 迁移与回退

在项目根目录使用对应环境的 `.venv`。服务器数据根 `/data/bxn/PathoReason`；本机 `~/.local/share/PathoReason`。不互拷 config/pathoreason.local.json、凭据、运行时目录或原生会话。

## 预览与执行

```bash
PYTHONPATH=src .venv/bin/python scripts/migrate_p4.py
PYTHONPATH=src .venv/bin/python scripts/migrate_p4.py --apply
```

初始化仅确保 P4 旁表存在；默认预览不写投影行。apply 要求没有活动/待恢复回合，在一个事务里写入批次回执和上下文投影。批次 ID 取决于旧行原文 SHA 与投影 digest；重复执行幂等；检测到同一源行对应的投影变化则报错，不覆盖旧投影。来源配置摘要不匹配时拒绝迁移。

此次服务器投影 12 条，本机 6 条；原项目、对话、回合、事件、配置、Skill、成果和引擎表完整保留。新上下文通过正常 submit 写 v2；历史迁移不会修改 context_snapshots。旁表是审计性物化记录；公共读取仍按固定来源执行同一适配，撤销旁表不破坏历史读取。

## 撤销投影批次

```bash
PYTHONPATH=src .venv/bin/python scripts/migrate_p4.py --rollback BATCH_ID
```

用 migration-receipt.json 的实际 ID 替换 BATCH_ID。仅删除该批次持有的 p4_context_projections 和 p4_projection_batches，不删除原回合或 p4_provenance。新一批如包含已存在投影，不会接管旧批次行的所有权。

验收在真实库的一致性临时副本中注入首行写入后的异常，确认投影和批次都回滚；随后 apply、重复 apply、rollback，并与 P4 前每张原表逐行比较。生产数据未用于故障注入。handoff 的文件写入和数据库中途失败分别有测试，确认新项目/会话/成果/来源/交接记录全部回滚。

## 应用代码回退

P4 前一致性 SQLite 备份、源码归档位于各自 `acceptance/p4-20261030/before-p4.sqlite3` 与 `before-p4-source.tar.gz`。本机源码归档取自字节一致的服务器 P3 源码，不含环境配置和凭据。归档包含 src、scripts、tests、前端 src、contracts 和文档；前端 dist 需要重新构建。pyproject.toml 本次只把已锁定的 jsonschema 从 dev 移至运行依赖，回退可继续保留该依赖。

当前验收没有新增生产回合或导入项目，因此可在确认空闲后，将归档解压到隔离目录核对，再恢复旧应用文件、重新构建前端并仅 restart-app。保留旁表不会影响 P3；不必覆盖整库。现有 P0/P1/P2/P3 契约快照没有改动。

若 P4 启用后已产生新的 v2 上下文或多次交接来源，先保存这些新记录，保留 P4 读取兼容层。不要为了降级直接覆盖整库或删除来源表，否则会丢失新会话或来源链。整库恢复只适用于明确核对无后续数据的灾难恢复，不是常规旁表撤销步骤。

## 只读复核

```bash
PYTHONPATH=src .venv/bin/python scripts/verify_p4.py
```

检查服务、源文件、上下文、成果、交接摘要和迁移事务；不调用模型、不压缩、不启动研究。脚本写本阶段验收报告，回滚测试只作用于临时副本。完整旧项目超过 2 MB 时，导出按原上限返回 handoff_artifact_limit；不会绕过预算复制大文件。
