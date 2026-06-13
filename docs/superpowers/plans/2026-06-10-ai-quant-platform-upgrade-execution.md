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

Status: delivered. The code now returns a soft trust envelope for hotspot failures, and the data-health audit includes `/api/market/hotspot`. The remaining competitor re-check note is deferred; do not treat that as an unimplemented API/UI trust envelope.

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

- [x] **Step 1: Write failing metadata audit test**

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

- [x] **Step 2: Add hotspot to safe path baseline**

Add `"/api/market/hotspot"` after `"/api/market/heatmap"` in `PLAN_BASELINE_SAFE_GET_PATHS`.

Run:

```bash
.venv/bin/python -m pytest tests/test_dashboard_data_health.py::test_metadata_findings_warn_when_hotspot_empty_lacks_trust_context tests/test_dashboard_data_health.py::test_safe_get_paths_cover_user_selected_data_areas -q
```

Expected: FAIL because `find_metadata_findings()` does not inspect hotspot and `SAFE_GET_PATHS` does not include it.

- [x] **Step 3: Write failing API no-break test**

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

- [x] **Step 4: Implement hotspot metadata audit**

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

- [x] **Step 5: Implement hotspot API trust envelope**

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

- [x] **Step 6: Run targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_dashboard_data_health.py::test_metadata_findings_warn_when_hotspot_empty_lacks_trust_context tests/test_dashboard_data_health.py::test_safe_get_paths_cover_user_selected_data_areas tests/test_api_v2_full.py::TestMarketAPI::test_market_hotspot_returns_soft_unavailable_state_when_source_fails -q
```

Expected: PASS.

- [x] **Step 7: Run P0 regression group**

Run:

```bash
.venv/bin/python -m pytest tests/test_dashboard_data_health.py tests/test_intelligence_market_frontend.py tests/test_overview_opportunity_frontend.py tests/test_research_toolbar_frontend.py tests/test_signal_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Browser and competitor re-check**

Browser verification is covered by later Task 8 and Task 9.19 in-app Browser smoke records. A fresh TongHuaShun competitor re-check for this exact hotspot degraded-state slice remains deferred.

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
- Task 9.7 later closes the basic same-day clustering and conservative semantic dedupe gap. Task 9.8 closes the first expandable date-group entry and draft-continuation loop. It is still not a full 同花顺-level professional event tape because hover previews, drawer-level event detail, richer related-index/peer mapping, event-group diagnosis weighting, and richer event-to-backtest condition generation remain follow-ups.

Remaining gaps:

- Basic same-day clustering/count badges are closed by Task 9.7; the first expandable date-group entry and draft continuation are closed by Task 9.8.
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
- Basic same-day event clustering and conservative semantic dedupe are closed by Task 9.7. The first expandable same-day event group entry is closed by Task 9.8; stronger cited dedupe, hover previews, drawer-level detail, and event-group diagnosis weighting remain future enhancements.
- `relatedContext.indices` and richer peer/index mappings still need reliable local data, so industry/peer diagnosis can still fall back to missing reasons.

## Task 9.7: P1 Same-day Event Clustering + Conservative Semantic Dedupe

Status: delivered as the next Stock Workbench event-tape slice. This does not complete the whole platform upgrade; it closes the dense-event readability gap left after chart overlays and evidence-based AI diagnosis.

TongHuaShun mechanism learned:

- K-line dates act as event anchors. When news,公告,资金,龙虎榜,研报, and signal events land on the same trading day, the chart should show that this date is event-dense instead of stacking indistinguishable markers.
- The bottom event center should still preserve the underlying individual events. 聚合 helps scanning; it must not erase the raw evidence a user needs to inspect.
- A professional workbench keeps the loop continuous: chart date -> event group -> selected evidence -> right-rail diagnosis, without losing symbol, period, indicator, source pool, or bottom tab context.

Why learn it:

- Task 9, 9.5, and 9.6 connected event feed, K-line markers, bottom selection, and AI diagnosis. With real multi-source data, the next failure mode is visual noise: many same-day dots overlap and repeated reports make the bottom list feel noisy.
- 同花顺 solves the user problem "that day what happened" by keeping date, event, and evidence together. AI Quant should learn that workflow while keeping data source, missing reason, and duplicate counts auditable.

AI Quant implementation:

- `stock-detail-core.js` keeps `state.eventFeed` as a per-event list. It does not replace raw events with a group model.
- `_stockEventOverlayEvents()` now derives chart overlay events from `eventFeed` and then `_clusterStockOverlayEvents()` groups ready chart events by `date_key`. A same-day cluster renders one `.stock-chart-event-dot.is-cluster` with `data-chart-event-count`.
- Cluster representatives are chosen conservatively by event priority: capital flow, 龙虎榜, northbound, Alpha,公告/分红, news, and then reports. The representative drives chart-click selection, while `event_ids` keeps the same-day member ids for highlighting and state inspection.
- `_renderStockEventList()` still shows individual bottom events, but adds `同日 n 条` and `合并 n 条` badges so dense or duplicate evidence is visible without hiding the raw rows.
- `_eventSemanticKey()` and `_mergeDuplicateStockEvent()` add conservative semantic dedupe for ready news/report events only. Generic report titles, announcements, dividends, cross-link mismatches, and short titles are not merged.
- Selecting a bottom event that belongs to a same-day cluster keeps the K-line cluster dot highlighted, so bottom -> chart -> AI diagnosis remains visually coherent.
- Cache versions bumped: `style.css?v=74`, `app.js?v=118`, `app-ui-shell.js?v=40`, `sw.js?v=60`, `ai-quant-v162`, `stock-detail-core.js?v=18`.

Parallel agents used:

- `019eb6f3-6cfb-73b0-8ec5-be470b670e33`: read-only implementation reviewer; confirmed `eventFeed` stays per-event, found the non-representative cluster highlight gap, and recommended stricter semantic dedupe.
- `019eb6f3-6d50-7551-b144-e54541adfd1f`: read-only plan/spec reviewer; confirmed Task 9.7 must update the execution plan and stale "same-day clustering missing" gaps.
- `019eb6f3-6da3-7b01-9905-d4177bb68dd4`: read-only verification reviewer; confirmed the new frontend contract should cover same-day clustering, duplicate badges, chart-click selection, and AI diagnosis focus.

Verification:

```bash
node --check dashboard/static/stock-detail-core.js
node --check dashboard/static/app.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_stock_workbench_same_day_events_cluster_chart_dot_without_losing_items tests/test_frontend_workflow_contracts.py::test_stock_workbench_chart_event_overlay_click_reverse_selects_bottom_event tests/test_frontend_workflow_contracts.py::test_stock_ai_diagnosis_consumes_event_focus_and_evidence_state -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_frontend_workflow_contracts.py::test_service_worker_precache_keeps_large_page_bundles_out_of_install_path tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
.venv/bin/python scripts/verify_context_pack.py
```

本轮是否学到精髓:

- 学到了基础机制：图表现在表达"这一天有多源事件"，底部继续保留逐条证据，AI 诊断仍消费当前选择的事件焦点。
- 没有照抄同花顺的视觉皮肤、付费内容、短线精灵包装或买卖建议。AI Quant 的差异仍是证据、来源、缺失原因、duplicate count 和免责声明。

Remaining gaps:

- 聚合点点击后展开同日事件组由 Task 9.8 关闭；更完整的事件抽屉和 hover 预览仍是后续增强。
- 语义去重是保守版，不是完整跨源 semantic dedupe 引擎；后续若做更强去重，需要引用、链接、机构、主体和方向证据。
- 分时图仍按日期级聚合，而不是分钟级事件定位。
- Richer `relatedContext.indices`/peer mappings, backend-owned cited LLM diagnosis, and event-to-backtest continuation remain follow-ups.

## Task 9.8: P1 Same-day Event Group Entry + Draft Continuation

Status: delivered as the next Stock Workbench event workflow slice. This does not complete the whole platform upgrade; it turns the Task 9.7 cluster dot from a representative-event selector into a same-day event group entry with follow-up draft actions.

TongHuaShun mechanism learned:

- K-line event markers are date anchors. The user question is "that day what happened", so clicking a dense date should open the same-day evidence context, not hide every non-representative event behind one dot.
- Event review is a workflow, not a static list: chart date -> same-day event group -> individual evidence -> diagnosis -> basket/backtest/research draft. The current stock, period, source pool, and event provenance must remain stable.

Why learn it:

- Task 9.7 made dense dates readable, but the cluster dot still behaved like a single representative event. That was better than overlap, but not yet the 同花顺-style "date as event doorway" workflow.
- AI Quant can improve on traditional terminals by keeping the raw events and `source_context.event_group` explicit, so later AI diagnosis or backtest drafts know exactly which stock/date/events produced the idea.

AI Quant implementation:

- `chartState.eventGroupFocus` now records the focused event date, representative event id, member event ids/types/counts, raw duplicate-aware count, and source context.
- Clicking a `.stock-chart-event-dot.is-cluster` selects the representative event and opens a bottom `stock-event-group` section for that date. The group lists the same-day raw events without replacing `eventFeed`.
- Selecting a group member keeps the group expanded and keeps the chart cluster dot highlighted when the selected event belongs to that event group. Selecting another date or a same-day non-chart event clears the old group focus.
- The event group source context preserves the original source (`AI信号`, `问财`, `板块`, etc.) and nests the group metadata under `source_context.event_group`.
- The group exposes safe continuation actions: `解释`, `篮子草案`, and `回测草案`. These reuse the existing `iwencai:analyze`, `iwencai:create-basket`, and `iwencai:draft-backtest` event bus paths, so they generate drafts or AI prompts instead of executing trades.
- `core/app-shell.js` now labels these draft toasts as `事件组` when `source_context.event_group` exists, rather than calling every draft a 问财候选.
- Follow-up multi-agent review tightened the group boundary: event membership is checked by event id rather than date alone, nested parent `event_group` context is preserved, and event bus emission uses `globalThis.App` for safer standalone contract tests.
- Cache versions bumped: `style.css?v=75`, `app.js?v=119`, `app-ui-shell.js?v=41`, `core/app-shell.js?v=29`, `sw.js?v=61`, `ai-quant-v163`, `stock-detail-core.js?v=19`.

Parallel agents used:

- `019eb70f-e96e-7610-be97-73d5e971abb2`: read-only mechanism reviewer; confirmed local 同花顺 App could not be operated due to macOS accessibility permission, then grounded the recommendation in existing observer reports and public product mechanism.
- `019eb70f-ea29-7e30-a3c3-abbe3ce21dc7`: read-only implementation reviewer; caught stale group focus, CSS escape risk, tab filtering hiding same-day events, and source-context overwrite risk.
- `019eb70f-ea7a-72e1-982d-e34231e8f979`: read-only verification reviewer; recommended extending the same-day cluster contract with group DOM, member selection, group context, and draft-action assertions.
- `019eb720-e2e9-7f40-b7c9-bbf170b78779`: follow-up read-only implementation reviewer; confirmed the core behavior and flagged the same-day non-group selection boundary and standalone `App?.emit` compatibility risk.
- `019eb721-4994-7d73-a695-822b96506d1c`: follow-up plan/spec reviewer; confirmed Task 9.8 learns the date-entry workflow and asked to update stale summary gaps.
- `019eb721-c454-7110-a99e-b67cbb11b41e`: follow-up browser-smoke reviewer; verified the injected DOM/interaction path on desktop/mobile and recorded the auth-gated visual limitation.

Verification:

```bash
node --check dashboard/static/stock-detail-core.js
node --check dashboard/static/core/app-shell.js
node --check dashboard/static/app.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_stock_workbench_default_state_keeps_event_selection_and_bottom_tab tests/test_frontend_workflow_contracts.py::test_stock_workbench_bottom_event_core_contracts_are_wired tests/test_frontend_workflow_contracts.py::test_stock_workbench_same_day_events_cluster_chart_dot_without_losing_items tests/test_frontend_workflow_contracts.py::test_stock_workbench_chart_event_overlay_click_reverse_selects_bottom_event tests/test_frontend_workflow_contracts.py::test_stock_ai_diagnosis_consumes_event_focus_and_evidence_state -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -k "stock_workbench or stock_ai_diagnosis or changed_frontend_assets or service_worker_precache" -q -p no:cacheprovider
.venv/bin/python scripts/verify_context_pack.py
git diff --check -- dashboard/static/stock-detail-core.js dashboard/static/style.css dashboard/static/core/app-shell.js dashboard/templates/partials/scripts.html dashboard/static/sw.js tests/test_frontend_workflow_contracts.py docs/specs/2026-06-10-ai-quant-platform-upgrade.md docs/superpowers/plans/2026-06-10-ai-quant-platform-upgrade-execution.md
```

本轮是否学到精髓:

- 学到了更完整的事件工作流：聚合点是日期入口，底部显示同日事件组，组内事件仍可逐条选择，后续动作继承同一股票、日期、事件 ids 和来源上下文。
- 仍不照抄同花顺交易导流、付费内容、黑盒评分或买卖建议；所有后续动作都是草案/分析入口。

Remaining gaps:

- 事件组 hover/popover 预览、真正抽屉式详情、分钟级分时定位、引用级 semantic dedupe、事件组级 AI 诊断权重、以及从事件组直接生成更丰富回测条件仍是后续增强。

## Task 9.9: P1 Event Group Diagnosis Weight + Backtest Draft Conditions

