"""后台实时行情服务 — 混合数据源架构

数据源分工：
  - 雪球 API：实时行情（快、稳定、批量）
  - 东方财富 datacenter：行业分类、财务指标
  - 东方财富 push2delay：单只行情备用

后台线程持续轮询，内存缓存，支持回调通知（WebSocket 推送）。
"""
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from loguru import logger

from data.collector.cache import TTLCache
from data.collector.http_client import (
    calculate_limit_prices,
    code_to_secid,
    code_to_xueqiu_symbol,
    fetch_industry_batch,
    fetch_json,
    fetch_kline,
    get_client,
)


@dataclass(frozen=True)
class QuoteData:
    """实时行情数据"""
    code: str
    name: str
    price: float
    open: float
    high: float
    low: float
    pre_close: float
    volume: float
    amount: float
    change_pct: float
    timestamp: float
    industry: str = ""
    sector: str = ""
    concepts: str = ""
    market_cap: float = 0.0
    circulating_cap: float = 0.0
    pe_ratio: float = 0.0
    pb_ratio: float = 0.0
    turnover_rate: float = 0.0
    amplitude: float = 0.0
    volume_ratio: float = 0.0
    high_52w: float = 0.0
    low_52w: float = 0.0
    avg_volume_5d: float = 0.0
    avg_volume_10d: float = 0.0
    eps: float = 0.0
    bps: float = 0.0
    revenue: float = 0.0
    revenue_growth: float = 0.0
    net_profit: float = 0.0
    net_profit_growth: float = 0.0
    gross_margin: float = 0.0
    net_margin: float = 0.0
    roe: float = 0.0
    debt_ratio: float = 0.0
    total_shares: float = 0.0
    circulating_shares: float = 0.0
    pe_ttm: float = 0.0
    ps_ratio: float = 0.0
    dividend_yield: float = 0.0
    limit_up: float = 0.0
    limit_down: float = 0.0
    outer_volume: float = 0.0
    inner_volume: float = 0.0


# ── 财务数据 TTL 缓存（30 分钟）──
_financial_cache = TTLCache(max_size=200)

# ── 行业数据 TTL 缓存（24 小时）──
_industry_cache = TTLCache(max_size=2000)


