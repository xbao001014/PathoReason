# 成果契约

由研究 Agent 在当前项目内创建新版本文件，不覆盖既有队列、方案或成果。推荐 plans/ 保存检索与方法库证据，outputs/ 保存可登记的候选表、benchmark 方案与工程缺口；不把患者明细发到搜索服务。

除易读方案外，保存一个 JSON 供 check_plan.py 检查。新方案使用版本 2；历史版本 1 仍按 CV 兼容检查，不覆写历史文件。先读 [验证协议](validation-protocols.md)，下面是 CV 格式示意；留出法替换其中 validation、split_counts、matrix 三段，其余来源与公平性字段保持完整（示意名称不是真实候选）：

```json
{
  "schema_version": "pathoreason.benchmark-plan/2",
  "objective": "当前研究问题及比较主张",
  "as_of": "YYYY-MM-DD",
  "recent_from_year": 2023,
  "inventory_ref": "plans/method-inventory-v1.json",
  "search_log_ref": "plans/benchmark-search-v1.md",
  "searches": [
    {"query": "近期方法检索词", "accessed_at": "YYYY-MM-DD", "source": "websearch", "urls": ["https://论文或原始来源"]},
    {"query": "已有比较研究检索词", "accessed_at": "YYYY-MM-DD", "source": "websearch", "urls": ["https://论文或原始来源"]}
  ],
  "candidates": [
    {"id": "method_a", "name": "真实方法名", "year": 2025,
     "role": "recent", "paper_url": "https://原论文", "code_url": null,
     "decision": "select", "reason": "为何有必要比较",
     "task_fit": "与当前任务的关系", "input_requirements": "所需特征/坐标/其他输入",
     "local_status": "absent", "executor_status": "needs_adaptation",
     "implementation_gap": "具体接入工作；unknown 不能写成已通过",
     "comparison_track": "fixed_features", "source_checked": "abstract_only",
     "paper_access": "abstract_only", "code_access": "not_checked",
     "evidence_notes": "实际读取的 URL、正文章节或代码文件，以及由该资料支持的具体判断；摘要未覆盖的细节待查"}
  ],
  "fairness": {
    "patient_split": "划分/队列引用及职责",
    "feature_policy": "固定特征及分轨规则",
    "tuning_policy": "模型配置、成本可比的调参/选择规则",
    "sampling_policy": "bag/patch/患者聚合",
    "held_out_policy": "封存测试使用规则"
  },
  "validation": {
    "method": "cross_validation", "fixed_split": true, "split_seed": 71,
    "group_unit": "patient", "stratification": "class label", "split_status": "proposed",
    "split_manifest_ref": null, "split_manifest_sha256": null
  },
  "split_counts": {"cohort": 100, "development": 80, "locked_test": 20, "cv_oof": [16, 16, 16, 16, 16]},
  "matrix": {"model_ids": ["method_a"], "folds": 5, "seeds": [17, 23, 42],
    "settings_per_model": 1, "cv_runs": 15,
    "final_fit_runs": 1, "total_fit_runs": 16, "test_inference_runs": 1},
  "coverage_exceptions": {"classic": "若缺经典参照，写实质理由，否则省略"},
  "training_authorized": false
}
```

local_status：absent / partial / structural_complete / validated。
executor_status：unknown / needs_adaptation / validated。
source_checked：metadata_only / abstract_only / paper / paper_and_code。
paper_access：metadata_only / abstract_only / full_text。code_access：not_checked / repository_page / source_files。
source_checked 的 paper/paper_and_code 必须对应 full_text；paper_and_code 还必须对应 source_files。摘要加仓库首页仍只能标 abstract_only。evidence_notes 对应实际读取记录，写明正文章节/代码文件和支持的判断，不能仅写“已核验”。
decision：select / defer / exclude。role 可 classic / recent / simple / alternative。
scientific selection 与 executor status 独立；选择 needs_adaptation 方法不意味着授权执行。

matrix 是拟议拟合矩阵；评估/推理次数、smoke 和其他敏感性实验在方案中另列。若模型设置数不同，应扩展成显式单元表并同时给出此统一矩阵的适用部分，不能填不成立的乘法。

运行：

```bash
/home/bxn/projects/PathoReason/.venv/bin/python \
  /home/bxn/projects/PathoReason/skills/benchmark-design/scripts/check_plan.py \
  --workspace /data/bxn/PathoReason/projects/PROJECT_ID \
  --plan outputs/benchmark-plan-vNEW.json
```

检查只验证必要字段、引用文件存在、矩阵算术和决策/状态一致性，不验证论文真实性或科学比较充分性。source_review_complete 也仅表示申报的选入论文均达到全文级，必须与实际工具轨迹和 evidence_notes 核对，不能将自报等级当第三方验证。必须先自行读取原始来源并保留实际搜索调用，再说明工程检查的有限范围。