Status: delivered as the next Stock Workbench event workflow slice. This does not complete the whole platform upgrade; it turns the Task 9.8 event group entry into an auditable diagnosis and strategy-draft handoff.

TongHuaShun mechanism learned:

- Mature terminals do not treat a dense event date as a flat list. They help the user identify the primary event, separate repeated reposting from independent evidence, notice missing/contradictory evidence, and continue into a hypothesis or strategy draft.
- The useful workflow is still chart-centered: K-line date -> event group -> evidence weighting -> AI diagnosis -> backtest draft. AI Quant should keep this as a draft and evidence chain, not a buy/sell recommendation.

Why learn it:

- Task 9.8 made the event group clickable, but the group was still mostly a container. The next user question is "which of these events matters, what is weak, and how would I test the hypothesis".
- AI Quant's advantage is auditability: it can explicitly store independent event count, raw duplicate-aware count, dedupe policy, counter-evidence, missing evidence, and draft conditions instead of making a black-box call.

AI Quant implementation:

- `stock-detail-core.js` now distinguishes `event_group.event_count` as independent events from `raw_count` and `duplicate_count`, preventing repeated reposts from being counted as multiple independent signals.
- `_buildEventGroupDiagnosisFocus()` produces event-group state with primary event, type distribution, raw/independent/duplicate counts, dedupe policy, counter-evidence, missing evidence, confidence, and signal direction.
- The AI right rail adds an `事件组` diagnosis row when `chartState.eventGroupFocus` is active. Technical, capital, news, and risk rows also consume the event-group context without replacing the normal eight-dimension diagnosis when no group is selected.
- The bottom event group panel now surfaces primary event, confidence, duplicate/repost down-weighting, and missing/counter evidence next to the group members.
- `_buildEventGroupBacktestDraft()` creates a readonly `backtest_draft.conditions` object with hypothesis, event date, event ids/types, primary event, entry/exit rules, holding windows, benchmark placeholder, sample range, cost model, risk controls, evidence filters, and counter-evidence filters.
- `core/app-shell.js` passes only an allowlisted event-group summary into the AI prompt and stores `backtest_draft` in the basket textarea dataset and `App._iwencaiBasketDraft`. It still does not call `loadBasketBacktest()`, trading APIs, paper-order APIs, or live-order paths.
- Cache versions bumped: `style.css?v=76`, `app.js?v=120`, `app-ui-shell.js?v=42`, `core/app-shell.js?v=30`, `sw.js?v=62`, `ai-quant-v164`, `stock-detail-core.js?v=20`.

Parallel agents used:

- `019eb72e-2d09-7d61-95a8-45ebe4f4a200`: read-only mechanism reviewer; recommended primary-event selection, duplicate repost down-weighting, counter/missing evidence, confidence state, and rich draft condition fields.
- `019eb72e-a6f0-7660-aa8f-bcd5be6add2d`: read-only implementation reviewer; identified `_buildWorkbenchAiDiagnosis()` as the safest local diagnosis insertion point and AppShell as a readonly routing/prompt allowlist layer.
- `019eb72f-0091-7443-a933-1e797cd48c2e`: read-only verification reviewer; recommended extending same-day event tests, asserting duplicate down-weighting and draft readonly behavior, and documenting auth-gated browser smoke limits.

Verification:

```bash
node --check dashboard/static/stock-detail-core.js
node --check dashboard/static/core/app-shell.js
node --check dashboard/static/app.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_stock_workbench_same_day_events_cluster_chart_dot_without_losing_items tests/test_intelligence_market_frontend.py::test_iwencai_app_shell_preserves_source_context_and_ignores_empty_basket_pool tests/test_intelligence_market_frontend.py::test_iwencai_basket_draft_routes_to_research_basket_without_auto_backtest -q -p no:cacheprovider
```

本轮是否学到精髓:

- 学到了更深一层：事件组不是一个漂亮容器，而是一个可审计的证据权重和策略假设入口。重复转载被降权，缺失/反证被显式展示，回测条件是草案并要求人工确认。
- 仍不照抄同花顺黑盒评分、交易导流、付费内容或买卖建议；没有自动执行回测、模拟盘或交易动作。

Remaining gaps:

- 事件组诊断还是前端 deterministic view model，不是后端引用级 LLM 诊断；后续需要后端证据版本、引用、样本统计和真实 provider coverage。
- 回测草案条件可见可编辑由 Task 9.10 关闭；用户仍需手动点击计划回测，草案不会自动执行。
- Hover/popover、抽屉式详情、分钟级定位、行业/指数相对强弱和更强 semantic dedupe 仍是后续增强。

## Task 9.10: P1 Event Group Backtest Draft Panel in Basket Workflow

Status: delivered as the next event-to-research workflow slice. This does not complete the whole platform upgrade; it promotes the Task 9.9 `backtest_draft.conditions` from hidden state into a visible, editable, manual-only basket workflow panel.

TongHuaShun mechanism learned:

- Mature terminals let users continue from an event cluster into a research task without losing the originating date, symbol, and evidence context.
- The useful pattern is not "auto-run a strategy"; it is "turn evidence into a hypothesis, show the editable assumptions, and make the next execution step explicit".

Why learn it:

- Task 9.9 produced richer backtest conditions, but the user could only trust that they were stored in state/dataset. That is still too invisible.
- The next useful action is to inspect and edit entry/exit/holding/benchmark/dedupe/反证条件 before manually running a plan backtest.

AI Quant implementation:

- `research/basket` now has a compact `事件回测草案` panel next to the candidate pool. It shows source/query context, event count/raw count, event types, event date, primary event, entry/exit rules, holding windows, benchmark, dedupe policy, and counter-evidence fields.
- The panel has a visible empty state so the workflow does not disappear when no draft exists, plus inline JSON validation feedback for edited conditions.
- The panel includes editable conditions JSON. Updating it synchronizes `#basket-candidates.dataset.backtestDraft` and `App._iwencaiBasketDraft.backtest_draft` without touching the candidate JSON.
- Drafts are normalized with `status: draft`, `requires_confirmation: true`, `execution_policy: manual_only`, `execution_status: not_executed`, and `allowed_actions: ['view', 'edit', 'run_backtest_after_confirmation']`; unsafe incoming states such as `executed` or live-trade actions are not preserved.
- Plain iWencai candidate pools without an explicit `backtest_draft` now receive a minimal manual-only backtest draft instead of showing a success toast with an empty draft panel.
- `core/app-shell.js` still routes `iwencai:draft-backtest` only to `research/basket`; it renders the draft panel but does not call `loadBasketBacktest()`, `/api/alpha/basket/backtest`, paper trading, live trading, or broker APIs.
- Mobile bottom spacing now uses the shared safe-area-aware bottom-nav offset, instead of draft-only padding; mobile toasts also sit above the bottom nav so they do not cover the draft panel header.
- Cache versions bumped: `style.css?v=80`, `app.js?v=120`, `app-ui-shell.js?v=43`, `core/app-shell.js?v=35`, `alpha.js?v=6`, `alpha-tools.js?v=9`, `stock-detail-core.js?v=21`, `sw.js?v=64`, `ai-quant-v166`.

Task 9.10 follow-up record:

- Manual plan-backtest now treats the visible `backtest_draft.conditions` editor as the source of truth: when the user manually submits the plan backtest, the frontend sends the latest edited `backtest_draft`/`conditions` payload instead of only the original hidden draft.
- The backend accepts the submitted draft for `draft_audit` only, producing an audit/sample-coverage envelope for the hypothesis and conditions. This remains a research audit path, not an automatic strategy execution path.
- Acceptance boundary: edited conditions must reach the backend audit payload, malformed conditions must stay visible as validation/audit feedback, and the returned audit must make sample coverage explicit before any user interprets the draft as testable.
- Safety boundary remains `manual_only`: no automatic backtest on route/render, no simulated-trading order, no live/broker call, and no `paper`/`live` continuation from the draft audit response.

Parallel agents used:

- `019eb74d-90c4-7c02-a8c6-019bd8071809`: read-only research/basket explorer; confirmed the safest UI insertion point is next to `#basket-candidates` and warned not to touch the generic backtest form yet.
- `019eb74d-9120-7b80-9d36-198614a442fe`: read-only verification explorer; identified the AppShell route test, stock event-group test, and research toolbar test as the highest-value coverage points.
- `019eb74d-9179-7583-a448-f2983ca903f9`: read-only safety explorer; confirmed current draft route has no automatic backtest/trading side effects and recommended explicit `manual_only/not_executed` state.
- `019eb7c7-d0da-7ff1-95df-ac38a41284db`: read-only contract explorer; confirmed the `skipBundle + applySession:false` route should be the product contract and test expectation.
- `019eb7c8-0454-7411-85d7-6fee437ccbc6`: read-only safety explorer; found unsafe incoming draft states/actions were preserved and that plain iWencai draft-backtest could lack a draft payload.
- `019eb7c8-3425-7b32-a98b-748e67cd42ab`: read-only UI/product explorer; recommended explicit source summary, visible empty state, inline JSON errors, and safer mobile bottom spacing.

Verification:

```bash
node --check dashboard/static/alpha-tools.js
node --check dashboard/static/alpha.js
node --check dashboard/static/core/app-shell.js
node --check dashboard/static/stock-detail-core.js
node --check dashboard/static/app.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_stock_workbench_same_day_events_cluster_chart_dot_without_losing_items tests/test_frontend_workflow_contracts.py::test_basket_backtest_draft_panel_renders_and_edits_manual_only_conditions tests/test_intelligence_market_frontend.py::test_iwencai_basket_draft_routes_to_research_basket_without_auto_backtest tests/test_intelligence_market_frontend.py::test_iwencai_app_shell_preserves_source_context_and_ignores_empty_basket_pool tests/test_intelligence_market_frontend.py::test_iwencai_send_to_screener_opens_research_screener_directly tests/test_research_toolbar_frontend.py::test_formula_basket_and_backtest_tabs_use_same_compact_research_form_surface tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_research_toolbar_frontend.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -k "basket_backtest_draft or stock_workbench_same_day_events or changed_frontend_assets or service_worker_precache" -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_intelligence_market_frontend.py::test_iwencai_send_to_screener_opens_research_screener_directly tests/test_intelligence_market_frontend.py::test_iwencai_basket_draft_routes_to_research_basket_without_auto_backtest tests/test_intelligence_market_frontend.py::test_iwencai_app_shell_preserves_source_context_and_ignores_empty_basket_pool -q -p no:cacheprovider
```

Remaining gaps:

- Task 9.12 closes the first structured event-study statistics layer under `draft_audit`; this remains audit/statistics rather than a provider-backed production backtest or executable strategy.
- Residual risk: audit coverage is only as good as the available event/sample data and condition parser; users must still review insufficient samples, malformed conditions, stale evidence, and benchmark assumptions before manually running any real backtest.
- Backend-cited LLM diagnosis, richer sector/index/peer evidence, hover/popover preview, drawer-level detail, and minute-level positioning remain follow-ups.

## Task 9.12: P1 Draft Audit Event-Study Statistics

Status: delivered as the next event-to-research safety slice. This does not complete the whole platform upgrade; it upgrades basket `draft_audit` from simple sample coverage into structured event-study statistics, while keeping the whole flow manual-only.

TongHuaShun mechanism learned:

- A mature terminal does not stop at "here is a candidate pool". It lets the user inspect whether the event hypothesis has enough samples and whether short holding windows show any signal before deciding to run a formal backtest.
- The useful pattern is "evidence -> hypothesis -> sample statistics -> explicit manual action", not silent execution or black-box promotion.

Why learn it:

- Task 9.10 made event-group backtest conditions visible and editable, but the audit still read like coverage/warnings. That is too weak for a serious research workflow.
- The user needs a separate, scannable section that answers: how many candidates have usable event samples, which holding periods have returns, what the best/worst windows look like, and what the limitations are.

AI Quant implementation:

- `alpha/basket.py` now returns `draft_audit.event_statistics` plus a compatible `event_study` alias. The contract includes `status`, `method`, `unit`, `holding_periods`, `by_holding_period`, `period_stats`, `best_period`, `sample_window`, `methodology`, and `limitations`.
- Event statistics use `next_bar_open_to_holding_close`: locate the draft `event_date`, enter at the next trading day's open, and compute simple close-to-holding-window returns. Missing/invalid `event_date` no longer falls back to the first price bar, so the audit cannot fabricate samples.
- The audit tracks `missing_samples`, `ready_sample_count`, `missing_sample_count`, `coverage_ratio`, `ready/partial/no_sample`, and per-period mean, median, win rate, best, worst, positive count, and negative count.
- `dashboard/static/alpha-tools.js` renders a separate `事件样本统计` panel (`#basket-draft-audit-study`) with coverage, event date, status, holding-period table, best period, methodology, and limitations. These details are no longer buried in warning text.
- The no-audit path now clears the event-study panel, warning list, and draft status so a normal basket backtest cannot show stale "后端已审计草案" state from the previous run.
- Basket backtest draft normalization now forces `status: draft`, `requires_confirmation: true`, `execution_policy: manual_only`, `execution_status: not_executed`, and `allowed_actions: ['view', 'edit', 'run_backtest_after_confirmation']`.
- Cache versions bumped: `style.css?v=81`, `app.js?v=123`, `app-ui-shell.js?v=44`, `core/app-shell.js?v=35`, `alpha.js?v=6`, `alpha-tools.js?v=12`, `stock-detail-core.js?v=21`, `sw.js?v=67`, `ai-quant-v169`.

