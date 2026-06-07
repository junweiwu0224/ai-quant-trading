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
| 2026-06-07 | 新增 context pack verifier | M | Superpowers brainstorming、TDD、verification-before-completion | RED：`tests/test_verify_context_pack.py` 因 `scripts.verify_context_pack` 缺失失败；GREEN：`11 passed`；真实验证：`.venv/bin/python scripts/verify_context_pack.py` 输出 `Context pack OK` | 正信号：把手动文档检查前移成无副作用门禁，能捕捉缺文件、错误架构引用、裸 `python`、缺少 `npm test` 警告和敏感模式；发现并修正了 `PLAYWRIGHT_BASE_URL` 误报 | 观察该脚本是否适合沉淀成 workflow kit repo 模板建议或通用脚本资产 |
| 2026-06-07 | 真实试跑 #1：前端/context 当前改动验证路由 | M | repo context pack、质量门禁矩阵、针对性 pytest | `.venv/bin/python scripts/verify_context_pack.py` 输出 `Context pack OK`；`.venv/bin/python -m pytest tests/test_verify_context_pack.py -q` 为 `11 passed, 1 warning`；`.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py tests/test_intelligence_market_frontend.py tests/test_overview_opportunity_frontend.py tests/test_research_toolbar_frontend.py -q` 为 `32 passed, 1 warning` | 正信号：`AGENTS.md`、`docs/testing.md`、`docs/quality-gates.md` 能直接把当前 dirty 的文档和前端改动路由到低副作用验证；未触发 Docker、外部数据、LLM 或浏览器长流程 | 下一轮试跑选择一个后端/API 或数据展示健康任务，验证是否同样能快速定位测试子集和风险边界 |
| 2026-06-07 | 真实试跑 #2：realtime quotes 后端/API 改动验证路由 | M | repo context pack、API 测试矩阵、前端契约测试 | `.venv/bin/python -m pytest tests/test_api_v2_full.py::TestWatchlist::test_realtime_quotes_status -q` 为 `1 passed, 1 warning`；`.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_realtime_websocket_initial_sends_are_disconnect_guarded -q` 为 `1 passed, 1 warning` | 正信号：从 `dashboard/routers/realtime_quotes.py` 的 WebSocket 初始发送断连改动，能快速定位到一个 API smoke 和一个既有静态契约测试；避免启动 Dashboard、真实 WebSocket 或行情服务 | 后续可把高风险 WebSocket helper 行为沉淀为更直接的 async 单测，但当前契约测试已覆盖关键结构 |
| 2026-06-07 | 真实试跑 #3：数据展示健康审计副作用校准 | M | debug-loop、质量门禁矩阵、数据展示健康脚本 | `.venv/bin/python scripts/dashboard_data_health.py --fail-on-hard` 生成 `api-report.json`，30 endpoints，failed 0，hard findings 0；`.venv/bin/python scripts/frontend_data_render_audit.py` 生成 `frontend-static-report.json`，risk_count 735；`.venv/bin/python -m pytest tests/test_frontend_data_render_audit.py -q` 为 `22 passed, 1 warning` | 正信号：数据展示脚本能提供有用健康信号；负信号：`dashboard_data_health.py` 会通过 TestClient lifespan 初始化本地 DB、启动/停止调度器和行情服务，并产生临时行情订阅，不应标为无副作用低层 hook | 已校准 `docs/testing.md` 和 `docs/quality-gates.md`：该脚本适合人工触发或较高层门禁，不放入默认无副作用 hooks |
| 2026-06-07 | 真实试跑 #4：hooks 候选集设计 | M | 质量门禁副作用分级、hooks 策略复盘 | 只读盘点 `.gitignore`、`docs/quality-gates.md`、`docs/testing.md`；未启用 hooks；更新后 `.venv/bin/python scripts/verify_context_pack.py` 复测 | 正信号：副作用分级帮助发现 `.venv/bin/python -m compileall -q .` 会写 `__pycache__/`、`frontend_data_render_audit.py` 会写 `test-results/`，二者不应列为严格无写入 hook；context pack verifier 适合默认阻断候选 | 当前只文档化候选集；后续若启用 hooks，先从 `verify_context_pack` 和稳定针对性 pytest 小集合开始 |
| 2026-06-07 | 真实试跑 #5：subagents 并行边界校准 | M | Superpowers `dispatching-parallel-agents`、两个只读 explorer、主 agent 集成 | 两个 explorer 只读分析前端和后端/API/data 边界；未改文件、未启动服务、未发外部请求；主 agent 更新 `docs/subagents.md` 后运行 context pack 验证 | 正信号：前端可按页面/数据域拆，后端可按独立 router/service/provider 拆；负信号：公共脚本加载链、service worker、全局 `App`、storage/schema、TestClient lifespan、paper/live trading 和共享 contract 测试都必须主 agent 串行控制 | 已把项目并行分组、禁止并行区、prompt 约束和推荐集成验证沉淀到 `docs/subagents.md`；后续真实实现任务再观察 subagents 是否实际减少耗时和返工 |

## 阶段复盘：5 次真实试跑后

结论基于 2026-06-07 的 context pack、质量门禁、验证路由、hooks 候选和 subagents 边界试跑。当前优先收敛流程，不增加自动化负担。

保留并继续使用：

- `AGENTS.md` + `docs/testing.md` + `docs/quality-gates.md` 的验证路由有效，能把前端、API、数据展示和文档改动快速定位到低副作用命令。
- `.venv/bin/python scripts/verify_context_pack.py` 是当前最适合的默认轻量门禁候选，适合文档/context pack 改动后主动运行。
- 副作用分级有效，已经阻止把 `compileall`、报告型 audit、TestClient health 误判为严格无写入 hooks。
- Superpowers 适合 M/L 或风险较高任务；XS/S 仍按全局任务分级直接处理，避免过度流程化。

保持文档化、暂不自动启用：

- hooks：当前不启用项目级阻断 hooks。若后续启用，只从 context pack verifier 和稳定、短耗时、无外部依赖的针对性 pytest 开始。
- subagents：只在边界清楚、owned files 不重叠、或只读分析能并行时使用；公共前端入口、storage/schema、lifespan、paper/live trading 和共享 contract 测试由主 agent 串行控制。
- 数据展示健康脚本：`frontend_data_render_audit.py` 和 `dashboard_data_health.py` 适合人工触发或标准交付门禁，不进入默认无副作用 hooks。

暂不推进：

- 不包装 `make` 或新的统一脚本入口，先继续观察真实任务中最常用、最稳定的命令。
- 不把每个任务都记录进 `codex-usage`；只记录 M/L/XL、返工/漏测、流程调整或明显可复用经验。
- 不把 MCP/memory/subagents 变成默认动作；必须有重复收益证据和清晰回退方式再升级。

下一轮观察：

- 用 3 个真实实现任务验证：context pack verifier 是否继续低误报、针对性 pytest 是否足够、subagents 是否真实减少耗时而不是增加集成成本。
- 若连续多次只需要同一组命令，再考虑把它们晋升到 `docs/quality-gates.md` 的更明确候选，或包装成项目脚本。

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

- 继续观察是否需要把常用验证命令包装成 `make` 或 `scripts/verify_*`；当前证据不足，暂不新增。
- 继续观察是否需要启用项目级 hooks；当前只文档化候选集，不自动启用。
- 用真实实现任务验证 subagents 是否减少耗时和返工；当前只完成边界校准。
