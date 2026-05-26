# A-Stock / 估值数据中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 A-Stock 变成行情、K 线、财务、F10、行业和估值的一条主链路，同时让估值数据中心与 datahub 读同一套可追溯底座。

**Architecture:** 先补持久化底座，再把 A-Stock 适配器提升为主数据源，随后让 `quote_service`、`scheduler` 和 `shadow_validator` 只做编排与对账，最后把 `/api/valuation/*` 和 `/api/datahub/*` 变成同一套 read model 的出口。旧的多源抓取逻辑先保留 fallback，再在 shadow 对账稳定后逐步收口。

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pandas, httpx, APScheduler, pytest, Playwright, vanilla JS

---

## File Map

- `data/storage/storage.py`: 新增数据来源版本、快照、质量记录和健康汇总。
- `data/providers/astock_data_adapter.py`: 成为 A-Stock 主适配器，完整实现 `DataSource` 合约。
- `data/collector/http_client.py`: 收缩为通用 HTTP / 重试 / 限速 / 代码转换层。
- `data/collector/quote_service.py`: 保留订阅、缓存和推送，移除 A-Stock 细节编排。
- `data/scheduler/scheduler.py`: 改为通过适配器做日常同步。
- `data/collector/shadow_validator.py`: 把影子对账结果写进存储层质量账本。
- `dashboard/routers/valuation.py`: 提供估值健康、快照、同业、行业汇总接口。
- `dashboard/routers/datahub.py`: 提供数据源健康、覆盖率、缓存年龄、shadow 摘要和决策矩阵。
- `dashboard/static/research-valuation.js`, `dashboard/static/research-datahub.js`, `dashboard/static/stock-detail-valuation.js`: 渲染新的估值/数据字段。
- `dashboard/static/intelligence-qlib.js`, `dashboard/static/app.js`, `dashboard/static/sw.js`: 让 qlib 与缓存清单跟上新 read model。
- `tests/test_data.py`, `tests/test_dashboard.py`, `tests/e2e/v2-smoke.spec.cjs`: 锁住迁移后的行为。
- `data/collector/data_source.py`: 保持 `get_valuation_snapshot` 合约稳定，不再扩散新签名。

---

### Task 1: Add the provenance and quality ledger

**Files:**
- Modify: `data/storage/storage.py`
- Modify: `tests/test_data.py`

- [ ] **Step 1: Write the failing test**

```python
class TestDataProvenance:
    def test_save_and_read_data_snapshot(self, db):
        snapshot_id = db.save_data_snapshot(
            code="000001",
            domain="valuation",
            source="eastmoney",
            source_version="reportapi-v1",
            payload={"peg_next_year": 0.16, "report_count": 12},
            quality_status="ok",
        )
        row = db.get_latest_data_snapshot("000001", "valuation")
        assert row["id"] == snapshot_id
        assert row["source"] == "eastmoney"
        assert row["source_version"] == "reportapi-v1"
        assert row["payload"]["peg_next_year"] == 0.16
        assert row["quality_status"] == "ok"

    def test_quality_summary_counts_shadow_diffs(self, db):
        db.save_data_quality_record("000001", "quote", "shadow_compare", "diff", {"diff_count": 2})
        db.save_data_quality_record("000001", "quote", "shadow_compare", "ok", {"diff_count": 0})
        summary = db.get_data_quality_summary("quote")
        assert summary["total"] == 2
        assert summary["shadow_diff_count"] == 2
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `C:\v\aiqt\Scripts\python.exe -m pytest -q tests/test_data.py -k data_provenance`

Expected: `AttributeError: 'DataStorage' object has no attribute 'save_data_snapshot'`

- [ ] **Step 3: Add the tables and query helpers**

```python
class DataSourceVersion(Base):
    __tablename__ = "data_source_versions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(64), nullable=False, index=True)
    version = Column(String(64), nullable=False)
    active = Column(Integer, default=1)
    metadata_json = Column(Text, default="{}")
    created_at = Column(String(30), nullable=False)
    updated_at = Column(String(30), nullable=False)