Parallel agents used:

- `019eb816-bf54-7be3-83e1-efc2746c1dde`: read-only backend contract reviewer; confirmed the event-study schema, no fake missing-event samples, and manual-only audit fields.
- `019eb816-ea54-7c71-9317-acd1bf5016c1`: read-only frontend display reviewer; confirmed the separate `事件样本统计` UI and caught the stale warning/status bug when a later response had no `draft_audit`.
- `019eb817-71cc-7f83-ba5c-eafd8effbcd9`: read-only safety/documentation reviewer; confirmed no paper/live/broker/order/backtest websocket auto path and flagged the cache-version and `status` consistency cleanup.

Verification:

```bash
node --check dashboard/static/alpha-tools.js
node --check dashboard/static/app.js
node --check dashboard/static/core/app-shell.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_alpha_formula_basket.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -k "basket_backtest_draft or changed_frontend_assets or service_worker_precache" -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py tests/test_research_toolbar_frontend.py -k "iwencai_basket_draft or changed_frontend_assets or research_toolbar_asset_versions" -q -p no:cacheprovider
.venv/bin/python scripts/verify_context_pack.py
git diff --check
```

Browser smoke:

- Temporary Dashboard on port `8013` passed a Playwright desktop and mobile smoke before final stale-state cleanup. It verified the manual plan-backtest request carried the edited draft, the response contained `draft_audit.event_statistics`, the UI showed `事件样本统计`, coverage, mean/win stats, and limitations, and no forbidden `/api/paper`, `/api/broker`, `/api/backtest/ws/run`, or `/api/backtest/run` calls occurred.
- Artifacts: `/tmp/task-9.12-event-study-desktop.png`, `/tmp/task-9.12-event-study-mobile.png`, `/tmp/task-9.12-event-study-smoke.json`.

本轮是否学到精髓:

- 学到了更接近专业终端的研究闭环：事件组不只是生成草案，草案进入篮子后能看到样本统计和方法限制，再由用户决定是否手动回测。
- 没有照抄黑盒评分、荐股语气、交易入口或自动执行。事件统计明确是 audit/statistics，不是策略验证、不是实盘信号、不是模拟盘下单。

Remaining gaps:

- Event-study stats are still local-price-data based and do not execute full entry/exit rules, provider-backed samples, or formal significance validation.
- Provider-backed event samples, backend-cited LLM diagnosis, richer sector/index/peer evidence, hover/popover preview, drawer-level detail, and minute-level positioning remain follow-ups.

## Task 9.13: P1 Draft Audit Net/Benchmark/Statistics Evidence

Status: delivered as the next event-study hardening slice. This still does not complete the whole platform upgrade; it upgrades `draft_audit.event_statistics` from naked local returns into clearer audit evidence with estimated costs, optional local benchmark/excess returns, and descriptive t-stat fields while preserving manual-only execution.

TongHuaShun mechanism learned:

- A serious terminal keeps validation evidence close to the hypothesis: the user should see cost drag, benchmark comparison, sample size, and limits before deciding whether to run a formal backtest.
- The useful pattern is "audit evidence with status", not "a higher-looking number". Every computed/uncomputed piece must tell the user whether it is available, missing, or only descriptive.

AI Quant implementation:

- `alpha/basket.py` now enriches each ready event sample with `holding_costs`, `holding_net_returns`, `holding_benchmark_returns`, `holding_excess_returns`, and exit dates. Existing `holding_returns` remains the gross/simple-return field for compatibility.
- `event_statistics.cost_model` records the estimated A-share round-trip cost model, its source (`default`, `draft_conditions`, or invalid fallback), and `estimated_round_trip_cost_pct`.
- `event_statistics.benchmark` records `calculation_status`, `available`, code/name, data source, and missing reason. It computes benchmark/excess only when inline `price_data`, normal storage lookup, or a read-only local `stock_daily` variant lookup provides usable benchmark prices. Missing benchmark data returns `missing_benchmark_price_data`; it does not fabricate excess returns.
- Per holding period now adds `mean_cost_pct`, `mean_net_return_pct`, `median_net_return_pct`, `net_win_rate`, `mean_benchmark_return_pct`, `mean_excess_return_pct`, `median_excess_return_pct`, `excess_win_rate`, sample std fields, `t_stat_return`, `t_stat_net_return`, `t_stat_excess_return`, and `significance_status/significance_note`.
- `calculation_status` is now present at the event-statistics root. Existing fields (`mean_return_pct`, `median_return_pct`, `win_rate`, `best/worst`, `period_stats`, and `event_study` alias) remain additive-compatible.
- `dashboard/static/alpha-tools.js` now renders the audit table as 毛收益/成本/净收益/基准/超额/胜率/t值 and keeps `事件样本统计` framed as audit/statistics, not strategy proof.
- Clearing a basket backtest draft now also clears the audit panel, preventing stale net/excess values from staying visible after the user removes the draft.
- Cache versions bumped: `style.css?v=82`, `alpha-tools.js?v=13`, `sw.js?v=68`, `ai-quant-v170`.

Safety boundary:

- No paper, live, broker, order, OpenClaw execution, external data sync, production config, or invite-code logic was changed.
- Draft fields still force `manual_only`, `requires_confirmation`, `not_executed`, and `allowed_actions: ['view', 'edit', 'run_backtest_after_confirmation']`.
- `entry_rule`, `exit_rule`, `benchmark`, `cost_model`, and risk fields remain audit inputs/unsupported execution keys. They do not alter the actual basket backtest execution path.
- t-stat is explicitly descriptive and limited; it is not a strategy-validity claim.

Parallel agents used:

- `019eb82d-c3b7-7943-8efb-e49bdb1ca3e1`: backend contract reviewer; confirmed additive schema, `event_study` alias, manual-only invariants, benchmark-missing handling, and safety tests.
- `019eb82d-c432-7720-9084-ae79f65af19f`: frontend display reviewer; recommended net/excess/cost table columns and found the `clearBasketBacktestDraft()` stale-audit risk.
- `019eb82d-c488-7362-ad93-1f11e43a79cd`: safety/documentation reviewer; confirmed benchmark/cost/significance must remain audit evidence, not execution or order routing.
- All three were closed after reporting.

Verification:

```bash
.venv/bin/python -m pytest tests/test_alpha_formula_basket.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_basket_backtest_draft_panel_renders_and_edits_manual_only_conditions -q -p no:cacheprovider
node --check dashboard/static/alpha-tools.js
node --check dashboard/static/app.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/core/app-shell.js
node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_intelligence_market_frontend.py::test_iwencai_basket_draft_routes_to_research_basket_without_auto_backtest tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_alpha_formula_basket.py tests/test_frontend_workflow_contracts.py::test_basket_backtest_draft_panel_renders_and_edits_manual_only_conditions tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_intelligence_market_frontend.py::test_iwencai_basket_draft_routes_to_research_basket_without_auto_backtest tests/test_intelligence_market_frontend.py::test_iwencai_app_shell_preserves_source_context_and_ignores_empty_basket_pool tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
.venv/bin/python -m compileall -q alpha/basket.py dashboard/routers/alpha.py
```

Results:

- Backend basket tests: `14 passed, 1 warning`.
- Focused frontend draft audit contract: `1 passed, 1 warning`.
- Version/no-auto-backtest focused tests: `4 passed, 1 warning`.
- Combined related suite: `19 passed, 1 warning`.
- JS/Python syntax checks: passed.

Remaining gaps:

- Benchmark/excess remains local-data dependent; no provider-backed benchmark sample service exists yet.
- Cost model is an estimate and does not account for per-trade minimum commission, market impact, partial fills, or real execution constraints.
- t-stat is descriptive only; no p-value, multiple-testing control, out-of-sample validation, or provider-grade event normalization is implemented.
- Full entry/exit rule execution, richer sector/index/peer mappings, backend-cited LLM diagnosis, hover/popover preview, drawer-level detail, and minute-level positioning remain follow-ups.

## Task 9.14: P2 Backend-Owned iWencai Routed Schema + Legacy Compatibility Gate

Status: delivered as the next P2 task-router hardening slice. This closes the main "frontend shim owns the routed schema" gap for iWencai while preserving legacy `data` / `total` compatibility. It does not claim real provider field-level evidence, rate-limit coverage, OpenClaw deep orchestration, or investment advice quality is complete.

TongHuaShun mechanism learned:

- The useful 问财 pattern is not the visual skin. It turns one sentence into visible task state: intent, parsed condition chips, result buckets, source status, and next actions.
- Users need to see how the system interpreted the question and what can safely happen next. A table alone is too weak because it hides route intent, condition hit counts, and provider state.
- AI Quant should learn the mechanism and evidence flow, not copy 同花顺 brand wording, paid/restricted content, screenshots, proprietary rankings, community content, or internal implementation guesses.

AI Quant implementation:

- `/api/llm/iwencai` now returns backend-owned `schema_version = "iwencai_task_router_v1"` plus `status`, `intent`, `parsed_conditions`, `buckets`, `actions`, `selected_bucket`, `source_context`, `source_status`, `issue`, and legacy `data` / `total`.
- Empty successful provider results now still use the routed schema with `status = "no_match"` instead of returning a legacy-only payload.
- Backend condition parsing covers common A-share screening phrases such as 高股息、低估值、近N日放量、主力净流入、ROE、新高、剔除ST, with hit counts or explicit degraded reasons.
- Backend buckets include candidate stock pool, theme aggregation, and condition evidence. Legacy `data` stays available for older consumers.
- `result_pool_id` fallback is deterministic with SHA-1 instead of Python process-randomized `hash()`.
- `source_context` is sanitized through an allowlist and cannot echo cookie, headers, session, token, API key, invite-code, broker credential, or account-sensitive keys.
- `dashboard/static/intelligence-iwencai.js` now treats backend-owned fields as authoritative: if `parsed_conditions`, `buckets`, or `actions` exists, the frontend does not infer fake replacements or append fake buckets. It only falls back for legacy responses where those fields are absent.
- Request context from global search/news/hotspot is preserved as `origin_context` and cannot override backend `result_pool_id`, `provider`, `data_as_of`, or `cache_status`.
- Standard backend candidate fields such as `code`, `name`, `industry`, `concept`, `price`, and `change_pct` render in the same focused table as legacy Chinese-column data.
- Cache versions bumped: `intelligence-iwencai.js?v=7`, `app.js?v=124`, `/sw.js?v=69`, `ai-quant-v171`.

Safety boundary:

- No real iWencai provider call was used in tests or browser smoke; API tests monkeypatch a fake provider and browser smoke mocks `/api/llm/iwencai`.
- No paper, live, broker, order, OpenClaw execution, external LLM call, external data sync, production config, auth-gate, or invite-code logic was changed. 邀请码 remains required.
- Basket/backtest follow-up actions remain drafts or UI actions only; this slice does not execute formal backtests, simulated trades, live orders, broker actions, or OpenClaw tasks.
- Failure and degraded states must be visible. The UI must not use empty tables to hide source failure, and it must not fabricate provider evidence or hit counts.

Parallel agents used:

- `019eb84f-bc5c-7c60-a107-b7810653c26f`: frontend schema ownership reviewer; identified field-presence vs empty-array ownership, backend source-context precedence, and legacy fallback boundaries.
- `019eb84f-e7b0-72e0-b9e3-52ab87990f94`: documentation/plan reviewer; mapped Task 9.14 into the existing spec and safety boundaries, including no invite-code/auth-gate changes.
- `019eb850-0ccf-74f2-b6a4-5b4c574b3769`: QA coverage reviewer; proposed fake-provider backend tests, frontend contract scope, JS syntax checks, context-pack verification, diff hygiene, and dangerous API interception for smoke.
- All three were closed after reporting.

Verification:

```bash
.venv/bin/python -m pytest tests/test_iwencai_task_router_api.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py -k iwencai -q -p no:cacheprovider
node --check dashboard/static/intelligence-iwencai.js
.venv/bin/python -m pytest tests/test_iwencai_task_router_api.py tests/test_intelligence_market_frontend.py tests/test_frontend_workflow_contracts.py -k "iwencai or global_search or basket_backtest_draft or assets_are_versioned or changed_frontend_assets_are_cache_busted" -q -p no:cacheprovider
node --check dashboard/static/intelligence-iwencai.js && node --check dashboard/static/app.js && node --check dashboard/static/app-ui-shell.js && node --check dashboard/static/sw.js && node --check dashboard/static/core/command-palette.js && node --check dashboard/static/core/app-shell.js && node --check dashboard/static/alpha-tools.js && node --check dashboard/static/stock-detail-core.js && node --check dashboard/static/alpha.js
.venv/bin/python -m compileall -q dashboard/routers/llm.py
.venv/bin/python scripts/verify_context_pack.py
git diff --check
```

Results:

- Backend iWencai API contract: `2 passed, 1 warning`.
- Focused iWencai frontend contracts: `12 passed, 49 deselected, 1 warning`.
- Focused global-search / iWencai / basket-backtest-draft / cache-busting contracts: `26 passed, 121 deselected, 1 warning`.
- JS syntax checks, compileall, context-pack verification, and `git diff --check`: passed.
- Mocked Playwright smoke passed on desktop `1280x900` and mobile `390x844` after normal invite-code registration/login. It mocked `/api/llm/iwencai`, blocked dangerous run/order/broker/live/OpenClaw write APIs, verified three condition chips, backend `result_pool_id`, provider context, bucket switch, no fake `news` bucket, and no horizontal overflow. Evidence: `/tmp/task914-iwencai-smoke.json`, `/tmp/task914-iwencai-desktop.png`, `/tmp/task914-iwencai-mobile.png`.

