# 稿件子 Skill 执行与草稿证据补强

## 最新状态：追加额度后的真实执行

用户同意追加 1200 秒，公开预算接口已记账至 15840 秒，未改变项目 160 / 目标 8 回合上限。修复证据容量时维护中断了 turn_965b7bee63104bc1a3e58ebd83ce4ed6，目标因此暂停；随后 turn_e132565ddc8f49fc8f9bbbfc98b82166 仅回复暂停状态，没有执行研究工作。这是开发维护与恢复过程的干预，不能算模型成果。

把用户原有修改要求通过公开稿件接口登记为 revise（非批准），目标编辑继承相同范围后公开 resume。最终 turn_452f1b35ccfb463bb72e96223e3ccd8f 完成，目标 revision 20、8/8 回合、waiting_input/manuscript_review_pending。项目 115/160 回合、Agent 消耗 15290.853638/15840 秒，尚余约 549 秒；目标回合已到上限，不能自行追加或换目标规避。无新实验、训练、测试调用或作者批准。

稿件工作流 revision 8，仍为 draft/awaiting_review；待审包 mrv_turn_452f1b35ccfb463bb72e96223e3ccd8f，digest a911770717e1e26425b0ce2ae666b824c7455ddf4c276285474a316f2aba03de。13 项材料全部成功进入 checkpoint evidence，证明原 10 项容量冲突已在真实调用中解除。正文 v6 SHA f8937dc541d066df098fd573e85c8bec740bb4aa9391188e4c4c4025ba008d65；BibTeX v4、新的引用/文献/论证/Skill/图件/完整性报告均由研究 Agent 生成登记。audit_status=blocked，不可宣称已通过草稿验收。

实际 native trace 本回合加载 scientific-schematics、citation-management、pathology-figures、scientific-writing；后两者发生在图件与正文生成之后。academic-research-suite、pathology-mil-paper-figures 仍缺，scientific-writing/evidence_workflow 和 ARS 角色参考也未见执行。前一回合已读 authorial-voice、methodology-figures 等的记录仍保留，但不足以覆盖本次所有依赖。skill_usage 的“部分覆盖”不是完整执行证明。

Seedream v2 用 v1 作唯一参考图生成，SHA f6de736ad7638aefbbd43940cb2dd5ec2bf5e7cf1e158f7d96181e89b972b118，2816×1584，原图/回执保留。开发窗口独立看图确认 MIDDLE 去除、三类标签与连接出现，分类头仍未明确呈现；pooling 直接指向输出，不能把请求增加分类头写成已修复。开发者仅检查并记录，未改图、未代签科学/作者批准。

其余未通过项：引言中央论断仍主要仅摘要级；Agent 把这一缺口列为投稿前非阻塞项，与当前补强要求不符。把 pre-registered 全文替成 prespecified 也尚未展示逐项、先于分析的计划依据，不能仅改词就认定历史主张核实。argument 的五段描述与实际四段引言定位不一致。当前包的 blocked 可防止批准，但这些额外问题尚未进入该历史包，开发者没有回写它。

据此进一步补强 stage-execution：必需加载/正文读取先于依赖工作；缺必需依赖和影响当前论断的证据缺口须为当前 draft blocking；预先计划须有日期依据；图件报告区分请求修复与观察结果。此末轮规则补强只做工程/原生检查，不声称已获新模型回合验收。

独立证据：`/data/bxn/PathoReason/acceptance/manuscript-skills-20261104/final-state.json`、`final-turn-trace.json`。后续应由研究 Agent 完成缺失依赖、关键全文/语义核验及图件修订后提交新包；不能只让作者确认视觉就进入下一节点，也不能自行增加额度或重置回合。

后续修复：发现 GoalEvidence.artifact_ids 上限10与 ReviewRequest.materials 上限24不兼容，导致完整草稿包无法提交。证据容量统一为24，保持有界；新增24项可接收/25项拒绝的回归，与稿件和目标回归共44项通过。用户明确追加1200秒后预算从14640调整为15840，历史消耗及项目/目标回合上限不变。

2026-11-04，0.6.36-p5-manuscript-skills。

