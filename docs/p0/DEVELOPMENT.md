# 开发与验证入口

主线开发/验收在 bxn-server:/home/bxn/projects/PathoReason，使用 OpenCode + DeepSeek。按用户新指令，Codex 开发验收只在本机开展，使用独立配置/数据/证据；服务器保留登录入口。以下命令是服务器基线，不能直接拿到本机执行。P0 未启动应用；P1 从此继续。

```bash
cd /home/bxn/projects/PathoReason
source .venv/bin/activate
export PYTHONPATH="$PWD/src"
export PYTHONDONTWRITEBYTECODE=1
python scripts/storage.py check
python scripts/export_schemas.py
python -m pytest -q --basetemp=/data/bxn/PathoReason/scratch/<新测试目录>
```

测试目录必须唯一；pytest 会清理所给 basetemp，不能指向已有研究或验收目录。

依赖恢复：使用 runtime-lock.json 所列 uv 工具创建 .venv（Python 3.14.4），uv pip sync requirements.lock --python .venv/bin/python --require-hashes --link-mode=copy --cache-dir /data/bxn/PathoReason/cache/uv。不修改旧 .venv；Node/npm 工具暂引用已安装版本，P1 前端使用自己的 node_modules。

新输出先经配置和存储入口分配：

```bash
python scripts/storage.py create acceptance p1-<唯一标识>
python scripts/storage.py create scratch tests-<唯一标识>
```

scripts/build_p0_example.py 是这次固定 CESC 观察样例的显式生成器，不是应用启动脚本。它仅读取声明的来源、写新项目样例和 P0 验收文件；不要作为通用数据扫描器。旧成果变化时生成新的观察版本并说明差异，不能在旧项目里修补字节使哈希通过。

Git：独立 main 分支；源码、文档、配置模板、契约样例与依赖锁纳入版本控制。local 配置、.venv、运行数据库、凭据、大文件与验收运行日志全部忽略或放数据盘。本阶段不设置远端、不推送、不对外发布。

P0 校验器防止常见路径越界/符号链接和内容变化，但不是抵抗并发恶意文件替换的操作系统沙箱。P1 暴露文件下载与模型工具前，以精确清单和安全文件描述符读取补齐运行边界并测试；不能让模型任意浏览旧数据根目录。
