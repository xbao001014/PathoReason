# 硬件监控与后续回合显卡选择

硬件功能为服务器正式研究提供设备可见性与可追溯绑定。硬件页只读采样；选择显卡不会启动训练、预留资源或迁移已有进程。

## 界面

固定导航增加“硬件设备”图标，展示服务器 CPU 使用率、逻辑核心数、系统内存，以及每张 NVIDIA GPU 的索引、型号、利用率、显存用量、温度和可展开的 UUID。页面可见时每 5 秒刷新；离开页面或浏览器切到后台后停止轮询，重新进入立即刷新。读取失败明确标记，不把未知指标显示成 0。

正式研究对话框下方增加“训练显卡”选择器。选项展示当前索引、型号和剩余显存；打开选择器及点击刷新时更新读数，不在聊天页持续轮询。选择立即保存，不需要再发送一条确认消息。回合执行、未决压缩/工具结果、归档或删除期间不可修改；其他窗口更新时按修订号拒绝覆盖。

以 GPU UUID 为身份，索引只是当前枚举。发现原配置索引与实际设备不一致时显示可操作提示。显存高占用但利用率为 0 仍展示实际占用；不自动抢占、杀进程或替用户换卡。

## 执行连接

`conversation_gpu_settings` 保存当前对话的显卡修订；不会修改同项目的其他对话或项目原始 `compute.json`。每次保存创建独立计算配置于 `DATA_ROOT/runtime/compute-bindings/gpu_*.json`，只替换 `gpu.index/uuid`，保留原存储位置、授权、并发和预算字段。配置摘要和 GPU 身份冻结到后续回合的 `runtime_configs.gpu_binding`，已有回合保持原记录。

正式提示词按当前回合的冻结绑定给出启动入口：

```bash
/home/bxn/projects/PathoReason/.venv/bin/python /home/bxn/projects/PathoReason/scripts/compute_exec.py --turn TURN_ID -- COMMAND ...
```

入口要求回合正在运行、冻结配置摘要正确，并核对实时 UUID/索引；随后实际设置 `CUDA_VISIBLE_DEVICES=GPU_UUID`、`AUTORESEARCH_COMPUTE_CONFIG=冻结配置路径` 和 `PYTHONDONTWRITEBYTECODE=1`，执行原命令。单卡可见时进程内使用 `cuda:0`。索引漂移时拒绝误用另一张卡，需重新选择。

该入口连接到后续计算命令，不是操作系统 GPU 沙箱；任意绕开入口或硬编码设备的历史脚本不受其强制控制。原生工具权限、原研究执行器的资源检查、训练授权和科学门禁继续生效。绑定到其他显卡的既有冻结实验应按原执行器流程准备新绑定，不直接改旧计划或迁移运行中进程。选择不保证下次启动时仍有空闲显存。

生成配置保留选择时的项目计算模板；若之后更改项目计算授权/资源模板，应重新保存显卡选择以生成匹配的新配置，不修改已冻结配置。历史绑定文件属于运行来源证据，不随删除聊天而抹去；已删除会话不能通过选择 API 读取或修改。

## 接口与采样

- `GET /api/v2/hardware`：聚合 `/proc/stat`、`/proc/meminfo` 和只读 `nvidia-smi` 查询。CPU 采样窗口约 150ms，GPU 查询 3 秒超时；后端缓存 4 秒并合并并发读取，无常驻采样进程。不读取进程命令行或凭据。
- `GET /api/v2/conversations/{cid}/gpu-settings`。
- `PUT /api/v2/conversations/{cid}/gpu-settings`，JSON `{"expected_revision":0,"gpu_uuid":"GPU-..."}`；新索引由服务器实时解析，客户端不能提交任意索引或路径。

新增契约为 `api-p5-hardware.openapi.json`、`p5-hardware/`，旧契约快照保留。仅服务器正式研究提供显卡切换；普通项目的合成 CPU 验证不因此获得 GPU 执行权限。

## 验证与范围

证据：`/data/bxn/PathoReason/acceptance/hardware-20261031/`。

- 基于开发基线的后端 209 项通过、1 项跳过；包括 CSV 异常值、采样缓存、UUID/索引差异、配置独立版本、原授权和预算保留、对话隔离、执行中拒绝修改、修订冲突、篡改检查、真实子进程环境以及索引漂移拒绝。
- TypeScript/Vite 构建通过。1440/390/320px 浏览器验证选择、保存失败回退、执行中禁用、硬件布局、读取失败不伪造零值；桌面验证 5 秒轮询、页面隐藏和导航离开停止采样。
- 服务器只读实测 96 个逻辑 CPU、8 张 GPU。发现已有项目模板中索引 5 与 UUID 当前对应的索引 2 不一致；仅记录问题，未修改这些模板。
- 没有启动真实训练、抢占其他任务、调用模型或修改既有研究输出。启动环境验证不等于科研训练或旧实验迁移验收。

## 主线程统一发布：0.6.10-p5-hardware

主线程基于 664ef5c 三方整合 22 个硬件文件。service.py、formal.py、App.tsx 的冲突按两侧功能合并，保留当前 execution_scope、Guidance 提议/选择事务及失败后的成果入口；没有整包覆盖仓库。交接包及基线/目标逐文件摘要校验通过。生成最终硬件契约，保留 guidance 和其他历史快照。

最终工程回归 221 passed、1 skipped；TypeScript/Vite 构建通过。对最终构建重新运行 1440/390/320px 硬件/选择器与 Guidance 浏览器检查，验证 UUID 提交、修订冲突、活动回合禁用、读取失败、页面轮询启停，以及旧引导的重复点击防护、草稿保留和过期选择处理。所有验证使用隔离夹具，部署烟测只 GET 硬件与已有会话选择状态，不修改真实 GPU 绑定。最终证据在 acceptance/hardware-20261031/main-integration；原 side 结果单独保留。

源码包：/data/bxn/PathoReason/releases/pathoreason-0.6.10-p5-hardware。manifest.json 校验包内文件，validation.json 记录实际提交、测试与部署结果。发布前核对应用回合、压缩、删除、工具回执及原生会话/待批工具空闲，保存一致性数据库备份、原源码和前端。仅重启应用，不重启 OpenCode，不运行模型或 GPU 训练。

回退应在空闲时恢复兼容的源码/前端版本；保留新数据库、GPU 绑定快照、回合预算和研究产物，不能恢复旧数据库抹掉发布后的历史。上一正式版本 0.6.9 不识别新显卡选择，回退后应停止使用该入口并明确后续回合的配置来源。真实训练及旧 runner 适配仍需要目标系统后续验证。

发布实际烟测识别 96 个逻辑 CPU 和 8 张 NVIDIA GPU，既有会话选择仍来自项目模板，conversation_gpu_settings 无新增选择。原研究 1701 个文件与三个项目 compute.json 摘要均不变。空闲预检发现上轮已中断的合成验证回合残留一条原生待批写入，核对来源后显式 reject 并保存回执，未批准/重放该命令；见 preflight-pending.json 和 stale-permission-rejection.json。
