# `/skill` 显式选择（2026-10-31）

已在聊天输入框接入显式 Skill 选择，复用 `/skills` 目录和现有 turn 请求的 `skill_id`。本次仅修改前端，不改变原生 Skill 内容、后端派发、研究文件或权限配置。

## 使用

- 输入 `/skill` 打开列表；输入 `/skill 数据` 等关键词按标题或 ID 筛选。
- 用鼠标、上下方向键选择，Enter/Tab 确认，Escape 关闭列表。确认只选择 Skill，不发送任务。
- 可直接输入或粘贴 `/skill pathology-data-api 核查当前数据接口提取任务的完整性`；准确 ID/完整标题后的空格将命令转换为 Skill 标签，任务正文保留。
- 标签适用于下一条成功发送的消息，发送成功后清除。失败保留正文、标签和重试 request_key；未发送草稿按会话保存，刷新可恢复。
- Shift+Enter 换行，中文输入法确认候选不会触发发送。可点标签上的 × 取消选择。

显式命令覆盖输入框此前的 Skill 选择。普通消息不强制指定 Skill，沿用原来的引擎路由；模型是否按需调用属于模型行为验证。未知 ID、无任务正文或当前不可用的 Skill 会阻止发送并提示，不能静默降级为普通请求。非开头的 `/skill`、`/skills/info`、`/skill/file.md` 和代码块中的示例保持普通文本。

目录按环境与项目上下文显示不可用原因。正式项目选择正式研究 Skill；普通项目的合成能力仍需用户先选择合成验证权限，结果解读需已有成果。选择命令不会开启训练权限、修改对话工具权限或增加预算。

## 实现与验证

- `apps/web/src/skillCommands.ts`：命令解析、目录解析与发送前校验。
- `apps/web/src/SkillCommandInput.tsx` / `skillCommands.css`：输入框菜单、键盘/输入法处理、视口内定位。
- `App.tsx`：复用 `skill_id` 和幂等重试，成功后清除本轮选择。
- `apps/web/tests/skillCommands.test.mjs`：5 项解析/校验测试。

TypeScript 检查和 Vite 生产构建通过；Playwright 在 1440px、390px、320px 下检查目录、不可用条目、中文筛选、Enter/Tab/Escape、输入法、单轮范围、失败重试、刷新恢复、切换会话和运行中禁用。全部 API 使用模拟响应，没有真实模型回合或研究任务。

证据目录：`/data/bxn/PathoReason/acceptance/slash-skill-20261031T063048Z/`。包含部署前源码与 `dist-before/`、构建 `dist/`、浏览器脚本/截图/结果和单元测试日志。服务器前端以先复制哈希资源、再原子替换 index.html 的方式更新；旧资源保留，不重启 8520/8522 服务。此验证说明 UI 正确传递选择，不等同于新的 OpenCode + DeepSeek 真实 Skill 行为验收。

复测（先依项目存储规范分配临时目录 `CHECK_DIR`）：

```sh
cd apps/web
npm run build -- --outDir "$CHECK_DIR/dist"
./node_modules/.bin/tsc src/skillCommands.ts --outDir "$CHECK_DIR/unit" --module es2022 --moduleResolution bundler --target es2022 --skipLibCheck
SKILL_COMMANDS_MODULE="file://$CHECK_DIR/unit/skillCommands.js" node --test tests/skillCommands.test.mjs
```

浏览器脚本在证据目录，使用独立静态页面和模拟 API；本机 Playwright/Chromium 路径写在脚本开头，异机复测需按安装位置调整。
