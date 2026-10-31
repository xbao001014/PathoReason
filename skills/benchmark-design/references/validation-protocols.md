# 验证协议与对话修订

用户可在同一项目对话要求从 CV 改为留出法、修改训练种子或调整候选模型。先读取最新方案和实际划分证据，再创建新版本并说明差异、运行次数与预算变化。只修改验证协议时，可引用既有方法库和检索证据，不必重拉数据或重做完整检索。明确授权的方案修订直接完成；训练授权独立。

新方案使用 `pathoreason.benchmark-plan/2`，以 `validation.method` 选择 `holdout` 或 `cross_validation`。版本 1 继续按原 CV 规则检查，不改写历史 JSON，不把 holdout 伪装成 folds=1。重复留出法、嵌套 CV、最终重新合并训练集等其他协议需独立建模，不能悄悄映射为固定留出法。

## 固定留出法

- 每位患者固定属于 train、validation、locked test 之一；同患者多切片同组。所有候选使用同一划分，按任务说明类别分层或不能分层的理由。
- `validation.split_seed` 是唯一数据划分种子；`matrix.seeds` 是训练随机种子，多训练种子不重新划分患者。声明 `fixed_split=true`。
- 验证集用于超参/检查点选择；锁定测试只用于预先确定的最终评价，不参与选型、调参、早停。主方案保留独立验证集，不自动合并到训练集做额外重训。
- 核对现存患者名单和来源。只有比例、人数或随机种子而没有已冻结名单时，标 `split_status=proposed`；不能把上轮文字中的“锁定”当作已经存在的冻结名单。若已有冻结名单，保留其患者身份与摘要。改变它必须明确理由和授权。
- `split_status=frozen` 必须提供工作区内 `split_manifest_ref` 和对应字节的 `split_manifest_sha256`。检查器只校验文件存在和 SHA；名单的患者不交叉、完整覆盖、类别分布以及冻结授权由实际证据核查，不能由计数替代。
- `split_counts.train + validation = development`，`development + locked_test = cohort`。移除 `cv_oof/cv_inner_train/cv_inner_val`，或设为空数组；不要保留过期 CV 统计。
- `matrix.folds=0`、`cv_runs=0`；`final_fit_runs = 模型数 × 训练种子数 × settings_per_model`；`total_fit_runs = final_fit_runs`。`test_inference_runs = final_fit_runs`，单独报告，不再加到拟合次数。
- 这里 settings 表示预先列明的主比较设置，每个对应一个最终被评价的拟合单元。通常每模型 1 个设置。若要先做超参搜索，搜索拟合、选择规则、smoke/敏感性及其预算另列，不能把每个试探配置都当成最终方案送入测试集。
- 多训练种子的均值/方差不能表述为跨数据划分的稳定性。说明固定划分的局限，不冒称与 CV 给出完全相同的证据。

示意（非任何实际项目的名单或推荐比例）：

```json
{
  "validation": {
    "method": "holdout", "fixed_split": true, "split_seed": 71,
    "group_unit": "patient", "stratification": "class label",
    "split_status": "proposed", "split_manifest_ref": null, "split_manifest_sha256": null
  },
  "split_counts": {"cohort": 100, "development": 80, "train": 64, "validation": 16, "locked_test": 20},
  "matrix": {"model_ids": ["method_a", "method_b"], "seeds": [17, 23, 42],
    "settings_per_model": 1, "folds": 0, "cv_runs": 0,
    "final_fit_runs": 6, "total_fit_runs": 6, "test_inference_runs": 6}
}
```

## 交叉验证

版本 2 明确 method=cross_validation，folds 至少 2；同样声明固定划分种子、分组/分层规则与 proposed/frozen 状态。训练种子不改变已确定的 CV 折分配。

保留开发集与最终锁定测试的边界，cv_oof 按折给人数，总和等于 development。cv_runs=模型数×折数×训练种子数×设置数；total_fit_runs=cv_runs+final_fit_runs；最终拟合的规则另述，test_inference_runs 与 final_fit_runs 对应。OOF 评估不计成最终锁定测试推理。不得将一折或只在最终测试集上验证称为 CV。

## 对话修订的交付

新 JSON、易读方案和变更摘要由研究 Agent 生成并登记。说明旧方案→新方案的协议、人数、拟合/推理次数、预算和剩余适配项；验证协议支持不等于训练 runner 已支持所有候选模型。不改 compute.json、既有方案或冻结名单来让检查通过。
