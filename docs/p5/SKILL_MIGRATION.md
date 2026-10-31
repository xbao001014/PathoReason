# P5 Skill 迁移

原来源：`/home/bxn/projects/auto-research/.agents/skills/`。目标：PathoReason `.agents/skills/`。13 项、2537 个原文件（含脚本、参考、模板、许可证）；原目录只读且逐文件 SHA 验证未变化。现有 `skills/results-explanation` 保留。完整来源清单：`config/p5/skill-migration.json`。

| Skill | 原文件数 |
|---|---:|
| `academic-research-suite` | 2369 |
| `citation-management` | 21 |
| `histolab` | 9 |
| `manuscript-to-latex` | 19 |
| `method-results-to-manuscript` | 8 |
| `paper-lookup` | 17 |
| `pathology-figures` | 1 |
| `pathology-mil-paper-figures` | 6 |
| `peer-review` | 24 |
| `scientific-schematics` | 7 |
| `scientific-visualization` | 18 |
| `scientific-writing` | 31 |
| `statistical-analysis` | 7 |

适配限于当前入口：ARS 工具映射到 OpenCode/DeepSeek，原科研与作者门禁保留；scientific-schematics 当前入口使用 Seedream，原入口归档于 references/upstream-entry.md；病理图件集成路径指向新 checkout；6 项兼容性说明从不受支持的 frontmatter compatibility 移到正文。以下原文件发生了明确修订，其余原文件按原字节保留：

- `.agents/skills/academic-research-suite/SKILL.md`
- `.agents/skills/citation-management/SKILL.md`
- `.agents/skills/histolab/SKILL.md`
- `.agents/skills/paper-lookup/SKILL.md`
- `.agents/skills/pathology-mil-paper-figures/references/auto-research-integration.md`
- `.agents/skills/peer-review/SKILL.md`
- `.agents/skills/scientific-schematics/SKILL.md`
- `.agents/skills/scientific-visualization/SKILL.md`
- `.agents/skills/scientific-writing/SKILL.md`

旧图件 manifest 保存在 config/p5/original-pathology-figure-skills.json，新 checkout 的明确摘要修订在 config/pathology_figure_skills.json，未更新旧实验的冻结指纹。

验证：13 项均通过 skill-creator quick_validate；原生 OpenCode /skill 实际发现 13 项和原 results-explanation；前端可见 20 项（原 7 场景 + 13 迁移 Skill），按病理 MIL → 实际流程展示。已迁移不表示每项全部依赖或真实研究已通过；详见 ENTRY_VALIDATION.md。