class DataSnapshot(Base):
    __tablename__ = "data_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)
    domain = Column(String(32), nullable=False, index=True)
    source = Column(String(64), nullable=False)
    source_version = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    payload_hash = Column(String(64), nullable=False, index=True)
    quality_status = Column(String(20), nullable=False, default="ok")
    created_at = Column(String(30), nullable=False)


class DataQualityRecord(Base):
    __tablename__ = "data_quality_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)
    domain = Column(String(32), nullable=False, index=True)
    check_name = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="ok")
    diff_count = Column(Integer, default=0)
    details_json = Column(Text, default="{}")
    created_at = Column(String(30), nullable=False)
```

Add these methods on `DataStorage`: `save_data_source_version(source, version, active=True, metadata=None)`, `get_data_source_versions(source=None, active_only=False)`, `save_data_snapshot(code, domain, source, source_version, payload, quality_status='ok')`, `get_latest_data_snapshot(code, domain)`, `save_data_quality_record(code, domain, check_name, status, details=None, diff_count=0)`, `get_data_quality_summary(domain=None)`, `get_data_source_health()`.

- [ ] **Step 4: Re-run the targeted tests**

Run: `C:\v\aiqt\Scripts\python.exe -m pytest -q tests/test_data.py -k data_provenance`

Expected: `2 passed`

- [ ] **Step 5: Commit the storage ledger**

Run:

```bash
git add data/storage/storage.py tests/test_data.py
git commit -m "feat: add data provenance ledger"
```

---

### Task 2: Make `AStockDataAdapter` the canonical provider

**Files:**
- Modify: `data/providers/astock_data_adapter.py`
- Modify: `data/collector/http_client.py`
- Modify: `tests/test_data.py`

- [ ] **Step 1: Write the failing test**

```python
class TestAStockProviderContract:
    def test_http_client_only_keeps_generic_transport_helpers(self):
        assert hasattr(http_client, "fetch_json")
        assert hasattr(http_client, "fetch_json_tencent")
        assert hasattr(http_client, "normalize_stock_code")
        assert hasattr(http_client, "code_to_secid")
        assert hasattr(http_client, "calculate_limit_prices")
        assert not hasattr(http_client, "fetch_kline")
        assert not hasattr(http_client, "fetch_industry_batch")
        assert not hasattr(http_client, "fetch_concepts_batch")

    def test_astock_adapter_returns_valuation_snapshot(self, monkeypatch):
        adapter = AStockDataAdapter()
        monkeypatch.setattr(
            adapter,
            "build_summary",
            lambda code, page_size=20: type(
                "Summary",
                (),
                {
                    "code": "000001",
                    "stock_name": "平安银行",
                    "report_count": 3,
                    "latest_report_date": "2026-05-01",
                    "latest_rating": "买入",
                    "latest_org": "某券商",
                    "target_price": 12.0,
                    "actual_last_year_eps": 0.8,
                    "forecast_this_year_eps": 1.0,
                    "forecast_next_year_eps": 1.5,
                    "forecast_next_two_year_eps": 2.0,
                    "forecast_this_year_pe": 10.0,
                    "forecast_next_year_pe": 8.0,
                    "forecast_next_two_year_pe": 6.0,
                    "growth_this_year_pct": 25.0,
                    "growth_next_year_pct": 50.0,
                    "growth_next_two_year_pct": 33.33,
                    "consensus_label": "高性价比",
                    "reports": [{"title": "看好成长"}],
                },
            )(),
        )
        payload = asyncio.run(adapter.get_valuation_snapshot("000001"))
        assert payload["code"] == "000001"
        assert payload["stock_name"] == "平安银行"
        assert payload["report_count"] == 3
        assert payload["consensus_label"] == "高性价比"
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `C:\v\aiqt\Scripts\python.exe -m pytest -q tests/test_data.py -k astock_provider_contract`

Expected: `AssertionError` because `http_client.py` still exports market-specific fetchers and `AStockDataAdapter` still lacks the full contract methods.

- [ ] **Step 3: Move A-Stock-specific parsing into the adapter**

