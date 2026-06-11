# AI Quant Platform Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn AI Quant into a trusted, non-breaking A-share research workstation by first stabilizing data trust, then rebuilding the stock workflow around a TongHuaShun-style context-preserving workbench, and then upgrading natural-language research into a real task router.

**Architecture:** Keep the existing FastAPI + Vanilla JS dashboard and do not rewrite the whole system. P0 standardizes trust metadata and no-break fallbacks across intelligence, opportunity, signal, and stock data; P1 first builds the market-map/sector-constituent linkage, then reorganizes the stock page into left context list, central chart state, right evidence rail, and bottom event center; P2 turns iWencai/OpenClaw/search into a routed research workflow that can continue into stock detail, basket, backtest draft, and AI explanation.

**Tech Stack:** Python 3.12 `.venv`, FastAPI, SQLite/DataStorage, Vanilla JS dashboard modules, Chart.js/KlineCharts, pytest, Node VM frontend contract tests, Codex Browser/Computer Use QA.

---

## Best-Path Confirmation

The best plan is still **incremental platform upgrade, not full rewrite**.

Why this is better than rewriting:

- The current system already has valuable pieces: market breadth, heatmap, hotspot, news, decision matrix, Signal Engine, stock detail, watchlist, research tools, OpenClaw, tests, and dashboard QA scripts.
- The user-visible weakness is not lack of features; it is broken workflow continuity, unclear data trust, slow selectors, Qlib wording confusion, and stock-page information organization.
- A rewrite would delay the exact problems users are feeling now: "why 0", "why not full coverage", "why timeout", "why Qlib", "why stock page is not useful".
- The accepted spec already defines the right north star: learn TongHuaShun's mature workflow mechanics, then surpass it with AI Quant's trust envelope, Signal validation, backtest, Agent audit, and simulated-trading loop.

What "perfect system" means for execution:

- Not a single giant delivery that claims perfection.
- A sequence of proven slices where each slice has: competitor observation, mechanism extraction, AI Quant mapping, implemented behavior, tests, browser evidence, and competitor re-check.
- A slice is not complete if it only adds static text, decorative cards, or buttons without real state, data, or next actions.

## Competitor Learning Protocol

Every P0/P1/P2 slice must include this loop:

1. **TongHuaShun Read-Only Check**
   - Observe the matching TongHuaShun feature with Computer Use.
   - Record what problem it solves, what stays visible, which defaults matter, and how empty/degraded states are handled.
   - Do not log in, trade, buy data, submit forms, or copy restricted content.

2. **Mechanism Extraction**
   - Convert the observation into one sentence.
   - Example: "The left stock list is not navigation; it is the active comparison pool."

3. **AI Quant Mapping**
   - Map the mechanism to existing AI Quant data and modules.
   - Prefer existing APIs and JS modules before adding new dependencies.

4. **User Benefit**
   - State what the user can now do with fewer clicks, less waiting, less ambiguity, or stronger evidence.

5. **TDD Implementation**
   - Write failing API/frontend contract tests first.
   - Implement the minimum real behavior that makes the tests pass.

6. **Local Verification**
   - Run targeted pytest and frontend contract tests.
   - Start dashboard when UI changed and verify affected routes in Browser.

7. **Competitor Re-Check**
   - Look again at TongHuaShun's matching area.
   - If AI Quant only copied surface layout but still loses context, lacks evidence, or has dead actions, iterate.

8. **AI Quant Advantage**
   - Add what TongHuaShun does not prove by default: source, coverage, stale reason, validation confidence, backtest route, Agent audit, and simulated action boundary.

## Parallel Agent Operating Model

The main agent owns architecture decisions, shared contracts, final integration, and verification. Parallel agents are used for independent, bounded work:

- **Plan Reviewer Agent:** read-only review of the accepted spec and this plan for missing best-path details.
- **P0 Data Trust Agent:** read-only or disjoint implementation for API trust metadata and health audit gaps.
- **P1 Stock Workbench Agent:** read-only mapping and later disjoint UI implementation for stock workbench structure.
- **P2 Task Router Agent:** read-only mapping and later disjoint implementation for iWencai/OpenClaw/search routing.
- **QA Agent:** later browser/contract verification on pages not being edited by the current implementer.

Parallel rules:

- Do not let two workers edit the same file set at the same time.
- Shared files such as `dashboard/templates/index.html`, `dashboard/static/style.css`, `dashboard/static/app.js`, `dashboard/static/search.js`, and `dashboard/routers/market.py` are integrated by the main agent unless a worker has explicit ownership.
- Explorer agents can run in parallel freely because they are read-only.
- Worker agents must report changed files and verification commands. Main agent reviews and reruns integration tests.

## File Structure

P0:

- Modify `dashboard/routers/market.py`: hotspot trust envelope, stale fallback, source metadata, no-break empty state.
- Modify `scripts/dashboard_data_health.py`: include `/api/market/hotspot` and audit hotspot metadata.
- Modify `tests/test_dashboard_data_health.py`: lock safe path list and metadata findings for hotspot.
- Modify `tests/test_api_v2_full.py`: API regression for hotspot source failure and stale cache behavior.
- Modify `tests/test_intelligence_market_frontend.py` only if frontend display cannot already render hotspot source/degradation.

P1:

- Modify `dashboard/routers/market.py`: add/read sector constituent view model with trust metadata and local fallback.
- Modify `dashboard/static/intelligence-market.js`: heatmap tile selection renders sector summary and constituent table instead of only querying iWencai.
- Modify `dashboard/static/overview-radar.js`: align sector/heatmap actions with the same sector drilldown contract where feasible.
- Modify `dashboard/templates/index.html`: stock workbench shell containers only after API and state contracts are tested.
- Modify `dashboard/static/app-stock-ops.js`: preserve source context when opening stock from opportunity/news/hotspot/signal/search.
- Modify `dashboard/static/stock-detail-core.js`: load and render stock context, right evidence tabs, and shorter header summary.
- Modify stock detail modules as needed: `stock-detail-chart*.js`, `stock-detail-data.js`, `stock-detail-valuation.js`, `stock-detail-alpha.js`.
- Modify `dashboard/static/style.css`: dense workbench layout, desktop/mobile constraints, no nested card clutter.
- Add or extend stock frontend contract tests under `tests/test_frontend_workflow_contracts.py` or a focused stock detail frontend test file.

P2:

- Modify `dashboard/static/intelligence-iwencai.js`: classify natural-language query results, render parsed conditions and result actions.
- Modify `dashboard/static/intelligence-market.js`: news/hotspot topic actions preserve source context into iWencai, stock detail, and basket.
- Modify `dashboard/static/search.js`: global search supports stock/function/question intent without full-market default rendering.
- Modify `dashboard/routers/llm.py`, `dashboard/routers/openclaw.py`, or `dashboard/openclaw_tools.py` only if needed for routeable task payloads.
- Extend frontend workflow tests for natural language -> candidates -> stock -> basket/backtest draft.

## Task 0: Confirm Plan Completeness With Parallel Explorers

**Files:**
- Read: `docs/specs/2026-06-10-ai-quant-platform-upgrade.md`
- Read: `docs/decisions/0001-signal-engine-v2.md`
- Read: `docs/decisions/0003-watchlist-workspace-boundary.md`
- Read: `docs/testing.md`
- Read: `docs/subagents.md`
- Modify: `docs/superpowers/plans/2026-06-10-ai-quant-platform-upgrade-execution.md`

**TongHuaShun mechanism:** Mature platforms do not rely on one isolated screen; they keep the current research context visible while switching views.

**Why learn it:** The current AI Quant problem is not only bad data. It is that a user cannot trust whether a number is full-market, stale, empty, or actionable, and context often gets lost between pages.

**AI Quant mapping:** Use parallel read-only agents to check the spec, P0 data trust, P1 stock workbench, and P2 task router. Main agent folds their findings into this implementation plan.

**Benefit:** The plan becomes harder to execute superficially because every slice has a reason, mapping, test, and re-check.

- [x] **Step 1: Dispatch read-only explorer agents**

Dispatch these independent explorers:

```text
Plan Reviewer: review spec for missing best-path details and first-slice priority.
P0 Data Trust: inspect market/datahub/signals/data health tests for no-break gaps.
P1 Stock Workbench: inspect stock page modules and propose first workbench slice.
P2 Task Router: inspect iWencai/OpenClaw/search route continuity and propose MVP.
```

Expected: all explorers return summaries without editing files.

- [x] **Step 2: Merge explorer findings into this plan**

Update the `Backlog Refinement From Parallel Agents` section with accepted changes.

Expected: each accepted addition maps to P0/P1/P2 and has a verification plan.

- [ ] **Step 3: Run documentation sanity check**

Run:

```bash
.venv/bin/python scripts/verify_context_pack.py
```

Expected: PASS. If unrelated context-pack failures appear, document and continue only if they do not invalidate this plan.

## Task 1: P0 Hotspot Trust Envelope

**Files:**
- Modify: `tests/test_dashboard_data_health.py`
- Modify: `tests/test_api_v2_full.py`
- Modify: `scripts/dashboard_data_health.py`
- Modify: `dashboard/routers/market.py`

**TongHuaShun mechanism:** Hot areas and short-line signals are never just a naked list; they carry source context, market state, and a usable fallback area even when parts of data are missing.

**Why learn it:** The user previously saw "数据源异常 资金流". If hotspot returns a hard failure or unexplained empty state, the intelligence page breaks the research chain.

**AI Quant mapping:** `/api/market/hotspot` must return a trust envelope with `source`, `provider`, `generated_at`, `timestamp`, `coverage_note`, `source_unavailable`, `stale`, `stale_reason`, `partial_errors`, and empty arrays when source data is unavailable. Cached stale data must explicitly say it is stale.

**Benefit:** 情报页 can show "暂无热点数据 / 数据源异常 / 缓存数据 / 更新时间" without turning into "加载失败".

**Proof of effect:** API tests prove no bare failure; data health audit includes hotspot; frontend contract already expects degraded hotspot to avoid "加载失败"; browser QA later confirms visible state.

- [ ] **Step 1: Write failing metadata audit test**

Add this test to `tests/test_dashboard_data_health.py`:

```python
def test_metadata_findings_warn_when_hotspot_empty_lacks_trust_context():
    findings = find_metadata_findings(
        "/api/market/hotspot",
        {
            "success": True,
            "summary": "暂无热点数据",
            "concepts": [],
            "industries": [],
            "fund_flow": [],
        },
    )
    rendered = {(item.path, item.kind, item.value, item.severity) for item in findings}

    assert ("$.source", "missing_metadata", "source", "soft") in rendered
    assert ("$.coverage_note", "missing_metadata", "coverage_note", "soft") in rendered
    assert ("$.generated_at", "missing_metadata", "generated_at", "soft") in rendered
    assert (
        "$.source_unavailable",
        "missing_degradation_metadata",
        "empty_hotspot_requires_degradation_context",
        "soft",
    ) in rendered
```

