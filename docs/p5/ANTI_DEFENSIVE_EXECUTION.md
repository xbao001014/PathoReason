# 防御型写作检查的显式调用

2026-11-04，`0.6.38-p5-writing-voice`。用户要求核对当前写作是否通过该项检查；若未明显体现，在合适环节显式调用 Skill。

## 当前稿件核验

只读核验时，目标等待作者审核，工作流 revision18、delivery/awaiting_review；用户已经批准 v11 科学内容，交付仍待审。目标累计15回合，本窗口1/14。没有替作者重开或批准节点。

v11 SHA-256：`dbac33cff9463c72af076f1e2290386892ff5a484ac2edf3daa399edc27a3fa7`；排版输入 SHA-256：`da8aca2914fc7d92ed61a88847c8c5d44950c6c51aea1a29d128af044b419033`。

项目文件未找到 `reader_facing_style_review.json` / `reader_facing_voice_report.json` 或其他 voice/style 命名报告。原生会话299条消息的工具输入核验找到 authorial-voice 读取和自报记录，未见 `check_reader_facing_voice` 执行或语义/voice报告名称。cross-material-integrity-v9 检查 R1–R7、引用一致性和科学事实，没有四项 policy-2 全文语义审核。这些证据不足以认定防御型写作检查通过。

开发者对两份文件只读执行既有 lint，将输出写在独立验收目录：均 `status=failed`、`style_status=needs_review`，第3行存在内部 `not submission-ready` 状态标记。`style_warnings` 为空也不等于语义通过。正文 References 另有全文访问/摘要核验状态及内部报告文件名，须由研究 Agent 按读者正文与审计材料分离规范判断。以上是缺口诊断，不是完整语义审核，不生成虚假的通过记录，不修改研究稿件或现有批准。

## 公共机制修复

- 新增可原生加载的 `anti-defensive-writing` Skill，明确为现有 authorial-voice policy-2 的 PathoReason 适配入口，保留原来源说明，没有原样导入外部 publication-first 指令。
- 写作主 Skill、stage-execution 与 workflow 显式路由：M4 起草使用并保存阶段报告；M6 作者裁定后、请求冻结前完成全文语义检查；M5 核查草稿记录；M7 只验证已批准稿及其报告，不在排版阶段改写冻结正文。
- 主机 `MANUSCRIPT AUTHOR WORKFLOW` 在 draft/scientific 注入实际加载、报告产出及注册要求；review/delivery 注入记录核查要求。压缩恢复和既有稿件阶段也能看到要求，不依赖 Agent 自行想起配套文件。
- 通过条件明确为确切 SHA、四项语义判断及双 `status/style_status=passed`。单纯读取文件、词法通过、完整性报告或 PDF QA 均不能替代。保留阴性结果、实质披露和作者批准边界。

本次增强的是 Skill 执行要求和运行时提示，不新增服务端报告 Schema 门禁，也不声称代码可验证文学判断。当前旧交付包保留；需要正文修改时由研究 Agent 提出新版本并走既有作者复审流程。不得用开发者 lint 冒充模型执行验收。

## 验证

验收目录 `/data/bxn/PathoReason/acceptance/anti-defensive-20261104/`：

- `native-voice-trace.json`：实际调用记录核查。
- `v11-developer-lint.json`、`typeset-developer-lint.json`：只读诊断，明确未完成语义审核。
- `pytest.log`：稿件门禁、回合窗口和原生 Skill 刷新回归。
- `release.json`、`native-check.log`：部署状态、发布前后研究状态一致性、原生 Skill 正文加载一致性。

Skill frontmatter 验证通过。真实研究 Agent 对新增 Skill 的调用和后续语义报告仍待其下一次获授权执行验证；本次未调用模型、增加额度、启动实验或改变作者门禁。
