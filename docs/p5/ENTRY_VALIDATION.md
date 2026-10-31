# P5 入口交付验证

日期：2026-10-30；版本：0.6.0-p5-entry；计划 v0.8。

结论：服务器正式试验入口已交付，真实端到端验收等待用户另开窗口。未在本次入口验证中拉取患者记录、调用模型、付费生图或发起训练，也未创建生产正式试验项目。

## 实现与工程验证

- 独立正式项目、冻结预算与运行配置；普通旧项目不能通过请求参数升级执行权限。
- 原生权限列表按会话隔离，“仅允许本次 / 拒绝”；审批回执未知保留 dispatching 并拒绝重复发送。
- 数据 GET、配置 Seedream、成果登记均限定项目工作区，保留单次输出/来源摘要；模型不能把正式成果伪装成合成结果。
- formal/1、artifact pathoreason/3、context/3、handoff/3 兼容与来源保留；旧契约快照不覆盖。
- 111 项应用测试通过，1 项条件跳过；新增 7 项覆盖预算隔离、模式升级拒绝、数据目录/重试边界、正式成果与交接、权限隔离/未知回执、图像私有配置、无全局 shell 放行。模型、数据和图像动作使用测试替身，不是供应商真实验收。pytest 有一项既有 Starlette/httpx 弃用警告。
- TypeScript 检查与 Vite 生产构建通过。
- 浏览器 1440px 展开/折叠、390px 折叠通过：固定导航、独立项目栏、20 项 Skill（13 项迁移）、设置入口和正式项目表单可用，无横向溢出、无页面异常；未提交创建操作。
- 13 项 Skill 通过 frontmatter/资源结构验证；OpenCode 1.18.33 原生 /skill 实际发现。原生 /agent 和权限 API 实机只读检查通过；本轮没有创建新原生模型会话。
- 旧数据库各表原行与开工前快照完全相同，服务器旧模型 12/12、本机 6/12、原合成物理作业 34 不变；旧研究服务实例未变、无活动任务。旧 Skill 原来源 SHA 未变。

## 配置与依赖

数据接口从原仓库 data_api.png 读取，写入 config/p5/data-source.json；服务器 /data/slide_files 存在，但未核验实际接口记录/特征或数据可训练性。Seedream 使用服务器旧稿件配置快照中的 doubao-seedream-5-0-flash-260915，私有配置权限 600；配置存在不等于在线额度、模型可用性或实际图像已验收。

独立安装 TinyTeX v2026.10（TeX Live 2026）和 Pandoc 3.13，下载文件 SHA 与官方发布摘要一致。pdflatex、xelatex、latexmk 4.88、bibtex、biber 2.22、pandoc 可启动；latexmk 和 Pandoc 各自完成无研究数据的 PDF 编译。工具不修改系统 PATH 或旧科研环境，service.py 为本项目加载 .tools/manuscript-path.json。

旧引擎 Python 已有 torch、PIL、matplotlib、pypdf。未安装 histolab、Poppler 的 pdftoppm/pdftotext、Ghostscript gs、Graphviz dot；若选定原始 WSI 预处理、这些渲染/质检路由，需要按实际流程补齐并验证，不能把“13 项已迁移”理解为所有可选工具齐备。PDF 编译通过不代替视觉审稿。

## 下一窗口必须实际验证

选定病种/目标和完整研究协议；数据接口获取、患者与特征映射、划分完整性；GPU UUID/预算和原引擎门禁；正式 Agent 真会话中的命令审批、长任务断线/恢复与重复执行防护；实际 Seedream 请求/回执与人工视觉复核；端到端成果关联、论文/图件交付及科学/作者审核。当前工作台显示已登记成果和模型预算，真实执行阶段以业务账本为准，未自动投影所有真实科研步骤。

审批回执未知时需要人工核对原生会话/权限和执行回执；当前没有自动恢复或“一键重新批准”入口。原生命令确认不是 OS 沙箱，也不替代科研授权。

## 证据

服务器 `/data/bxn/PathoReason/acceptance/p5-entry-20261030/`：entry-verification.json、native-contract-observation.json、before-p5.sqlite3、before-p5-source.tar.gz、before-p5-config.json、pytest.txt、build.txt、browser/、skill-validation.json、toolchain-smoke/report.json。发布目录见 RELEASE_RECOVERY.md。

本机浏览器证据 `/home/bbbxn/outputs/PathoReason/p5/`。本机 8530 服务仍为 P4；P5 服务器入口交付不冒称本机 P5 部署验收。