Remaining gaps:

- Real provider hit counts, rate-limit/cache states, field-level evidence, and provider drift handling still need deterministic provider fixtures or a dedicated provider adapter test layer.
- OpenClaw deep orchestration and backend-cited LLM explanations are still future slices.
- Browser smoke with mocked iWencai proves UI routing and safety gates, not live provider coverage.

## Task 9.15: Provider-Grade iWencai Source Status Contract

Status: delivered as a provider-status hardening slice after Task 9.14. This closes the specific gap where provider dependency failure, request failure, rate limit, or response-shape drift could be collapsed into `no_match`.

TongHuaShun mechanism learned:

- The valuable 问财 behavior is not that it always returns a table. It tells the user whether the query was interpreted, whether the source answered, whether evidence is partial, and what next action is safe.
- AI Quant must treat "source unavailable" differently from "normal source returned no stocks." Otherwise users will loosen conditions or create follow-up artifacts from a broken provider state.

AI Quant implementation:

- `alpha/iwencai_client.py` now exposes `IwencaiProviderResult` and `query_iwencai_with_status()`, while preserving legacy `query_iwencai() -> DataFrame`.
- Provider states now include `provider_status`, `failure_type`, `failure_reason`, `response_type`, `local_wait_seconds`, `retry_after_seconds`, `data_as_of`, and `cache_status`.
- `/api/llm/iwencai` uses the status-aware provider API when available and falls back to the legacy DataFrame API for compatibility.
- Only a provider-normal empty DataFrame becomes `status = no_match`. `provider_unavailable`, `request_failed`, `rate_limited`, and `invalid_provider_response` become top-level `status = failed` with typed `failure_type` and `source_status`.
- `source_context` now carries provider diagnostics such as `data_status`, `failure_type`, `status_reason`, and normalized provider status through the same task-router envelope.
- `dashboard/static/intelligence-iwencai.js` blocks pool/write actions when `source_status` or provider status indicates unavailable, rate-limited, invalid response, stale cache, offline fallback, permission denied, or request failure, even if cached candidates exist.
- `dashboard/static/intelligence.js` adds the same execution-layer guard so stale DOM or indirect event paths cannot fire send-to-screener, add-watchlist, create-basket, or draft-backtest when provider/cache status is blocked.
- Cache versions bumped: `intelligence.js?v=12`, `intelligence-iwencai.js?v=8`, `app.js?v=126`, `/sw.js?v=70`, `ai-quant-v173`.

Safety boundary:

- No real iWencai, pywencai network request, TongHuaShun login/session, OpenClaw write, external LLM call, formal backtest execution, paper/live order, broker API, production config, or auth/invite-code logic was changed. 邀请码 remains required.
- This slice proves deterministic provider-status fixtures and UI safety gates. It does not claim live provider coverage, field-level real hit counts, or provider drift handling against the real upstream site is complete.

Parallel agents used:

- `019eb862-a364-7433-8fa0-b8cf33a72c1a`: provider/client status semantic reviewer; confirmed empty DataFrame was hiding missing provider, request failure, rate limit, and invalid response.
- `019eb862-e8e0-7482-b266-fe37b69d5380`: frontend/global-search failure-state reviewer; confirmed action gating depends on top-level status and needs source-status fallback for cached candidates.
- `019eb863-2e0e-7800-b2e9-08a4e0b456e3`: docs/TongHuaShun gap reviewer; recommended explicit provider evidence contract, deterministic fixtures, and no fabricated evidence.
- All three were closed after reporting.

Verification:

```bash
.venv/bin/python -m pytest tests/test_iwencai_client_status.py tests/test_iwencai_task_router_api.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_iwencai_provider_failure_blocks_write_actions_even_with_cached_candidates tests/test_frontend_workflow_contracts.py::test_iwencai_run_preserves_source_context_and_renders_failure_degraded_states tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled -q -p no:cacheprovider
node --check dashboard/static/intelligence-iwencai.js && node --check dashboard/static/intelligence.js && node --check dashboard/static/app.js && node --check dashboard/static/app-ui-shell.js && node --check dashboard/static/sw.js
.venv/bin/python -m compileall -q alpha/iwencai_client.py dashboard/routers/llm.py
.venv/bin/python scripts/verify_context_pack.py
git diff --check
```

Results:

- Provider/client/API contracts: `7 passed, 1 warning`.
- Focused frontend failure-state and version contracts: `4 passed, 1 warning`.
- Wider iWencai/global-search/cache-busting regression: `32 passed, 122 deselected, 1 warning`.
- JS syntax checks, `compileall`, context-pack verification, and `git diff --check`: passed.
- Playwright smoke against existing `127.0.0.1:8001` service passed desktop `1280x900` and mobile `390x844` after normal invite-code auth/login. It mocked `/api/llm/iwencai`, blocked dangerous backtest/trading/broker/OpenClaw write APIs, verified source-rate-limit reason, candidate table visibility, write/pool action suppression, no console/page errors, and no horizontal overflow. Evidence: `/tmp/task915-iwencai-provider-smoke.json`, `/tmp/task915-iwencai-provider-1280x900.png`, `/tmp/task915-iwencai-provider-390x844.png`.

Remaining gaps:

- Field-level provider evidence still needs an explicit deterministic fixture contract for `parsed_conditions[].evidence`, unsupported fields, stale cache, partial evidence, and schema drift.
- Browser smoke should continue to mock `/api/llm/iwencai` unless the user explicitly approves a real provider call.

## Task 9.16: Provider-Grade iWencai Field Evidence Fixture Contract

Status: delivered as the next iWencai hardening slice. This closes the most misleading field-level gap: backend condition chips no longer use visible candidate count or frontend inference as fake provider evidence.

TongHuaShun mechanism learned:

- The useful 问财 pattern is that each natural-language condition becomes an inspectable condition chip with hit range and next-step state.
- AI Quant should learn the audit mechanism, not copy data, wording, screenshots, paid features, rankings, or internal implementation. The goal is stronger than "looks like 问财": every condition must say which provider/result field supports it or why that evidence is missing.

AI Quant implementation:

- `parsed_conditions[]` now includes field-level evidence fields: `hit_count_status`, `missing_reason`, `evidence_level`, `source_field`, `source_fields`, and nested `evidence`.
- Backend condition hit counts are only `verified` when a matching provider/result field is present. Missing fields return `hit_count = null`, `hit_count_status = missing_source_field`, and a visible missing reason instead of falling back to `len(records)`.
- Provider unavailable or failed states keep parsed conditions for transparency but mark evidence as `source_unavailable` and condition status as `failed`.
- Provider-normal empty results can show `hit_count = 0` with `hit_count_status = provider_empty_result`.
- If a result has candidates but one or more parsed conditions lack verified field evidence, `/api/llm/iwencai` downgrades the task to `partial_result`, marks `source_status.status = partial_source_failure`, and omits send-to-screener, add-watchlist, create-basket, and draft-backtest actions.
- Frontend `normalizeCondition()` preserves nested `evidence`, `hit_count_status`, `source_field(s)`, `missing_reason`, and `evidence_level`. Condition chips show source field when available or missing reason when unavailable.
- `source_context` now carries `condition_evidence` in addition to legacy `condition_hit_count`, so downstream stock detail, AI explain, basket draft, and future OpenClaw flows can audit condition evidence without trusting user-supplied context.
- Post-review hardening closed the stale-DOM/indirect-event gap: `_canRunIwencaiAction()` now blocks pool/write actions for `partial_result` and `degraded_data` even when provider/source/cache status values look ok, while keeping read-only `open_stock/analyze/ask_ai` paths available.
- Cache versions bumped: `intelligence.js?v=14`, `intelligence-iwencai.js?v=10`, `app.js?v=129`, `/sw.js?v=71`, `ai-quant-v175`.

Safety boundary:

- No real iWencai/pywencai network call, TongHuaShun App operation, login/session/cookie use, paid/restricted data, OpenClaw write, external LLM call, backtest execution, paper/live order, broker API, production config, or invite-code/auth-gate logic was changed.
- This slice proves local deterministic evidence contracts and UI/action gates. It does not claim real provider coverage, upstream schema stability, investment advice quality, strategy profitability, or OpenClaw deep orchestration.

Parallel agents used:

- `019eb87f-e00e-7d12-b8a7-45408fb8fbc7`: backend evidence reviewer; identified fake hit-count fallback, client-supplied context risk, and missing provider evidence statuses.
- `019eb880-08b6-7513-8938-546810f13bfb`: frontend evidence reviewer; identified nested `evidence` loss and recommended preserving source field/status into chips and source context.
- `019eb880-2ff7-7fb2-a0de-874ae31e6355`: docs/spec reviewer; framed Task 9.16 as a provider-grade fixture contract, not a real provider completion claim.
- `019eb88f-0382-79a0-bd1a-cc1cdb741363`: final auth-gate reviewer; confirmed invite-code registration remains required and no auth gate was weakened.
- `019eb88f-03eb-7030-88db-ed3a55d3257e`: final evidence-gate reviewer; caught the execution-layer `partial_result/degraded_data` write-action bypass and recommended the status-only guard test.
- All five were closed after reporting.

Verification:

```bash
.venv/bin/python -m pytest tests/test_iwencai_client_status.py tests/test_iwencai_task_router_api.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py tests/test_frontend_workflow_contracts.py -k "iwencai or global_search or assets_are_versioned or changed_frontend_assets_are_cache_busted" -q -p no:cacheprovider
node --check dashboard/static/intelligence-iwencai.js
node --check dashboard/static/intelligence.js
node --check dashboard/static/app.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/sw.js
.venv/bin/python -m compileall -q alpha/iwencai_client.py dashboard/routers/llm.py
.venv/bin/python scripts/verify_context_pack.py
git diff --check
```

Results:

- Backend/provider evidence tests passed: `8 passed, 1 warning`.
- Frontend iWencai/global-search/cache-bust contract tests passed: `25 passed, 122 deselected, 1 warning`, including the execution-layer guard for `partial_result` and `degraded_data` when provider/source/cache are otherwise ok.
- JS syntax checks, targeted `compileall`, context-pack verification, and `git diff --check`: passed.
- Playwright smoke against existing `127.0.0.1:8001` service passed desktop `1280x900` and mobile `390x844` after normal invite-code auth/login. It mocked `/api/llm/iwencai`, blocked dangerous backtest/trading/broker/OpenClaw write APIs, verified verified-field evidence text, missing-field reason, write/pool action suppression, no console/page errors, and no horizontal overflow. Evidence: `/tmp/task916-iwencai-evidence-smoke.json`, `/tmp/task916-iwencai-evidence-1280x900.png`, `/tmp/task916-iwencai-evidence-390x844.png`.

Remaining gaps:

- Real provider condition metadata, unsupported-field taxonomy, stale-cache fixture matrix, and provider schema drift fixtures remain future work.
- Candidate-level provenance is closed by Task 9.17 for deterministic backend-owned row evidence; real provider schema drift fixtures remain future work.
- Browser smoke should keep mocking `/api/llm/iwencai` unless the user explicitly approves real provider calls.

## Task 9.17: iWencai Candidate Row Provenance Contract

Status: delivered as the next iWencai auditability slice. This does not complete the full platform upgrade; it closes the gap between condition-level evidence and per-stock candidate evidence.

TongHuaShun mechanism learned:

- 问财式结果 is useful because a user can inspect why each candidate belongs in the result, not just see a flat table.
- AI Quant should learn the auditable workflow: query -> parsed conditions -> candidate row evidence -> open stock / AI explanation / draft actions, while being stricter than a traditional terminal about missing fields and stale source state.

AI Quant implementation:

- `/api/llm/iwencai` now attaches backend-owned `candidate_provenance` to each normalized candidate and legacy `data` row.
- Row provenance includes `result_pool_id`, deterministic `row_id`, `code/name/rank`, provider/source metadata, query, matched conditions, missing conditions, source fields, a safe raw field map, `evidence_level`, `validation_status`, warnings, and missing reason.
- Row provenance is computed only from provider result rows, backend parsed conditions, and provider metadata. Client-supplied `source_context` can preserve origin workflow context but cannot create verified row evidence.
- Candidates with partial/unverified row evidence remain visible for read-only inspection and AI explanation, but are excluded from actionable `pool/watchlistCodes` and basket/backtest draft payloads.
- The iWencai table now shows a compact evidence column with verified/partial/unverified badges, source fields, missing reasons, provider, and data timestamp.
- `contextList`, `open_stock`, `ask_ai`, row-level watchlist metadata, and research basket/backtest drafts now carry row-level `candidate_provenance` in `source_context` or sanitized candidate metadata.
- Execution-layer row guards check current candidate, `result_pool_id`, row evidence id, task state, source state, and row `actionable` before allowing row write actions; pool actions require a non-empty verified/actionable pool, closing stale-DOM and indirect-event bypasses.
- Cache versions bumped: `intelligence.js?v=16`, `intelligence-iwencai.js?v=12`, `app.js?v=131`, `core/app-shell.js?v=36`, `app-ui-shell.js?v=45`, `/sw.js?v=72`, `ai-quant-v177`.

