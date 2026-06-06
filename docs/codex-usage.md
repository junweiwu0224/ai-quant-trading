# Codex Usage

本文件记录 Codex 在 AI Quant Trading 中的使用效果、复盘信号和流程调整依据。目标是减少返工、漏测、误判和沟通成本，不追求更多流程、更多文件或更多工具。

## 什么时候记录

默认不记录 XS/S 小任务。以下情况才记录：

- M/L/XL 任务完成后发现了可复用经验。
- 出现明显返工、漏测、验证失败、用户纠偏或上下文误判。
- 使用了 Superpowers、`spec-kit-xl`、subagents、hooks、MCP/plugin、frontend QA 或 debug loop，且结果值得以后参考。
- 准备新增、修改或删除 repo 规则、hooks、skills、MCP、memory 记录或质量门禁。

不要记录一次性过程流水账、未验证猜测、敏感信息、凭证、生产数据或用户隐私。

## 轻量记录

| 日期 | 任务/范围 | 分级 | 使用的流程/工具 | 验证 | 效果信号 | 后续动作 |
|---|---|---|---|---|---|---|
| 2026-06-07 | 建立 Codex repo context pack | M | `repo-onboarding`、全局 workflow kit、只读仓库盘点 | `git status --short`、`rg/find/sed` 只读检查、Markdown 文件存在性检查 | 正信号：模板能快速转成项目事实；发现 `docs/ARCHITECTURE.md` 已存在，避免重复创建大小写冲突文件；确认 `npm test` 是占位失败命令 | 用 3-5 个真实 M/L/XL 任务继续观察：验证选择是否更快、是否减少重复解释和漏测 |
| 2026-06-07 | 基线质量门禁试运行 | M | context pack 路由、`debug-loop`、前端静态渲染扫描 | 文件存在性检查通过；`python scripts/frontend_data_render_audit.py` 失败，因为当前 shell 没有 `python`；改用 `.venv/bin/python scripts/frontend_data_render_audit.py` 后通过并生成报告，风险计数 727 | 正信号：`docs/testing.md` 和 `docs/quality-gates.md` 帮助选出低副作用验证；负信号：模板命令没有先验证解释器可用，已修正为 `.venv/bin/python` 并记录到 playbook | 后续 onboarding 写命令前必须探测 `python`/`python3`/`.venv/bin/python` 等实际可用入口 |

## 周期复盘

每完成 3-5 个有代表性的 M/L/XL 任务，或发生一次明显返工/漏测后，回看上方记录：

- 哪些规则确实减少了误判或漏测？
- 哪些规则让小任务变慢或让文档变嘈杂？
- 哪些验证命令最常用、最可靠、最应该前移到 `docs/quality-gates.md`？
- 哪些项目知识应该晋升到 repo `AGENTS.md`、`docs/testing.md`、`docs/ARCHITECTURE.md` 或 ADR？
- 哪些经验已经跨项目稳定，应该升级到全局 `AGENTS.md`、个人 skill 或 memory？
- 哪些 hooks、MCP、subagent 模式或 skills 没有实际收益，应该放宽或删除？

## 调整决策

- 项目规则：更新 repo `AGENTS.md`。
- 项目命令或验证：更新 `docs/commands.md`、`docs/testing.md` 或 `docs/quality-gates.md`。
- 项目工作经验：更新 `docs/codex-playbook.md`。
- 长期技术取舍：写入 `docs/decisions/`。
- XL/正式需求边界：写入 `docs/specs/`。
- 跨项目稳定偏好：升级到全局 `AGENTS.md`、个人 skill 或 memory。

## 待评估事项

- 是否需要把常用验证命令包装成 `make` 或 `scripts/verify_*`。
- 是否需要启用项目级 hooks。
- 哪些前端模块最适合 subagents 并行处理。