```python
class AStockDataAdapter(DataSource):
    SOURCE_NAME = "astock"
    SOURCE_VERSION = "datacenter+qt+reportapi"

    async def get_realtime_quotes(self, codes: list[str]) -> list[Quote]:
        return await asyncio.to_thread(self._get_realtime_quotes_sync, codes)

    async def get_kline(self, code: str, frequency: int = 9, start: int = 0, offset: int = 800):
        return await asyncio.to_thread(self._get_kline_sync, code, frequency, start, offset)

    async def get_minute(self, code: str):
        return await asyncio.to_thread(self._get_minute_sync, code)

    async def get_finance(self, code: str):
        return await asyncio.to_thread(self._get_finance_sync, code)

    async def get_xdxr(self, code: str):
        return await asyncio.to_thread(self._get_xdxr_sync, code)

    async def get_f10(self, code: str, section: str | None = None):
        return await asyncio.to_thread(self._get_f10_sync, code, section)
```

Keep `http_client.py` limited to `get_client`, `close_client`, `fetch_json`, `fetch_json_tencent`, `run_sync`, `normalize_stock_code`, `code_to_secid`, and `calculate_limit_prices`.

- [ ] **Step 4: Re-run the targeted tests**

Run: `C:\v\aiqt\Scripts\python.exe -m pytest -q tests/test_data.py -k astock_provider_contract`

Expected: `PASS`

- [ ] **Step 5: Commit the provider split**

Run:

```bash
git add data/providers/astock_data_adapter.py data/collector/http_client.py tests/test_data.py
git commit -m "feat: promote astock provider to canonical data source"
```

---

### Task 3: Route quote collection and daily sync through the provider

**Files:**
- Modify: `data/collector/quote_service.py`
- Modify: `data/scheduler/scheduler.py`
- Modify: `data/collector/shadow_validator.py`
- Modify: `tests/test_data.py`

- [ ] **Step 1: Write the failing test**

```python
class FakeProvider:
    async def get_realtime_quotes(self, codes):
        return [
            Quote(
                code="000001",
                name="平安银行",
                price=10.0,
                open=9.9,
                high=10.2,
                low=9.8,
                pre_close=9.9,
                volume=1000,
                amount=10000,
                change_pct=1.01,
            )
        ]


def test_quote_service_polls_provider(monkeypatch):
    provider = FakeProvider()
    service = QuoteService(interval=1.0, provider=provider)
    service.subscribe(["000001"])
    monkeypatch.setattr(service, "_provider", provider)
    monkeypatch.setattr(service, "_legacy_poll_once", lambda codes: None)
    service._poll_once()
    quote = service.get_quote("000001")
    assert quote.price == 10.0
    assert service.update_count >= 1


def test_shadow_validator_persists_quality_record(db, tmp_path, monkeypatch):
    monkeypatch.setattr(shadow_validator, "_SHADOW_LOG_DIR", tmp_path)
    shadow_validator.log_shadow_result(
        "000001",
        [{"field": "price", "old": 9.9, "new": 10.0, "type": "null_mismatch"}],
        {"price": 9.9, "name": "平安银行"},
        {"price": 10.0, "name": "平安银行"},
        storage=db,
    )
    summary = db.get_data_quality_summary("quote")
    assert summary["total"] == 1
    assert summary["shadow_diff_count"] == 1
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `C:\v\aiqt\Scripts\python.exe -m pytest -q tests/test_data.py -k "quote_service_polls_provider or shadow_validator_persists_quality_record"`

Expected: `TypeError` because `QuoteService` and `log_shadow_result` still do not accept provider/storage injection.

- [ ] **Step 3: Replace the old hard-coded composition with injectable orchestration**

```python
class QuoteService:
    def __init__(self, interval: float = 5.0, provider: DataSource | None = None, storage: DataStorage | None = None):
        self._interval = interval
        self._provider = provider or AStockDataAdapter()
        self._storage = storage or DataStorage()
```

```python
class DataScheduler:
    def __init__(self, storage: DataStorage | None = None, collector: StockCollector | None = None, provider: DataSource | None = None):
        self._storage = storage or DataStorage()
        self._collector = collector or StockCollector()
        self._provider = provider or AStockDataAdapter()