Parallel agents used:

- `019eb898-035f-7803-8e0a-2085660ac4d4`: backend reviewer; identified the missing row evidence contract, advised provider-row-only provenance and tests for missing row values.
- `019eb898-03c2-7363-9fad-90f11b4b76e1`: frontend reviewer; identified missing evidence UI, row context propagation, row write gating, stale-DOM, and slow-response risks.
- `019eb898-0421-7303-87ea-031abb35290f`: docs/spec reviewer; defined FR-WENCAI-3g/3h/3i, acceptance criteria, validation commands, and safety boundary.
- All three were closed after reporting.

Verification:

```bash
.venv/bin/python -m pytest tests/test_iwencai_client_status.py tests/test_iwencai_task_router_api.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py tests/test_frontend_workflow_contracts.py -k "iwencai or global_search or assets_are_versioned or changed_frontend_assets_are_cache_busted" -q -p no:cacheprovider
node --check dashboard/static/intelligence-iwencai.js
node --check dashboard/static/intelligence.js
node --check dashboard/static/app.js
node --check dashboard/static/core/app-shell.js
node --check dashboard/static/app-ui-shell.js
node --check dashboard/static/sw.js
.venv/bin/python -m compileall -q alpha/iwencai_client.py dashboard/routers/llm.py
.venv/bin/python scripts/verify_context_pack.py
git diff --check
```

Results:

- Backend/provider/client contracts passed: `9 passed, 1 warning`, including candidate row provenance and missing row evidence coverage.
- Frontend iWencai/global-search/cache-bust contract tests passed: `27 passed, 122 deselected, 1 warning`, plus focused post-review provenance/pool/draft tests passed: `3 passed, 1 warning` and cache-version tests passed: `4 passed, 1 warning`.
- JS syntax checks, targeted `compileall`, context-pack verification, and `git diff --check`: passed.
- Playwright smoke against existing `127.0.0.1:8001` service passed desktop `1280x900` and mobile `390x844` after normal invite-code auth/login. It mocked `/api/llm/iwencai`, blocked dangerous backtest/trading/broker/OpenClaw write APIs, verified the row evidence column, verified/partial badges, verified-only `pool/watchlistCodes/actionableCandidates`, excluded partial row, no console/page errors, and no horizontal overflow. Evidence: `/tmp/task917-iwencai-row-provenance-smoke.json`, `/tmp/task917-iwencai-row-provenance-1280x900.png`, `/tmp/task917-iwencai-row-provenance-390x844.png`.

Safety boundary:

- No real iWencai/pywencai network call, TongHuaShun App operation, login/session/cookie use, paid/restricted data, OpenClaw write, external LLM call, backtest execution, paper/live order, broker API, production config, or invite-code/auth-gate logic was changed.
- Row provenance is audit evidence, not investment advice, profitability proof, or a buy/sell signal.

Remaining gaps:

- Real provider row schema drift, stale-cache fixture matrix, unsupported-field taxonomy, and payload-size tuning remain future work.
- Browser smoke should continue to mock `/api/llm/iwencai` unless the user explicitly approves a real provider call.

## Task 9.18: iWencai Request Generation + Stale Response Guard

Status: delivered as the next iWencai workbench stability slice. This does not complete the full platform upgrade; it closes the slow-response race where an older query could overwrite the latest query, candidate pool, evidence state, or write actions.

TongHuaShun mechanism learned:

- 问财 is a continuous task workbench. When a user quickly rewrites a question, the screen should always represent the current question, not whichever network response returns last.
- AI Quant should learn that workflow stability, not just the natural-language table. A stale response must not steal the current candidate pool, source context, or follow-up actions.

AI Quant implementation:

- `runIwencai()` now creates a monotonic `request_generation` token for each query and stores pending state with empty `pool/watchlistCodes/actionableCandidates`.
- New queries abort the previous request through `AbortController` when available, while generation checks still discard old responses when cancellation is not enough.
- Success, failure, timeout, and `AbortError` paths check the active generation before touching DOM or `state.iwencaiResult/state.iwencaiActionState`.
- Old responses silently return the current view model and cannot render a stale failed card or clear the latest candidate pool.
- Rendered global and row action buttons carry `data-request-generation`; execution-layer guards reject old DOM or indirect events when generation, result pool, or row evidence id no longer matches.
- Cache versions bumped: `intelligence.js?v=17`, `intelligence-iwencai.js?v=13`, `app.js?v=132`, `/sw.js?v=73`, `ai-quant-v178`.

Parallel agents used:

- `019eb9ec-e5ab-7ae0-b265-fc8a4a4d5f68`: frontend race-risk reviewer; reviewed request/state paths and stale action risks.
- `019eb9ed-bcb7-7c20-b633-a4bd396a6ec3`: spec/plan reviewer; defined FR-WENCAI-3j/3k/3l, Task 9.18 acceptance, validation, and safety boundary.

Verification:

```bash
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_iwencai_stale_slow_response_cannot_overwrite_latest_query_state tests/test_intelligence_market_frontend.py::test_iwencai_candidate_row_provenance_renders_and_flows_to_actions -q -p no:cacheprovider
node --check dashboard/static/intelligence-iwencai.js
node --check dashboard/static/intelligence.js
```

Results:

- Focused request-generation and stale DOM contract tests passed: `2 passed, 1 warning`.
- Wider iWencai/global-search/cache-bust contract tests passed: `28 passed, 122 deselected, 1 warning`.
- JS syntax checks for `intelligence-iwencai.js`, `intelligence.js`, `app.js`, `app-ui-shell.js`, and `sw.js`: passed.
- Playwright smoke against existing `127.0.0.1:8001` service passed desktop `1280x900` and mobile `390x844` after normal invite-code auth/login. It mocked `/api/llm/iwencai`, simulated query A slow, query B fast, then query A late, and verified final query/pool/source context stayed on B, `data-request-generation="2"` was present, no console/page errors occurred, and no horizontal overflow appeared. Evidence: `/tmp/task918-iwencai-request-generation-smoke.json`, `/tmp/task918-iwencai-request-generation-1280x900.png`, `/tmp/task918-iwencai-request-generation-390x844.png`.

Safety boundary:

- No real iWencai/pywencai network call, TongHuaShun App operation, login/session/cookie use, paid/restricted data, OpenClaw write, external LLM call, backtest execution, paper/live order, broker API, production config, or invite-code/auth-gate logic was changed.
- Request generation is UI/task-state integrity, not provider reliability, investment advice quality, profitability proof, or a buy/sell signal.

Remaining gaps:

- A late-failure browser smoke is still future work; current browser smoke covers A-slow/B-fast/A-late-success on desktop and mobile.
- Real provider latency and broader unsupported-field taxonomy remain future work. Deterministic stale-cache/schema-drift fixtures are closed by Task 9.20.

## Task 9.19: Release Readiness Security Gate

Status: delivered as a pre-release hardening gate. This does not complete the full platform upgrade or approve production deployment; it closes the immediate trust-boundary issue found during release/security review.

Security/readiness findings addressed:

- Backend iWencai row provenance no longer trusts frontend `source_context.result_pool_id` for `candidate_provenance.result_pool_id` or `row_id`.
- `/api/llm/iwencai` now generates server-owned `iwencai:<digest>` result pool ids from query, total, provider, data timestamp, and cache state.
- Frontend/origin result pool ids remain available only as source tracing via `source_context.origin_result_pool_id` and `source_context.origin_context.result_pool_id`.
- Stock event-group continuation payloads now declare `evidence_scope = "stock_event_group"` and `row_evidence_status = "not_applicable"` at source-context and draft levels, so they cannot be confused with iWencai provider row evidence.
- Release review also flagged the two new iWencai pytest files as untracked; they must be included in any commit/release bundle.

Verification:

```bash
.venv/bin/python -m pytest tests/test_iwencai_task_router_api.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_stock_workbench_same_day_events_cluster_chart_dot_without_losing_items -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_iwencai_client_status.py tests/test_iwencai_task_router_api.py tests/test_alpha_formula_basket.py tests/test_frontend_workflow_contracts.py tests/test_intelligence_market_frontend.py tests/test_research_toolbar_frontend.py -q -p no:cacheprovider
node --check dashboard/static/alpha-tools.js dashboard/static/alpha.js dashboard/static/intelligence.js dashboard/static/intelligence-iwencai.js dashboard/static/app.js dashboard/static/app-ui-shell.js dashboard/static/core/app-shell.js dashboard/static/stock-detail-core.js dashboard/static/sw.js
.venv/bin/python -m compileall -q alpha/basket.py alpha/iwencai_client.py dashboard/routers/alpha.py dashboard/routers/llm.py
.venv/bin/python scripts/verify_context_pack.py
git diff --check
```

Results:

- Focused backend provenance and event-group contract tests passed.
- Broader related suite passed: `179 passed, 1 warning`.
- JS syntax checks, targeted `compileall`, context-pack verification, and `git diff --check`: passed.
- In-app Browser smoke reused the existing `127.0.0.1:8001` service. Desktop `1280x720` and mobile `390x844` loaded Dashboard/Intelligence without console errors or horizontal overflow; mobile iWencai widget DOM existed with input, button, result container, aria label, and sane responsive widths. No real iWencai/provider query was submitted.

Safety boundary:

- No production config, deployment, Docker, database migration, data cleanup, real provider call, external LLM call, OpenClaw write, broker API, paper/live order, or auth/invite-code gate change was performed.
- Provenance remains audit/display evidence only. It must not be used as an authorization or execution boundary.

Remaining gaps:

- New tests are still untracked until a commit/release step explicitly includes them.
- Real provider/live schema drift, rate-limit fixture expansion, backend-cited LLM diagnosis, OpenClaw deep orchestration, and production deploy readiness remain future gates. Deterministic stale-cache and schema-drift router fixtures are closed by Task 9.20.

## Task 9.20: Provider-Grade iWencai Fixture Matrix

Status: delivered as a provider-fixture hardening slice after the release readiness gate. This does not complete the full platform upgrade or approve production deployment; it closes the deterministic stale-cache, unsupported-field, and schema-drift fixture gap without making a real iWencai/pywencai network call.

Implemented:

- `alpha/iwencai_client.py` now classifies unsupported-field and schema-drift provider exceptions into explicit diagnostic states while preserving legacy `query_iwencai() -> DataFrame` compatibility.
- `/api/llm/iwencai` now treats `stale_cache`, `unsupported_field`, `schema_drift`, and `offline_fallback` as degraded source states instead of collapsing them into `result_ready`, `no_match`, or hard provider failure.
- Stale-cache responses may still expose candidates for read-only review and AI explanation, but pool/write actions remain blocked.
- Unsupported-field empty responses return `degraded_data` with typed missing evidence instead of fake `no_match` hit counts.
- Schema-drift responses preserve `response_type` and `schema_signature`, do not fabricate condition evidence, and keep row provenance unverified.

Safety boundary:

- No real iWencai/pywencai provider call, external LLM call, OpenClaw write, backtest execution, paper/live order, broker API, Docker, deployment, database migration, production config, or auth/invite-code change was performed.
- Degraded candidates are read/explain only; `send_screener`, watchlist, basket, and backtest-draft actions remain blocked until evidence is verified.

Verification:

```bash
.venv/bin/python -m pytest tests/test_iwencai_client_status.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_iwencai_task_router_api.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py tests/test_frontend_workflow_contracts.py -k "iwencai or global_search or changed_frontend_assets" -q -p no:cacheprovider
.venv/bin/python -m compileall -q alpha/iwencai_client.py dashboard/routers/llm.py
```

Results:

- iWencai client provider-status fixtures passed: `5 passed, 1 warning`.
- iWencai backend task-router fixtures passed: `9 passed, 1 warning`.
- Frontend iWencai/global-search/cache-bust contract tests passed: `27 passed, 123 deselected, 1 warning`.
- Targeted Python syntax check for the changed provider/router modules passed.

Remaining gaps:

- Real provider/live behavior is still unverified; browser smoke should continue to mock `/api/llm/iwencai` unless the user explicitly approves a real provider call.
- Unsupported-field taxonomy is intentionally conservative and should be expanded only from observed provider fixtures or documented upstream behavior.

## Task 9.21: Local Release Preflight Gate

Status: delivered as a local delivery-readiness gate. This does not deploy, build Docker, approve production release, or validate real provider/live trading behavior; it turns the repeated manual local gate sequence into one reproducible preflight command.

Implemented:

- Added `scripts/release_preflight.py` with an auditable `--dry-run` plan and ordered local gates: context pack verifier, full pytest, compileall, and `git diff --check`.
- Added optional `--with-audits` for report-writing `dashboard_data_health.py` and `frontend_data_render_audit.py`; these remain explicit because they write `test-results/data-display-audit/` reports and trigger app lifespan/static scans.
- Added `tests/test_release_preflight.py` to lock the default non-deploying command list, explicit audit inclusion, dry-run behavior, and fail-fast behavior.
- Updated `AGENTS.md`, `docs/commands.md`, `docs/testing.md`, and `docs/quality-gates.md` so future delivery work can use the preflight gate without guessing the command sequence.

Safety boundary:

- Default preflight does not start Dashboard/dev server, Docker, E2E server, real provider calls, external LLM/OpenClaw calls, data sync, broker/paper/live trading scripts, migrations, deployments, or production config changes.
- This is local release evidence only; production deployment still requires explicit user confirmation and separate environment validation.

