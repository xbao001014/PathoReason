# 上下文占用指示器补发

2026-11-02，用户指出重命名版本部署后上下文显示消失，随后明确要求补发。原指示器已在 `acceptance/context-indicator-20261102/release.json` 记录静态发布，但源码未提交。重命名发布使用已提交源码构建，将该功能遗漏；仅以 Git 已提交文件作为发布范围不足以保护已交付功能。

本次将 App 接入、ContextIndicator 及其 CSS 原样纳入提交 `3096896`，从该提交独立构建，发布前端增量 `pathoreason-0.6.16-context-indicator`。保留重命名功能及上下文与交接入口。应用健康版本仍为 `0.6.16-p5-conversation-titles`；本次没有修改后端。

显示当前上下文百分比、已用量/上限及可键盘访问的说明。继续使用会话 API、已有 SSE 和 4 秒轮询；压缩后使用其独立保守投影，未知值和待核对状态不冒充零用量。未改预算或计量规则。

TypeScript/Vite 构建通过；预览通过正常用量、未知用量、未知上限、压缩后估计及待核对五种状态；线上 1440/390/320 三宽度、提示框边界和重命名入口均通过。所有浏览器 API 请求均为 GET，没有新增模型调用。发布前后 42 张数据库表摘要一致，回合数仍为 91；app PID 3661907 / identity 46678253 和 OpenCode PID 380742 / identity 30015353 均未变化，其他未提交文档 SHA 不变。

静态发布保留旧 assets，最后替换 index，保留前一版静态包。证据在 `/data/bxn/PathoReason/acceptance/context-indicator-restore-20261102/`；前端源与 dist 包、49 个文件 SHA 清单在 `/data/bxn/PathoReason/releases/pathoreason-0.6.16-context-indicator/`。发布前应同时核对既有静态发布记录与 Git 状态，避免再次遗漏已经上线但尚未提交的功能。