- [ ] **Step 2: Add hotspot to safe path baseline**

Add `"/api/market/hotspot"` after `"/api/market/heatmap"` in `PLAN_BASELINE_SAFE_GET_PATHS`.

Run:

```bash
.venv/bin/python -m pytest tests/test_dashboard_data_health.py::test_metadata_findings_warn_when_hotspot_empty_lacks_trust_context tests/test_dashboard_data_health.py::test_safe_get_paths_cover_user_selected_data_areas -q
```

Expected: FAIL because `find_metadata_findings()` does not inspect hotspot and `SAFE_GET_PATHS` does not include it.

- [ ] **Step 3: Write failing API no-break test**

Add this test to `tests/test_api_v2_full.py` inside `TestMarketAPI`:

```python
def test_market_hotspot_returns_soft_unavailable_state_when_source_fails(self, client, monkeypatch):
    """GET /api/market/hotspot — 热点源不可用时不能让情报页硬失败"""
    from dashboard.routers import market as market_router

    previous_last_hotspot = market_router._last_hotspot
    market_router._cache.delete("hotspot")
    market_router._last_hotspot = None

    async def fail_hotspot():
        raise RuntimeError("hotspot unavailable")

    import alpha.hotspot_attribution as hotspot_module
    monkeypatch.setattr(hotspot_module, "get_hotspot_attribution", fail_hotspot)

    try:
        resp = client.get("/api/market/hotspot")
        data = resp.json()

        assert resp.status_code == 200
        assert data["success"] is True
        assert data["source"] == "hotspot_attribution"
        assert data["provider"] == "hotspot_attribution"
        assert data["source_unavailable"] is True
        assert data["stale"] is True
        assert data["stale_reason"] == "hotspot_source_unavailable"
        assert "hotspot unavailable" in data["error"]
        assert data["coverage_note"]
        assert data["generated_at"]
        assert data["timestamp"] == data["generated_at"]
        assert data["summary"] == "暂无热点数据"
        assert data["concepts"] == []
        assert data["industries"] == []
        assert data["fund_flow"] == []
        assert "hotspot unavailable" in data["partial_errors"][0]
    finally:
        market_router._cache.delete("hotspot")
        market_router._last_hotspot = previous_last_hotspot
```

Run:

```bash
.venv/bin/python -m pytest tests/test_api_v2_full.py::TestMarketAPI::test_market_hotspot_returns_soft_unavailable_state_when_source_fails -q
```

Expected: FAIL because current API returns `success: False` with only `error`.

- [ ] **Step 4: Implement hotspot metadata audit**

In `scripts/dashboard_data_health.py`, add `"/api/market/hotspot"` to `SAFE_GET_PATHS` and add a hotspot branch to `find_metadata_findings()`:

```python
if parsed_path == "/api/market/hotspot":
    _add_missing_fields(
        findings,
        payload,
        ("source", "coverage_note", "generated_at", "timestamp", "summary"),
    )
    empty_hotspot = (
        payload.get("concepts") == []
        and payload.get("industries") == []
        and payload.get("fund_flow") == []
    )
    if empty_hotspot and not _has_degradation_context(payload):
        findings.append(_missing_degradation("empty_hotspot_requires_degradation_context"))
    return findings
```

- [ ] **Step 5: Implement hotspot API trust envelope**

In `dashboard/routers/market.py`, add a helper near `_last_hotspot`:

```python
def _empty_hotspot_result(error: str = "", reason: str = "hotspot_source_unavailable") -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    result: dict[str, Any] = {
        "success": True,
        "source": "hotspot_attribution",
        "provider": "hotspot_attribution",
        "generated_at": generated_at,
        "timestamp": generated_at,
        "coverage_note": "热点归因源不可用，当前无可用热点数据",
        "summary": "暂无热点数据",
        "concepts": [],
        "industries": [],
        "fund_flow": [],
        "source_unavailable": True,
        "stale": True,
        "stale_reason": reason,
        "partial_errors": [error] if error else [reason],
    }
    if error:
        result["error"] = error
    return result
```

Then change `get_hotspot()` so success responses are enriched:

```python
generated_at = datetime.now().isoformat(timespec="seconds")
source_errors = data.get("errors") or data.get("partial_errors") or []
result = {
    "success": True,
    "source": data.get("source") or "hotspot_attribution",
    "provider": data.get("provider") or "hotspot_attribution",
    "generated_at": data.get("generated_at") or generated_at,
    "timestamp": data.get("timestamp") or data.get("generated_at") or generated_at,
    "coverage_note": data.get("coverage_note") or "热点归因：概念、行业和资金流聚合快照",
    **data,
}
if source_errors:
    result["partial_errors"] = source_errors
```

On exception:

```python
if _last_hotspot:
    generated_at = datetime.now().isoformat(timespec="seconds")
    return {
        **_last_hotspot,
        "stale": True,
        "source_unavailable": True,
        "stale_reason": "hotspot_source_unavailable",
        "generated_at": _last_hotspot.get("generated_at") or generated_at,
        "timestamp": _last_hotspot.get("timestamp") or _last_hotspot.get("generated_at") or generated_at,
        "coverage_note": _last_hotspot.get("coverage_note") or "热点归因源异常，展示最近一次缓存",
        "partial_errors": list(_last_hotspot.get("partial_errors") or []) + [str(e)],
    }
return _empty_hotspot_result(str(e))
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_dashboard_data_health.py::test_metadata_findings_warn_when_hotspot_empty_lacks_trust_context tests/test_dashboard_data_health.py::test_safe_get_paths_cover_user_selected_data_areas tests/test_api_v2_full.py::TestMarketAPI::test_market_hotspot_returns_soft_unavailable_state_when_source_fails -q
```

Expected: PASS.

- [ ] **Step 7: Run P0 regression group**

Run:

```bash
.venv/bin/python -m pytest tests/test_dashboard_data_health.py tests/test_intelligence_market_frontend.py tests/test_overview_opportunity_frontend.py tests/test_research_toolbar_frontend.py tests/test_signal_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Browser and competitor re-check**

Start dashboard:

```bash
.venv/bin/python scripts/run_dashboard.py --port 8001 --no-signal-service
```

Open `http://127.0.0.1:8001/#intelligence` in Browser. Verify:

- Hotspot section does not show a hard loading failure.
- Source, update time, cache/stale/source unavailable state are visible when applicable.
- News, market breadth, heatmap, and AI signal pool still render.

Then re-check TongHuaShun short-line/hotspot/right-rail behavior with Computer Use and record whether AI Quant now preserves the same "usable even with degraded evidence" mechanism.

## Task 2: P0 Data Trust UI Ledger

**Files:**
- Modify: `dashboard/static/intelligence-market.js`
- Modify: `dashboard/static/overview-radar.js`
- Modify: `dashboard/static/overview.js`
- Modify: `tests/test_intelligence_market_frontend.py`
- Modify: `tests/test_overview_opportunity_frontend.py`

**TongHuaShun mechanism:** Dense market panels keep counts, time, and source-like context near the data instead of hiding it in tooltips.

**Why learn it:** The user repeatedly asked "why 0", "why 100 up 0 down", "is heatmap right", and "market radar must be full coverage".

**AI Quant mapping:** Every intelligence and overview panel should render a compact trust line from response metadata: `source`, `generated_at/timestamp`, `universe`, `effective_count/total_count`, `coverage_note`, `source_unavailable`, and `stale_reason`.

**Benefit:** The user can judge whether a number is actionable, partial, stale, or unavailable without asking Codex.

- [ ] **Step 1: Write frontend contract tests for trust lines**

Add or extend tests so mocked payloads for breadth/news/heatmap/hotspot/decision-matrix render:

```text
数据源异常
缓存数据
全市场 / 本地覆盖池 / 非全量
有效 5,515/5,525
更新 2026-06-06 23:26:30
```

Run:

```bash
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py tests/test_overview_opportunity_frontend.py -q
```

Expected: fail only on missing specific trust-line rendering, not on setup errors.

- [ ] **Step 2: Implement reusable trust summary formatting**

Add small local helpers in the existing frontend modules, not a new global framework:

```javascript
function formatTrustParts(payload = {}) {
    const parts = [];
    if (payload.source_unavailable) parts.push('数据源异常');
    if (payload.stale) parts.push('缓存数据');
    if (payload.generated_at || payload.timestamp) parts.push(`更新 ${formatDateTime(payload.generated_at || payload.timestamp)}`);
    if (payload.universe) parts.push(payload.universe);
    if (payload.coverage_note) parts.push(payload.coverage_note);
    return parts.filter(Boolean);
}
```

Use existing escaping and date helpers.

- [ ] **Step 3: Run frontend contracts**

Run:

```bash
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py tests/test_overview_opportunity_frontend.py -q
```

Expected: PASS.

## Task 3: P1 Market Map + Sector-Constituent Linkage MVP

**Files:**
- Modify: `tests/test_api_v2_full.py`
- Modify: `tests/test_intelligence_market_frontend.py`
- Modify: `tests/test_frontend_workflow_contracts.py`
- Modify: `dashboard/routers/market.py`
- Modify: `dashboard/static/intelligence-market.js`
- Modify: `dashboard/static/app-stock-ops.js`
- Modify: `dashboard/static/style.css`

**TongHuaShun mechanism:** Market entry is a map, not a naked menu. The user picks a universe/board, selects a sector, sees constituent count and constituent rows, then clicks a constituent while the sector context remains visible.

**Why learn it:** The user repeatedly said market radar/heatmap is meaningless without full coverage and drilldown. A heatmap that only colors sectors but cannot answer "which stocks, why, and what next" does not support research.

**AI Quant mapping:** Use local `stock_daily + stock_info` coverage as the first safe constituent source. Heatmap tile selection calls a sector-members view model with `sector_name`, `grouping`, `source`, `universe`, `total_count`, `effective_count`, `display_count`, `generated_at`, `coverage_note`, and `members[]`. Opening a member calls `App.openStockDetail(code, context)` with `source: 'market:sector-heatmap'`, `sector_name`, and the candidate pool.

**Benefit:** The market page becomes a continuous path: market map -> sector -> constituents -> stock workbench. The stock left rail starts with a meaningful comparison pool instead of one isolated stock.

- [ ] **Step 0: Write failing market-entry-map contract**

Add a frontend contract in `tests/test_intelligence_market_frontend.py` that renders a minimal market-entry strip before heatmap drilldown. Assert it contains:

- at least these entry labels: `本地覆盖池`, `指数`, `板块/主题`, `资金流`;
- each entry exposes `universe`, `explanation`, `source`, `updated_at` or `generated_at`, and `status`;
- not-yet-implemented cross-asset entries render `待接入` or a clear unavailable reason instead of a generic stock table;
- selecting `板块/主题` keeps the heatmap visible and does not clear source/coverage text.

Run:

```bash
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_intelligence_market_entry_map_declares_universe_explanation_and_status -q
```

Expected: FAIL because the page has heatmap content but no explicit market-entry map contract yet.

- [ ] **Step 1: Write failing API sector-members test**

Add a `TestMarket` test that monkeypatches `_local_market_stock_rows()` with two bank stocks and one battery stock, then asserts:

```python
resp = client.get("/api/market/sector-members?name=银行&grouping=industry&limit=10")
data = resp.json()

assert resp.status_code == 200
assert data["success"] is True
assert data["sector_name"] == "银行"
assert data["source"] == "local_stock_daily"
assert data["universe"] == "local_stock_daily_coverage_pool"
assert data["total_count"] == 2
assert data["effective_count"] == 2
assert data["display_count"] == 2
assert data["generated_at"]
assert [item["code"] for item in data["members"]] == ["000001", "600000"]
```

Run:

```bash
.venv/bin/python -m pytest tests/test_api_v2_full.py::TestMarket::test_market_sector_members_returns_local_constituents_with_trust_context -q
```

Expected: FAIL with 404 or missing route.

- [ ] **Step 2: Write failing heatmap drilldown test**

Add a Node VM test in `tests/test_intelligence_market_frontend.py` that:

- mocks `/api/market/heatmap?fast=true` with a `银行` heatmap tile;
- mocks `/api/market/sector-members?name=%E9%93%B6%E8%A1%8C&grouping=industry&limit=30`;
- calls `Intelligence.loadHeatmap()`;
- clicks the rendered tile;
- asserts the same heatmap container renders `板块成分`, `有效 2/2`, `平安银行`, `浦发银行`;
- clicks `平安银行` and asserts `App.openStockDetail('000001', { source: 'market:sector-heatmap', sector_name: '银行', contextList: [...] })`.

Run:

```bash
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_intelligence_heatmap_click_renders_sector_members_and_opens_stock_with_pool_context -q
```

Expected: FAIL because heatmap tiles still use `query-hotspot` and no constituent panel exists.

- [ ] **Step 3: Implement sector-members API**

In `dashboard/routers/market.py`, add a safe local helper and route:

```python
def _build_local_sector_members(name: str, grouping: str = "industry", limit: int = 30) -> dict[str, Any]:
    ...

@router.get("/sector-members")
async def get_sector_members(name: str, grouping: str = "industry", limit: int = 30):
    ...
```

Filtering rules:

- `grouping == "industry"` filters by `stock["industry"] == name`.
- otherwise it filters by `_exchange_board_name(stock["code"]) == name`.
- sort members by `change_pct` descending, then `amount` descending.
- include trust metadata and explicit empty state when no members match.

- [ ] **Step 4: Implement heatmap constituent panel**

In `dashboard/static/intelligence-market.js`:

- render the market-entry strip before or above the heatmap with entries for `本地覆盖池`, `指数`, `板块/主题`, and `资金流`;
- each entry must show its universe, explanation variable, source/time/coverage, and `ready`/`deferred`/`degraded` state;
- non-implemented cross-asset or资金流 entries must be marked deferred with a reason, not represented as a fake all-stock table;
- change heatmap tile action to `data-intel-action="select-sector"`;
- store `Intelligence.state.latestHeatmapPayload`;
- bind click handling inside the heatmap container;
- fetch `/api/market/sector-members?...`;
- render a compact panel below the treemap with summary, trust line, and constituent rows;
- constituent row button calls `App.openStockDetail(code, { source: 'market:sector-heatmap', context_type: 'sector', sector_name, contextList, stock, price, change_pct, updated_at, rank_reason })`.

- [ ] **Step 5: Let stock context accept candidate pools**

In `dashboard/static/app-stock-ops.js`, make `openStockDetail()` pass `options.contextList`, `options.context_type`, `options.sector_name`, and `options.rank_reason` into `_pushStockContextItem()`. In `_pushStockContextItem()`, merge the selected stock and the candidate pool so the left context list shows the whole sector pool with source label `板块` and keeps the selected stock first.

- [ ] **Step 6: Verify this slice**

Run:

```bash
.venv/bin/python -m pytest tests/test_api_v2_full.py::TestMarket::test_market_sector_members_returns_local_constituents_with_trust_context tests/test_intelligence_market_frontend.py::test_intelligence_market_entry_map_declares_universe_explanation_and_status tests/test_intelligence_market_frontend.py::test_intelligence_heatmap_click_renders_sector_members_and_opens_stock_with_pool_context tests/test_frontend_workflow_contracts.py::test_open_stock_detail_uses_sector_candidate_pool_for_context_list -q
```

Expected: PASS.

- [ ] **Step 7: Browser and TongHuaShun re-check**

Browser path:

```text
#intelligence -> heatmap tile -> sector members -> open stock -> #stock context list
```

Confirm:

- no full page jump when selecting sector;
- market-entry map shows universe, explanation variable, source/time/coverage, and deferred reasons for not-yet-implemented entries;
- sector summary and constituent count visible;
- source/time/coverage visible;
- opening a constituent preserves `来自板块` context in the stock list.

Then re-check TongHuaShun market/sector page read-only and record whether AI Quant preserves the same "sector stays visible while constituent changes" mechanism.

## Task 4: P1 Stock Context List MVP

**Files:**
- Modify: `tests/test_frontend_workflow_contracts.py`
- Modify: `dashboard/static/app-stock-ops.js`
- Modify: `dashboard/static/stock-detail-core.js`
- Modify: `dashboard/templates/index.html`
- Modify: `dashboard/static/style.css`

**TongHuaShun mechanism:** The left stock list is the current comparison pool: recent browsing, watchlist, question results, and hot candidates stay visible while the chart changes.

**Why learn it:** Real research compares a set of candidates. Searching one stock at a time loses why the user opened it.

**AI Quant mapping:** Build a Stock Context List from `App.watchlistCache`, recent opened stocks, opportunity pool items, iWencai results, hotspot/news source payloads, and basket entries. First slice can use watchlist + recent + source payload passed by `App.openStockDetail()`.

**Benefit:** From opportunity/news/hotspot/signal into stock detail, the user can switch candidates without losing source label or reloading the full page.

- [ ] **Step 1: Write failing stock context contract**

Create a Node VM test that opens three stocks through `App.openStockDetail()` with different sources:

```javascript
await App.openStockDetail('300308', { stock: { code: '300308', name: '中际旭创' }, source: 'signal:top' });
await App.openStockDetail('002484', { stock: { code: '002484', name: '江海股份' }, source: 'opportunity:matrix' });
await App.openStockDetail('600519', { stock: { code: '600519', name: '贵州茅台' }, source: 'watchlist' });
```

Assert the stock tab contains a left context list with all three names, source badges, and active state. Assert clicking a context item calls `App.openStockDetail(code, { source: 'stock-context-list' })`.
Revise the final assertion before implementation: clicking a context item must preserve the item's original `source`, `sourceLabel`, `context_type`, `sector_name` or query metadata, and may add `trigger: 'stock-context-list'`; it must not overwrite the source with `stock-context-list`.

- [ ] **Step 2: Implement minimal DOM shell**

Add stock workbench containers:

```html
<div class="stock-workbench">
  <aside id="stock-context-list" class="stock-context-list" aria-label="股票上下文"></aside>
  <section class="stock-workbench-main">existing stock detail content</section>
  <aside id="stock-evidence-rail" class="stock-evidence-rail" aria-label="证据栏"></aside>
</div>
```

Keep existing content usable if JS fails.

- [ ] **Step 3: Implement context state**

In `app-stock-ops.js` or `stock-detail-core.js`, maintain:

```javascript
App._stockContextItems = App._stockContextItems || [];
```

Each item:

```javascript
{ code, name, source, sourceLabel, context_type, sector_name, rank_reason, query, price, change_pct, updated_at }
```

Do not load full-market lists.

- [ ] **Step 4: Render and bind list**

Render at most 50 context items. Empty state:

```text
暂无上下文股票；从自选、机会池、热点或问财打开股票后会出现在这里
```

- [ ] **Step 5: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -q
```

Then browser-check `#stock` desktop and mobile.

## Task 5: P1 Stock Header Compression and Evidence Rail

**Files:**
- Modify: `tests/test_frontend_workflow_contracts.py`
- Modify: `dashboard/static/stock-detail-core.js`
- Modify: stock detail data modules if needed
- Modify: `dashboard/static/style.css`

**TongHuaShun mechanism:** Stock identity is short: name, code, price, tags, company positioning, industry, concept, and key metrics. Long F10 text is moved into side details.

**Why learn it:** The user explicitly said stock name had a long unnecessary block, PEG was missing, AI was not covered, and Qlib coverage wording was confusing.

**AI Quant mapping:** The stock header shows one-line positioning, 3-6 tags, key valuation/financial chips, data coverage, and source. Long description moves to the right evidence rail under `资料`.

**Benefit:** The user knows "what this company is and why I am looking at it" in five seconds.

- [x] **Step 1: Write failing header compression test**

Mock stock detail payload with long `description` and assert:

- Header does not render the full long text.
- Header renders name, code, industry, concepts, PEG or `PEG 缺失`, Signal/AI coverage state, source badge.
- Evidence rail `资料` tab contains expandable long description.

- [x] **Step 2: Implement header summary helper**

Add:

```javascript
_buildStockIdentitySummary(data) {
    const tags = [...(data.concepts || []).slice(0, 4)];
    if (data.industry) tags.unshift(data.industry);
    return {
        positioning: data.positioning || data.main_business || data.industry || '公司定位数据暂缺',
        tags: tags.slice(0, 6),
        valuation: {
            pe: data.pe,
            pb: data.pb,
            peg: data.peg,
        },
    };
}
```

- [x] **Step 3: Render evidence rail tabs**

First tabs: `盘口`, `资料`, `资金`, `AI`, `舆情`.

Trading actions must remain disabled or simulated only.

Verified with:

```bash
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -q -p no:cacheprovider
```

Browser QA:

- Desktop `#overview -> 数据机会池 -> 600396 -> #stock`: header returns to the top of the stock workbench, `app.js?v=110` loads `stock-detail-core.js?v=13`, PEG/AI/Signal/source chips render, the long profile stays out of the header, and there is no horizontal overflow or console error.
- Mobile `390x844`: stock workbench collapses to one column, header remains readable, evidence rail exists, and there is no horizontal overflow.

## Task 6: P1 Chart-State MVP