Verification:

```bash
.venv/bin/python -m pytest tests/test_release_preflight.py -q -p no:cacheprovider
.venv/bin/python scripts/release_preflight.py --dry-run
.venv/bin/python -m pytest tests/test_release_preflight.py tests/test_verify_context_pack.py -q -p no:cacheprovider
.venv/bin/python -m compileall -q scripts/release_preflight.py
.venv/bin/python scripts/verify_context_pack.py
.venv/bin/python scripts/release_preflight.py
.venv/bin/python scripts/dashboard_data_health.py
.venv/bin/python scripts/frontend_data_render_audit.py
node --check dashboard/static/alpha-tools.js && node --check dashboard/static/alpha.js && node --check dashboard/static/intelligence.js && node --check dashboard/static/intelligence-iwencai.js && node --check dashboard/static/app.js && node --check dashboard/static/app-ui-shell.js && node --check dashboard/static/core/app-shell.js && node --check dashboard/static/stock-detail-core.js && node --check dashboard/static/sw.js
```

Results:

- Release preflight contract tests passed: `4 passed, 1 warning`.
- Release preflight plus context-pack tests passed: `16 passed, 1 warning`.
- Dry-run printed only the four default local gates and no Docker/dev-server/trading/external-service commands.
- Full preflight passed: context pack OK, pytest `789 passed, 1 warning`, compileall passed, `git diff --check` passed.
- Dashboard data health audit passed and wrote `test-results/data-display-audit/api-report.json`: `37` endpoints, `0` failed, `0` hard findings, `3` soft findings.
- Frontend static render audit completed and wrote `test-results/data-display-audit/frontend-static-report.json`: `914` risks by heuristic severity (`354` high, `545` medium, `15` low); these are historical/static heuristic findings, not new preflight blockers.
- JS syntax checks for the changed dashboard bundles passed.

Remaining gaps:

- `--with-audits`, browser smoke, E2E, Docker compose, real provider/live validation, OpenClaw/LLM integration, and production deployment remain manual/confirmed gates.
- Large dirty worktree and untracked new tests still need a deliberate staging/release bundle step before handoff.

## Task 9.22: Local E2E Runner Portability + Stock Workbench Gate

Status: delivered as a local browser-gate hardening slice after Task 9.21. This does not deploy, build Docker, approve production release, validate real provider behavior, or run trading/live flows; it closes the immediate local E2E runner breakage that blocked repeatable stock-workbench browser evidence.

Implemented:

- `scripts/e2e-local.sh` now resolves Node from `NODE_BIN`, shell `node`, Codex runtime Node, or repo-local Node instead of a hardcoded app bundle path.
- The local runner now resolves Playwright from either normal `@playwright/test`, repo `node_modules`, or the hidden `.tools/playwright/node_modules/@playwright/.test-*` package layout present on this workspace.
- Hidden Playwright packages are exposed through a temporary `NODE_PATH` shim and cleaned up with a script-scope variable so `set -u` does not fail at exit.
- The script now invokes Playwright directly with `playwright.config.cjs` and forwards extra arguments after `all|smoke|data-health`, so targeted runs such as `--grep` work without relying on `npm run e2e`.
- `tests/test_e2e_local_script.py` locks bash syntax, flexible Node/Playwright resolution, hidden `.test-*` support, direct config usage, and the cleanup regression.
- Current delivery docs now point local browser E2E to `scripts/e2e-local.sh` instead of the less portable direct `npm run e2e` path.
- Delivery docs now state the runtime split explicitly: local verification `.venv` uses Python 3.12, while the Docker image baseline remains Python 3.11; README/commands also note that Docker is outside the default local preflight.
- Added `docs/release-evidence/2026-06-12-local-delivery-readiness.md` as the local delivery evidence index for release delta, verification results, ignored reports, safety boundary, remaining gates, and rollback notes.
- `scripts/release_preflight.py --verify-evidence` now checks the current modified/untracked Git files against that evidence document, and the default preflight runs this check before pytest.
- `scripts/build_release_bundle.py` now builds a local delta archive from the evidence document, writes a manifest and SHA256 checksum, and performs an unpack/checksum verification drill.

Safety boundary:

- The gate reuses an already-running local Dashboard at `127.0.0.1:8001`.
- No Docker, deployment, production config, database migration, data sync, real iWencai/provider call, external LLM/OpenClaw write, broker API, paper/live order, or auth/invite-code change was performed.

Verification:

```bash
bash -n scripts/e2e-local.sh
.venv/bin/python -m pytest tests/test_e2e_local_script.py -q -p no:cacheprovider
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001 scripts/e2e-local.sh smoke --grep "stock hash restores|stock detail fallback"
.venv/bin/python -m pytest tests/test_e2e_local_script.py tests/test_frontend_workflow_contracts.py -k "open_stock_detail or stock_workbench or stock_detail" -q -p no:cacheprovider
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8001 scripts/e2e-local.sh all
.venv/bin/python scripts/build_release_bundle.py
.venv/bin/python scripts/build_release_bundle.py --verify-only
.venv/bin/python scripts/release_preflight.py --verify-evidence
.venv/bin/python scripts/release_preflight.py
.venv/bin/python scripts/release_preflight.py --with-audits
.venv/bin/python scripts/verify_context_pack.py
git diff --check
```

Results:

- E2E runner script syntax passed.
- E2E runner contract tests passed: `3 passed, 1 warning`.
- Targeted stock-workbench Playwright gate passed: `2 passed`.
- Focused stock/frontend contract suite passed: `21 passed, 67 deselected, 1 warning`.
- Full local Playwright gate passed: data-display health `1 passed`; smoke/OpenClaw `13 passed`.
- Release evidence coverage check passed: current modified and untracked files match the local delivery evidence document.
- Local release bundle created: `releases/local-delivery-2026-06-12/local-delivery-2026-06-12.tar.gz` with `39` files plus `manifest.json`; the archive checksum is written to `releases/local-delivery-2026-06-12/local-delivery-2026-06-12.tar.gz.sha256`; verify-only checks current workspace hashes and passed.
- Latest release preflight with deployment static gate passed: context pack OK, release evidence OK, pytest `807 passed, 1 warning`, compileall passed, `git diff --check` passed, deployment static preflight passed with soft findings only.
- Release preflight with audits previously passed: context pack OK, pytest `797 passed, 1 warning`, compileall passed, `git diff --check` passed, data health report `37` endpoints with `0` failed and `0` hard findings, frontend static render audit wrote `914` historical heuristic risks.
- Follow-up documentation/context checks passed after aligning local E2E, Python runtime, and Docker/preflight wording.
- Local delivery evidence document created and linked from `docs/commands.md` and `docs/testing.md`.

Remaining gaps:

- Docker compose, production environment validation, real provider/live validation, OpenClaw/LLM integration, release staging, and production deployment remain separate manual/confirmed gates.

## Task 9.24: Production Environment Variable Preflight Gate

Status: delivered as a production-readiness hardening slice after the local delivery gates. This does not deploy, start Docker, validate real provider credentials, call LLM/OpenClaw, change production config, or approve production release; it turns the previously manual "are the production variables actually injected?" check into a reproducible read-only gate.

Implemented:

- Added `scripts/production_env_preflight.py`, a sanitized environment checker that reads only the current process environment and never reads `.env` files or prints secret values.
- Profiles are explicit: `base` checks `APP_ENV=production` and `QUANT_SYSTEM_API_KEY`; `docker` also checks `OPENCLAW_API_KEY`; `llm` also checks `OPENAI_API_KEY` and `OPENAI_BASE_URL`; `provider` also checks `IWENCAI_COOKIE`; `all` checks every gate.
- Findings classify missing, placeholder, invalid literal, invalid URL, and too-short secret states without exposing values.
- `scripts/release_preflight.py --with-production-env` now appends the environment gate explicitly; the default local preflight remains free of production-secret requirements.
- Updated `AGENTS.md`, `docs/commands.md`, `docs/testing.md`, `docs/quality-gates.md`, `docs/production-readiness-runbook.md`, ADR `0004`, the production release decision template, and the local delivery evidence document so production-env validation is documented as a confirmed/manual production gate.
- Added `tests/test_production_env_preflight.py` and extended `tests/test_release_preflight.py` to lock the profile matrix, no-secret-output behavior, dry-run plan integration, and release evidence coverage.

Safety boundary:

- No secret values were written to tests, docs, logs, screenshots, or final evidence.
- No Docker, deployment, production config mutation, real provider call, external LLM/OpenClaw call, data sync, broker API, paper/live order, migration, or auth/invite-code change was performed.
- A local shell without production variables is expected to fail `scripts/production_env_preflight.py`; that failure proves the gate is active, not that local delivery is broken.

Verification:

```bash
.venv/bin/python -m pytest tests/test_production_env_preflight.py tests/test_release_preflight.py -q -p no:cacheprovider
.venv/bin/python -m compileall -q scripts/production_env_preflight.py scripts/release_preflight.py
.venv/bin/python scripts/production_env_preflight.py --profile base
.venv/bin/python scripts/production_env_preflight.py --profile base --json
.venv/bin/python scripts/release_preflight.py --dry-run --with-production-env
.venv/bin/python scripts/release_preflight.py --verify-evidence
.venv/bin/python scripts/verify_context_pack.py
git diff --check
```

Results:

- Focused preflight tests passed: `19 passed, 1 warning`.
- Targeted compileall and `git diff --check` passed.
- Local production-env CLI correctly failed without `APP_ENV` and `QUANT_SYSTEM_API_KEY`, reporting only missing statuses and "Secret values were not printed."
- Sanitized JSON output reported statuses without secret values.
- Release preflight dry-run shows `production-env: .venv/bin/python scripts/production_env_preflight.py --profile all` only when `--with-production-env` is explicit.
- Release evidence and context-pack verification passed.

Remaining gaps:

- The production-env gate still must be run in an approved staging/production shell after operator-managed variables are injected; do not copy secrets into repo files or release evidence.
- Passing the env gate proves only presence/shape/placeholders. It does not prove Docker startup, provider validity, LLM/OpenClaw connectivity, data sync safety, or trading readiness.

## Task 9.25: Production Auth Static Preflight Gate

Status: delivered as a production-readiness hardening slice after the production environment gate. This does not deploy, import the FastAPI app, start Docker, read `.env`, touch account databases, or approve production release; it turns the Dashboard auth/session/CORS/invite boundaries into a reproducible static gate.

Implemented:

- Added `scripts/production_auth_preflight.py`, a source/test static checker for production auth invariants.
- The gate verifies that the API session bypass is test-only, API key auth remains enabled when configured, API key comparison uses `secrets.compare_digest`, production CORS does not include localhost, production session cookies are `secure`/`httponly`/`samesite=lax`, production does not auto-bootstrap `LOCAL1`, and invite/session secrets remain hash-only in storage/audit paths.
- Added `tests/test_production_auth_preflight.py` with current-state coverage and mutation-style fixtures for weakened CORS, cookie secure flag, API key compare, production invite bootstrap, and plaintext invite audit regression.
- `scripts/release_preflight.py --with-production-auth` now appends the auth static gate explicitly; the default local preflight remains unchanged.
- Updated `AGENTS.md`, `docs/commands.md`, `docs/testing.md`, `docs/quality-gates.md`, `docs/production-readiness-runbook.md`, ADR `0004`, the production release decision template, and local delivery evidence so the auth gate is part of production readiness.

Safety boundary:

- No app import, lifespan startup, database access, Docker, deployment, production config mutation, real provider call, external LLM/OpenClaw call, data sync, broker API, paper/live order, migration, or auth weakening was performed.
- This is a static gate; it does not replace HTTPS/proxy/session/browser smoke in the approved staging/production environment.

Verification:

```bash
.venv/bin/python scripts/production_auth_preflight.py
.venv/bin/python -m pytest tests/test_production_auth_preflight.py tests/test_release_preflight.py -q -p no:cacheprovider
.venv/bin/python -m compileall -q scripts/production_auth_preflight.py scripts/release_preflight.py
.venv/bin/python scripts/release_preflight.py --dry-run --with-production-auth
.venv/bin/python scripts/release_preflight.py --verify-evidence
git diff --check
```

Remaining gaps:

- The auth static gate must still be followed by real staging browser/API smoke after Docker/env confirmation.
- It does not prove reverse proxy TLS, external domain cookies, live account creation, or operator-managed API key distribution.

## Task 9.26: Production Release Decision Verification Gate

Status: delivered as a production-readiness hardening slice after the production auth static gate. This does not deploy, start Docker, read production environment variables, validate credentials, call providers/LLM/OpenClaw, write data, or approve production release; it turns the release decision template and filled decision record into a reproducible read-only gate.

Implemented:

- Added `scripts/production_release_decision_verify.py`, a Markdown verifier for the production release decision template and filled records.
- The default mode verifies `docs/release-evidence/production-release-decision-template.md` for required sections, release fields, gate fields, and explicit "do not record secrets" guidance.
- `--decision <record>` verifies a filled record has release identity values, every production gate conclusion, one exact final decision (`Approved`, `Rejected`, or `Deferred`), risk-acceptance owner/expiry/compensating-control/rollback fields, and no literal secret-like values in output.
- Added `tests/test_production_release_decision_verify.py` for current template coverage, missing section/field failures, filled-record success, unfilled values, final decision placeholders, temporary OpenClaw risk acceptance, final accepted risk metadata, and secret redaction in text/JSON output.
- `scripts/release_preflight.py --with-release-decision` now appends the template verification explicitly; the default local preflight remains unchanged.
- Updated `AGENTS.md`, `docs/commands.md`, `docs/testing.md`, `docs/quality-gates.md`, `docs/production-readiness-runbook.md`, ADR `0004`, and local delivery evidence so the decision verifier is part of production release review.