## 问题与修复

现有主 Skill 的 coordination 列表未形成阶段必需执行依赖；已有稿件默认进入 audit，导致背景与研究动机修订跳过 M2 文献发现和 M3 综合。原生返回的文件清单只是发现证据，不能证明 authorial-voice.md、methodology-figures.md 等正文被读取。前一版工程框图质量修复也不能替代用户明确要求的 Seedream 病理概念图。

主 Skill 新增必读 stage-execution.md，明确各子 Skill 作用、触发条件、必读配套文件及可观察产物。文献补强要求 paper-lookup、citation-management、ARS 文献角色；起草要求 scientific-writing、ARS 起草角色和 authorial-voice；病理概念图要求 pathology-figures、pathology-mil-paper-figures、scientific-schematics、manuscript-to-latex 图像能力及 methodology-figures/raster-generation。数字图、统计复核、真实组织图、同行评议和交付按阶段触发，排版不提前执行。

新 draft 包必须登记 literature、argument、skill_usage，分别保存检索/来源层级/语义证据、段落功能与研究论证、实际加载和正文读取/执行记录。后端保证材料存在且字节绑定，不把 Agent 自报当作平台已核验调用；真实验收仍对照 native trace。已有审核历史不回写。

Introduction 以疾病问题、当前评估局限、计算病理/MIL 背景、最接近工作、具体缺口、研究问题及设计理由形成公开论证。禁止用引用数量、堆砌 DOI 或事后编造预注册代替证据深度。

草稿病理概念图使用已配置 Seedream，通过 study_io.py image 单次候选调用、新目录、原图及 candidate.json 留证；生成组织纹理只能标为示意，不能冒充患者切片。现有数字图仍保留数据来源。付费失败不自动重试，无图时明确阻塞；OCR 和几何不能冒充真实视觉验收。

## 验证与边界

29 项稿件/正式入口回归通过。用户本轮已明确要求 Seedream 生成与文献补强；不新增实验、不增加研究预算、不代批稿件。开始时预算剩余约 358 秒，真实 Agent 行为与完成度需单独记录，不能由工程通过推定。

## 真实行为与未完成项

本轮 turn_f33850ba13db4fcd8bb1b6217f67c2b9 实际 native 加载主 Skill 与 paper-lookup；read 工具读取 stage-execution.md、authorial-voice.md、methodology-figures.md、raster-generation.md。其余要求的 citation-management、ARS、scientific-writing、病理图件专业 Skills 未执行，Agent 在 skill-usage-v1.md 如实记为预算不足，不能算完整通过。

首次 image helper 因请求文件未创建而失败，未到供应商；随后 Agent 创建请求后单次 Seedream 调用成功。candidate.json 为 pending_review，模型 doubao-seedream-5-0-flash-260915，原图 JPEG 2816×1584，SHA bb1e9baca8fe3cd49ef487aa933d30362c6eb5924ad398e894a0468965390838。独立视觉检查确认病理组织示意/patch/embedding/pooling 内容已出现，并标明 AI-generated not patient data；残留 MIDDLE 标签、分类头及输出连接表达仍需完善，未批准。不能把候选成功等同图件科学验收。

Agent 已登记正文 v5、literature-v1.md、argument-v1.md、skill-usage-v1.md 和 Seedream 原图。引言扩充并新增两条引用，但中央背景论断仍仅摘要级，新增引用元数据及 BibTeX 未完成绑定。旧稿已有的 pre-registered 表述也须追溯确切来源，不能从叙述推定预注册。

最后 checkpoint 返回 manuscript_material_not_in_checkpoint，尚未完成修正即触及原有时间上限。目标 blocked/turn_time_limit，项目 112/160 回合，计时 14640.421/14640 秒（检查粒度产生约0.421秒超出，不是额度增加）；目标6/8。旧 draft pending revision 6 仍在，v5 未替换它。保留未完成事实，不回填批准、不由开发者补造研究材料。后续需明确可用额度，研究 Agent 再完成子 Skill 和语义核验、图件修订、文献库/manifest/完整性与 checkpoint evidence 全量绑定。