**Files:**
- Modify: `dashboard/static/stock-detail-core.js`
- Modify: `dashboard/static/stock-detail-kline.js`
- Modify: `dashboard/static/stock-detail-timeline.js`
- Modify: `dashboard/static/app.js`
- Modify: `dashboard/static/app-ui-shell.js`
- Modify: `dashboard/static/sw.js`
- Modify: `dashboard/templates/partials/scripts.html`
- Modify: `tests/test_frontend_workflow_contracts.py`

**TongHuaShun mechanism:** Period,复权, indicators, event overlays, and chart zoom belong to one chart state, not scattered cards.

**Why learn it:** Technical research needs price, volume, indicator, and event in one decision surface.

**AI Quant mapping:** Maintain chart state:

```javascript
{
  code,
  period: 'daily',
  adjust: 'qfq',
  mainIndicator: 'MA',
  subIndicators: ['VOL'],
  eventOverlay: true
}
```

Persist to `sessionStorage` by workspace.

**Benefit:** Switching stocks and periods does not reset the user's research lens.

- [x] **Step 1: Write chart-state contract**

Assert that changing period/indicator updates state, reloads chart data, and leaves context list/right rail visible.

Verified contracts:

- `StockWorkbenchState` initializes from `open()` source context and candidate pool.
- Period and indicator changes update `chartState`/`indicatorState` without losing `sourceContext` or `contextList`.
- Refresh keeps source context.
- Evidence rail content survives period/indicator changes.
- Chart lens persists to workspace-scoped `sessionStorage`.
- Opening the next stock in the same candidate pool restores the saved period/indicator lens.

- [x] **Step 2: Implement state and controls**

Define `App.StockWorkbenchState` or an equivalent module-owned state object before wiring controls:

```javascript
{
  selectedSymbol: { code: '', name: '', exchange: '', asset_type: 'stock' },
  quoteSnapshot: {},
  sourceContext: {},
  contextList: [],
  chartState: { period: 'daily', adjust: 'qfq', visibleRange: null, selectedCandle: null },
  indicatorState: { main: ['MA'], sub: ['VOL'] },
  layoutState: { leftOpen: true, rightOpen: true, bottomTab: 'events', railTab: 'quote' },
  relatedContext: { sectors: [], indices: [], peers: [] },
  eventFeed: [],
  fundamentalSnapshot: {},
  dataQuality: {},
  aiContext: {}
}
```

All controls in this task must update this state first and then render from it. Do not create period, indicator, rail, and event states as isolated globals.

Support first batch: `timeline`, `daily`, `weekly`, `monthly`, one intraday period if available; indicators `VOL`, `MACD`, `KDJ`, `RSI`, `BOLL`.

- [x] **Step 3: Browser verify nonblank chart**

Use Browser/Playwright to check `#stock`: chart canvas/SVG is nonblank after period switch and no overlapping controls on mobile.

Implemented:

- `App.StockWorkbenchState` is hydrated and synchronized from `StockDetail.open()`, detail header rendering, K-line/timeline period changes, and indicator changes.
- `chartState`, `indicatorState`, and `layoutState` persist to `sessionStorage` under `stock_workbench_state:<workspaceId>`.
- Opening a stock uses the persisted/active period first: if the user switched to `weekly + MACD`, the next symbol in the same pool opens with the same research lens instead of falling back to timeline.
- Fresh-page restore handles the legacy `stock-detail.js` default `_currentPeriod='daily'`: the persisted `weekly + MACD` lens wins over that default.
- `StockWorkbenchState.contextList` now prefers the rendered left-rail source `App._stockContextItems`, so the left context list and state object do not diverge after candidate switching.
- Timeline/K-line loaders now synchronize the indicator selector and timeline info panel visibility.
- Cache versions bumped: `app.js?v=110`, `app-ui-shell.js?v=35`, `sw.js?v=54`, `ai-quant-v156`, `stock-detail-core.js?v=13`, `stock-detail-timeline.js?v=4`, `stock-detail-kline.js?v=3`.

Verified with:

```bash
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -q -p no:cacheprovider
```

Browser QA:

- Desktop Playwright `#stock`: open `600396` from AI signal context, switch to `weekly`, select `MACD`, then open `600726` from the same candidate pool. Result: `selectedSymbol.code=600726`, `chartState.period=weekly`, `indicatorState.active=MACD`, `contextList.length=2`, evidence rail contains AI source and long profile, and KLineCharts renders 14 canvases.
- Workspace storage: `sessionStorage.stock_workbench_state:qa-ws` stores `period=weekly` and `active=MACD`.
- Fresh restore Playwright `#stock`: preseed `sessionStorage.stock_workbench_state:qa-ws` with `weekly + MACD`, then open `600396`. Main chart requests are all `period=weekly&count=200`, the selector shows `MACD`, KLineCharts renders 14 canvases, and no page/console errors appear.
- Mobile `390x844`: stock workbench collapses to a single column, header and evidence rail remain visible, and no horizontal overflow.
- No page errors and no significant console errors in the mocked browser run.

Known P1 follow-ups from read-only review:

- Add an explicit adjust/复权 UI (`qfq`/`none`) and make unsupported periods disabled with visible reasons.
- Promote chart-state writes into a single public setter before adding visible range, selected candle, zoom, and event overlay persistence.
- Bottom event tabs still need to read/write `layoutState.bottomTab`.
- Convert news/announcement/Signal entries into richer `eventFeed` and later wire bidirectional K-line event markers.

## Task 6.5: P1 Workbench State Completion Gate

Status: delivered as an incremental Stock Workbench gate. This does not complete the whole upgrade; it closes the first shallow-state gap found by the TongHuaShun Stock/K-line observer review.

TongHuaShun mechanism learned:

- The left candidate pool, central chart, right evidence rail, and bottom events are one workbench state, not separate page decorations.
- A missing data source should be visible as a missing/degraded reason, not hidden as an empty UI.
- Right-side evidence tabs need to behave like real stateful tabs so switching chart period or stock does not reset the research context.

AI Quant implementation:

- `StockWorkbenchState.relatedContext`, `eventFeed`, `dataQuality`, and `aiContext` now get a centralized evidence snapshot from `stock-detail-core.js`.
- Fields are either populated from current detail/source data or carry explicit `missing_reason` values, especially for `relatedContext.indices`, `relatedContext.peers`, and `news_research`.
- The right evidence rail now renders `数据质量`, `相关上下文`, `事件`, and `AI/Signal` sections in addition to the existing profile/PEG/source summary.
- Evidence rail tabs now write/read `layoutState.railTab`, expose `data-stock-evidence-tab`, `role="tab"`, and `aria-selected`, and preserve source context after tab switching.
- `app-stock-ops.js` now syncs the left context pool into `StockWorkbenchState.contextList` when the workbench state already exists, and active context rows expose `aria-current`.
- Cache versions bumped: `style.css?v=69`, `app.js?v=114`, `app-stock-ops.js?v=12`, `stock-detail-core.js?v=14`.

Verification:

```bash
node --check dashboard/static/stock-detail-core.js
node --check dashboard/static/app-stock-ops.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_stock_workbench_evidence_state_completes_with_missing_reasons_and_tab_state tests/test_frontend_workflow_contracts.py::test_stock_detail_header_compresses_identity_and_moves_long_profile_to_evidence_rail tests/test_frontend_workflow_contracts.py::test_open_stock_detail_builds_context_list_with_source_badges tests/test_frontend_workflow_contracts.py::test_stock_chart_state_changes_keep_evidence_rail_content tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_frontend_workflow_contracts.py::test_signal_engine_is_primary_frontend_semantics tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -q
```

Results:

- Focused workbench/cache/version suite: `8 passed, 1 warning`.
- Full frontend workflow contracts: `66 passed, 1 warning`.

Remaining gaps:

- `eventFeed` now has source/detail/quote/news-research state, but real news/announcement/Signal event aggregation is still a later slice. Closed by Task 9 first aggregation gate.
- `layoutState.bottomTab`, `selectedEvent`, and K-line event marker <-> bottom event bidirectional navigation are not implemented in this slice. Closed by Task 9 first selection/focus gate.
- `relatedContext.indices` and richer peers still require reliable local mappings from index/industry/valuation modules.

## Task 9: P1 EventFeed Aggregation + Bottom Event Center

Status: delivered as an incremental Stock Workbench slice. This does not complete the whole upgrade; it closes the first bottom-event and selected-event gap from the TongHuaShun Stock/K-line observer review.

TongHuaShun mechanism learned:

- News, announcements, research, capital events, and signal points stay attached to the current stock workbench instead of living as disconnected cards.
- A bottom event center should preserve the current chart context while letting the user filter event types and select one event.
- Selecting an event should create a visible chart focus state; missing event sources should explain why they are missing instead of faking complete coverage.

Parallel agents used:

- `019eb2d8-25a4-77f3-ab02-657c82ecc424`: event-source worker for `stock-detail-data.js` and `stock-detail-research.js`; completed and closed.
- `019eb2d8-2609-70d0-bb9d-af73934760ff`: chart-focus/style worker for `stock-detail-kline.js`, `stock-detail-timeline.js`, and `style.css`; completed and closed.
- `019eb2d8-2673-7d21-91b9-61acfab64962`: frontend-contract worker for `tests/test_frontend_workflow_contracts.py`; completed and closed.

AI Quant implementation:

- `StockWorkbenchState.selectedEvent` is now part of the stock workbench state.
- `stock-detail-core.js` now normalizes event records with `id`, `type`, `status`, `title`, `detail`, `at`, `date_key`, `source/source_label`, `direction`, `value`, `link_url`, `missing_reason`, and `raw`.
- Base events from detail/quote/source context merge with dynamic event sources without overwriting deferred loader results.
- The old `news_research` missing placeholder is removed when concrete news, research, announcement, dividend, northbound, or Alpha events arrive.
- `#stock-bottom-panel` renders bottom tabs (`events`, `news`, `reports`, `announcements`, `chart`) and writes `layoutState.bottomTab`.
- Clicking a bottom event writes `StockWorkbenchState.selectedEvent`, syncs `chartState.selectedCandle.event_id`, and renders `.stock-selected-event-marker` over the chart.
- News, announcements, dividends, northbound records, research reports, and Alpha signals now call `_setWorkbenchEvents(...)` with explicit missing states on empty/failure paths.
- K-line and timeline crosshair handlers now write selected candle payloads into `StockWorkbenchState.chartState`.
- Cache versions bumped: `style.css?v=70`, `app.js?v=115`, `stock-detail-core.js?v=15`, `stock-detail-data.js?v=2`, `stock-detail-research.js?v=2`, `stock-detail-kline.js?v=4`, `stock-detail-timeline.js?v=5`.

Verification:

```bash
node --check dashboard/static/stock-detail-core.js
node --check dashboard/static/stock-detail-data.js
node --check dashboard/static/stock-detail-research.js
node --check dashboard/static/stock-detail-kline.js
node --check dashboard/static/stock-detail-timeline.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q
.venv/bin/python scripts/verify_context_pack.py
git diff --check -- dashboard/static/stock-detail-core.js dashboard/static/stock-detail-data.js dashboard/static/stock-detail-research.js dashboard/static/stock-detail-kline.js dashboard/static/stock-detail-timeline.js dashboard/static/style.css dashboard/templates/index.html dashboard/static/app.js dashboard/templates/partials/scripts.html tests/test_frontend_workflow_contracts.py tests/test_intelligence_market_frontend.py tests/test_research_toolbar_frontend.py
```

Results:

- JS syntax checks: passed.
- Frontend contracts and affected version tests: `74 passed, 1 warning`.
- Context pack: `Context pack OK`.
- Diff whitespace check: passed.
- Playwright browser smoke on existing `127.0.0.1:8001` service: desktop `1440x1000` and mobile `390x844` both passed. The smoke authenticated locally, opened `600519`, rendered the bottom event panel, selected the `news` tab, clicked a QA event, verified `selectedEvent`, `chartState.selectedCandle.event_id`, chart marker, nonblank chart, no horizontal overflow, and no serious console errors.
- In-app Browser navigation tool was not exposed in this session, so browser QA used local Playwright instead of Chrome.

Remaining gaps:

- This is a first event-center gate, not a full professional event tape. Native KLineCharts event overlays and chart-click -> bottom-event reverse selection are closed by Task 9.5.
- Event de-duplication is deterministic enough for the current source groups, but not yet a full cross-source semantic dedupe engine.
- Dragon tiger and capital-flow eventFeed aggregation are closed by Task 9.5.
- `relatedContext.indices` and richer peers still require reliable local mappings from index/industry/valuation modules.

## Task 9.5: P1 Native K-line Event Overlay + Reverse Selection

Status: delivered as the next Stock Workbench event slice. This does not complete the whole platform upgrade; it closes the most important 同花顺 K-line workbench gap left after Task 9.

TongHuaShun mechanism learned:

- K-line is not only a price chart. Events such as news, announcements, dividends, capital flow, northbound changes, and 龙虎榜 need to land on the date/candle where the user is looking.
- Bottom news/event panels and chart markers are bidirectional: the user can start from an event list or from the chart date and still arrive at the same evidence.
- Missing event sources should stay visible as `missing_reason`; they must not create fake markers.

Why learn it:

- The user question behind a jump, breakdown, or volume spike is usually "that day what happened?" If events stay in a separate bottom list, the user still has to manually match dates.
- 同花顺's advantage here is workflow continuity: chart -> event -> evidence -> next action without losing the current stock, period, source pool, or right-rail context.

AI Quant implementation:

- `StockWorkbenchState.chartState` now includes `eventFocus`, `eventOverlay`, `eventOverlayEvents`, and `eventOverlayCount`.
- `stock-detail-core.js` maps ready `eventFeed` items with `date_key/chartTime` onto current chart data, renders `.stock-chart-event-dot` DOM hit targets, and creates best-effort locked KLineCharts `straightLine` overlays for the same event dates.
- Clicking a chart event calls `_onStockChartEventClick()`, writes `selectedEvent`, sets `layoutState.bottomTab` to the matching event group, updates `chartState.eventFocus`, highlights the bottom event, and refreshes the chart marker.
- K-line and timeline renderers now refresh event overlays after chart data loads, so period switches rebuild the overlay layer.
- `stock-detail-timeline-overlays.js` now feeds capital-flow records into `eventFeed` with `capital_flow` events or explicit missing/failure reasons.
- `stock-detail-market-dragon.js` now feeds recent 龙虎榜 records into `eventFeed` with `dragon_tiger` events or explicit missing/failure reasons.
- Cache versions bumped: `style.css?v=72`, `app.js?v=116`, `app-ui-shell.js?v=38`, `sw.js?v=58`, `ai-quant-v160`, `stock-detail-core.js?v=16`, `stock-detail-kline.js?v=5`, `stock-detail-timeline.js?v=6`, `stock-detail-timeline-overlays.js?v=2`, `stock-detail-market-dragon.js?v=2`.

Parallel agents used:

- `019eb340-5ec4-7a52-b552-98ad88cb5dd5`: read-only Stock Workbench/K-line event linkage explorer; confirmed current one-way linkage and minimal overlay/reverse-selection points.
- `019eb340-5f32-7ba2-91dd-1671dd3c0f8f`: read-only event data/API explorer; confirmed existing capital-flow and 龙虎榜 endpoints/modules and safe missing-state boundaries.
- `019eb340-5fa5-7721-86fb-3bbe0912550d`: read-only plan/spec gap reviewer; confirmed Task 9.5 as the highest-priority next slice after Task 7.6.

Verification:

```bash
node --check dashboard/static/stock-detail-core.js
node --check dashboard/static/stock-detail-kline.js
node --check dashboard/static/stock-detail-timeline.js
node --check dashboard/static/stock-detail-timeline-overlays.js
node --check dashboard/static/stock-detail-market-dragon.js
node --check dashboard/static/app.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -k "stock_workbench or stock_detail_asset_versions or service_worker_precache or changed_frontend_assets" -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
.venv/bin/python scripts/verify_context_pack.py
```

Results:

- JS syntax checks: passed.
- Focused stock workbench/cache contracts: `10 passed, 71 deselected, 1 warning`.
- Affected version tests: `2 passed, 1 warning`.
- Context pack: `Context pack OK`.
- Playwright browser smoke on existing `127.0.0.1:8001` service: desktop `1440x1000` and mobile `390x844` both passed after local QA login. The smoke opened `600519`, injected a deterministic QA `capital_flow` event on the current chart date, verified `.stock-chart-event-dot`, clicked the chart event, confirmed `selectedEvent.type=capital_flow`, `layoutState.bottomTab=chart`, `chartState.eventFocus.event_id`, bottom selected state, nonblank KLineCharts canvases, cache-busted scripts, and no horizontal overflow.
- Screenshots: `/tmp/ai-quant-task95-desktop.png`, `/tmp/ai-quant-task95-mobile.png`.
- In-app Browser navigation tool was not exposed in this session, so browser QA used local Playwright with service workers blocked.

本轮是否学到精髓:

- 部分学到。AI Quant now supports chart-date event points and chart -> bottom reverse selection, which is the core interaction missing after Task 9.
- It is not yet a full 同花顺-level professional event tape because same-day event clustering, semantic dedupe, richer related-index/peer mapping, and event-to-backtest/diagnosis continuation remain follow-ups.

Remaining gaps:

- Same-day events can still become dense when many sources land on one date; add clustering/count badges before treating this as a professional event tape.
- `relatedContext.indices` and richer peer/index mappings still need reliable local data.
- AI diagnosis consumption of `eventFocus` is closed by Task 9.6; deeper LLM-backed stock diagnosis remains deferred until evidence contracts are stable.

## Task 9.6: P1 AI Diagnosis Evidence Consumption MVP

Status: delivered as the next Stock Workbench evidence slice. This does not complete the whole platform upgrade; it closes the gap where AI/Signal in the right rail only showed coverage state and did not consume the selected K-line event or workbench evidence.

TongHuaShun mechanism learned:

- Stock diagnosis is not a single opaque recommendation. It is a structured checklist around the current symbol, chart event, capital evidence, news/event evidence, sector context, fundamentals, valuation, Signal state, and risk.
- The diagnosis must stay attached to the same stock workbench: selecting an event on the K-line should immediately change the evidence being explained, without losing period, indicator, source pool, or right-rail tab.
- Missing evidence is part of the answer. The UI should explain what is absent instead of inventing a score, probability, or buy/sell conclusion.

Why learn it:

- After a user sees a volume spike or capital-flow marker, the next question is not just "what happened" but "what does the current evidence prove, and what is still missing".
- AI Quant's advantage over a traditional terminal should be traceability: every diagnostic dimension points back to `StockWorkbenchState`, `eventFeed`, `eventFocus`, `dataQuality`, and `sourceContext`, and carries an explicit risk disclaimer.

AI Quant implementation:

- `stock-detail-core.js` now defines `_buildWorkbenchAiContext()`, `_buildWorkbenchAiDiagnosis()`, `_syncWorkbenchAiContextFromState()`, and `_renderAiDiagnosisRows()`. This also removes the runtime risk where `_syncWorkbenchEvidenceState()` referenced `_buildWorkbenchAiContext()` before it existed.
- `aiContext.diagnosis` is now a deterministic view model with eight dimensions: technical, capital, news, industry, fundamental, valuation, Signal, and risk. Each row carries status, evidence, counter-evidence or missing reason, source, timestamp, confidence, and focus state.
- `_setWorkbenchEvents()` refreshes AI diagnosis after asynchronous event sources arrive, so capital-flow, northbound, 龙虎榜, news, reports, announcements, dividends, and Alpha events can update the diagnosis.
- `_selectStockEvent()` refreshes AI diagnosis after bottom-event or K-line-event selection, so `selectedEvent`, `chartState.eventFocus`, and `diagnosis_focus_event_id` stay aligned.
- The right evidence rail AI section now renders `.stock-ai-diagnosis` rows below the existing AI/Signal coverage state. The output remains evidence-only and explicitly avoids buy/sell, probability, or certainty wording.
- Cache versions bumped: `style.css?v=73`, `app.js?v=117`, `app-ui-shell.js?v=39`, `sw.js?v=59`, `ai-quant-v161`, `stock-detail-core.js?v=17`.

Parallel agents used:

- `019eb360-de03-7ba0-b63a-ea86c55c57e1`: read-only plan/spec gap reviewer; confirmed P1 AI Diagnosis Evidence Consumption as the correct next slice and warned against static text or pseudo-scoring.
- `019eb360-de7b-7c80-82ea-6e337fec9789`: read-only implementation explorer; confirmed `eventFeed`, `selectedEvent`, and `eventFocus` ownership in `stock-detail-core.js`, and found the missing `_buildWorkbenchAiContext()` runtime risk.
- `019eb360-defe-7a42-96ac-d3a612599147`: read-only testing/QA explorer; recommended extending existing Stock Workbench frontend contracts and desktop/mobile browser smoke instead of adding a separate testing framework.

Verification:

```bash
node --check dashboard/static/stock-detail-core.js
node --check dashboard/static/app.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_stock_ai_diagnosis_consumes_event_focus_and_evidence_state tests/test_frontend_workflow_contracts.py::test_stock_workbench_evidence_state_completes_with_missing_reasons_and_tab_state tests/test_frontend_workflow_contracts.py::test_stock_workbench_chart_event_overlay_click_reverse_selects_bottom_event -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_frontend_workflow_contracts.py::test_service_worker_precache_keeps_large_page_bundles_out_of_install_path tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -k "stock_workbench or stock_ai_diagnosis or changed_frontend_assets or service_worker_precache" -q -p no:cacheprovider
```