Safety boundary:

- The verifier reads Markdown files only.
- It does not inspect `.env`, current shell variables, Docker, external services, databases, accounts, broker state, or production config.
- Findings identify the file/line and issue type but never echo the detected secret-like value.

Verification:

```bash
.venv/bin/python -m pytest tests/test_production_release_decision_verify.py tests/test_release_preflight.py -q -p no:cacheprovider
.venv/bin/python -m compileall -q scripts/production_release_decision_verify.py scripts/release_preflight.py
.venv/bin/python scripts/production_release_decision_verify.py
.venv/bin/python scripts/release_preflight.py --dry-run --with-release-decision
.venv/bin/python scripts/release_preflight.py --verify-evidence
git diff --check
```

Remaining gaps:

- A real production release still needs a filled decision record generated from the template and verified with `--decision <record>` after Docker/provider/OpenClaw/LLM/data/trading gates have actual evidence.
- This gate proves record structure and secret-redaction discipline; it does not prove production services are healthy or approved.

## Task 9.27: Backend-Owned iWencai Provider Evidence Summary

Status: delivered as the next P2 provider-evidence hardening slice after the release decision verifier. This does not call real iWencai/pywencai, log in to TongHuaShun, submit a provider query, call OpenClaw/LLM, write data, run backtests, or approve production release; it makes the already-derived provider evidence easier for UI/OpenClaw/release review to consume without trusting frontend inference.

Implemented:

- Added `provider_evidence` to `/api/llm/iwencai` responses and to the sanitized `source_context`.
- The evidence summary includes `schema_version`, result pool, provider/data/cache status, reported total, candidate count, field coverage status, condition hit-count status counts, per-condition evidence, candidate row validation counts, degradation metadata, and write-action gating.
- `write_actions_allowed` is true only when the router status is `result_ready` and the backend has enabled write-class actions; partial, degraded, stale-cache, schema-drift, rate-limited, no-match, and failed states stay read-only.
- The frontend iWencai view model now preserves `provider_evidence` at both `viewModel.provider_evidence` and `source_context.provider_evidence`.
- Cache-busting was updated for the dynamically loaded iWencai module: `intelligence-iwencai.js?v=14`, `app.js?v=133`, and service worker cache `ai-quant-v179`.

Safety boundary:

- The new summary is derived from already-sanitized rows, parsed conditions, source status, and action metadata.
- No raw provider payload, cookie, token, secret, frontend-supplied provenance, external call, Docker, data sync, broker, paper/live, production config, or auth/invite-code path was changed.

Verification:

```bash
.venv/bin/python -m pytest tests/test_iwencai_task_router_api.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py tests/test_frontend_workflow_contracts.py::test_signal_engine_is_primary_frontend_semantics tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted -q -p no:cacheprovider
.venv/bin/python -m compileall -q dashboard/routers/llm.py
.venv/bin/python scripts/release_preflight.py --verify-evidence
.venv/bin/python scripts/build_release_bundle.py --verify-only
.venv/bin/python scripts/release_preflight.py
git diff --check
```

Remaining gaps:

- This closes the backend-owned evidence summary for deterministic fixtures; it still does not prove real provider credentials, live schema, rate-limit behavior, or OpenClaw deep orchestration.
- OpenClaw should next consume `provider_evidence` in read-only research tasks before any write-capable orchestration is considered.

## Task 9.28: Read-Only AI Assistant iWencai Evidence Handoff

Status: delivered as the next P2 evidence-consumption slice after Task 9.27. This does not call external LLM/OpenClaw, enable OpenClaw orchestration, run a real provider query, write watchlists/baskets, execute backtests, submit paper/live orders, or approve production release; it makes the existing AI-assistant explanation path consume the backend-owned iWencai evidence summary instead of only conditions/hit counts.

Implemented:

- Added a compact allowlisted `App._buildIwencaiProviderEvidenceForPrompt()` helper for AI-assistant prompts.
- `iwencai:analyze` now includes `provider_evidence` in the `来源上下文` JSON sent to the local AI assistant prompt path.
- The prompt evidence includes schema/status, provider/data/cache status, candidate/report totals, condition status counts, candidate validation counts, write-action gate, enabled/blocked write actions, and degradation metadata.
- The prompt helper redacts secret-like text and intentionally excludes raw provider payloads, raw rows, headers, cookies, tokens, and frontend-supplied arbitrary fields.
- Cache-busting was updated for `core/app-shell.js?v=37`, `/sw.js?v=74`, and service worker cache `ai-quant-v180`.

Safety boundary:

- This is a read-only prompt-context handoff. It does not perform OpenClaw tool invocation, external LLM calls, provider calls, Docker, data sync, broker, paper/live, production config, or auth/invite-code changes.
- The evidence remains advisory context for explanation; write-capable iWencai actions are still gated separately by backend/router status and UI action checks.

Verification:

```bash
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_iwencai_app_shell_preserves_source_context_and_ignores_empty_basket_pool -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_intelligence_market_frontend.py::test_iwencai_send_to_screener_opens_research_screener_directly tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
node --check dashboard/static/core/app-shell.js
node --check dashboard/static/app-ui-shell.js
git diff --check
```

Remaining gaps:

- This closes local AI-assistant evidence handoff only. It still does not prove real external LLM behavior, OpenClaw deep orchestration, real provider credentials/schema/rate limits, or production deployment readiness.
- A future OpenClaw slice should consume the same `provider_evidence` through a read-only research task contract before any write-capable orchestration is considered.

## Task 9.29: Read-Only OpenClaw iWencai Evidence Review Tool

Status: delivered as the next P2 evidence-consumption slice after Task 9.28. This does not call real OpenClaw, external LLM, iWencai/pywencai, Docker, data sync, backtest execution, paper/live trading, broker APIs, production config, or auth/invite-code paths; it lets OpenClaw Bridge callers review backend-owned `provider_evidence` through a read-only system tool before any write-capable orchestration is considered.

Implemented:

- Added `quant.iwencai.evidence.review` to `dashboard/openclaw_tools.py` with `read_market` permission and `confirm: false`.
- The tool accepts caller-provided `provider_evidence` or `source_context.provider_evidence`, validates `iwencai_provider_evidence_v1`, and returns `iwencai_evidence_review_v1`.
- The review summarizes evidence status, provider/data/cache status, condition status counts, condition samples, candidate validation counts, degradation metadata, and safe next actions.
- The review tool never authorizes writes: `write_action_gate.allowed_by_review_tool` is always `false`, and any evidence-level write capability is explicitly marked as requiring separate tools and confirmation.
- OpenClaw audit argument redaction is now recursive and covers cookies, authorization headers, API keys, invite/session/credential fields, tokens, passwords, and secret-like inline text.
- `tests/test_openclaw_bridge.py` allowlists the new tool and verifies Bridge permission behavior with `read_market`.

Safety boundary:

- The tool only reviews caller-provided, compact provider evidence. It does not fetch provider data, call OpenClaw/LLM, inspect credentials, start services, mutate watchlists/baskets, run backtests, create memories, submit orders, or approve production release.
- Audit metadata redacts sensitive argument fields before persistence.
- Write-capable follow-up still must use existing explicit system tools, permission checks, confirmation cards, and production runbook gates.

Verification:

```bash
.venv/bin/python -m pytest tests/test_openclaw_tools.py tests/test_openclaw_bridge.py -q -p no:cacheprovider
.venv/bin/python -m compileall -q dashboard/openclaw_tools.py dashboard/routers/openclaw.py
.venv/bin/python scripts/release_preflight.py --verify-evidence
.venv/bin/python scripts/build_release_bundle.py
.venv/bin/python scripts/build_release_bundle.py --verify-only
git diff --check
```

Remaining gaps:

- This proves only local deterministic OpenClaw system-tool behavior. It still does not prove real OpenClaw Gateway, external LLM behavior, real iWencai credentials/schema/rate limits, Docker startup, production environment injection, or trading/data gates.
- A future slice can wire this review output into an OpenClaw read-only research workflow, but write-capable orchestration remains out of scope until the provider, LLM, data, and confirmation gates are signed off.

## Task 9.30: AI Assistant Uses OpenClaw iWencai Evidence Review

Status: delivered as the next P2 read-only workflow slice after Task 9.29. This does not call the real OpenClaw Gateway, external LLM, iWencai/pywencai, Docker, data sync, backtest execution, paper/live trading, broker APIs, production config, or auth/invite-code paths; it makes the existing `iwencai:analyze` workflow consume the local OpenClaw evidence-review system tool before building the AI assistant prompt.

Implemented:

- `dashboard/static/core/app-shell.js` now calls local `/api/openclaw/tools/invoke` with `quant.iwencai.evidence.review` when `source_context.provider_evidence` exists.
- The request body uses an allowlisted compact evidence payload rather than forwarding raw provider payloads or arbitrary frontend-supplied fields.
- The AI assistant prompt now includes `openclaw_evidence_review` alongside `provider_evidence`, preserving review status, evidence/provider/cache status, condition counts, candidate validation, degradation, safe next actions, and the write-action gate.
- The prompt allowlist keeps `allowed_by_review_tool=false` visible and redacts secret-like text before prompt construction.
- Cache versions bumped: `core/app-shell.js?v=38` and service worker cache `ai-quant-v181`.

Safety boundary:

- This is still a local FastAPI system-tool call using the current Dashboard session. It does not send messages to OpenClaw chat, invoke native tools, call OpenClaw Gateway, call external LLM, fetch real provider data, or perform write-capable actions.
- If the review call is unavailable or permission-denied, the workflow falls back to the existing AI explanation prompt without blocking the user.
- Write-capable follow-up still must use explicit tools, permissions, confirmation cards, and production runbook gates.

Verification:

```bash
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_iwencai_app_shell_preserves_source_context_and_ignores_empty_basket_pool tests/test_intelligence_market_frontend.py::test_iwencai_send_to_screener_opens_research_screener_directly tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
node --check dashboard/static/core/app-shell.js && node --check dashboard/static/sw.js
.venv/bin/python scripts/release_preflight.py --verify-evidence
.venv/bin/python scripts/build_release_bundle.py
.venv/bin/python scripts/build_release_bundle.py --verify-only
git diff --check
```

Remaining gaps:

- This proves only the local browser-to-FastAPI review handoff and prompt context. It still does not prove real OpenClaw Gateway behavior, external LLM responses, real iWencai credentials/schema/rate limits, Docker startup, production environment injection, or trading/data gates.
- A future confirmed-environment slice can run a real OpenClaw/LLM smoke after credentials and external-service scope are approved.

## Task 9.31: Visible iWencai Evidence Review Panel

Status: delivered as the next P2 visible workflow slice after Task 9.30. This does not call the real OpenClaw Gateway, external LLM, iWencai/pywencai, Docker, data sync, backtest execution, paper/live trading, broker APIs, production config, or auth/invite-code paths; it makes the existing iWencai result UI show backend provider evidence and the local OpenClaw evidence-review result as an auditable panel instead of hiding review context only inside the AI assistant prompt.

Implemented:

- `dashboard/static/intelligence-iwencai.js` now renders a `证据审查` panel inside the iWencai router when `provider_evidence` exists.
- The panel shows provider status, result pool, data/cache state, condition status counts, candidate validation counts, degradation reason/next action, and write-action gate context.
- When `App._reviewIwencaiProviderEvidence()` is available, iWencai results render immediately with a `review_pending` OpenClaw review state and then asynchronously update to the local review result without blocking the candidate table.
- The visible panel preserves the review result across bucket switches and stores it in `state.iwencaiActionState.source_context.openclaw_evidence_review`.
- The renderer redacts secret-like text and excludes raw provider payloads/cookies/tokens from the visible panel.
- Cache versions bumped: `style.css?v=83`, `app.js?v=134`, `intelligence-iwencai.js?v=15`, and service worker cache `ai-quant-v182`.

Safety boundary:

- This is a local Dashboard UI and local FastAPI system-tool handoff only. It does not send messages to OpenClaw chat, invoke native tools, call OpenClaw Gateway, call external LLM, fetch real provider data, or perform write-capable actions.
- If the local review helper is unavailable, the provider evidence panel still renders from backend-owned `provider_evidence`.
- If the local review call fails, the UI keeps the candidate/result workflow available and marks the OpenClaw review as unavailable/failed rather than authorizing any write.

Verification:

```bash
node --check dashboard/static/intelligence-iwencai.js && node --check dashboard/static/app.js && node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_iwencai_visible_openclaw_evidence_review_panel_updates_safely tests/test_intelligence_market_frontend.py::test_iwencai_renders_task_router_conditions_buckets_and_source_context tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py -k "iwencai" -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -k "iwencai or changed_frontend_assets" -q -p no:cacheprovider
.venv/bin/python scripts/release_preflight.py --verify-evidence
git diff --check
```

Remaining gaps:

