# 稿件子 Skill 执行与草稿证据补强

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