Results:

- JS syntax checks: passed.
- Focused AI diagnosis/workbench event contracts: `3 passed, 1 warning`.
- Cache/version/service-worker contracts: `4 passed, 1 warning`.
- Wider stock workbench/cache contracts: `11 passed, 71 deselected, 1 warning`.
- Playwright browser smoke on existing `127.0.0.1:8001` service: desktop `1440x1000` and mobile `390x844` both passed after local QA login. The smoke opened `600519`, injected a deterministic QA `capital_flow` event, clicked `.stock-chart-event-dot`, switched to the AI rail tab, confirmed eight diagnosis dimensions, verified technical/capital dimensions consumed `eventFocus`, confirmed `diagnosis_focus_event_id` equals the selected event, confirmed nonblank KLineCharts canvases, cache-busted `app.js?v=117`, no horizontal overflow, and no console/page errors.
- Screenshots: `/tmp/ai-quant-ai-diagnosis-desktop.png`, `/tmp/ai-quant-ai-diagnosis-mobile.png`.
- In-app Browser navigation tool was not exposed in this session, so browser QA used local Playwright with service workers blocked.

本轮是否学到精髓:

- 基本学到。AI Quant now uses the current workbench state to explain evidence dimensions, not just render an AI status chip. Chart event -> bottom event -> right-rail AI diagnosis now forms a single loop.
- It still intentionally avoids 同花顺-style opaque stock scores, buy/sell conclusions, paid content, or hidden model claims.

Remaining gaps:

- Diagnosis is deterministic and evidence-based; a future LLM-backed explanation should be added only after backend evidence contracts and citation rules are stable.
- Same-day event clustering and semantic dedupe are still needed before the event tape feels professional with dense live data.
- `relatedContext.indices` and richer peer/index mappings still need reliable local data, so industry/peer diagnosis can still fall back to missing reasons.

## Task 7: P2 iWencai Task Router MVP

**Files:**
- Modify: `tests/test_intelligence_market_frontend.py`
- Modify: `tests/test_frontend_workflow_contracts.py`
- Modify: `tests/test_research_toolbar_frontend.py`
- Modify: `dashboard/static/intelligence-iwencai.js`
- Modify: `dashboard/static/intelligence.js`
- Modify: `dashboard/static/core/app-shell.js`
- Modify: `dashboard/static/app-stock-ops.js`
- Modify: `dashboard/static/stock-detail-core.js`
- Modify: `dashboard/static/screener-ai.js`
- Modify: `dashboard/static/alpha-tools.js`
- Modify: `dashboard/static/style.css`
- Modify: `dashboard/static/app.js`
- Modify: `dashboard/static/app-ui-shell.js`
- Modify: `dashboard/static/sw.js`
- Modify: `dashboard/templates/partials/scripts.html`

**TongHuaShun mechanism:** 问财 is a task router. It starts from the same "行情/功能/问句" input, routes into buckets, shows parsed condition chips with hit counts, and keeps the chart/evidence context visible while results remain available.

**Why learn it:** A single natural-language input that returns a table is not enough. The user needs to continue into stock detail, basket, backtest draft, or AI explanation.

**AI Quant mapping:** Query result model:

```javascript
{
  query,
  intent: { type, confidence, reason },
  parsed_conditions: [{ field, op, value, window, hit_count, status, raw_text }],
  buckets: [{ id: 'candidates', name: '候选股票', items: [] }, { id: 'themes', name: '板块主题', items: [] }, { id: 'news', name: '新闻证据', items: [] }],
  actions: ['open_stock', 'add_watchlist', 'send_screener', 'analyze', 'ask_ai', 'create_basket', 'draft_backtest'],
  status: 'result_ready',
  source_context: { source: 'iwencai', query, intent_type, result_pool_id, parsed_conditions, condition_hit_count }
}
```

**Benefit:** Natural language becomes the start of a workflow, not a dead-end result.

- [x] **Step 1: Write routed-result frontend test**

Mock a query response and assert:

- Parsed conditions are visible.
- Condition hit counts or unavailable reasons are visible.
- Buckets are visible and switching buckets preserves `query` and `source_context`.
- Status states render distinctly for `parsing`, `partial_result`, `needs_disambiguation`, `no_match`, `degraded_data`, and `requires_confirmation`.
- Candidate stocks have open/add/basket actions.
- "生成回测草案" action carries selected candidate codes.
- Source context survives into `App.openStockDetail()`.
- No-space Chinese fallback query such as `高股息低估值近5日放量` still splits into multiple conditions.
- `actions` gates both rendered buttons and delegated click handlers.

- [x] **Step 2: Implement render and actions**

Use existing `App.openStockDetail`, `Watchlist`, basket/research hooks, and OpenClaw/Copilot explain entry if available.

- [x] **Step 3: Verify end-to-end smoke**

Browser path:

```text
#intelligence -> input natural language -> candidate -> open stock -> stock context list shows source -> research/backtest draft action visible
```

Implementation evidence:

- `dashboard/static/intelligence-iwencai.js` now wraps legacy `/api/llm/iwencai` responses and richer routed responses into a view model with `intent`, `parsed_conditions`, `buckets`, `actions`, `status`, `source_context`, and `contextList`.
- Backend remains legacy-compatible for now: structured task routing is a frontend wrapper over `/api/llm/iwencai` unless the backend returns richer routed fields.
- `dashboard/static/intelligence.js` now handles bucket switching, row-level open/add/ask-AI actions, basket draft, and backtest draft events, with action gating at click time.
- `dashboard/static/core/app-shell.js` now accepts `iwencai:create-basket` and `iwencai:draft-backtest`, opens `research/basket`, fills candidates, refuses empty candidate pools, and does not auto-run backtest.
- `dashboard/static/app-stock-ops.js` and `dashboard/static/stock-detail-core.js` now preserve structured `source_context` into the stock workbench and context-list second clicks.
- `dashboard/static/screener-ai.js` stores `lastSourceContext`; Copilot prompts include `result_pool_id`, selected bucket, parsed conditions, and condition hit counts.
- Cache versions bumped: `style.css?v=67`, `app.js?v=112`, `app-stock-ops.js?v=11`, `app-ui-shell.js?v=36`, `core/app-shell.js?v=28`, `alpha-tools.js?v=7`, `screener-ai.js?v=2`, `intelligence.js?v=11`, `intelligence-iwencai.js?v=5`, `/sw.js?v=56`, `ai-quant-v158`.

Verification so far:

```bash
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/intelligence-iwencai.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/intelligence.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/core/app-shell.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/app-stock-ops.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/stock-detail-core.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/screener-ai.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/alpha-tools.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/app-ui-shell.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/sw.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" .venv/bin/python -m pytest tests/test_intelligence_market_frontend.py tests/test_frontend_workflow_contracts.py::test_open_stock_detail_passes_source_context_into_stock_detail_open tests/test_frontend_workflow_contracts.py::test_stock_workbench_state_initializes_from_open_context tests/test_frontend_workflow_contracts.py::test_stock_detail_refresh_preserves_source_context tests/test_frontend_workflow_contracts.py::test_stock_context_click_preserves_iwencai_source_context tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
```

Result: `65 passed, 1 warning`.

Browser smoke evidence:

```text
Desktop 1440x1000, Playwright with QA auth/API mocks:
#intelligence -> query 高股息低估值近5日放量 -> partial_result router -> bucket switch preserves iwencai:browser-smoke -> open 600000 stock -> stock workbench source_context has 3 parsed conditions -> context-list second click 000001 preserves result_pool_id -> create basket opens research/basket, writes sourceContext, includes candidates with rank instead of fake probability, and does not auto-run backtest.

Empty candidate pool check:
App.emit('iwencai:create-basket', candidates=[]) leaves location hash, basket-candidates value, and sourceContext unchanged.

Mobile 390x844:
router visible, document scrollWidth = 390, candidate table overflow remains inside .iwencai-table-wrap.
```

## Task 8: Final Verification and Iteration Gate

**Files:**
- Modify docs only if findings need recording.

- [x] **Step 1: Run core backend/API tests**

```bash
.venv/bin/python -m pytest tests/test_dashboard_data_health.py tests/test_api_v2_full.py::TestMarket tests/test_signal_api.py -q -p no:cacheprovider
```

Result: `45 passed, 1 warning`.

- [x] **Step 2: Run frontend contracts**

```bash
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" .venv/bin/python -m pytest tests/test_intelligence_market_frontend.py tests/test_overview_opportunity_frontend.py tests/test_research_toolbar_frontend.py tests/test_frontend_workflow_contracts.py -q -p no:cacheprovider
```

Result: `153 passed, 1 warning`.

Additional provenance fix verified:

```bash
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/intelligence.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/app-stock-ops.js
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" .venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_intelligence_news_topic_board_can_send_ai_prioritized_pool_to_screener tests/test_intelligence_market_frontend.py::test_iwencai_open_stock_action_preserves_task_router_source_context tests/test_intelligence_market_frontend.py::test_iwencai_app_shell_preserves_source_context_and_ignores_empty_basket_pool tests/test_frontend_workflow_contracts.py::test_open_stock_detail_uses_sector_candidate_pool_for_context_list -q -p no:cacheprovider
```

Result: targeted tests passed. This fixed the residual provenance gap where topic/hotspot send-to-screener and hotspot-to-iWencai did not carry `source_context`. Browser smoke also found a false-positive source label: `local_stock_daily` was shown as `AI信号` because `daily` matched the old broad `/ai/` rule. `_stockContextSourceLabel()` now maps local sector/heatmap sources to `板块` before AI/signal matching.

- [x] **Step 3: Run dashboard health audit**

```bash
.venv/bin/python scripts/dashboard_data_health.py
```

Result: `Endpoints: 37, failed: 0, hard findings: 0, soft findings: 3`.

Residual soft findings are stock_info cleanup debt:

```text
$.stock_info.duplicate_plain_count: duplicate_plain_count=318 extra_rows=318
$.stock_info.wrong_prefix_count: wrong_prefix_count=318
$.stock_info.blank_industry_count: raw_blank_industry_count=318 merged_blank_industry_count=0
```

- [x] **Step 4: Browser QA**

Use Browser for:

```text
http://127.0.0.1:8001/#overview
http://127.0.0.1:8001/#intelligence
http://127.0.0.1:8001/#stock
http://127.0.0.1:8001/#research
```

Check desktop and mobile:

- no blank page
- no fatal console/runtime errors
- no obvious overlap or clipped critical text
- source/time/coverage/stale state visible
- stock context list works
- chart nonblank
- iWencai result can continue into stock detail/backtest/basket

Evidence:

```text
In-app Browser, 1440x1000, http://127.0.0.1:8001/?_qa=task8-clean#intelligence:
Loaded the real intelligence page after recovering from one stale crashed tab. Visible sections: market breadth, market entry map, hotspot attribution, iWencai, AI signal pool. Console errors: none on initial load. Market entries showed universe/source/update/status, including deferred cross-asset entries.

In-app Browser sector click on existing 8001 session:
Clicking a sector rendered "板块成分加载失败"; console showed /api/market/sector-members failure. Direct API probe showed the route exists in current code, but unauthenticated curl returned 401. Treat this as current-session/auth/cache risk, not a frontend contract pass.

Temporary current-code server, 8011, Playwright with QA auth/API mocks:
Desktop 1440x1000 golden paths passed:
1. #intelligence heatmap tile -> .intel-sector-members -> open sector stock.
2. Stock workbench: context list preserved 2 candidates; weekly period selected; MACD indicator active; K-line chart container nonblank with canvas and nonzero dimensions.
3. iWencai: query 高股息低估值近5日放量 -> 3 condition chips -> bucket switch -> open stock preserves result_pool_id=iwencai:qa-pool -> create basket opens #research basket and writes sourceContext.
Console errors: none. Failed requests: none.

Mobile 390x844:
document.documentElement.scrollWidth = 390, iWencai router visible, 13 visible action controls, no console errors.
```

- [x] **Step 5: TongHuaShun re-check**

Use Computer Use read-only:

- Stock page: compare left list, chart area, right rail, bottom event center.
- 问财: compare categories, popular questions, structured follow-up actions.
- Market panels: compare market-entry map, sector constituent table, right evidence continuity, and dense status.

Record:

```text
Slice:
TongHuaShun mechanism:
AI Quant learned:
Evidence:
Remaining gap:
Next iteration:
```

Recorded from the three read-only TongHuaShun observer agents and one follow-up plan-review explorer:

| Slice | TongHuaShun mechanism | AI Quant learned | Evidence | Remaining gap | Next iteration |
| --- | --- | --- | --- | --- | --- |
| Market map / sector linkage | Universe-first sidebar and market entry map; sector is a first-class research object with constituent table, right evidence rail, related index, short-line events, news/research. | Keep market entries as `universe + explanation variable + source/time/coverage`; preserve sector -> constituent -> stock context. | Task 3 and Task 8 smoke verify market entry metadata and sector member -> stock context. | Sector panel is still mostly constituent table; right evidence model is not deep enough. | Add Task 3.5 `Sector Evidence Context MVP`: funds/volume proxy, news/research or missing reason, related index, Signal overlap, follow-up actions. |
| iWencai / task router | Unified search accepts market symbols, functions, and natural-language questions, then routes into buckets with visible parsed-condition chips and follow-up actions. | Use `intent -> parsed_conditions -> buckets -> actions -> source_context`; never treat natural language as a table-only query. | Task 7 tests and Task 8 smoke verify chips, buckets, stock open, basket draft, source context. Topic/hotspot provenance was fixed in this gate. Task 7.5 adds top global search intent routing, result buckets, task result rendering, and source-context handoff into iWencai. | Backend still returns mostly legacy iWencai payloads; richer field-level evidence, backend-owned hit counts, rate-limit/cache states, and golden-question coverage remain follow-up. | Add P2 golden-question and failure-state iteration for global search + iWencai, then promote backend routed schema when stable. |
| Stock/K-line workbench | One screen keeps left context pool, central K-line, right evidence, bottom events, period/indicator muscle memory. | Treat `StockWorkbenchState` as the state container: selected symbol, source pool, chart state, indicators, related context, event feed, data quality, AI context. | Task 6 tests and Task 8 smoke verify context pool, period, MACD, nonblank chart, source context preservation. Task 6.5 verifies right-rail state completion, missing reasons, rail tab state, and left context pool sync. Task 9 verifies dynamic event aggregation, bottom tab state, selected event, chart focus marker, and desktop/mobile smoke. Task 9.5 verifies chart event overlays, chart-click -> bottom-event reverse selection, capital-flow and 龙虎榜 event aggregation. Task 9.6 verifies evidence-based AI diagnosis consumes `eventFocus`, `eventFeed`, `dataQuality`, and `sourceContext`. | Same-day event clustering, semantic event dedupe, richer index/peer mappings, and backend-cited LLM explanation remain follow-up. | Add next P1 event-tape iteration for same-day clustering, or harden backend-owned iWencai router semantics depending on product priority. |

Task 8 close condition: tests and smoke pass for the delivered P0/P1/P2 slices, but the whole upgrade is not complete. Task 3.5, Task 6.5, Task 9, Task 9.5, Task 9.6, Task 7.5, and Task 7.6 are delivered; the next blocking product-quality gates are same-day event clustering, backend-owned iWencai router semantics, richer sector/index/peer evidence, and backend-cited LLM explanations.

## Task 7.5 Execution: Global Search Task Router

Status: delivered as an incremental P2 slice. This does not complete the whole upgrade; it closes the top-entry router gap identified by the TongHuaShun iWencai observer review and the follow-up product checker.

TongHuaShun mechanism learned:

- The top input is not only a command box. It presents one entry for行情、功能、问句, then keeps the result grouped by intent/bucket instead of forcing the user to choose the right page first.
- Natural-language queries should become tasks with visible route intent, selected bucket, and follow-up actions, not a dead-end table.
- Source context is part of the product behavior: the original query, intent type, selected bucket, result pool, and condition metadata must survive into iWencai, stock detail, basket, and backtest draft.

AI Quant implementation:

- `dashboard/static/core/command-palette.js` now supports `RESULT_KIND.TASK`, `TASK_INTENT`, `taskResults`, `resultBuckets`, and `activeIntent`.
- The command palette classifies exact stock/code lookups, function navigation, natural-language screeners, market topics, and market questions.
- Natural-language screeners/topics/questions produce a task result with `source_context.source = "global_search"`, `raw_query`, `intent_type`, `selected_bucket`, `result_pool_id`, and `rank_reason`.
- Executing a task result loads/switches to `#intelligence`, fills `#intel-iwencai-input`, and calls `Intelligence.runIwencai({ source_context })`.
- Browser QA found and fixed a real lazy-load race: the task execution path now waits for the latest `global.Intelligence.runIwencai` after the intelligence bundle has mounted instead of caching an empty pre-load object.
- `dashboard/static/intelligence-iwencai.js` now accepts `runIwencai(options)`, merges external source context into the iWencai view model, preserves hotspot/query provenance, and returns the view model for command-palette callers.
- `dashboard/static/app-ui-shell.js` renders task rows with title, description, bucket, intent, and disabled/action semantics without breaking stock/action rows.
- `dashboard/templates/index.html` advertises the top entry as `搜索行情 / 功能 / 问句...` and marks it as the task-router entry.
- Cache versions bumped for `core/command-palette.js?v=1` and `app-ui-shell.js?v=37`.

Parallel agents used and closed:

- `Cicero` read-only code explorer confirmed the true global entry is `command-palette.js`, not `search.js`.
- `McClintock` contract worker seeded failing global-search tests; the main implementation adapted them to the command-palette architecture.
- `Mencius` read-only product checker verified the slice must preserve single-entry semantics, buckets, degraded states, and source context.
- `Harvey` UI worker implemented task rendering, entry copy, cache-busts, and version assertions.
- `Hypatia` and `Poincare` observer attempts disconnected/errored and were closed; no results were integrated from them.
- `Heisenberg` test worker moved the global-search contract to the real command-palette entry and was reviewed/closed after returning `5 passed, 72 deselected, 1 warning`.

Verification:

```bash
node --check dashboard/static/core/command-palette.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/intelligence-iwencai.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -k global_search -q
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q
node - <<'NODE'
# Playwright browser smoke, using local auth and mocked /api/llm/iwencai:
# desktop 1280x800 and mobile 390x844 both run:
# command palette task row -> click -> #intelligence -> iWencai router -> source_context assertions.
NODE
```

Results:

- JS syntax checks: passed.
- Focused global-search contracts: `5 passed, 1 warning`.
- Broader affected frontend/version contracts: `79 passed, 1 warning`.
- Playwright browser smoke: desktop `1280x800` and mobile `390x844` both passed. The smoke verified task row copy, one iWencai request, `#intelligence` route, filled iWencai input, `source_context.source = "global_search"`, `intent_type = "natural_language_screener"`, `result_pool_id = "global-search:..."`, visible condition chips, no horizontal overflow, no page errors, and no console errors.

Remaining gaps:

- This is still a frontend routing slice. Backend iWencai fields remain legacy-compatible and are wrapped client-side when richer fields are absent.
- Top search currently exposes actionable task buckets, but field-level hit counts, cache/limit state, and provider evidence are still strongest inside the iWencai view model.
- Need a P2 golden-question pack covering 20-30 natural-language queries, including failure/partial/degraded states.
- Need browser smoke for the full top-entry path: command palette query -> task result -> iWencai router -> bucket switch -> open stock -> basket/backtest draft.

## Task 7.6 Execution: Global Search/iWencai Golden Questions + Failure States

Status: delivered as an incremental P2 quality gate. This closes the immediate regression-test and failure-state gap after Task 7.5. It does not yet promote backend iWencai/OpenClaw routers to own the full routed schema.

Files changed:

- `dashboard/static/core/command-palette.js`
- `dashboard/static/intelligence-iwencai.js`
- `dashboard/static/style.css`
- `tests/test_frontend_workflow_contracts.py`

Safety boundary:

- No production trading/live-order code, external-data sync scripts, broker credentials, real account flows, or provider credentials were modified.

**Why learn TongHuaShun:** 同花顺/问财 lowers the user's decision cost by making "行情/功能/问句" one entry and then showing structured follow-up paths. The mechanism worth learning is not the visual skin; it is that a vague or precise question becomes a visible task state with routed result buckets, parsed conditions, and next actions. AI Quant needs this because Task 7.5 proved the top-entry handoff works, but not yet that common real questions and degraded provider states are consistently understandable.

**What to learn:**
- Single-entry routing: stock lookup, function navigation, topic exploration, natural-language screener, news/research evidence, and strategy/backtest intents start from the same top search.
- Golden-question discipline: keep a stable pack of representative questions so the router can be regression-tested instead of manually sampled.
- Structured task states: `parsing`, `routed`, `bucket_pending`, `result_ready`, `partial_result`, `needs_disambiguation`, `no_match`, `degraded_data`, and `requires_confirmation` must render different user-facing states.
- Evidence and continuity: parsed conditions, hit counts or unavailable reasons, data time/cache/rate-limit status, selected bucket, result pool, and source context must survive into iWencai, stock detail, basket, and backtest draft.

