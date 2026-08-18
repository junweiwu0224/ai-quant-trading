# Research Context Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (recommended). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Dashboard usable as one real workflow: select a research instrument, inspect real data, run validation, and safely preview paper execution while preserving context.

**Architecture:** Add a focused Pinia research-context store for cross-page state while keeping page-owned data local. Reuse existing stock, backtest, Decision Worker, Paper Engine, QuoteService, and Risk Policy APIs; remove frontend mock data and placeholder actions from the critical path. Make route state recoverable, API errors explicit, and UI transitions state-driven.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vue Router, FastAPI, existing Python backtest/Paper Engine APIs, Playwright, pytest.

## Global Constraints

- The core flow is `Decision → Research → Validation → Paper preview`.
- Existing backend engines and risk policies are the source of truth; do not implement a second frontend trading or backtest engine.
- Do not display fixed recommendations, random prices, random fills, or mock account balances in production views.
- Missing, stale, failed, and blocked data must show the reason and the next available action.
- Live broker/trading remains hard-disabled.
- Route parameters are the recoverable source for the current market and symbol.
- Every task must include focused tests and a real-browser or API-surface verification where applicable.

---

## File Map

**Create**
- `dashboard/ui/src/stores/researchContext.ts` — cross-page market/instrument/strategy/backtest/eligibility context.
- `dashboard/ui/src/components/research/ResearchContextBar.vue` — current instrument breadcrumb and next-step actions.
- `dashboard/ui/src/components/research/ResearchStatePanel.vue` — shared loading/empty/stale/unavailable/ready state display.
- `dashboard/ui/src/components/research/ResearchDataPanel.vue` — real K-line and technical data presentation if existing chart components cannot be safely extended.
- `tests/test_vue_research_context_contract.py` — source-level contracts for context and state transitions.
- `tests/e2e/research-context-loop.spec.cjs` — desktop/mobile workflow coverage.

**Modify**
- `dashboard/app.py` — serve the Vue shell for `/auth` and other history-mode routes.
- `dashboard/ui/src/api/client.ts` — safe JSON header merging, abort support, and consistent error behavior.
- `dashboard/ui/src/api/research.ts` — real research response normalization and source-specific evidence loading.
- `dashboard/ui/src/api/paper.ts` — replace mock implementations with `/api/paper/*` clients.
- `dashboard/ui/src/api/market.ts` — use current market/symbol in data-health calls where backend supports it.
- `dashboard/ui/src/router.ts` — add context-aware validation/paper routes and remove hardcoded research fallback from critical navigation.
- `dashboard/ui/src/App.vue` — preserve deep-link and session-expiry destinations.
- `dashboard/ui/src/views/DecisionView.vue` — make instrument selection the primary workflow entry.
- `dashboard/ui/src/views/ResearchView.vue` — load real K-line, indicators, evidence, and actionable states.
- `dashboard/ui/src/views/ValidationView.vue` — inherit context, write back backtest results, and gate paper preview.
- `dashboard/ui/src/views/more/PaperTradingView.vue` — use real account/positions/orders/performance APIs and safe confirmation flow.
- `dashboard/ui/src/components/research/KLineChart.vue` — render normalized bars and explicit empty/error states.
- `dashboard/ui/src/components/research/TechnicalIndicators.vue` — render real indicator values or unavailable states.
- `dashboard/ui/src/components/research/EvidenceChain.vue` — render real source-specific evidence.
- `dashboard/ui/src/components/research/DecisionCard.vue` — render backend result or “unable to determine,” never fixed values.
- `dashboard/ui/src/components/research/BacktestDraft.vue` — remove dead disabled actions or replace with navigation to the real validation workflow.
- `dashboard/ui/src/components/market/DataQualityBadge.vue` — stop presenting global health as instrument-specific health.
- `dashboard/ui/src/styles.css` / relevant scoped styles — keep desktop/mobile task completion usable.
- `tests/test_vue_repairs_contract.py` and related frontend contracts — update assertions to the real workflow.

---

## Task 1: Fix history-mode authentication and API request foundation

**Files:**
- Modify: `dashboard/app.py:374-399`
- Modify: `dashboard/ui/src/App.vue:19-36`
- Modify: `dashboard/ui/src/api/client.ts:710-739`
- Create/modify: `tests/test_auth_frontend.py`, `tests/test_vue_repairs_contract.py`

**Interfaces:**
- `GET /auth` and `GET /auth?next=/app/...` return the Vue shell when `ui/dist/index.html` exists.
- `request<T>(path: string, init?: RequestInit)` preserves default headers when `init.headers` is omitted and accepts `init.signal`.

