# 研究工作台：阶段、修订与证据展示

0.6.12-p5-workbench。正式研究入口采用新工作台；旧项目工作台保留。设计依据见 [设计说明](RESEARCH_WORKBENCH_REDESIGN.md)，原型见 [离线原型](RESEARCH_WORKBENCH_PROTOTYPE.html)。

## 使用

工作台顶部选择研究方向，依次提供概览、创新方案、阶段材料、修订脉络、实验运行五个视图。八个研究阶段可直接定位材料或实验。文件按系列与版本标记收拢，同名 JSON/Markdown 作为格式候选并列；展开可查看旧文件、字段差异和首次引用的原始对话。

页面可见时每 5 秒更新一次；切后台停止轮询，返回立即更新。读取失败保留最后记录并提示，手动刷新保留当前筛选。活动 Agent 回合与实验进程分开显示。讨论按钮将所选材料带入对话草稿，保留已有输入，需要用户正常发送；不会自动执行、采纳或授权。

## 状态边界

GET `/api/v2/research-projects/{project_id}/research-workbench` 返回 `pathoreason.research-workbench/1`。接口只读，不注册任务、不迁移成果、不改预算、不回写运行状态。单次数据库快照读取成果、可见对话、已登记任务及源码快照；结构化文件通过已有 SHA 校验读取，单文件最多 2 MiB、总计 16 MiB，超限或损坏保留原文件入口并提示。

历史 benchmark-plan 的文件系列形成展示分组，不冒充正式任务。明确的方案文件引用优先；同会话的首次引用可推断材料属于哪个方案阶段，界面标为待核对。多方案共同依赖保留在共享区，跨会话不继承阶段。不能证明修订因果、方案采纳或父子任务时不补造。已删除对话不用于回溯。

八阶段目前展示材料覆盖与最新材料位置，不将“有材料”判为阶段验收通过。报告中的 pass/complete 等是文件声明。实验矩阵读取方案的模型和种子；结果按同任务中的模型/种子对照，保留 `plan_binding=unverified`。历史 smoke 不计入正式矩阵完成数。重复报告不静默合并成已完成单元；各报告明细可分别查看。测试集暴露记录原样展示。

当前独立任务代码快照仍为 `source_only` / `execution_ready=false`。统一后台训练状态、冻结方案与运行单元的权威绑定、阶段验收事件尚未接入。本版不声称实时 GPU 作业监控或研究科学验收已经完成。

## Agent 发布结构化材料

先读取上述接口，或用平台任务工具取得本项目真实 task_id；不要发明 ID。历史 `view_...` 是稳定的展示标识，未来注册正式任务后可通过新关联清单重新组织材料。使用既有 `scripts/study_io.py publish --help` 所列入口发布独立的新文件；不覆盖旧输出。工作台读取已发布成果，不扫描未发布的患者数据或源码目录。

可发布 `pathoreason.workbench-manifest/1` 关联清单。完整 schema 在 `contracts/p5-workbench/WorkbenchManifest.schema.json`。以下为字段示意，尖括号值必须替换成真实引用：

```json
{
  "schema_version": "pathoreason.workbench-manifest/1",
  "task_id": "<本项目任务或展示分组 ID>",
  "links": [{
    "artifact_id": "<已发布成果 ID>",
    "stage_id": "plan",
    "family_id": "benchmark-plan",
    "revision": "3",
    "supersedes": []
  }]
}
```

stage_id 为 data、plan、readiness、baseline、innovation、innovation_runs、analysis、delivery。每份清单内成果 ID 唯一，所有引用必须属于本项目；无效清单整份不应用。新清单可修正展示关联，旧文件仍保留。supersedes 仅为声明，不能改变采纳、有效性或完成状态。本版版本列表按成果登记顺序显示，不按 v 数字大小跨系列比较。

创新方案使用 `pathoreason.innovation-proposal/1`，schema 见 `contracts/p5-workbench/InnovationProposal.schema.json`。必要字段：schema_version、proposal_id、task_id、revision、title、hypothesis。同一候选保持 proposal_id，修订时发布新成果。建议补充 gap、mechanism、baseline、selection_reason、falsification、implementation、source_refs、evidence_artifact_ids、parent_proposal_ids 和 conditions。conditions 的展示字段为 title、question、criterion；只放研究设计，不放患者明细。

decision 可为 proposed、selected、deferred、rejected，只代表方案文件的声明，不能代替平台采纳或作者审核。source_refs 保留来源，evidence_artifact_ids 必须是本项目已发布成果。界面提供候选比较、机制变化、反证与对照条件、关联证据和历次修订。未有实际结构化创新方案时显示空状态，绝不以示例候选冒充研究结果。

正式回合提示已指向本文；不会改写已存在项目的 AGENTS.md、历史回合或研究输出。新增声明格式的目标 Agent 端到端生成效果仍需后续研究中验证，本次不代替 Agent 补写创新成果。

## 验证与回滚

工程测试覆盖任务隔离、共享依赖、对话来源、无效清单、创新修订、最新报告、文件损坏/超限及读取不回写。实际研究成果仅重新展示。交付记录及浏览器截图保存于 `/data/bxn/PathoReason/acceptance/workbench-redesign-20261101T224424/`。

本版不改变数据库结构。回滚仅回退本次应用代码和静态构建，再确认无活动 Agent/上下文操作后重启 app；不要恢复旧数据库、成果目录、研究预算或 OpenCode session。原 app 静态构建备份保留在同一验收目录。

实际交付验证：全量 288 passed / 2 skipped；TypeScript 与 Vite 构建通过。线上三宽度五视图共 15 组布局通过；任务切换、版本差异、原文件预览、较早来源回合定位、刷新保留视图和仅草稿讨论入口均已检查，浏览器没有 JS 异常或写接口请求。原研究 78 条成果、历史回合与预算不变，3618 个已有文件无元数据变化，其中 3237 个不超过 1 MiB 的文件逐一 SHA 校验不变。未触发模型调用、数据拉取或真实训练。

补充的隔离浏览器合成检查覆盖创新候选正文、未采用候选保留、候选并排比较、读取中断保留最后视图及恢复。合成候选仅替换测试浏览器内的 GET 响应，未登记、发布或保存到真实研究；证据见 browser-fixture-check.json。