def _fetch_inner_outer_volume(code: str) -> tuple[float, float]:
    """获取内外盘数据（push2delay stock/get，当前 502，优雅降级返回 0）"""
    try:
        secid = code_to_secid(code)
        url = (
            f"https://push2delay.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}&fields=f164,f165"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(url, timeout=3)
        d = data.get("data")
        if not d:
            return 0.0, 0.0
        return float(d.get("f164", 0) or 0), float(d.get("f165", 0) or 0)
    except Exception:
        return 0.0, 0.0


def _fetch_single_quote_push2(code: str) -> Optional[QuoteData]:
    """从东方财富 push2delay API 获取单只股票行情（备用）"""
    secid = code_to_secid(code)
    url = (
        f"https://push2delay.eastmoney.com/api/qt/stock/get"
        f"?secid={secid}"
        f"&fields=f43,f44,f45,f46,f47,f48,f50,f52,f57,f58,f60,f116,f117,f127,f128,f129,f162,f167,f168,f169,f170"
        f"&_={int(time.time() * 1000)}"
    )
    try:
        data = fetch_json(url, timeout=5)
        d = data.get("data")
        if not d:
            return None

        def price_val(v):
            if v is None or v == "-":
                return 0.0
            return float(v) / 100

        def safe_float(v, div=1):
            if v is None or v == "-":
                return 0.0
            return float(v) / div

        pre_close_price = price_val(d.get("f60"))
        limit_up, limit_down = calculate_limit_prices(code, pre_close_price)
        outer_volume, inner_volume = _fetch_inner_outer_volume(code)

        return QuoteData(
            code=str(d.get("f57", code)),
            name=str(d.get("f58", "")),
            price=price_val(d.get("f43")),
            open=price_val(d.get("f46")),
            high=price_val(d.get("f44")),
            low=price_val(d.get("f45")),
            pre_close=pre_close_price,
            volume=float(d.get("f47", 0) or 0),
            amount=float(d.get("f48", 0) or 0),
            change_pct=float(d.get("f170", 0) or 0) / 100,
            timestamp=time.time(),
            industry=str(d.get("f127") or ""),
            sector=str(d.get("f128") or ""),
            concepts=str(d.get("f129") or ""),
            market_cap=safe_float(d.get("f116")),
            circulating_cap=safe_float(d.get("f117")),
            pe_ratio=safe_float(d.get("f162"), 100),
            pb_ratio=safe_float(d.get("f167"), 100),
            turnover_rate=safe_float(d.get("f168"), 100),
            amplitude=safe_float(d.get("f50"), 100),
            volume_ratio=safe_float(d.get("f52"), 100),
            limit_up=limit_up,
            limit_down=limit_down,
            outer_volume=outer_volume,
            inner_volume=inner_volume,
        )
    except Exception as e:
        logger.warning(f"获取 {code} push2行情失败: {e}")
        return None


def _fetch_financial_data(code: str) -> dict:
    """获取股票财务数据（52周高低、财务指标等），带 30 分钟 TTL 缓存"""
    hit, cached = _financial_cache.get(f"fin:{code}")
    if hit:
        return cached

    result = {}

    # 1. K线数据计算 52 周高低和平均成交量
    kline = fetch_kline(code, count=250, period="day")
    if kline:
        highs, lows, volumes = [], [], []
        for parts in kline["klines_raw"]:
            if len(parts) >= 6:
                highs.append(float(parts[3]))
                lows.append(float(parts[4]))
                volumes.append(float(parts[5]))
        if highs:
            result["high_52w"] = max(highs)
            result["low_52w"] = min(lows)
            result["avg_volume_5d"] = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else 0.0
            result["avg_volume_10d"] = sum(volumes[-10:]) / 10 if len(volumes) >= 10 else 0.0

    # 2. 财务指标
    try:
        finance_url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_F10_FINANCE_MAINFINADATA&sty=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&p=1&ps=1&sr=-1&st=REPORT_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        finance_data = fetch_json(finance_url, timeout=5,
                                  headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com"})
        if finance_data.get("result") and finance_data["result"].get("data"):
            items = finance_data["result"]["data"]
            if items:
                latest = items[0]
                result["eps"] = latest.get("EPSJB", 0) or 0
                result["bps"] = latest.get("BPS", 0) or 0
                result["revenue"] = latest.get("TOTALOPERATEREVE", 0) or 0
                result["revenue_growth"] = latest.get("TOTALOPERATEREVETZ", 0) or 0
                result["net_profit"] = latest.get("PARENTNETPROFIT", 0) or 0
                result["net_profit_growth"] = latest.get("PARENTNETPROFITTZ", 0) or 0
                result["gross_margin"] = latest.get("XSMLL", 0) or 0
                result["net_margin"] = latest.get("XSJLL", 0) or 0
                result["roe"] = latest.get("ROEJQ", 0) or 0
                result["debt_ratio"] = latest.get("ZCFZL", 0) or 0
    except Exception as e:
        logger.warning(f"获取 {code} 财务指标失败: {e}")

    # 3. 股本信息
    try:
        share_url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_F10_EH_EQUITY&sty=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&p=1&ps=1&sr=-1&st=END_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        share_data = fetch_json(share_url, timeout=5,
                                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com"})
        if share_data.get("result") and share_data["result"].get("data"):
            items = share_data["result"]["data"]
            if items:
                latest = items[0]
                result["total_shares"] = latest.get("TOTAL_SHARES", 0) or 0
                result["circulating_shares"] = latest.get("FREE_SHARES", 0) or 0
    except Exception as e:
        logger.warning(f"获取 {code} 股本信息失败: {e}")

    # 4. 估值指标
    try:
        valuation_url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_VALUEANALYSIS_DET&sty=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&p=1&ps=1&sr=-1&st=TRADE_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        valuation_data = fetch_json(valuation_url, timeout=5,
                                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com"})
        if valuation_data.get("result") and valuation_data["result"].get("data"):
            items = valuation_data["result"]["data"]
            if items:
                latest = items[0]
                result["pe_ttm"] = latest.get("PE_TTM", 0) or 0
                result["ps_ratio"] = latest.get("PS_TTM", 0) or 0
                result["dividend_yield"] = latest.get("DVY_TTM", 0) or 0
    except Exception as e:
        logger.warning(f"获取 {code} 估值指标失败: {e}")

    _financial_cache.set(f"fin:{code}", result, ttl=1800)
    return result


def _enrich_with_industry(result: dict[str, QuoteData], codes: list[str]):
    """用 DB 数据 + datacenter 批量 API + push2delay 补充行业/板块/概念"""
    from data.collector.http_client import fetch_concepts_batch

    # 从缓存查找
    missing = []
    for code in codes:
        if code not in result:
            continue
        hit, cached = _industry_cache.get(f"ind:{code}")
        if hit and cached:
            q = result[code]
            result[code] = QuoteData(**{**q.__dict__, **cached})
        else:
            missing.append(code)

    if not missing:
        return

    # datacenter 批量获取行业/板块（1 次 HTTP）
    batch = fetch_industry_batch(missing)

    # push2delay 并发获取概念（每只 1 次，但概念丰富）
    need_concepts = [c for c in missing if c in result]
    concepts_map = fetch_concepts_batch(need_concepts)

    # 合并结果
    for code in missing:
        if code not in result:
            continue
        info = batch.get(code, {})
        concepts = concepts_map.get(code, "")
        merged = {**info, "concepts": concepts or info.get("concepts", "")}
        q = result[code]
        result[code] = QuoteData(**{**q.__dict__, **merged})
        _industry_cache.set(f"ind:{code}", merged, ttl=86400)


def _fetch_batch_quotes_xueqiu(codes: list[str], stock_info: dict[str, dict] | None = None) -> dict[str, QuoteData]:
    """通过雪球 API 批量获取行情"""
    if not codes:
        return {}
    try:
        symbols = ",".join(code_to_xueqiu_symbol(c) for c in codes)
        url = f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={symbols}"
        client = get_client()
        resp = client.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        resp.raise_for_status()
        data = resp.json()

        result = {}
        for item in data.get("data", []):
            symbol = item.get("symbol", "")
            code = symbol[2:] if len(symbol) > 2 else ""
            if not code:
                continue
            current = float(item.get("current", 0) or 0)
            if current <= 0:
                continue

            pre_close = float(item.get("last_close", 0) or 0)
            limit_up, limit_down = calculate_limit_prices(code, pre_close)

            # 从 DB 预加载的 stock_info 填充 name/industry
            info = (stock_info or {}).get(code, {})
            name = info.get("name", "")
            industry = info.get("industry", "")

            result[code] = QuoteData(
                code=code,
                name=name,
                price=current,
                open=float(item.get("open", 0) or 0),
                high=float(item.get("high", 0) or 0),
                low=float(item.get("low", 0) or 0),
                pre_close=pre_close,
                volume=float(item.get("volume", 0) or 0),
                amount=float(item.get("amount", 0) or 0),
                change_pct=float(item.get("percent", 0) or 0),
                timestamp=time.time(),
                industry=industry,
                market_cap=float(item.get("market_capital", 0) or 0),
                circulating_cap=float(item.get("float_market_capital", 0) or 0),
                turnover_rate=float(item.get("turnover_rate", 0) or 0),
                amplitude=float(item.get("amplitude", 0) or 0),
                limit_up=limit_up,
                limit_down=limit_down,
            )
        return result
    except Exception as e:
        logger.warning(f"雪球行情获取失败: {e}")
        return {}


def _fetch_batch_quotes(codes: list[str], stock_info: dict[str, dict] | None = None) -> dict[str, QuoteData]:
    """批量获取行情：雪球为主，DB + datacenter 补充行业数据"""
    if not codes:
        return {}

    result = _fetch_batch_quotes_xueqiu(codes, stock_info)

    if not result:
        logger.warning(f"雪球行情为空，跳过本轮({len(codes)}只)")
        return result

    # 补充行业/板块/概念（DB 预加载 + datacenter 批量，0-1 次 HTTP）
    _enrich_with_industry(result, [c for c in codes if c in result])

    return result


def _fetch_single_quote_xueqiu(code: str) -> Optional[QuoteData]:
    """通过雪球 API 获取单只股票行情"""
    result = _fetch_batch_quotes_xueqiu([code])
    return result.get(code)


def _fetch_single_quote(code: str) -> Optional[QuoteData]:
    """获取单只股票行情：雪球优先，push2 回退，合并行业/板块/概念 + 财务指标"""
    quote = _fetch_single_quote_xueqiu(code)
    if quote:
        if not quote.industry:
            push2 = _fetch_single_quote_push2(code)
            if push2:
                quote = QuoteData(
                    **{**quote.__dict__,
                       "industry": push2.industry or quote.industry,
                       "sector": push2.sector or quote.sector,
                       "concepts": push2.concepts or quote.concepts,
                       "market_cap": push2.market_cap or quote.market_cap,
                       "pe_ratio": push2.pe_ratio if push2.pe_ratio else quote.pe_ratio,
                       "pb_ratio": push2.pb_ratio if push2.pb_ratio else quote.pb_ratio,
                       "turnover_rate": push2.turnover_rate or quote.turnover_rate,
                    }
                )
        fin = _fetch_financial_data(code)
        if fin:
            quote = QuoteData(
                **{**quote.__dict__,
                   "high_52w": fin.get("high_52w", quote.high_52w),
                   "low_52w": fin.get("low_52w", quote.low_52w),
                   "avg_volume_5d": fin.get("avg_volume_5d", quote.avg_volume_5d),
                   "avg_volume_10d": fin.get("avg_volume_10d", quote.avg_volume_10d),
                   "eps": fin.get("eps", quote.eps),
                   "bps": fin.get("bps", quote.bps),
                   "revenue": fin.get("revenue", quote.revenue),
                   "revenue_growth": fin.get("revenue_growth", quote.revenue_growth),
                   "net_profit": fin.get("net_profit", quote.net_profit),
                   "net_profit_growth": fin.get("net_profit_growth", quote.net_profit_growth),
                   "gross_margin": fin.get("gross_margin", quote.gross_margin),
                   "net_margin": fin.get("net_margin", quote.net_margin),
                   "roe": fin.get("roe", quote.roe),
                   "debt_ratio": fin.get("debt_ratio", quote.debt_ratio),
                   "total_shares": fin.get("total_shares", quote.total_shares),
                   "circulating_shares": fin.get("circulating_shares", quote.circulating_shares),
                   "pe_ttm": fin.get("pe_ttm", quote.pe_ttm),
                   "ps_ratio": fin.get("ps_ratio", quote.ps_ratio),
                   "dividend_yield": fin.get("dividend_yield", quote.dividend_yield),
                }
            )
        return quote
    return _fetch_single_quote_push2(code)


def get_financial_cache(code: str) -> dict | None:
    """获取预缓存的财务数据（供 stock_detail 等外部模块使用）"""
    hit, cached = _financial_cache.get(f"fin:{code}")
    return cached if hit else None


class QuoteService:
    """后台实时行情服务（单例）

    - 后台线程持续轮询订阅的股票（1 秒间隔）
    - 财务数据后台刷新线程（30 分钟间隔）
    - 内存缓存最新行情
    - 支持回调通知（WebSocket 推送用）
    """

    def __init__(self, interval: float = 5.0):
        self._interval = interval
        self._subscriptions: set[str] = set()
        self._cache: dict[str, QuoteData] = {}
        self._lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._fin_thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable[[dict[str, QuoteData]], None]] = []
        self._update_count = 0
        self._last_update: Optional[float] = None
        self._stock_info: dict[str, dict] = {}
        self._reload_stock_info()

    def _reload_stock_info(self):
        """从 DB 加载股票名称和行业信息"""
        try:
            from data.storage.storage import DataStorage
            df = DataStorage().get_stock_list()
            if not df.empty:
                self._stock_info = {
                    row["code"]: {"name": row.get("name", ""), "industry": row.get("industry", "")}
                    for _, row in df.iterrows()
                }
                logger.info(f"加载股票信息: {len(self._stock_info)} 只")
        except Exception as e:
            logger.warning(f"加载股票信息失败: {e}")

    def subscribe(self, codes: list[str]):
        """订阅股票行情"""
        with self._lock:
            self._subscriptions.update(codes)
        logger.info(f"行情订阅: {codes}, 总计 {len(self._subscriptions)} 只")

    def unsubscribe(self, codes: list[str]):
        """取消订阅"""
        with self._lock:
            for c in codes:
                self._subscriptions.discard(c)
                self._cache.pop(c, None)
        logger.info(f"取消订阅: {codes}, 剩余 {len(self._subscriptions)} 只")

    def set_codes(self, codes: list[str]):
        """设置订阅列表（替换）"""
        with self._lock:
            self._subscriptions = set(codes)
            for c in list(self._cache.keys()):
                if c not in self._subscriptions:
                    del self._cache[c]
        logger.info(f"设置行情订阅: {len(codes)} 只股票")

    def on_update(self, callback: Callable[[dict[str, QuoteData]], None]):
        """注册行情更新回调"""
        self._callbacks.append(callback)

    def get_quote(self, code: str) -> Optional[QuoteData]:
        """获取单只股票最新行情"""
        with self._lock:
            return self._cache.get(code)

    def get_all_quotes(self) -> dict[str, QuoteData]:
        """获取所有缓存行情"""
        with self._lock:
            return dict(self._cache)

    def get_prices(self) -> dict[str, float]:
        """获取价格字典 {code: price}"""
        with self._lock:
            return {c: q.price for c, q in self._cache.items()}

    def get_financial_data(self, code: str) -> dict | None:
        """获取预缓存的财务数据"""
        return get_financial_cache(code)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def subscription_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)

    @property
    def cache_count(self) -> int:
        with self._lock:
            return len(self._cache)

    @property
    def update_count(self) -> int:
        with self._stats_lock:
            return self._update_count

    @property
    def last_update_time(self) -> Optional[float]:
        with self._stats_lock:
            return self._last_update

    def start(self):
        """启动后台行情采集 + 财务数据刷新"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="quote-service"
        )
        self._thread.start()
        self._fin_thread = threading.Thread(
            target=self._financial_refresh_loop, daemon=True, name="quote-financial"
        )
        self._fin_thread.start()
        logger.info(f"行情服务启动: 间隔={self._interval}秒, 财务刷新=30分钟")

    def stop(self):
        """停止行情采集"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        if self._fin_thread:
            self._fin_thread.join(timeout=5)
            self._fin_thread = None
        logger.info("行情服务已停止")

    def _run_loop(self):
        """后台采集循环"""
        while self._running:
            try:
                self._poll_once()
            except Exception as e:
                logger.error(f"行情采集异常: {e}")
            time.sleep(self._interval)

    def _poll_once(self):
        """执行一次行情采集（仅 1 次 HTTP：雪球批量）"""
        with self._lock:
            codes = list(self._subscriptions)
        if not codes:
            return

        quotes = _fetch_batch_quotes(codes, self._stock_info)
        if not quotes:
            return

        with self._lock:
            self._cache.update(quotes)

        with self._stats_lock:
            self._update_count += 1
            self._last_update = time.time()

        for cb in self._callbacks:
            try:
                cb(quotes)
            except Exception as e:
                logger.error(f"行情回调异常: {e}")

    def _financial_refresh_loop(self):
        """后台线程：每 30 分钟刷新订阅股票的财务数据"""
        # 启动后等 10 秒再开始首次刷新（让行情先跑起来）
        time.sleep(10)
        while self._running:
            try:
                self._refresh_financial_data()
            except Exception as e:
                logger.error(f"财务数据刷新异常: {e}")
            time.sleep(1800)

    def _refresh_financial_data(self):
        """刷新所有订阅股票的财务数据"""
        with self._lock:
            codes = list(self._subscriptions)
        if not codes:
            return

        success, fail = 0, 0
        for code in codes:
            try:
                _fetch_financial_data(code)  # 内部有 TTL 缓存
                success += 1
            except Exception as e:
                logger.warning(f"财务数据刷新失败 {code}: {e}")
                fail += 1

        # 刷新股票信息（名称/行业可能更新）
        self._reload_stock_info()

        logger.info(f"财务数据刷新完成: 成功 {success}, 失败 {fail}, 共 {len(codes)} 只")


# ── 全局单例 ──
_quote_service: Optional[QuoteService] = None
_service_lock = threading.Lock()


def get_quote_service(interval: float = 5.0) -> QuoteService:
    """获取全局行情服务单例（线程安全）"""
    global _quote_service
    with _service_lock:
        if _quote_service is None:
            _quote_service = QuoteService(interval=interval)
        return _quote_service
