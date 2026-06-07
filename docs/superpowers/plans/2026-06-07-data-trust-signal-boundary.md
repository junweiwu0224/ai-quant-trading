# Data Trust and Signal Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Signal Engine the trusted runtime AI signal boundary, keep legacy Qlib compatibility, and expose data coverage/validation evidence where users make decisions.

**Architecture:** Keep `data/signals/` as the primary signal read boundary and `/api/qlib/*` as a legacy adapter. DataHub and intelligence pages should show signal provider, validation confidence, sample days, coverage, cache age, and degradation reasons before using scores in opportunity workflows.

**Tech Stack:** Python 3.12 in `.venv`, FastAPI, SQLite/DataStorage, Vanilla JS dashboard, pytest, Node VM frontend contract tests, Playwright smoke via `scripts/e2e-local.sh`.

---

## File Structure

- Modify `dashboard/routers/datahub.py`: separate `signal` health from legacy `qlib` health; keep compatibility summary fields.
- Modify `tests/test_dashboard.py`: cover DataHub health and decision score signal semantics.
- Modify `scripts/dashboard_data_health.py`: add Signal Engine endpoints to safe audit coverage.
- Modify `tests/test_dashboard_data_health.py`: lock the data health endpoint list.
- Modify `dashboard/static/intelligence-qlib.js`: migrate visible AI pool labels from Qlib-first to Signal-first while preserving legacy source note.
- Modify `tests/test_intelligence_market_frontend.py`: cover AI pool trust metadata and Signal wording.
- Modify `dashboard/static/research-datahub.js`: ensure opportunity pool summary prioritizes `signal_*` fields and shows validation confidence.
- Modify or add targeted frontend contract tests for research opportunity rendering if coverage is missing.
- Update `dashboard/templates/partials/scripts.html` and `dashboard/static/sw.js` only if static asset versions or cache lists require cache busting after JS changes.

## Task 1: DataHub Health Uses Signal Health

**Files:**
- Modify: `tests/test_dashboard.py`
- Modify: `dashboard/routers/datahub.py`

- [x] **Step 1: Write the failing test**

Add `test_datahub_health_uses_signal_health_not_legacy_qlib_health` to `tests/test_dashboard.py`. Monkeypatch `_load_signal_health()` and `_load_qlib_health()` with distinct payloads, then assert `/api/datahub/health` returns `payload["signal"]["provider"] == "local_momentum"` and `payload["qlib"]["status"] == "stale"`.

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py::TestValuationDataHubAPI::test_datahub_health_uses_signal_health_not_legacy_qlib_health -q`

Expected: FAIL with missing `payload["signal"]["provider"]`.

- [x] **Step 3: Write minimal implementation**

In `dashboard/routers/datahub.py`, call `_load_signal_health()` inside `datahub_health()` and set response `"signal": signal_health`; keep `"qlib": qlib_health`.

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py::TestValuationDataHubAPI::test_datahub_health_uses_signal_health_not_legacy_qlib_health -q`

Expected: PASS.

## Task 2: Data Health Audit Covers Signal Endpoints

**Files:**
- Modify: `scripts/dashboard_data_health.py`
- Modify: `tests/test_dashboard_data_health.py`

- [x] **Step 1: Write the failing test**

Extend `PLAN_BASELINE_SAFE_GET_PATHS` in `tests/test_dashboard_data_health.py` with:

```python
"/api/signals/health",
"/api/signals/top?limit=5",
```

