# Subagents

本文件记录 AI Quant Trading 中 subagents 的并行边界、任务拆分规则和集成验证方式。

## 适用场景

可以并行：

- 多个独立 pytest 文件失败，根因可能不同。
- 后端 API、前端契约、样式/E2E 分属不同文件且边界清楚。
- 不同数据域的只读影响分析，例如 Signal、OpenClaw、Portfolio、Alpha。
- 已有 Superpowers 实施计划，任务之间不会修改同一文件或同一状态。

不要并行：

- 同一 `dashboard/static/style.css` 或同一 JS bundle 的竞争性修改。
- 同一 API contract、同一数据库 schema、同一数据迁移链。
- Signal/Qlib 语义迁移这种需要整体一致性的架构判断。
- 实盘、交易、权限、凭证、生产配置、外部服务写操作。

## 推荐工作流

- 有实现计划且任务独立：使用 Superpowers `subagent-driven-development`。
- 多个独立失败或独立调查：使用 Superpowers `dispatching-parallel-agents`。
- 计划不清楚或边界不稳：主 agent 先调查，不急于 dispatch。

## 项目并行分组

前端可以按页面/数据域拆分，但不要让多个 subagents 同时修改公共加载入口：

- Overview 机会池/雷达/告警：`dashboard/static/overview.js`、`dashboard/static/overview-radar.js`、`dashboard/static/alerts.js`，配套 `tests/test_overview_opportunity_frontend.py` 和 `tests/test_frontend_workflow_contracts.py` 的相关用例。若同时编辑，需要进一步按文件独占拆分。
- OpenClaw workbench 局部 UI：`dashboard/static/openclaw-workbench.js`、`dashboard/static/openclaw-conversations.js`，配套 `tests/test_openclaw_entry_frontend.py`、相关 frontend contract 和 `tests/e2e/openclaw.spec.cjs` 只读参考。
- Intelligence/研究页：`dashboard/static/intelligence-market.js`、`dashboard/static/intelligence-iwencai.js`、`dashboard/static/intelligence-qlib.js`，配套 `tests/test_intelligence_market_frontend.py`。
- Agentic signals/strategy lab：`dashboard/static/agentic-signals.js` 和 `dashboard/templates/index.html` 中 agentic 专属区域，配套 `tests/test_agentic_frontend.py`。如果涉及公共模板大段改动，改为主 agent 串行集成。
- Stock detail 局部：`dashboard/static/stock-detail-*.js`，配套 stock detail 相关 frontend contract。不要并行修改 `App.openStockDetail` 公共入口。

后端/API/data 可以按独立业务域拆分，但共享状态和生命周期必须由主 agent 串行控制：

- Signal / Qlib 只读信号层：`data/signals/*`、`dashboard/routers/signals.py`，配套 `tests/test_signal_engine.py`、`tests/test_signal_api.py`。不要同时改 `dashboard/routers/qlib.py` 的 legacy adapter contract。
- Qlib predictor/service 离线预测：`data/qlib/predictor.py`、`data/qlib/service.py`、`data/qlib/candidates.py`，配套 `tests/test_qlib_predictor.py`、`tests/test_qlib_service.py`。改 cache schema 或 `/api/qlib/top` 字段时必须串行。
- 行情采集适配器/HTTP/cache：`data/collector/http_client.py`、`data/collector/field_mapper.py`、`data/providers/astock_data_adapter.py`，配套 `tests/test_data.py` 中 provider/http/adapter 段。禁止真实外部数据请求。
- 纯规则/纯计算 engine：`engine/market_rules.py`、`engine/metrics.py`、`engine/portfolio_optimizer.py`、`dashboard/routers/market_rules.py`、`dashboard/routers/portfolio_opt.py`，可配套局部单测或 `tests/test_api_v2_full.py` 中相关小段。
- 账户/工作区 API 与 broker config 静态配置：`dashboard/routers/account.py`、`dashboard/routers/broker_config.py`，配套 `tests/test_account_store_config.py`、`tests/test_session_gate.py` 和相关 API 测试。不要触碰真实凭证文件。

不适合并行的共享区域：