- This proves only the local visible review UI, local review helper handoff, and no-leak/no-write contracts. It still does not prove real OpenClaw Gateway behavior, external LLM responses, real iWencai credentials/schema/rate limits, Docker startup, production environment injection, or trading/data gates.
- A future confirmed-environment slice can run a real OpenClaw/LLM/provider smoke after credentials and external-service scope are approved.

## Task 9.32: Stock Event Group Detail Preview

Status: delivered as the next P1 stock-workbench workflow slice after the visible iWencai evidence panel. This does not call real provider data, external LLM/OpenClaw, Docker, data sync, backtest execution, paper/live trading, broker APIs, production config, or auth/invite-code paths; it closes the first hover/detail gap by making an already-selected same-day K-line event group expose a compact, auditable detail preview in the bottom event center.

TongHuaShun mechanism learned:

- The useful K-line event workflow is not just dots on a chart. A date cluster should behave as an evidence doorway: date -> event group -> selected evidence detail -> diagnosis/draft next action.
- AI Quant should learn the continuity and evidence inspection pattern, not copy 同花顺 visual skin, paid content, social/community features, proprietary signals, or trading prompts.

Implemented:

- `stock-detail-core.js` now builds an event-group preview from the current event group, preserving the distinction between the representative/main event and a manually selected group member.
- The bottom event-group card shows `主事件详情` for the representative event and `选中事件详情` when the user clicks another group member.
- The preview displays event type, title, source, time, detail text, independent/raw evidence counts, duplicate-source hints, optional direction/value fields, and a source-link caution without opening external links or executing follow-up actions.
- Event-list detail fallback is centralized through `_eventDetailText()` so missing/detail/source text is consistent across the group preview and event list.
- Cache versions bumped: `style.css?v=84`, `app.js?v=135`, `app-ui-shell.js?v=46`, `stock-detail-core.js?v=22`, `/sw.js?v=75`, and service worker cache `ai-quant-v183`.

Safety boundary:

- This is a frontend evidence/interaction slice only. It does not fetch new event data, call provider/LLM/OpenClaw services, run backtests, create baskets/watchlists automatically, submit orders, or change production/auth/trading behavior.
- Existing event-group actions remain manual draft/explain paths; broker, paper/live, backtest execution, provider, and external-service gates remain behind explicit confirmation.

Verification:

```bash
node --check dashboard/static/stock-detail-core.js && node --check dashboard/static/app.js && node --check dashboard/static/app-ui-shell.js && node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_stock_workbench_same_day_events_cluster_chart_dot_without_losing_items tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py -k "stock_workbench or stock_ai_diagnosis or changed_frontend_assets or service_worker_precache" -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
.venv/bin/python -m compileall -q dashboard/static
git diff --check
```

Results:

- JS syntax checks passed for `stock-detail-core.js`, `app.js`, `app-ui-shell.js`, and `sw.js`.
- Focused event-group/cache-busting contracts passed: `4 passed, 1 warning`.
- Broader stock-workbench/cache-busting contracts passed: `12 passed, 74 deselected, 1 warning`.
- Focused asset-version contracts passed: `2 passed, 1 warning`.
- Targeted `compileall` and `git diff --check` passed.
- In-app Browser QA on a temporary local Dashboard at `127.0.0.1:8001` passed for `#stock` at desktop `1280x900` and mobile `390x844`: page loaded without console errors, resource versions were `app.js?v=135`, `stock-detail-core.js?v=22`, and `style.css?v=84`, and there was no horizontal overflow. The event-group detail state itself is covered by the Node DOM contract because the in-app Browser read-only page scope cannot construct internal workbench state.

Remaining gaps:

- This is the first detail-preview slice, not a full drawer. Richer drawer-level detail, hover-triggered previews, minute-level positioning, cited semantic dedupe, provider-backed event samples, richer sector/index/peer mappings, and backend-cited LLM diagnosis remain follow-ups.
- Browser QA did not use real provider/event feeds and did not run any write or execution path.

## Task 9.33: Stock Event Group Drawer Detail

Status: delivered as the next P1 stock-workbench workflow slice after the compact event-group preview. This does not call real provider data, external LLM/OpenClaw, Docker, data sync, backtest execution, paper/live trading, broker APIs, production config, or auth/invite-code paths; it closes the first drawer-level detail gap by making the selected same-day K-line event group expandable into an auditable evidence drawer.

TongHuaShun mechanism learned:

- The useful K-line event cluster workflow needs a second inspection layer after the compact preview: date cluster -> group summary -> full event evidence list -> manual next action.
- AI Quant should learn the continuity and evidence-audit pattern, not copy 同花顺 visual skin, paid content, social/community features, proprietary signals, or trading prompts.

Implemented:

- `stock-detail-core.js` now stores `layoutState.eventGroupDrawerOpen`, resets it when opening a new stock or leaving the active event group, and exposes a manual `详情/收起详情` control inside the same-day event-group card.
- The drawer renders event date, stock identity, independent/raw evidence scale, duplicate转载 note, event-type mix, main event, selected event, source context, counter/missing evidence, and the full ranked evidence list.
- Each drawer item keeps chart-event selection behavior and shows type, title, detail, source/time facts, duplicate-source hints, primary/selected badges, optional direction/value fields, and external-source caution without opening external links.
- `style.css` adds responsive, compact drawer styles that preserve long-title wrapping/ellipsis and avoid horizontal overflow on narrow screens.
- Cache versions bumped: `style.css?v=85`, `app.js?v=136`, `app-ui-shell.js?v=47`, `stock-detail-core.js?v=23`, `/sw.js?v=76`, and service worker cache `ai-quant-v184`.

Safety boundary:

- This is a frontend evidence/interaction slice only. It does not fetch new event data, call provider/LLM/OpenClaw services, run backtests, create baskets/watchlists automatically, submit orders, or change production/auth/trading behavior.
- Existing event-group actions remain manual draft/explain paths; broker, paper/live, backtest execution, provider, and external-service gates remain behind explicit confirmation.

Verification:

```bash
node --check dashboard/static/stock-detail-core.js && node --check dashboard/static/app.js && node --check dashboard/static/app-ui-shell.js && node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_stock_workbench_same_day_events_cluster_chart_dot_without_losing_items tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
```

Results:

- JS syntax checks passed for `stock-detail-core.js`, `app.js`, `app-ui-shell.js`, and `sw.js`.
- Focused event-group/cache-busting contracts passed: `4 passed, 1 warning`.
- The Node DOM contract covers opening the drawer, rendering drawer facts/warnings/evidence list, switching to a selected group member, resetting the drawer when leaving the group, and closing the drawer.

Remaining gaps:

- Hover-triggered previews, minute-level positioning, cited semantic dedupe, provider-backed event samples, richer sector/index/peer mappings, backend-cited LLM diagnosis, and formal/provider-grade event-study validation remain follow-ups.
- Browser QA does not use real provider/event feeds and does not run any write or execution path.

## Task 9.34: Stock Chart Event Hover Preview

Status: delivered as the next P1 stock-workbench workflow slice after drawer-level event detail. This does not call real provider data, external LLM/OpenClaw, Docker, data sync, backtest execution, paper/live trading, broker APIs, production config, or auth/invite-code paths; it closes the first hover/popover preview gap by making K-line event dots reveal compact, auditable event context before the user clicks into the bottom event group.

TongHuaShun mechanism learned:

- A mature K-line workbench lets the user inspect a dense event marker before committing to a click. The useful mechanism is quick evidence preview at the chart coordinate, then click-through into the richer event center.
- AI Quant should learn the evidence continuity pattern, not copy 同花顺 visual skin, proprietary signals, paid/community content, or trading prompts.

Implemented:

- `stock-detail-core.js` now builds a chart-event hover preview for every DOM event marker, with single-event and same-day cluster copy kept distinct.
- The K-line cluster dot now carries raw evidence count, event titles, type mix, source/date context, and a `点击进入事件组` cue; single events cue `点击同步底部事件`.
- Overlay event construction now preserves `duplicate_count`, so chart-level cluster preview can distinguish independent events from raw evidence count instead of silently collapsing duplicate reposts.
- `style.css` adds a compact hover/focus-visible popover for chart event dots, with constrained width and `overflow-wrap` so long titles do not create horizontal overflow.
- Cache versions bumped: `style.css?v=86`, `app.js?v=137`, `app-ui-shell.js?v=48`, `stock-detail-core.js?v=24`, `/sw.js?v=77`, and service worker cache `ai-quant-v185`.

Safety boundary:

- This is a frontend rendering and interaction slice only. It does not fetch new event data, open external links, call provider/LLM/OpenClaw services, run backtests, create baskets/watchlists automatically, submit orders, or change production/auth/trading behavior.
- Clicking event dots still uses the existing manual chart -> bottom event group path.

Verification:

```bash
node --check dashboard/static/stock-detail-core.js && node --check dashboard/static/app.js && node --check dashboard/static/app-ui-shell.js && node --check dashboard/static/sw.js
.venv/bin/python -m pytest tests/test_frontend_workflow_contracts.py::test_stock_workbench_same_day_events_cluster_chart_dot_without_losing_items tests/test_frontend_workflow_contracts.py::test_changed_frontend_assets_are_cache_busted tests/test_intelligence_market_frontend.py::test_intelligence_market_assets_are_versioned_and_styled tests/test_research_toolbar_frontend.py::test_research_toolbar_asset_versions_are_bumped_for_browser_cache -q -p no:cacheprovider
```

Results:

- JS syntax checks passed for `stock-detail-core.js`, `app.js`, `app-ui-shell.js`, and `sw.js`.
- Focused chart-event hover/cache-busting contracts passed after fixing the overlay raw-count propagation gap: `4 passed, 1 warning`.
- The Node DOM contract covers popover markup, cluster title, independent/raw count, click-through cue, event title preservation, and cache-bust literals.

Remaining gaps:

- Minute-level positioning, cited semantic dedupe, provider-backed event samples, richer sector/index/peer mappings, backend-cited LLM diagnosis, and formal/provider-grade event-study validation remain follow-ups.
- Browser QA does not use real provider/event feeds and does not run any write or execution path.

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
| iWencai / task router | Unified search accepts market symbols, functions, and natural-language questions, then routes into buckets with visible parsed-condition chips and follow-up actions. | Use `intent -> parsed_conditions -> buckets -> actions -> source_context`; never treat natural language as a table-only query. | Task 7 tests and Task 8 smoke verify chips, buckets, stock open, basket draft, source context. Topic/hotspot provenance was fixed in this gate. Task 7.5 adds top global search intent routing, result buckets, task result rendering, and source-context handoff into iWencai. Task 7.6 adds golden-question and failure-state contracts. Task 9.14 promotes the base iWencai routed schema to the backend while preserving legacy `data/total`. | Backend now owns the base routed schema; richer real-provider field-level evidence, rate-limit/cache states, provider drift handling, and OpenClaw deep orchestration remain follow-up. | Connect backend task outputs to deeper OpenClaw workflows and provider-grade evidence fixtures. |
| Stock/K-line workbench | One screen keeps left context pool, central K-line, right evidence, bottom events, period/indicator muscle memory. | Treat `StockWorkbenchState` as the state container: selected symbol, source pool, chart state, indicators, related context, event feed, data quality, AI context. | Task 6 tests and Task 8 smoke verify context pool, period, MACD, nonblank chart, source context preservation. Task 6.5 verifies right-rail state completion, missing reasons, rail tab state, and left context pool sync. Task 9 verifies dynamic event aggregation, bottom tab state, selected event, chart focus marker, and desktop/mobile smoke. Task 9.5 verifies chart event overlays, chart-click -> bottom-event reverse selection, capital-flow and 龙虎榜 event aggregation. Task 9.6 verifies evidence-based AI diagnosis consumes `eventFocus`, `eventFeed`, `dataQuality`, and `sourceContext`. Task 9.7 verifies same-day clustering, conservative dedupe, raw-event preservation, and cluster focus into diagnosis. Task 9.8 verifies the same-day event group entry, group-member selection, source-context preservation, and safe draft continuation. Task 9.9 verifies event-group diagnosis weighting, duplicate down-weighting, and richer readonly backtest draft conditions. Task 9.10, Task 9.12, and Task 9.13 verify visible/manual-only basket draft conditions plus structured draft-audit event-study statistics with estimated cost, optional local benchmark/excess, and descriptive t-stat fields. | Frontend event-group diagnosis, draft conditions, and local event-study audit evidence are done; stronger backend-cited LLM diagnosis, provider-grade event samples, formal significance validation, hover/popover preview, drawer-level detail, richer index/peer mappings, and minute-level positioning remain follow-up. | Harden event-study audit into provider-grade sample/benchmark/statistical validation, or harden backend-owned iWencai router semantics depending on product priority. |

Task 8 close condition: tests and smoke pass for the delivered P0/P1/P2 slices, but the whole upgrade is not complete. Task 3.5, Task 6.5, Task 9, Task 9.5, Task 9.6, Task 9.7, Task 9.8, Task 9.9, Task 9.10, Task 9.12, Task 9.13, Task 9.14, Task 7.5, and Task 7.6 are delivered; the next blocking product-quality gates are provider-grade event-study samples/formal validation, provider-grade iWencai evidence and OpenClaw orchestration, richer sector/index/peer evidence, and backend-cited LLM explanations.

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
- Task 9.14 later promotes the base iWencai routed schema to the backend; remaining risk is now real-provider field drift, rate-limit/cache evidence, and OpenClaw orchestration rather than frontend-only schema ownership.
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
