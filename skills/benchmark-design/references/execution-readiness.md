# MIL 执行前检查与对齐

用于方案进入 smoke、pilot、主训练，或排查不学习/结果异常时。先查看本轮授权、冻结方案及原失败记录；同范围授权沿用。结构检查、forward 成功、合成可训练性、真实数据学习与科学结论是不同层级。

## 公共适配入口

`src/pathoreason/mil_execution.py` 当前支持 MIL_BASELINE 的 MEAN_MIL、MAX_MIL、AB_MIL 多分类 CE。其他模型返回 `adapter_missing`，保留在原 benchmark 中并列出适配缺口；不改用另一个模型冒充，也不把已导入/做过 forward 写成正式执行器就绪。

从已确认配置继承 `in_dim/num_classes/dropout/act`、训练种子、优化器及 weight_decay、scheduler/warmup、采样、检查点选择等。公共入口拒绝布尔型 dropout、p=1、缺失或不支持的设置；不依赖构造器隐式默认值。异常先查实际层参数、train/eval 模式、非偏置权重梯度和更新，再判断数据/任务难度；不能仅凭低 AUC 或预测近似常数推断“数据无信号”。

先由研究 Agent 在项目 `plans/` 或 `runs/` 下生成新版本配置及 train/val 清单，保持冻结成员。CSV 需要 train/val/test 三组 path/label 列，test 两列均空；不填假测试样本，也不把训练样本借作 test。工具遇到非空 test 列即拒绝，不替你删除或改写原清单。已读取/评价过的测试集保留暴露记录，不能通过新文件名恢复“未见测试集”的身份。

在有 Torch、PyYAML 的训练环境运行（当前为旧项目 `.venv`，源码只读）：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/bxn/projects/auto-research/.venv/bin/python \
  /home/bxn/projects/PathoReason/scripts/mil_preflight.py \
  --config /data/bxn/PathoReason/projects/PROJECT_ID/plans/config-vNEW.yaml \
  --vendor-root /home/bxn/projects/auto-research/engines/auto_mil/third_party/MIL_BASELINE \
  --report /data/bxn/PathoReason/projects/PROJECT_ID/plans/preflight-vNEW.json
```

CLI 在独立 CPU 子进程运行，限时 60 秒、单线程；仅读取配置和清单元数据，不打开真实特征。执行三个合成更新步骤，逐个检查可训练权重矩阵的有限梯度及实际更新，避免“只有偏置更新”或“只有 weight decay 更新”误判。退出 0 表示这些检查通过；退出 2 表示失败，原因保存在新报告中。输出独占创建，旧报告不能覆盖。

可加 `--reference-config OLD_CONFIG` 比较全部配置字段。差异独立记录，不自动归为对齐成功，也不会将新配置改成旧配置。对齐还需核对样本、特征、标签/类别映射、采样、batch 顺序、初始化、评价单位与选模规则；不同 epoch 数等有意变更也应明确。不得以“达到先前某个 AUC”作为工程通过条件。

## smoke 与主训练复用构建和循环

由研究 Agent 创建新的 runner 修订，导入公共模块，不修补共享上游源码或覆盖旧研究脚本。GPU 命令使用当前回合提示中的 `compute_exec.py --turn … --` 前缀，遵守原研究执行器的隔离、预算、日志和检查点要求。CPU preflight 不申请 GPU。以下仅说明组件接口，不是独立作业启动器：

```python
import sys
sys.path.insert(0, '/home/bxn/projects/PathoReason/src')
from pathoreason.mil_execution import prepare_training, trainval_loaders, train_epoch, validate_epoch

# 先在获批执行器中核对授权/预算/输入；单可见 GPU 使用 cuda:0。
components = prepare_training(config_path, vendor_root, preflight_report, device='cuda:0')
train_loader, val_loader = trainval_loaders(components)
# 获批执行器负责有界循环、预算截止、日志、验证选模、检查点和恢复。
# epoch 从 1 开始；train_epoch 内部每 epoch 推进一步 scheduler，不在外层重复 step。
train_loss, elapsed = train_epoch(components, train_loader, 'cuda:0', epoch)
val_loss, val_metrics = validate_epoch(components, val_loader, 'cuda:0')
```

`prepare_training` 校验通过报告的配置、清单、适配/上游源码 SHA、Torch 版本与 `AUTO_MIL_*` 环境，再创建全新模型与优化器；不会把合成 probe 训练后的权重带入研究。配置、训练 seed、采样或源文件变化需要新 preflight。DataLoader 复用配置中的平衡采样开关和随机 generator。两条循环共享上游实现，不建立 test loader；训练数据与验证数据的患者关系、实际特征/标签语义仍由原执行器核验。

这个入口提供组件和前置检查，不提供新的矩阵调度器、GPU 租约、硬预算截止或安全沙箱；报告不是训练授权凭证。不得以 preflight 通过代替缺失的执行门禁。先在已有授权内完成 train/val 的小规模对齐，核对真实梯度/更新、日志和配置差异，再按原计划及资源预算推进矩阵；缺少可靠作业执行支持时明确报告缺口，不用后台裸进程绕过。

失败、旧脚本和原结果保留；新修订的生成、重试与成果登记由研究 Agent 完成。开发者的合成工程检查不能计作 Agent 自主研究成功。
