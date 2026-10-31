# 思考强度切换（2026-10-31）

模型选择旁增加「思考强度」下拉：关闭、低、高、最高，默认高。DeepSeek V4 Pro 与 DeepSeek Flash 使用同一组官方参数。按当前浏览器的对话和模型记住偏好；提交后冻结为本回合配置，执行中禁用控件。其他未声明支持的模型不显示或发送此参数。

## 参数和记录

- DeepSeek 官方 Chat Completions `reasoning_effort`：`none` / `low` / `high` / `max`；未混入优先级更高的 `thinking` 开关。参考 https://api-docs.deepseek.com/api/create-chat-completion/ 和 https://api-docs.deepseek.com/guides/thinking_mode/。
- OpenCode 自定义 variants 的 `reasoningEffort`，通过 `/session/{id}/prompt_async` 的 `variant` 选择。参考 https://opencode.ai/docs/models/#custom-variants。
- `GET /api/v1/models/reasoning` 返回当前模型配置实际支持的档位。`TurnInput.reasoning_effort` 校验枚举；不支持的模型拒绝显式强度。受支持的模型缺省固定为 high。
- `runtime_configs.document.reasoning_effort` 纳入配置摘要；公共 `TurnView.reasoning_effort` 来自冻结配置。旧记录不改写，未记录的旧回合返回 null。新参数不改变预算和输出 token 上限。
- 待派发恢复使用原回合冻结值；已派发任务仍仅核对、不重发。适配器在派发前验证原生 variant；缺失或不匹配报错，不静默退回默认值。
- 原 P0–P5 及权限契约快照保留，新增 `contracts/api-p5-reasoning.openapi.json` 和 `contracts/p5-reasoning/`。运行配置的可选字段为兼容性增量，无数据库迁移。

## 验证与发布

- 后端全量：127 passed，1 skipped。覆盖四档、默认值、正式回合、快照/恢复、幂等冲突、旧记录、非法/不支持档位，以及原生配置不匹配拒绝派发。
- 前端 TypeScript/Vite 构建通过。隔离浏览器 1440/390/320px：四档菜单、圆角与箭头留白、刷新记忆、各模型独立偏好、提交参数、运行锁定、不支持模型隐藏均通过；无页面异常，无真实提交。
- 实际 OpenCode 1.18.33 对隔离 loopback 模拟上游的四档请求均序列化为对应 `reasoning_effort`。无真实 DeepSeek 推理、费用或科研任务；此验证不冒称模型输出质量验收。
- 发布版本：`0.6.2-p5-reasoning`。证据、备份、文件 SHA 与只读线上验收见 `/data/bxn/PathoReason/acceptance/reasoning-20261031`；发布包见 `/data/bxn/PathoReason/releases/pathoreason-0.6.2-p5-reasoning`。
- 回滚仅恢复此次变更的源码、配置及前端入口，并重启已核对身份且空闲的应用/引擎；保留数据库、原生会话和新增证据，禁止用旧数据库覆盖新研究记录。