Keep the exact assertion `assert SAFE_GET_PATHS == PLAN_BASELINE_SAFE_GET_PATHS`.

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dashboard_data_health.py::test_safe_get_paths_cover_user_selected_data_areas -q`

Expected: FAIL because `scripts.dashboard_data_health.SAFE_GET_PATHS` does not yet include the Signal Engine endpoints.

- [x] **Step 3: Write minimal implementation**

Add the same two paths to `SAFE_GET_PATHS` in `scripts/dashboard_data_health.py`, near the existing `/api/qlib/health` entry:

```python
"/api/signals/health",
"/api/signals/top?limit=5",
"/api/qlib/health",
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_dashboard_data_health.py::test_safe_get_paths_cover_user_selected_data_areas -q`

Expected: PASS.

## Task 3: AI Pool Wording Shows Signal Trust Before Qlib Legacy Source

**Files:**
- Modify: `dashboard/static/intelligence-qlib.js`
- Modify: `tests/test_intelligence_market_frontend.py`

- [x] **Step 1: Locate current AI pool rendering contract**

Run:

```bash
rg -n "Qlib|qlib|AI 预测池|validation|trust|provider|confidence" dashboard/static/intelligence-qlib.js tests/test_intelligence_market_frontend.py
```

Expected: find the render function and existing test coverage.

- [x] **Step 2: Write the failing frontend contract test**

Add a Node VM test that stubs `/api/signals/top` or the current AI pool endpoint response with:

```js
{
  success: true,
  provider: "local_momentum",
  model_version: "local_momentum_v1",
  raw_source: "legacy_qlib",
  validation: {
    confidence: "unverified",
    sample_days: 0,
    metrics: {}
  },
  signals: [
    { code: "600519", name: "贵州茅台", score: 0.88, rank: 1, signal_provider: "local_momentum" }
  ]
}
```

Assert rendered HTML includes `AI 信号池`, `local_momentum`, `未验证`, and `legacy qlib` or `legacy_qlib`; assert it does not present `qlib LightGBM` as the primary title.

- [x] **Step 3: Run test to verify it fails**

Run the specific Node-backed pytest for the new test:

```bash
.venv/bin/python -m pytest tests/test_intelligence_market_frontend.py::test_intelligence_signal_pool_renders_validation_summary -q
```

Expected: FAIL on missing Signal-first wording.

- [x] **Step 4: Implement minimal rendering change**

Update the AI pool header/trust summary in `dashboard/static/intelligence-qlib.js` so visible primary text uses `AI 信号池` or `AI 信号`, provider uses `provider/model_version`, and raw legacy source appears only as a secondary trust note.

- [x] **Step 5: Run test to verify it passes**

Run the same targeted pytest.

Expected: PASS.

## Task 4: Opportunity Pool Summary Prioritizes Signal Validation

**Files:**
- Modify: `dashboard/static/research-datahub.js`
- Modify or add: targeted research frontend contract test under `tests/`

- [x] **Step 1: Locate opportunity summary rendering**

Run:

```bash
rg -n "signal_quality|signal_validation|qlib|AI未验证|机会池|decision-matrix" dashboard/static/research-datahub.js tests
```

Expected: identify summary render function and current test file.

- [x] **Step 2: Write failing test**

Create or extend a Node VM test that feeds decision matrix summary:

```js
{
  signal_provider: "local_momentum",
  signal_quality: {
    label: "未验证",
    sample_days: 0,
    penalty_applied: true,
    message: "历史样本不足，AI信号已降权"
  },
  signal_coverage_pct: 80,
  qlib_coverage_pct: 80
}
```

Assert summary prefers `AI信号覆盖 80%`, displays `未验证`, displays `已降权`, and does not use `Qlib覆盖` as the primary label.

- [x] **Step 3: Run test to verify it fails**

Run the targeted pytest for the new/updated test.

Expected: FAIL on legacy Qlib-first wording or missing validation message.

- [x] **Step 4: Implement minimal rendering change**

Update summary rendering to prefer `signal_*` fields. Keep legacy qlib data only as fallback when `signal_*` is absent.

- [x] **Step 5: Run test to verify it passes**

Run the targeted pytest.

Expected: PASS.

## Task 5: Verification and Browser Smoke

**Files:**
- No production file changes expected.

- [x] **Step 1: Run targeted Python tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_dashboard.py tests/test_signal_engine.py tests/test_signal_api.py tests/test_dashboard_data_health.py -q
```

Expected: PASS except the known Starlette/httpx deprecation warning.

- [x] **Step 2: Run context pack verifier**

Run:

```bash
.venv/bin/python scripts/verify_context_pack.py
```

Expected: PASS.

- [x] **Step 3: Run data health audit**

Run:

```bash
.venv/bin/python scripts/dashboard_data_health.py
```

Expected: report has `failed_endpoint_count == 0` and no hard bad display strings.

- [x] **Step 4: Run browser smoke**

Ensure dashboard is listening on `127.0.0.1:8001`, then run:

```bash
scripts/e2e-local.sh smoke
```

Expected: PASS.

- [x] **Step 5: Inspect real browser pages**

Open:

- `http://127.0.0.1:8001/#intelligence`
- `http://127.0.0.1:8001/#overview`
- `http://127.0.0.1:8001/#research`

Expected: no blank page, no visible overflow, no console errors, and data cards show source/update/degradation evidence.
