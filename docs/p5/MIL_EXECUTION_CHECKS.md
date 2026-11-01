# MIL 公共构建与执行前检查

2026-11-01，基于应用 0.6.11 的公共执行组件增量；benchmark-design 0.4.0，报告契约 `pathoreason.mil-preflight/1`。无 API/数据库契约或前端变更，应用 release 字段保持 0.6.11。

## 失败与根因

真实研究 Agent 的 pilot 和对齐诊断直接调用共享 MEAN_MIL 构造器，未显式传 dropout。只读源码及 CPU 合成复现确认：上游默认 `True` 被 `nn.Dropout` 作为概率 1.0 使用，训练特征全部清零，head/classifier 权重无数据梯度，仅偏置更新。已验证配置原本显式使用数值 dropout。不能据此把原低分解释为“图像无信号”，也不能保证修正后恢复某个历史 AUC；优化器、scheduler、采样等仍需真正对齐。

原诊断证据：`/data/bxn/PathoReason/acceptance/executor-review-20261101/`。旧模型实现、研究脚本、报告、结果与已暴露测试集记录均保留。

## 公共修复

- `src/pathoreason/mil_execution.py`：显式配置校验及共享构建，首批支持 MEAN_MIL、MAX_MIL、AB_MIL 多分类 CE。布尔型或 p=1 dropout、缺失及未支持参数报错，不代选参数或替换模型。复用上游优化器、scheduler、loss、训练/验证循环和 DataLoader 采样方式；初始化种子与 cudnn 设置明确。
- `scripts/mil_preflight.py`：60 秒 CPU 单线程子进程，只读配置及 CSV 元数据，三个合成步骤检查有限 loss、每个可训练权重矩阵的非零梯度及实际更新。报告独占创建；失败和超时留下独立失败报告。不会读真实特征、运行 GPU 或生成研究分数。
- `prepare_training`：检查成功报告与当前配置、CSV、公共适配/上游源码 SHA、Torch 版本、AUTO_MIL 环境相符后重新初始化组件；不复用 probe 权重。训练和 smoke 可调用相同的 `trainval_loaders/train_epoch/validate_epoch`。旧脚本不会被自动替换。
- 清单检查拒绝非空测试列、path/label 缺配、重复/重叠特征路径及非法类别；无需假测试样本。仅构造 train/val loader。患者归属、特征内容、标签语义与独立测试授权仍由研究协议/原执行器核验。
- 全字段配置差异报告，覆盖 weight_decay、scheduler、seed 等，差异不会被静默改平。正式回合指引及 benchmark-design 引用执行说明，适用于已有会话的下一回合，无需改写原 workspace AGENTS.md 或历史消息。

使用方法见 [Skill 执行指引](../../skills/benchmark-design/references/execution-readiness.md)。公共工具不是签名授权凭证、训练沙箱或后台任务调度器，原有计算绑定、隔离、预算、检查点和科学门禁仍需执行。

## 验证

证据目录：`/data/bxn/PathoReason/acceptance/executor-fix-20261101/`。

全量 **254 通过、1 跳过**；随后补充 CSV 空白字符/重复列名拒绝，最终定向回归 **18 项通过**。训练环境为旧项目只读 `.venv`，所有本次计算均为 CPU 合成测试，未安装或修改共享依赖。测试覆盖：

- 真实上游默认 p=1 的重现；即使 weight decay 引起权重变化，仍能因零数据梯度拒绝。
- 三个已适配模型均通过合成可训练性，以及新生成合成张量上的一轮公共训练/验证循环。
- 明确使用 weight_decay、scheduler、训练种子；配置、清单、采样环境或源码绑定变化使原报告失效。
- 非空 test、缺配、重复/重叠路径、类别错误拒绝；空 test 列可正常使用 Train_Val。
- CLI 成功/失败状态和旧报告不覆盖；Skill 校验通过。

全量回归有既有 Starlette 测试客户端弃用提示，无失败。研究目录 3,579 个文件的 size/mtime 基线及小型脚本/结果 SHA 留存，发布后逐项复核；其中 2,200 个文件校验了 SHA；大型特征/检查点未为此重复全量读取。没有新增真实模型调用或真实训练；工程和原生配置可用性不能算 OpenCode + DeepSeek 行为验收通过。

## 发布、恢复与下一节点

核验产品回合、原生状态、待批权限、压缩及删除操作空闲，备份一致性数据库和原公共源后，仅重启 8520 应用。8522 OpenCode、本机 8530、旧研究及其他 GPU 进程不重启。发布完成，原生进程保持不变；线上目录返回 benchmark-design 0.4.0，动态指引包含新入口。发布与原文件校验回执见上述 evidence 目录的 deployment.json。无迁移；回退时恢复本增量的公共代码/Skill 即可，不回滚数据库或覆盖研究输出。已生成的新报告、失败与后续 Agent 产物继续保留。

下一步由研究 Agent 自行生成新版本 runner/config/train-val 清单并调用公共检查，随后在原授权内做真实 train/val 对齐。CLAM、TransMIL、DTFD、R2T 等其余候选仍需各自适配与验收，不能因已有一次 smoke 就认定完整矩阵执行器接通，也不能从 benchmark 静默删除。21 fits 主矩阵、封存测试隔离及恢复/硬预算闭环尚未由本轮验收。