**What not to copy:**
- Do not copy 同花顺/问财 brand wording, paid/restricted content, community content, proprietary rankings, exact layout skin, screenshots, or protected datasets.
- Do not infer or claim 同花顺 internal agent/framework details as fact; any competitor note must stay at the observable product-mechanism level.
- Do not wire public/commercial flows to unofficial scraping, login-gated content, trading account actions, or provider calls that require credentials.
- Do not fake hit counts, confidence, or provider evidence. If a field is unavailable, render `missing_reason`, cache state, or degraded state.

Implemented:

- `GLOBAL_SEARCH_GOLDEN_QUERIES` is now a 30-item fielded golden pack with `query`, `intent_type`, `bucket`/`primary_bucket`, `route`, expected/allowed fallback status, required actions, required `source_context` fields, and required visible reason.
- Golden coverage includes exact stock lookup, ambiguous stock lookup, function navigation, natural-language screener, sector/topic questions, market questions, basket/backtest draft intent, no-match, unsupported field, timeout, rate limit, stale cache, degraded hit count, partial evidence, disambiguation, and confirmation.
- `CommandPalette.classifyIntent()` round-trips golden intent, bucket, route, and expected status; global-search task results keep `raw_query`, `intent_type`, `selected_bucket`, `result_pool_id`, parsed-condition slots, and golden expectations in `source_context`.
- iWencai task states now normalize common failure/degraded types: `parse_failure`, `unsupported_field`, `stale_cache`, `rate_limited`, `timeout`, `permission_denied`, `offline_fallback`, `no_match`, `ambiguous_market_scope`, `write_confirmation_required`, `request_failed`, `degraded_data`, and `partial_source_failure`.
- The iWencai UI renders a diagnostic card with concrete type, reason, next action, provider, data date, cache status, and data status where available.
- Request startup now renders a `parsing` task view instead of a generic spinner, so users see the active query and parsed-condition direction while waiting.
- Blocked statuses (`failed`, `no_match`, `needs_disambiguation`, `requires_confirmation`) keep safe read/explain actions but do not expose write or broad pool actions before clarification/confirmation.
- Command-palette task execution now waits for the intelligence page load promise before running iWencai, preventing the tab loader from resetting the result area after a routed query.

Verified:

```bash
node --check dashboard/static/core/command-palette.js
node --check dashboard/static/intelligence-iwencai.js
node --check dashboard/static/intelligence.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -k "global_search or iwencai or golden" -q -p no:cacheprovider
```

Results:

- JS syntax checks: passed.
- Focused global-search/iWencai/golden contracts: `9 passed, 71 deselected, 1 warning`.
- Browser smoke with Playwright fallback passed for desktop `1280x800` and mobile `390x844` because the in-app Browser tool was unavailable in this turn.
- Browser smoke covered: top search -> iWencai success state, timeout failure, degraded hit-count state, confirmation-required state, no horizontal overflow, no fatal console/page errors, screenshots at `/tmp/ai-quant-task76-desktop.png` and `/tmp/ai-quant-task76-mobile.png`.
- Full-chain browser smoke passed for bucket switch, open-stock source context, basket draft, and backtest draft; the backtest path only generated a draft and did not execute a backtest.
- Warning: existing `StarletteDeprecationWarning` from FastAPI/TestClient.

**Remaining risks:**
- Backend iWencai remains mostly legacy-compatible; frontend wrappers can hide schema drift until the backend owns routed task semantics.
- Golden questions can overfit to test fixtures if they do not include realistic A-share wording, typos, broad prompts, and partial-provider states.
- Provider/rate-limit/cache states may be hard to verify without deterministic mocks; keep those tests local and explicit.
- Browser smoke used deterministic mocked iWencai responses, so it proves UI routing and state handling, not real provider coverage.
- This task improves research workflow reliability, but it must not be interpreted as financial advice quality or trading readiness.

## Task 3.5 Execution: Sector Evidence Context MVP

Status: delivered as an incremental P1 slice. This does not complete the whole upgrade; it closes the next market-map gap identified by the TongHuaShun observers.

TongHuaShun mechanism learned:

- Sector is not just a list entry. It behaves like a research object with constituent diffusion, trend/volume evidence, related index/news/short-line context, and follow-up actions.
- Selecting a sector should preserve the sector context while the user drills into constituents.
- Missing evidence should be visible as a reason, not hidden behind an empty panel or faked as a complete data source.

AI Quant implementation:

- `/api/market/sector-members` now returns `evidence_context` alongside legacy `members` fields, keeping backwards compatibility.
- `evidence_context` contains `summary`, `liquidity`, `signal_overlap`, `news_research`, `related_index`, and `next_actions`.
- Liquidity is explicitly labeled as a local `stock_daily.amount` volume/turnover proxy, not real-time capital flow.
- Signal overlap is calculated from the full sector member set, not only the displayed `limit` rows.
- News/research and related-index evidence currently render explicit `missing_reason` values instead of invented content.
- The intelligence heatmap drilldown renders `.intel-sector-evidence` between the sector header and constituent table.
- Opening a constituent or sending the sector pool to the screener preserves `source_context.context_type = "sector"`.

Verification:

```bash
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" node --check dashboard/static/intelligence-market.js
.venv/bin/python -m pytest tests/test_api_v2_full.py::TestMarket::test_market_sector_members_returns_local_constituents_with_trust_context tests/test_api_v2_full.py::TestMarket::test_market_sector_members_evidence_uses_full_sector_not_display_limit tests/test_api_v2_full.py::TestMarket::test_market_sector_members_empty_result_is_not_source_unavailable -q -p no:cacheprovider
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" .venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_intelligence_heatmap_click_renders_sector_members_and_opens_stock_with_pool_context tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled -q -p no:cacheprovider
PATH="/Users/junwei/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" .venv/bin/python -m pytest tests/test_intelligence_market_frontend.py tests/test_api_v2_full.py::TestMarket -q -p no:cacheprovider
```

Results:

- Focused API: `3 passed, 1 warning`.
- Focused frontend contract: `2 passed, 1 warning`.
- Broader intelligence/market suite: `84 passed, 1 warning`.

Remaining gaps:

- `news_research` is still a missing-reason placeholder until a local sector-news/research mapping exists.
- `related_index` is still a missing-reason placeholder until local sector-index mapping exists.
- `DataStorage()` initialization can run schema setup on cold/old local databases; this is pre-existing storage behavior and should be addressed by a separate read-path storage hardening slice if strict read-only GET semantics become a release gate.

## Backlog Refinement From Parallel Agents

Accepted additions from parallel read-only agents:

- **Best path confirmed:** Do not rewrite. Continue incremental upgrade because the current repo already has the valuable primitives. The real gap is workflow continuity and trust, not missing raw feature count.
- **P0 gate: slice-level competitor re-check:** Every delivered slice must include before/after TongHuaShun observation. A slice without a re-check record is not complete.
- **P0 gate: universe/coverage vocabulary:** Standardize visible universe names such as `all_a`, `watchlist`, `signal_top`, `local_stock_daily_coverage_pool`, and `iwencai_result_pool`. Every market-wide claim must show coverage/sample/time.
- **P0 gate: slow request state machine:** Use `cached`, `fast`, `full`, `fallback`, and `failed` states for opportunity/news/hotspot/radar flows. Cold starts must still leave the page usable.
- **P0 first cut:** `/api/market/hotspot` is the largest current no-break gap because it could still return a bare failure and the data health audit did not inspect it.
- **P1 first slice from current TongHuaShun observation:** Market Map + Sector-Constituent Linkage should precede the full stock workbench. TongHuaShun treats sector as a research object: sector list, constituent count/table, selected constituent, related index, short-line events, and news remain same-screen.
- **P1 market map contract:** Every market entry must declare universe, explanation variable, source/time/coverage, and next actions. Non-implemented cross-asset entries should stay deferred instead of pretending to be a generic stock table.
- **P1 sector context contract:** `openStockDetail()` context from sector drilldown must carry `type='sector'`, `sector_name`, `universe`, `rank_reason`, selected constituent, and candidate pool.
- **P1 Stock Workspace model:** Treat the three-column layout as a state container, not decoration. Persist current stock, source, candidate list, chart state, rail tab, and bottom tab.
- **P1 implementation boundary:** Do not rewrite stock detail. Reuse existing `App.openStockDetail()`, `syncActiveStockContext`, `StockDetail.open()`, KLineCharts rendering, and L1/L2 fallback. First implementation should move containers and state, not replace loaders.
- **P1 test priority:** Stock workbench tests must cover real JS behavior: pass `contextList/sourceLabel`, render left context items, click an item, preserve `chartState`, and keep existing `sd-*` ids reachable.
- **P1 observed state model:** The TongHuaShun stock page keeps left pool, central K-line, right evidence, and bottom events attached to one current stock. AI Quant should define `StockWorkbenchState` with current stock, source pool, period, adjust, main/sub indicators, drawing/range selection, right rail tab, bottom tab, and selected event.
- **P1 company profile contract:** Add a `company_profile_summary` style view model or equivalent renderer: one-line positioning, concepts, reason tags, business summary, valuation percentile, and missing-data reasons.
- **P1 event link:** K-line overlays and bottom event center must be bidirectionally linked. Clicking a chart event should locate the matching bottom event.
- **P1 AI diagnosis:** AI diagnosis must be evidence-based: technical, capital, news, industry, fundamentals, Signal, valuation, and risk dimensions, each with evidence, counter-evidence, missing reason, timestamp, and risk disclaimer.
- **P2 task router:** iWencai must become `intent -> parsed_conditions -> buckets -> actions -> source_context`, not a table-only input box. Parsed condition chips must show hit counts or unavailable reasons. First actions: open stock, add watchlist, add basket, draft backtest, ask AI/OpenClaw.
- **P2 golden questions:** Maintain 20-30 golden natural-language questions to smoke-test routing, buckets, candidate continuity, and follow-up actions.
- **P2/P3 verification bridge:** Backtest drafts must carry source, benchmark, period, costs, sample, and risk constraints. Simulated or live order-like actions remain explicit user-confirmed actions only.

Rejected or deferred additions:

- Do not add full social/community, login-gated features, paid unlocks, or real trading actions.
- Do not use pywencai or any third-party source as an unlimited guaranteed data base. Keep rate limits, source labels, and degraded states visible.
- Do not introduce a heavyweight engine such as LEAN in P0/P1; evaluate as a P3 provider with a separate ADR.

Parallel agent statuses:

- Done: TongHuaShun Market Entry/Sidebar/Sector-Constituent Agent.
- Done: TongHuaShun iWencai/Task Router Agent.
- Done: TongHuaShun Stock/K-line Workbench Agent.
- Done: Earlier Plan Reviewer/P0/P1/P2 read-only agents; all follow-up agents have been closed after reporting.
