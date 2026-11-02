# PathoReason 正式试验操作说明

本次交付的是 P5 正式试验入口。真实数据拉取、GPU 训练、Seedream 生图和论文全流程验收由用户另开窗口开展；尚未宣称端到端通过。

## 入口与运行环境

源码：`/home/bxn/projects/PathoReason`；运行数据：`/data/bxn/PathoReason`。
服务器应用监听 `127.0.0.1:8520`，原生 OpenCode 监听 `127.0.0.1:8522`（有密码，仅供应用使用）。在本机执行 `ssh -N -L 8520:127.0.0.1:8520 bxn-server` 后打开 http://127.0.0.1:8520/ 。已有转发可直接沿用，不重复占用端口。

左侧研究项目 `+` → 项目类型选择“正式试验” → 填写实际研究目标与明确的模型回合/墙钟预算 → 创建。创建只分配独立项目，不拉取数据、不调用模型、不训练。对话发送后使用 OpenCode + deepseek-v4-pro；迁移的 Skill 可按研究类别/流程选取。

普通旧项目继续只读解释或独立合成验证。正式研究使用新项目预算，不重置服务器原 12/12 验收账本。本机 Codex 仍只用于本机开发；不能用它代替服务器验收。

## 模型与操作授权

模型对话预算是应用回合数及累计墙钟，包含等待确认时间；每个 OpenCode 回合可以有多个内部模型步骤，并非精确供应商调用次数或货币额度。默认表单值只是可编辑建议，由创建项目的人提交后生效。训练 GPU/时间/矩阵、图像候选次数和供应商实际费用需在具体研究方案中另外明确。

正式研究启用迁移 Skill、文件查阅和原生工具。输入区“权限”按钮设置当前对话的逐次确认、自动批准或自定义工具规则，仅作用于后续回合。自动批准保留明确禁止项；执行中不能保存设置。需要询问的操作显示具体内容，提供“仅允许本次 / 本会话同类操作 / 拒绝”。“本会话同类操作”仅在原生请求提供匹配范围时出现，范围可展开查看；不代表永久授权，切回逐次确认不会自动撤销已授予的会话规则。未知审批回执保留为 dispatching，不自动重放。停止生成只终止模型回合，不能假称后台研究已停止；先检查训练 PID/启动身份和研究账本。

此入口使用服务器现有用户权限和 OpenCode 操作确认，不是新的 OS 级隔离沙箱。原研究执行器的隔离证明、冻结合同、完整矩阵、预算、后续回合确认及科学/作者门禁仍须执行。不能通过任意 bash 绕过原执行器来冒称已满足原科研流程。

## 数据接口

配置：`config/p5/data-source.json`，来源是原仓库 `data_api.png`。GET `http://ai.gzfxyl.cn/api/v1/pathology/diseases/slides`，参数 `DiseaseName`、`Limit`；没有凭空增加认证头或改变接口。当前交付只核对配置，不获取真实患者记录。

在正式项目内，确认实际病种、范围后：

```bash
/home/bxn/projects/PathoReason/.venv/bin/python /home/bxn/projects/PathoReason/scripts/study_io.py data --project PROJECT_ID --disease '实际病种' --limit 1000 --output inputs/source-v1
```

输出目录必须全新；保存原 JSON 和响应 SHA/大小/查询参数回执，不自动重试。不在聊天中输出患者原始记录。接口返回远端 FeaturePath/原始图像路径不等于可训练样本：核对服务器可访问路径、患者/玻片/标本对应、标签来源、特征格式、完整性与划分。不能凭一次接口成功声称数据验证通过。

## 原有 Skill 与业务执行

13 个原 Skill 连同脚本、参考材料、模板和许可证迁入 `.agents/skills/`；现有结果解读 Skill 留在 `skills/results-explanation`。OpenCode 显式注册两目录。原始逐文件摘要在 `config/p5/skill-migration.json`；`config/pathology_figure_skills.json` 是新 checkout 的明确修订，原 manifest 另存，未改旧实验指纹。

按原研究顺序使用：数据与任务定义 → 基线 → 机制/消融 → 统计与解释 → 稿件编写/审核 → 图件与排版交付。ARS 保留 WORKFLOW.md 的阶段与作者门禁，将运行时工具映射到 OpenCode。科学示意图入口只采用 Seedream；历史 OpenRouter/Gemini 示例不是当前调用配置。Skill 可加载不证明其全部可选依赖已安装或真实研究流程已验收。

