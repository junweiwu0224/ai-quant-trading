# Quality Gates

本文件记录 AI Quant Trading 的质量门禁和 hooks 策略。默认先文档化，不自动启用阻断型 hooks。

## 当前状态

- Codex hooks：未启用。
- Git hooks / pre-commit：未启用项目级阻断 hooks；启用前需按本文候选集逐条确认。
- CI required checks：未在本阶段调整。
- 本地质量门禁脚本：context pack verifier、pytest、compileall、Vue build、dashboard data health、frontend render audit、Playwright E2E。
- 本次纵切的无外部依赖定向门禁：见 docs/testing.md 的最小命令。
- operation/evidence 纵切的默认配置定向门禁：`tests/test_agentic_operations.py`、`tests/test_signal_service_ledger.py`、`tests/test_evidence_store.py`、`tests/test_news_collector.py`；其中 API 测试必须保留项目级 `conftest.py`。
- 决策平台集中门禁：`tests/test_decision_platform_invariants.py`、`tests/test_decision_backup.py`、`tests/test_vue_decision_contract.py`、`tests/test_vue_more_contract.py`、`tests/test_decision_runtime_config.py`、`tests/test_decision_report_exports.py`、`tests/test_decision_report_export_contract.py`，见 docs/testing.md。

## 门禁分层

### Level 0：文档化门禁

适用于所有任务。Codex 根据 `AGENTS.md`、`docs/commands.md`、`docs/testing.md` 和本文选择验证命令。

### Level 1：快速本地门禁

适合在明确成本后前移到 hooks。默认只考虑无网络、无外部服务、无业务数据写入、不会生成大量产物的命令。

可作为默认阻断候选：

- `.venv/bin/python scripts/verify_context_pack.py`
- 针对性 pytest，根据受影响范围选择，不要求每次全部运行：
  - Context pack verifier / repo 规则：`.venv/bin/python -m pytest tests/test_verify_context_pack.py -q`
  - Dashboard 启动脚本和环境变量路由：`.venv/bin/python -m pytest tests/test_run_dashboard.py -q`
  - Intelligence 市场前端契约：`.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py -q`
- 文档路径和引用检查。
- `npm run build --prefix dashboard/ui`：Vue 类型检查和生产构建。

不作为默认阻断 hook，但可人工触发：

- `.venv/bin/python -m compileall -q .`：会写 `__pycache__/`，适合标准交付门禁，不适合严格无写入 hook。
- `.venv/bin/python scripts/frontend_data_render_audit.py`：会写 `test-results/data-display-audit/frontend-static-report.json`，适合报告型门禁。

`scripts/dashboard_data_health.py` 不连接外部服务，但会通过 TestClient lifespan 初始化本地数据库、短暂启动/停止调度器和行情服务，并写 `test-results/data-display-audit/api-report.json`。不要把它放入无副作用 hooks；适合人工触发或较高层级门禁。

### Level 2：标准交付门禁

适合实现完成后主动运行：

- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m compileall -q .`
- `.venv/bin/python scripts/frontend_data_render_audit.py`
- `.venv/bin/python scripts/dashboard_data_health.py`
- 针对受影响前端页面的 browser smoke。
- 受影响 E2E：`scripts/e2e-local.sh smoke` 或 `scripts/e2e-local.sh data-health`。
- 决策平台集中 pytest 和 `npm run build --prefix dashboard/ui`。

本地 Dashboard/dev server 或 E2E server 启动属于人工触发的标准交付门禁：需要监听 `localhost`/`127.0.0.1` 时默认外部/非沙箱执行启动，但页面验证仍使用 Codex in-app Browser。启动前检查端口/PID，验证后清理临时服务。

### Level 3：高风险门禁

需要用户确认或专门环境：

- `DECISION_WORKER_ENABLED=true DECISION_EXTERNAL_DELIVERY_ENABLED=false AI_WORKER_ENABLED=true docker compose --profile ai --profile trading up -d --build`
- 真实数据同步。
- 外部 LLM/provider 服务联调。
- 实盘/券商 SDK、交易、下单、权限和生产配置验证。

## 改动类型矩阵

| 改动类型 | 最小门禁 | 推荐门禁 | 禁止自动 hook |
|---|---|---|---|
| 文档/context pack | `.venv/bin/python scripts/verify_context_pack.py` | `.venv/bin/python -m pytest tests/test_verify_context_pack.py -q`、路径/引用检查 | 无 |
| Python 逻辑 | 针对性 pytest | compileall、全量 pytest | 外部数据同步；`compileall` 不进严格无写入 hook |
| Dashboard 启动脚本 | `.venv/bin/python -m pytest tests/test_run_dashboard.py -q` | context pack verifier、必要时手动启动 smoke | 自动启动长期服务；真实外部服务 |
| API/router | 针对性 pytest | dashboard data health（人工触发；会写本地报告并触发应用 lifespan） | 真实外部服务写入 |
| Vue/TypeScript UI | `.venv/bin/python -m pytest tests/test_vue_*_contract.py -q` 与 `npm run ui:test` | frontend render audit、browser smoke、E2E | 自动启动长期服务；报告型扫描不进严格无写入 hook |
| 数据模型/存储 | 针对性 pytest | 全量 pytest | 迁移/清库/真实数据写入 |
| AI Runtime/LLM | `tests/test_ai_*.py`、`tests/test_ai_runtime.py` | 用户确认后联调 | 凭证、外部调用默认禁用 |
| 模拟盘/实盘 | 单元测试 | 人工确认的 dry-run | 下单、撤单、真实账户 |
| Docker/配置 | `docker compose config -q` | 用户要求“部署”时执行全量 `ai` + `trading` profile，并验证容器、API、浏览器 | tunnel、生产配置、真实 provider、实盘 |

## 决策平台特殊门禁

- 自动推送必须同时通过预览、walk-forward、当前数据健康、MarketAdapter provider qualification 和每个 NotificationTarget 测试；手动分析不得被这些门禁锁死。
- `DECISION_WORKER_ENABLED`、`DECISION_EXTERNAL_DELIVERY_ENABLED` 和 `vue_app_default` 默认关闭；配置缺失或非法时按关闭处理。
- Dashboard legacy 调度只有在 `DASHBOARD_BACKGROUND_WORKER=true` 且 `WORKER_OWNERSHIP=dashboard-legacy` 时才可启动；否则不得出现第二个决策/报告所有者。
- 恢复验证必须写入隔离目录，校验 manifest、SQLite 引用、附件内容 hash，并按指定 `decision_id` replay；不得连接外部通知、provider、LLM 或交易接口。
- 多市场显示不等于自动化资格。没有合格盘中 provider 的市场只能手动日线，不能生成 5 分钟自动推送。

## 禁止放入 hooks

- 全量 Docker 部署/停止命令；部署默认使用 `docs/commands.md` 的 `ai` + `trading` profile 命令，不能用只启动 Dashboard 的 `docker compose up -d` 冒充完整部署。
- 本地 Dashboard/dev server、E2E server 或任何长期监听端口的命令。
- 安装依赖、升级依赖、修改 lock 文件。
- 数据同步、数据库迁移、清库、清缓存。
- 外部 LLM/provider 真实调用。
- 实盘、券商、交易、下单、撤单、权限变更。
- 需要凭证、生产配置或真实外部服务的命令。

## 失败处理

1. 记录失败命令和关键输出。
2. 判断是否由当前改动引起。
3. 使用 `debug-loop` 定位根因并最小修复。
4. 复测同一门禁。
5. 如果是既有失败或环境缺失，在最终回复说明证据、影响和未验证风险。

## 待确认

- 是否需要在本仓库启用项目级 hooks；2026-06-07 阶段复盘结论是暂不启用，只保留候选集。
- 是否需要把已验证的 Level 1 候选组合成一个项目脚本；当前证据支持文档化路由，暂不新增包装入口。
- 如果连续多次总是运行同一组命令且耗时稳定，再考虑启用 hooks 或包装成统一快速门禁。
