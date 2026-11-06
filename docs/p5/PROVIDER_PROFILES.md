# 连接与模型设置：双提供商配置

版本：0.6.44-p5-provider-profiles，2026-11-06。

## 甲方如何切换

1. 连接 Tailscale，打开交付页面，进入左下角「连接与模型设置」。
2. 在「接入方式」中选择「阿里云百炼 · DeepSeek」。
3. API 地址保持 `https://dashscope.aliyuncs.com/compatible-mode/v1`；按账号实际开通情况选择默认模型 `deepseek-v4-pro` 或 `deepseek-v4.1-flash`。
4. 输入甲方自己的 API Key，点击「保存并应用」。配置会保存到服务器，并自动重新加载本部署的模型引擎。
5. 等待配置加载成功后使用对话。配置加载不代表真实推理已通过；鉴权、模型开通和余额以实际请求回执为准。

切回官方时选择「DeepSeek 官方」并保存即可。已经保存过 Key 时，输入框留空表示保留。界面只显示是否已配置，不回显 Key，也不将 Key 放入浏览器持久存储。未配置 Key 的提供商不能启用。切换针对当前部署的所有对话；已有对话的模型选择会按新提供商的可用列表校正。

正在执行模型回合、上下文压缩、研究目标、训练或有原生权限等待时，拒绝切换；先正常结束或暂停相应工作。配置被其他浏览器更新时需重新选择后保存。加载失败会恢复原配置并尝试重新加载；若恢复加载也失败，界面明确提示服务维护。

## 双方环境与凭据

| 环境 | 数据目录 | 私有配置目录 |
|---|---|---|
| 甲方交付 | `/data/bxn/PathoReason` | `runtime/providers/` |
| 开发验收 | `/data/bxn/PathoReason-dev` | `runtime/providers/` |

上述路径相对于各自数据目录。每个环境有独立 `profiles.json`、`deepseek-direct.env`、`dashscope-deepseek.env`。目录权限 700，凭据和配置原子写入为 600，不提交 Git。两个部署互不修改对方配置；最初复制已有官方凭据后，后续以本部署私有凭据为准，不再被全局同名环境变量覆盖。生图提供商配置不属于这个模型设置入口。

本次两套环境均保留 DeepSeek 官方为当前接入，百炼 Key 留空。无需让甲方编辑服务器环境文件。当前产品沿用受信任 Tailscale 网络操作员模型；能访问应用的人能修改本部署设置，没有新增账户角色隔离。运行在同一 Unix 用户下的环境分离也不构成操作系统级安全沙箱。

新部署可在服务空闲并停止应用后执行 `.venv/bin/python scripts/provider_config.py init`，然后重启引擎和应用。仅初始化时可额外指定 `--dashscope-env-file /private/file.env`（600），导入 `DASHSCOPE_API_KEY` 或 `OPENAI_API_KEY`、`OPENAI_API_BASE` 或 `OPENAI_BASE_URL`、`OPENAI_MODEL`；导入仍不自动启用百炼。已有部署日常使用前端维护。

## 兼容与验证边界

百炼使用 OpenAI 兼容 Chat Completions 接口，但须适配 `enable_thinking`、`reasoning_effort`、工具消息中的推理字段、输出上限以及不同模型的推理档位。Pro 别名提供关闭/高/最高，Flash 提供关闭/低/高/最高。仅允许受支持的官方 HTTPS API 域名，避免将 Key 发送到任意地址。

原生配置只包含活动提供商，保留该部署的 MCP、Skill 和会话目录。重启模型引擎不会删除会话、研究材料、审核或预算；切换后的可用模型与输出选项动态更新。历史官方推理记录不能作为百炼验证证据。

依据：[百炼 DeepSeek 文档](https://help.aliyun.com/zh/model-studio/deepseek-api)、[OpenAI 兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、[地域地址](https://help.aliyun.com/zh/model-studio/base-url)。具体账号可用模型、地域和额度仍由提供商决定。

验证分层：

- 工程：完整后端回归 644 通过、3 跳过；TypeScript/Vite 构建通过。专项覆盖隔离、缺失 Key、旧版本冲突、忙碌拒绝、回滚、凭据脱敏、同源请求和输出能力。
- 原生协议：实际安装的 OpenCode 连接本地模拟接口，4 组推理/输出配置、工具读取回传和上下文压缩通过，共 9 次模拟请求；没有付费模型请求。初次因 `enableThinking` 被原样透传失败，改为 `enable_thinking` 后通过，保留失败证据。
- 浏览器：1440/390/320 宽度及忙碌、冲突、提交后关闭共 6 场景通过；没有页面异常、弹窗横向溢出、Key 回显或持久化。开发环境实际执行一次保留已有 Key 的官方配置保存及引擎重载。
- 真实模型：百炼 Key 尚未提供，未验证真实百炼鉴权、推理或科学任务行为；没有新增训练、生图、作者批准或额度。

开发证据：`/data/bxn/PathoReason-dev/acceptance/provider-pytest-20261106.log`、`provider-wire-20261106-4/result.json`；同级保留早期失败与中间协议回执。正式发布的浏览器、数据保全和健康回执保存在交付环境 `acceptance/provider-profiles-20261106/`。