```

```python
def log_shadow_result(code: str, diffs: list[dict], old_data: dict, new_data: dict, storage: DataStorage | None = None):
    if not diffs:
        return
    date_str = time.strftime("%Y%m%d")
    log_file = _SHADOW_LOG_DIR / f"shadow_{date_str}.jsonl"
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "code": code,
        "diff_count": len(diffs),
        "diffs": diffs,
        "old_price": old_data.get("price"),
        "new_price": new_data.get("price"),
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.warning(
        f"[SHADOW] {code}: {len(diffs)} 项差异 — "
        f"价格 old={old_data.get('price')} new={new_data.get('price')}"
    )
    if storage is not None:
        storage.save_data_quality_record(
            code=code,
            domain="quote",
            check_name="shadow_compare",
            status="diff" if diffs else "ok",
            diff_count=len(diffs),
            details={"old": old_data, "new": new_data, "diffs": diffs},
        )
```

`QuoteService._poll_once()` should call the provider first, keep the legacy helpers only as fallback for the migration window, and keep publishing the same `QuoteData` cache shape to callers.

- [ ] **Step 4: Re-run the targeted tests**

Run: `C:\v\aiqt\Scripts\python.exe -m pytest -q tests/test_data.py -k "quote_service_polls_provider or shadow_validator_persists_quality_record"`

Expected: `PASS`

- [ ] **Step 5: Commit the orchestration migration**

Run:

```bash
git add data/collector/quote_service.py data/scheduler/scheduler.py data/collector/shadow_validator.py tests/test_data.py
git commit -m "feat: route quotes through astock provider"
```

---

### Task 4: Surface valuation and datahub health on the same ledger

**Files:**
- Modify: `dashboard/routers/valuation.py`
- Modify: `dashboard/routers/datahub.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

```python
class TestValuationAPI:
    def test_valuation_health_endpoint_exposes_source_health(self):
        res = client.get("/api/valuation/health")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "source_health" in data
        assert "shadow" in data
        assert "coverage" in data


class TestDataHubAPI:
    def test_datahub_health_includes_quality_summary(self):
        res = client.get("/api/datahub/health")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "shadow" in data
        assert "valuation" in data
        assert "quote" in data
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `C:\v\aiqt\Scripts\python.exe -m pytest -q tests/test_dashboard.py -k "valuation_health_endpoint_exposes_source_health or datahub_health_includes_quality_summary"`

Expected: `AssertionError` because the endpoints do not yet expose the new health payload.

- [ ] **Step 3: Add health and snapshot fields to both routers**

```python
@router.get("/health")
async def valuation_health(account: dict = Depends(current_account)):
    storage = DataStorage()
    qlib_health = _load_qlib_health()
    shadow = _load_shadow_summary()
    quality_summary = storage.get_data_quality_summary()
    return {
        "success": True,
        "source_health": storage.get_data_source_health(),
        "quality_summary": quality_summary,
        "coverage": {
            "valuation": quality_summary.get("valuation_coverage_pct"),
            "quote": quality_summary.get("quote_coverage_pct"),
        },
        "shadow": shadow,
        "qlib": qlib_health,
    }
```

```python
latest_snapshot = storage.get_latest_data_snapshot(plain, "valuation")
if latest_snapshot:
    item.update({
        "source": latest_snapshot["source"],
        "source_version": latest_snapshot["source_version"],
        "quality_status": latest_snapshot["quality_status"],
        "snapshot_at": latest_snapshot["created_at"],
    })