- [ ] Write a failing contract test that asserts `/auth` is served by the Vue shell and the request helper merges `Accept`/`Content-Type` with custom headers.
- [ ] Run `.venv/bin/python -m pytest tests/test_auth_frontend.py tests/test_vue_repairs_contract.py -q` and verify the new assertions fail.
- [ ] Add a FastAPI `/auth` shell route or general history-mode shell helper without exposing gated APIs; preserve the `next` query for the Vue router.
- [ ] Change `request` to construct headers first, merge `init.headers`, and pass `signal` through without replacing JSON defaults. Keep 401 session-expiry dispatch behavior.
- [ ] Run the focused pytest command and verify it passes.
- [ ] Start Dashboard and use a browser to open a protected deep link while logged out; verify `/auth?next=...` renders the login page, then verify login returns to the original `/app/...` path.
- [ ] Commit: `fix(ui): restore auth deep-link and request headers`

---

## Task 2: Add the research context store and route recovery

**Files:**
- Create: `dashboard/ui/src/stores/researchContext.ts`
- Modify: `dashboard/ui/src/router.ts:36-75`
- Modify: `dashboard/ui/src/App.vue:13-52`
- Modify: `dashboard/ui/src/views/ValidationView.vue:8-38`
- Modify: `dashboard/ui/src/views/more/PaperTradingView.vue:1-30`
- Create: `tests/test_vue_research_context_contract.py`

**Interfaces:**
- `useResearchContextStore()` exposes `context`, `hasInstrument`, `setInstrument({ market, symbol, name? })`, `setStrategy(strategy)`, `setBacktest(request, result)`, `setEligibility(value)`, `clearDerivedState()`, and `clear()`.
- `context.market` and `context.symbol` are nullable until the user selects an instrument.

- [ ] Add source-level tests for route recovery, nullable direct-entry state, and clearing derived results on instrument change.
- [ ] Run the focused contract test and verify failure.
- [ ] Implement the store with normalized uppercase market, trimmed symbol, session persistence only for the current research context, and `clearDerivedState()` on instrument changes.
- [ ] On research route entry, call `setInstrument` from route params; do not overwrite a newer route selection with stale store state.
- [ ] Make direct `/app/validation` and `/app/more/paper` show a “先选择研究对象” state instead of defaulting to `000001` or fabricated account context.
- [ ] Run the focused contract test and `npm run ui:build`.
- [ ] Commit: `feat(ui): add research context across workflow`

---

## Task 3: Normalize research APIs and real data states

**Files:**
- Modify: `dashboard/ui/src/api/research.ts:12-121`
- Modify: `dashboard/ui/src/api/market.ts:16-18`
- Modify: `dashboard/ui/src/components/market/DataQualityBadge.vue:84-180`
- Create: `dashboard/ui/src/components/research/ResearchStatePanel.vue`
- Create/modify: `tests/test_vue_research_context_contract.py`, `tests/test_frontend_data_render_audit.py`

**Interfaces:**
- `getKLineData(market, symbol, period, count, signal?) => Promise<{ bars: KLineBar[]; source?: string; asOf?: string; error?: string }>`.
- `getTechnicalIndicators(market, symbol, signal?) => Promise<TechnicalIndicators>`.
- `getEvidence(market, symbol, signal?) => Promise<{ evidence: Evidence[]; sources: SourceState[] }>`.
- `getDataHealth(fast, market?, symbol?)` passes only supported query fields and returns the backend health response unchanged.

- [ ] Add tests for empty K-line responses, malformed bar rows, source-specific evidence failure, and explicit unavailable state.
- [ ] Run focused tests and verify failure.
- [ ] Normalize `klines_raw` without converting missing/non-numeric values into fake zeros; return an empty/partial state with source metadata.
- [ ] Make news and report evidence load independently and preserve per-source error messages instead of swallowing errors into an empty list.
- [ ] Update the quality badge to distinguish global market health from instrument data availability and display actual `as_of`/provider values where present.
- [ ] Run focused tests, frontend static audit, and `npm run ui:build`.
- [ ] Commit: `feat(ui): expose real research data states`

---

## Task 4: Implement the real single-stock research workflow

**Files:**
- Modify: `dashboard/ui/src/views/ResearchView.vue`
- Modify: `dashboard/ui/src/components/research/KLineChart.vue`
- Modify: `dashboard/ui/src/components/research/TechnicalIndicators.vue`
- Modify: `dashboard/ui/src/components/research/EvidenceChain.vue`
- Modify: `dashboard/ui/src/components/research/DecisionCard.vue`
- Modify: `dashboard/ui/src/components/research/BacktestDraft.vue`
- Create: `dashboard/ui/src/components/research/ResearchContextBar.vue`
- Create/modify: `tests/test_research_view_integration.py`, `tests/test_vue_repairs_contract.py`