- 前端公共运行时/导航/加载链：`dashboard/static/app.js`、`dashboard/static/core/app-shell.js`、`dashboard/static/app-bootstrap.js`、`dashboard/templates/partials/scripts.html`。
- Service worker/cache busting：`dashboard/static/sw.js`、`scripts.html`、bundle 版本号和加载顺序必须统一处理。
- 全局共享对象和跨页动作：`window.App`、`App.fetchJSON`、`App.switchTab`、`App.emit/on`、`PollManager`、`GlobalStockStore`、`OpenClawWorkbench`、`Watchlist`、`PaperTrading`。
- 竞争性 CSS/模板编辑：同一 `dashboard/static/style.css`、同一 `dashboard/templates/index.html` 中相邻 tab、共享 toolbar、共享 id 或 `data-*` action。
- 共享市场数据 DB/schema/storage：`data/storage/storage.py`、`data/storage/tick_storage.py`、`data/sync/*` 和依赖 `DataStorage` 返回结构的 routers。
- Dashboard app lifecycle / TestClient health：`dashboard/app.py`、`tests/conftest.py`、`scripts/dashboard_data_health.py`、`tests/test_dashboard_data_health.py`。
- Paper trading / conditional orders / risk / migration chain：`engine/models.py`、`engine/migrate.py`、`engine/order_manager.py`、`engine/risk_manager.py`、`engine/conditional_order.py`、`dashboard/routers/paper_trading.py`、`dashboard/routers/conditional_orders.py`。
- Live/broker/external services：`engine/live_engine.py`、`engine/broker.py`、`engine/brokers/*`、OpenClaw/LLM routers/tools。
- 跨 router 合同测试：`tests/test_api_v2_full.py`、`tests/test_dashboard.py` 可以只读参考，最终由主 agent 集成验证，不作为多个 subagents 的共同编辑区。

## Prompt 要求

给 subagent 的 prompt 必须包含：

- 目标和非目标。
- 相关文件、测试、错误输出。
- 可修改范围和禁止修改范围。
- 必须遵守的安全边界。
- 需要运行的验证命令。
- 返回格式：状态、改动、验证、风险、需要主 agent 集成检查的点。

不要把完整会话历史交给 subagent；只给完成子任务所需的最小上下文。

前端 prompt 额外要求：

- 明确 owned files，默认禁止改 `dashboard/templates/partials/scripts.html`、`dashboard/static/app.js`、`dashboard/static/core/app-shell.js`、`dashboard/static/app-bootstrap.js`、`dashboard/static/sw.js`，除非该 agent 独占公共入口。
- 返回新增或依赖的 `window.*`、`App.*`、DOM id、`data-*` action、bundle 版本号和需要主 agent 统一验证的测试。
- 不得假设脚本是 ES module；本仓库依赖 `defer` 顺序和全局 `App`。

后端 prompt 额外要求：

- 默认禁止改 `dashboard/app.py`、`tests/conftest.py`、`data/storage/storage.py`、`engine/migrate.py` 和共享 API contract 测试，除非 prompt 明确列入 ownership。
- 不得启动长期服务、Docker、数据同步、迁移、外部 API/LLM/OpenClaw/券商调用。
- 测试必须使用 `tmp_path`、monkeypatch 或 fake provider，避免写真实 `data/db/`、`data/paper_trading.db` 或凭证配置。

## 集成检查

主 agent 收到结果后：

1. 阅读摘要和改动。
2. 检查文件冲突和语义冲突。
3. 回读关键源码和测试，不把 subagent 结论当作事实。
4. 运行相关集成验证。
5. 必要时进入 `debug-loop`。

## 推荐验证

按实际改动选择目标验证，最后由主 agent 集中执行。

前端契约集中集：

```bash
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py tests/test_auth_frontend.py tests/test_overview_opportunity_frontend.py tests/test_openclaw_entry_frontend.py tests/test_intelligence_market_frontend.py tests/test_research_toolbar_frontend.py tests/test_agentic_frontend.py -q
```

后端/API/data 常用集：

```bash
.venv/bin/python -m pytest tests/test_data.py tests/test_scheduler.py tests/test_signal_engine.py tests/test_signal_api.py tests/test_qlib_predictor.py tests/test_qlib_service.py -q
.venv/bin/python -m pytest tests/test_paper.py tests/test_risk.py tests/test_conditional_orders.py tests/test_live.py -q
.venv/bin/python -m pytest tests/test_api_v2_full.py tests/test_dashboard.py -q
```

文档或流程改动：

```bash
.venv/bin/python scripts/verify_context_pack.py
```

只在人工接受报告产物和生命周期副作用时运行：

```bash
.venv/bin/python scripts/frontend_data_render_audit.py
.venv/bin/python scripts/dashboard_data_health.py
```