```

`dashboard/routers/datahub.py` should keep the current decision matrix shape, but add `source_health`, `quality_summary`, and `shadow` into the top-level `summary` payload so the UI can show coverage and freshness without extra round trips.

- [ ] **Step 4: Re-run the targeted tests**

Run: `C:\v\aiqt\Scripts\python.exe -m pytest -q tests/test_dashboard.py -k "valuation_health_endpoint_exposes_source_health or datahub_health_includes_quality_summary"`

Expected: `PASS`

- [ ] **Step 5: Commit the API surface**

Run:

```bash
git add dashboard/routers/valuation.py dashboard/routers/datahub.py tests/test_dashboard.py
git commit -m "feat: expose valuation and datahub health"
```

---

### Task 5: Refresh the research and detail UIs to consume the new fields

**Files:**
- Modify: `dashboard/static/research-valuation.js`
- Modify: `dashboard/static/research-datahub.js`
- Modify: `dashboard/static/stock-detail-valuation.js`
- Modify: `dashboard/static/intelligence-qlib.js`
- Modify: `dashboard/static/app.js`
- Modify: `dashboard/static/sw.js`
- Modify: `tests/e2e/v2-smoke.spec.cjs`

- [ ] **Step 1: Write the failing smoke test**

```javascript
test('A-Stock valuation center and data hub show health fields', async ({ page }) => {
    await ensureAuthenticated(page, 'valuation_hub');
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await waitForAppReady(page);

    await page.evaluate(() => window.App.switchTab('research'));
    await page.locator('.research-sub-tab[data-subtab="valuation"]').click();
    await expect(page.locator('#sd-valuation-snapshot')).toContainText('PEG');
    await expect(page.locator('#sd-peer-panel')).toBeVisible();

    await page.locator('.research-sub-tab[data-subtab="data"]').click();
    await expect(page.locator('#datahub-total')).toBeVisible();
    await expect(page.locator('#datahub-pipe-shadow')).toContainText('差异');
});
```

- [ ] **Step 2: Run the smoke test and confirm it fails**

Run: `npm run e2e`

Expected: the new assertions fail because the UI still does not render the new health fields.

- [ ] **Step 3: Render the new read-model fields in the UI**

```javascript
// research-datahub.js
set('datahub-pipe-shadow', shadow.total_checks ? `${shadow.total_diffs || 0} 条差异 · ${shadow.codes_with_diffs || 0} 只股票` : '暂无差异日志');
set('datahub-source-health', summary.source_health ? `${summary.source_health.active_sources} 个来源在线` : '--');
set('datahub-quality-summary', summary.quality_summary ? `质量记录 ${summary.quality_summary.total}` : '--');
```

```javascript
// research-valuation.js
set('valuation-source', data.source || '--');
set('valuation-source-version', data.source_version || '--');
set('valuation-quality', data.quality_status || '--');
```

```javascript
// stock-detail-valuation.js
const sourceLabel = data.source ? `${data.source} · ${data.source_version || '--'}` : '--';
```

Bump the bundle cache keys in `dashboard/static/app.js` and the cache manifest in `dashboard/static/sw.js` so the browser does not keep stale scripts after the migration.

- [ ] **Step 4: Re-run the smoke test**

Run: `npm run e2e`

Expected: `PASS`

- [ ] **Step 5: Commit the UI refresh**

Run:

```bash
git add dashboard/static/research-valuation.js dashboard/static/research-datahub.js dashboard/static/stock-detail-valuation.js dashboard/static/intelligence-qlib.js dashboard/static/app.js dashboard/static/sw.js tests/e2e/v2-smoke.spec.cjs
git commit -m "feat: refresh valuation data center ui"
```

---

### Task 6: Run the full regression suite and clean up legacy gaps

**Files:**
- Modify: `tests/test_data.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/e2e/v2-smoke.spec.cjs`
- Modify: any file that still imports `fetch_kline`, `fetch_industry_batch`, or `fetch_concepts_batch` from `data/collector/http_client.py`

- [ ] **Step 1: Run the focused backend suite**

Run: `C:\v\aiqt\Scripts\python.exe -m pytest -q tests/test_data.py tests/test_dashboard.py`

Expected: `PASS`

- [ ] **Step 2: Run the browser smoke suite**

Run: `npm run e2e`

Expected: `PASS`

- [ ] **Step 3: Run the full Python test suite**

Run: `C:\v\aiqt\Scripts\python.exe -m pytest -q tests`

Expected: no `FAILED` lines and the final summary reports the full test count passing.

- [ ] **Step 4: Remove or quarantine any leftover legacy imports**

If any module still imports the market-specific helpers from `data/collector/http_client.py`, move that logic into `data/providers/astock_data_adapter.py` or a provider-local helper and keep `http_client.py` transport-only.

- [ ] **Step 5: Commit the full migration**

Run:

```bash
git add -A
git commit -m "feat: complete astock valuation data center migration"
```