**Interfaces:**
- Research view owns `researchLoadState`, `kline`, `indicators`, and `evidence`; it writes only instrument/strategy/derived results to the context store.
- All loaders use an `AbortController` and a request key `${market}:${symbol}:${period}`; stale responses are ignored.
- `DecisionCard` accepts real decision data or `null` and renders an unavailable state with reason.

- [ ] Add failing tests for real API calls, no fixed `65%`/`观望`, K-line empty state, source-specific evidence errors, and stale response protection.
- [ ] Run focused tests and verify failure.
- [ ] Load K-line and indicators in parallel on route/instrument change, cancel the previous request, and clear old instrument data before loading the new instrument.
- [ ] Render an actual SVG/canvas chart from normalized bars using the existing project chart conventions; include period control, source, as-of time, loading, empty, partial, and error states.
- [ ] Render actual indicators and show “暂无数据/数据不可用” when a metric is absent.
- [ ] Replace hard-coded evidence with API-backed source cards and show each source’s loading/error/empty state.
- [ ] Replace fixed decision data with a real backend decision result if available; otherwise render “当前无法生成确定性结论” with the actual reason and keep AI commentary visibly non-authoritative.
- [ ] Replace disabled backtest buttons with a clear “进入验证并继承当前股票” navigation action to the real ValidationView.
- [ ] Add a bottom action bar whose actions derive from data state: refresh, add to watchlist, run validation, or explain why paper preview is blocked.
- [ ] Run focused tests, `npm run ui:build`, and browser verification for CN and unavailable/non-CN instruments.
- [ ] Commit: `feat(ui): restore usable single-stock research`

---

## Task 5: Make validation inherit context and gate paper preview

**Files:**
- Modify: `dashboard/ui/src/views/ValidationView.vue`
- Modify: `dashboard/ui/src/api/client.ts` only if typed backtest helpers are missing
- Create/modify: `tests/test_vue_research_context_contract.py`, `tests/e2e/research-context-loop.spec.cjs`

**Interfaces:**
- Validation initializes from context when `hasInstrument`; otherwise renders an explicit guide and does not run a backtest.
- `runBacktest()` calls `/api/backtest/run` with `codes: [context.symbol]` unless the user explicitly adds more symbols.
- Successful response calls `researchContext.setBacktest(requestBody, result)`.
- `canPreviewPaper` requires a real backtest result, valid instrument, and no blocking risk/eligibility state.

- [ ] Add failing tests for no-context guidance, inherited symbol/strategy, result persistence, and disabled paper preview before validation.
- [ ] Run focused tests and verify failure.
- [ ] Remove the hardcoded form code `000001`; initialize dates/strategy from context or a documented current-date window.
- [ ] Add a visible context header and parameter-origin labels; preserve user edits in local page state.
- [ ] Write successful backtest and robustness results to the store and show errors without clearing the selected instrument.
- [ ] Add navigation to `/app/more/paper` with a serialized context token or store-backed state; the paper page must verify the context before enabling preview.
- [ ] Run focused tests, frontend build, and the browser validation path with a real or controlled local backend response.
- [ ] Commit: `feat(ui): carry research context into validation`

---

## Task 6: Replace paper mock APIs and implement safe Paper Engine actions

**Files:**
- Modify: `dashboard/ui/src/api/paper.ts`
- Modify: `dashboard/ui/src/views/more/PaperTradingView.vue`
- Modify: `dashboard/ui/src/api/client.ts` if envelope extraction helper is needed
- Create/modify: `tests/test_paper_trading.py`, `tests/test_vue_more_contract.py`, `tests/e2e/research-context-loop.spec.cjs`

**Interfaces:**
- `getPaperAccount()` reads `/api/paper/performance` and returns the real performance data or an explicit empty state.
- `getPaperHoldings()` reads `/api/paper/positions` and unwraps `data`.
- `getPaperTrades(limit)` reads `/api/paper/trades-v2?page=1&page_size=${limit}` and unwraps `data.items`.
- `createPaperTrade({ symbol, action, shares })` posts `{ code, direction, order_type: 'market', volume, strategy_name, signal_reason }` to `/api/paper/orders` and returns the created order.
- No function in `paper.ts` may return module-level mock objects or random values.

