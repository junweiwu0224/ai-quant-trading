# 首页数据机会池增强实施计划

> **面向代理执行者：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步执行此计划。步骤使用复选框 (`- [ ]`) 追踪。

**目标：** 将首页“数据机会池”从单一自选股摘要增强为可解释、可切换范围的轻量机会入口。

**架构：** 复用现有 `/api/datahub/decision-matrix` 合同，在前端维护机会池范围状态：`watchlist`、`qlib`、`default`。首页只展示摘要、覆盖状态和评分依据，完整表格仍留在研发页。

**技术栈：** FastAPI、Vanilla JS、Jinja2、CSS、pytest + Node `vm` 前端单测。

---

### 任务 1: 前端机会池状态与渲染

**文件：**
- 修改: `dashboard/static/overview.js`
- 测试: `tests/test_overview_opportunity_frontend.py`

- [x] **步骤 1：编写失败测试**

在 `tests/test_overview_opportunity_frontend.py` 新增 Node `vm` 测试，构造最小 DOM，加载 `dashboard/static/overview.js`，断言：
- `App._buildOverviewOpportunityQuery('watchlist')` 返回 `scope=watchlist&limit=8&fast=true`。
- `App._buildOverviewOpportunityQuery('qlib')` 返回 `scope=qlib&limit=8&fast=true`。
- `App._buildOverviewOpportunityQuery('default')` 返回 `scope=watchlist&limit=8&fast=true&force_fallback=true`。
- `App._renderOverviewOpportunityData(data, true)` 会写入状态条、评分依据、风险标签。

- [x] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_overview_opportunity_frontend.py -q`
预期: 失败，提示 `_buildOverviewOpportunityQuery` 未定义或状态条元素未渲染。

- [x] **步骤 3：实现最小前端逻辑**

在 `dashboard/static/overview.js` 中：
- 新增 `App._overviewOpportunityScope = 'watchlist'`。
- 新增 `_buildOverviewOpportunityQuery(scope, { fast = true } = {})`。
- 修改 `_loadOverviewOpportunities()` 使用 `_overviewOpportunityScope`，自选为空时默认切到 `qlib`。
- 新增 `_renderOverviewOpportunitySummary(summary, itemCount)`，填充 `#ov-opportunity-status`。
- 修改 `_renderOpportunityRow(item)`，在股票列下展示 `reason_tags` 和 `risk_tags`，在风险列保留风险等级。
- 扩展 `_bindOverviewOpportunityActions()`，处理 `data-ov-opportunity-scope` 按钮点击并刷新。

- [x] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_overview_opportunity_frontend.py -q`
预期: 通过。

### 任务 2: 模板与样式

**文件：**
- 修改: `dashboard/templates/index.html`
- 修改: `dashboard/templates/partials/scripts.html`
- 修改: `dashboard/static/style.css`
- 测试: `tests/test_overview_opportunity_frontend.py`

- [x] **步骤 1：编写失败测试**

在同一测试文件新增断言：
- `dashboard/templates/index.html` 包含 `id="ov-opportunity-status"`。
- 包含三个 `data-ov-opportunity-scope` 按钮。
- `dashboard/static/style.css` 包含 `.opportunity-status-strip`、`.opportunity-scope-toggle`、`.opportunity-evidence-tags`。
- `scripts.html` 中 `overview.js` 版本号提升到新版本。

- [x] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_overview_opportunity_frontend.py -q`
预期: 新模板/样式断言失败。

- [x] **步骤 3：实现模板和样式**

在首页机会池卡片 header 中：
- 增加三段切换按钮：自选、Qlib Top、默认候选。
- 增加 `<div id="ov-opportunity-status" class="opportunity-status-strip">`。
- 保持“看完整矩阵”按钮。

在 CSS 中：
- 增加紧凑状态条、范围按钮、证据标签样式。
- 保持 8px 以下圆角，避免嵌套卡片和营销式大 hero。

在 `scripts.html` 中：
- 将 `/static/overview.js?v=11` 提升到 `/static/overview.js?v=12`。

- [x] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_overview_opportunity_frontend.py -q`
预期: 通过。

### 任务 3: 后端 fallback 支持与验收

**文件：**
- 修改: `dashboard/routers/datahub.py`
- 测试: `tests/test_dashboard.py`

- [x] **步骤 1：编写失败测试**

在 `tests/test_dashboard.py` 增加测试：当 `scope=watchlist&force_fallback=true` 且工作区自选为空时，`/api/datahub/decision-matrix` 返回非空默认候选，并且 `summary.used_fallback=true`、`summary.fallback_reason='forced_default'`。

- [x] **步骤 2：运行测试确认失败**

运行: `python -m pytest tests/test_dashboard.py::TestDashboardAPI::test_datahub_decision_matrix_forced_fallback -q`
预期: 失败，提示 `force_fallback` 参数未生效。

- [x] **步骤 3：实现后端最小支持**

在 `decision_matrix()` 增加 Query 参数：
`force_fallback: bool = Query(False, description="强制使用默认候选池")`

选择代码时：
- 如果 `force_fallback` 为 true，直接调用 `_fallback_seed_codes(storage, limit)`。
- 设置 `used_fallback=true`，`fallback_reason='forced_default'`。
- 其他路径保持现有行为。

- [x] **步骤 4：运行测试确认通过**

运行: `python -m pytest tests/test_dashboard.py::TestDashboardAPI::test_datahub_decision_matrix_forced_fallback -q`
预期: 通过。

### 任务 4: 集成验证

**文件：**
- 修改: 无新增逻辑，必要时修正前面任务缺口。

- [x] **步骤 1：运行相关单测**

运行: `python -m pytest tests/test_overview_opportunity_frontend.py tests/test_dashboard.py tests/test_auth_frontend.py -q`
预期: 全部通过。

- [x] **步骤 2：浏览器验收**

重启 `127.0.0.1:8311` 服务，刷新 `#overview`：
- 默认显示自选范围；若只有 1 只自选，状态条说明候选数量。
- 点击 `Qlib Top` 后表格刷新，状态条显示 Qlib 状态。
- 点击 `默认候选` 后显示默认候选池，不依赖当前自选股。
- 行内能看到评分依据和风险标签。

- [x] **步骤 3：记忆更新**

更新 `junwei-quant-session.md` 和必要的状态文件，运行：
`powershell -ExecutionPolicy Bypass -NoProfile -File "C:\Users\13960\Documents\Junwei Vault\CodexMemory\scripts\refresh-start.ps1"`
`powershell -ExecutionPolicy Bypass -NoProfile -File "C:\Users\13960\Documents\Junwei Vault\CodexMemory\scripts\validate-memory.ps1"`