可复用引擎仍在 `/home/bxn/projects/auto-research`，只读使用。新项目生成自己的 `compute.json`，存储目录全部指向 `/data/bxn/PathoReason/studies/PROJECT_ID/`；默认 GPU 仅继承服务器配置作为候选，不等于获得使用授权。实际训练前核对设备 UUID/空闲状态、冻结研究协议和明确预算，使用原执行器的正常准备/门禁路径。

调用旧引擎 Python 时显式设置：

```bash
export PYTHONDONTWRITEBYTECODE=1
export AUTORESEARCH_COMPUTE_CONFIG=/data/bxn/PathoReason/projects/PROJECT_ID/compute.json
```

`compute.json` 初始 `real_training_authorized=false`。后续窗口在具体协议获确认后按原流程准备新研究；不恢复已停止实验，不修改旧特征或冻结证据。稿件运行根要指向新 checkout 中迁移后的 Skill 和私有 Seedream 配置，不能因旧路径存在就继续写入旧实验。

## Seedream

私有配置：`/home/bxn/.config/pathoreason/image-generation.json`，权限 600；沿用服务器旧配置快照中的 `doubao-seedream-5-0-flash-260915` 和凭据。源快照未修改。凭据不进入 Git、公开接口、原生提示词或命令行参数。

在工作区保存请求 JSON，字段只有 `prompt`、`sources`（工作区内方法/实现证据的相对路径）、可选 `reference_images`。不能将患者原始材料提交到图像服务。确认一次图像请求后：

```bash
/home/bxn/projects/PathoReason/.venv/bin/python /home/bxn/projects/PathoReason/scripts/study_io.py image --project PROJECT_ID --request figures/request-v1.json --output figures/method-v1
```

适配器单次生成、无自动重试、独占新目录；保存请求绑定、候选原图与回执。DeepSeek 的文字描述不等于看过图片，实际视觉复核与作者审核独立进行。概念图不得代替真实组织图像、注意力图或测量结果。

## 工作台成果登记

完成输出后显式登记，保留源文件原字节：

```bash
/home/bxn/projects/PathoReason/.venv/bin/python /home/bxn/projects/PathoReason/scripts/study_io.py publish --project PROJECT_ID --file outputs/report.md --title '研究报告'
```

只接受 outputs/、figures/、manuscript/ 中的结果文件，默认不公开 inputs/ 的患者记录。复制为不可变成果文件并生成引用 ID；同路径内容变化创建新成果，不覆盖旧版本。正式成果使用独立 formal_study 来源类型，不伪装成合成 MIL。生成/登记不构成科学审核通过。

工作台展示已登记成果与模型预算。原业务运行阶段和结果仍以实际执行器回执/账本为准；尚未验收的真实流程不能依据 Agent 文字自动标为完成。

## 排版工具与依赖

本项目独立工具路径在 `.tools/manuscript-path.json`；服务启动时自动加载。手工命令可执行 `export PATH="/home/bxn/projects/PathoReason/.tools/manuscript/.TinyTeX/bin/x86_64-linux:/home/bxn/projects/PathoReason/.tools/manuscript/pandoc-3.13/bin:$PATH"`。latexmk/Pandoc 无研究数据编译已通过；可选 WSI、PDF 渲染与图结构依赖的未安装项见 ENTRY_VALIDATION.md，按实际研究路径补齐。

运行接口参照 [OpenCode 权限](https://opencode.ai/docs/permissions/)、[Skill](https://opencode.ai/docs/skills/) 和 [Server](https://opencode.ai/docs/server/)，本次以已安装版本原生 /doc 为准；图像协议参照 [火山方舟图像 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=en)。这些文档不构成本项目真实调用已经通过的证据。


## FXio 玻片读取（2026-10-31）

服务器已安装 FXio 0.1.2。读取接口记录中核验后的实际切片路径时，使用 `/home/bxn/projects/PathoReason/.venv/bin/python`，Python 入口为 `from wsi import open_wsi`。真实 ZYP/MRXS 的元信息、区域和缩略图读取已验证；其他格式和可选功能需分别核验。调用、依赖恢复与安装证据见 [FXio 环境说明](FXIO.md)。元信息清单写入当前项目 inputs/，图件和报告分别写入 figures/、outputs/，原切片只读。