- [ ] Add failing tests that assert API paths, envelope extraction, order field mapping, positive-volume validation, and no mock markers.
- [ ] Run focused tests and verify failure.
- [ ] Implement real clients using the existing `api` wrapper; map `buy/sell` to the backend direction values and preserve backend errors.
- [ ] Replace `alert`/permanently disabled submit with a confirmation panel showing symbol, direction, volume, price source, context status, and Paper Engine environment.
- [ ] Submit only after client validation and explicit confirmation; refresh account, positions, and trades after success.
- [ ] Show rejected/failed order detail in the page, not a browser alert.
- [ ] Run focused tests, frontend build, and a browser probe for invalid volume and successful/blocked order paths using the local paper backend.
- [ ] Commit: `feat(ui): connect paper trading to Paper Engine`

---

## Task 7: Make DecisionView the workflow entry and preserve mobile usability

**Files:**
- Modify: `dashboard/ui/src/views/DecisionView.vue`
- Modify: `dashboard/ui/src/components/MainContent.vue`
- Modify: `dashboard/ui/src/components/AppShell.vue`
- Modify: `dashboard/ui/src/styles.css` and relevant scoped styles
- Modify: `tests/e2e/research-context-loop.spec.cjs`
- Modify: `tests/test_mobile_responsiveness.py`, `tests/test_vue_layout.py`

**Interfaces:**
- Every candidate instrument exposes one consistent research action that calls `setInstrument` and routes to `/app/research/:market/:symbol`.
- Main content layout is full-width on mobile and does not rely on a scoped desktop margin override.
- Mobile primary actions remain at least 44px and the context/action bar remains reachable above the bottom navigation.

- [ ] Add failing browser/contract assertions for candidate-to-research navigation, current-object summary, context persistence, and mobile action reachability.
- [ ] Run focused tests and verify failure.
- [ ] Add a current-object panel with “继续研究”, “运行回测”, and “加入自选”; add clear empty-state entry points when no instrument is selected.
- [ ] Normalize all opportunity/watchlist links to the same research route and set the context before navigation.
- [ ] Remove the scoped mobile margin conflict and verify content width at 375/390px.
- [ ] Add breadcrumbs and return paths for Decision, Research, Validation, and Paper pages.
- [ ] Run `npm run ui:build`, relevant pytest contracts, and the desktop/mobile browser workflow.
- [ ] Commit: `feat(ui): make decision center the research workflow entry`

---

## Task 8: End-to-end verification and documentation update

**Files:**
- Modify: `tests/e2e/research-context-loop.spec.cjs`
- Modify: `tests/e2e/vue-migration.spec.cjs` and `tests/e2e/vue-workspace-health.spec.cjs` only where assertions conflict with the new workflow
- Modify: `docs/specs/2026-08-17-vue-feature-equivalence-matrix.md`
- Modify: `PRODUCTION_READY_SUMMARY.md` and `KNOWN_ISSUES.md`

**Interfaces:**
- E2E helper authenticates a workspace and drives the real UI; no direct internal imports or test-only component calls.
- The equivalence matrix reports “partial” until the core workflow and its failure states are verified.

- [ ] Add desktop test: authenticate → choose candidate → research → inspect real/explicitly unavailable data → validation inherits context → run/observe result → paper preview gate.
- [ ] Add mobile test at 390px for the same navigation and primary action reachability.
- [ ] Add probes for direct auth deep-link, no-context validation, rapid instrument switching, empty K-line, failed evidence source, invalid order volume, and risk-blocked paper preview.
- [ ] Run the browser suite against a locally started Dashboard and capture route, network, console, and screenshot evidence.
- [ ] Run `.venv/bin/python -m pytest tests/test_vue_*_contract.py tests/test_frontend_data_render_audit.py tests/test_mobile_responsiveness.py -q`.
- [ ] Run `npm run ui:build` and `npm run ui:test`.
- [ ] Run the relevant API tests for backtest, paper, auth, and decision workflows.
- [ ] Update docs to distinguish implemented, partial, and intentionally disabled capabilities; remove any production-ready claim that the evidence does not support.
- [ ] Commit: `test(ui): verify research context workflow end to end`

---

## Execution Order and Checkpoints

1. Task 1 establishes safe shell routing and request behavior.
2. Task 2 establishes context and removes hardcoded direct-entry defaults.
3. Task 3 establishes real response normalization and state semantics.
4. Task 4 makes the research page usable.
5. Task 5 connects research to validation.
6. Task 6 connects validation context to safe paper execution.
7. Task 7 improves workflow entry and mobile completion.
8. Task 8 verifies the complete user task and corrects status documentation.

Each task is independently reviewable and must pass its focused tests before the next task begins. Do not mark the Vue migration equivalent or production-ready until Task 8 passes with captured runtime evidence.
