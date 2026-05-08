"""后台实时行情服务

用东方财富个股 API 替代 AKShare 全市场拉取，只采集订阅的股票。
后台线程持续轮询，内存缓存，支持回调通知。
"""
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional
from urllib.request import Request, urlopen

from loguru import logger


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
    # 新增专业字段
    high_52w: float = 0.0  # 52周最高
    low_52w: float = 0.0  # 52周最低
    avg_volume_5d: float = 0.0  # 5日平均成交量
    avg_volume_10d: float = 0.0  # 10日平均成交量
    eps: float = 0.0  # 每股收益
    bps: float = 0.0  # 每股净资产
    revenue: float = 0.0  # 营业收入
    revenue_growth: float = 0.0  # 营收增长率
    net_profit: float = 0.0  # 净利润
    net_profit_growth: float = 0.0  # 净利润增长率
    gross_margin: float = 0.0  # 毛利率
    net_margin: float = 0.0  # 净利率
    roe: float = 0.0  # ROE
    debt_ratio: float = 0.0  # 负债率
    total_shares: float = 0.0  # 总股本
    circulating_shares: float = 0.0  # 流通股本
    pe_ttm: float = 0.0  # 市盈率(TTM)
    ps_ratio: float = 0.0  # 市销率
    dividend_yield: float = 0.0  # 股息率
    limit_up: float = 0.0  # 涨停价
    limit_down: float = 0.0  # 跌停价
    outer_volume: float = 0.0  # 外盘
    inner_volume: float = 0.0  # 内盘


def _code_to_secid(code: str) -> str:
    """股票代码转东方财富 secid 格式

    沪市 6 开头 -> 1.code
    深市 0/3 开头 -> 0.code
    """
    if code.startswith("6"):
        return f"1.{code}"
    return f"0.{code}"


def _calculate_limit_prices(code: str, pre_close: float) -> tuple[float, float]:
    """计算涨跌停价

    主板(600xxx, 000xxx): ±10%
    创业板(300xxx): ±20%
    科创板(688xxx): ±20%
    ST股票: ±5% (需要额外判断，这里简化处理)
    """
    if pre_close <= 0:
        return 0.0, 0.0

    # 确定涨跌幅限制
    if code.startswith("300") or code.startswith("688"):
        # 创业板/科创板: ±20%
        limit_pct = 0.20
    else:
        # 主板: ±10%
        limit_pct = 0.10

    # 计算涨跌停价（四舍五入到分）
    limit_up = round(pre_close * (1 + limit_pct), 2)
    limit_down = round(pre_close * (1 - limit_pct), 2)

    return limit_up, limit_down


def _fetch_inner_outer_volume(code: str) -> tuple[float, float]:
    """获取内外盘数据

    东方财富API字段:
    - f164: 外盘(手)
    - f165: 内盘(手)
    """
    try:
        secid = _code_to_secid(code)
        url = (
            f"https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}"
            f"&fields=f164,f165"
            f"&_={int(time.time() * 1000)}"
        )
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com",
        })
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())

        d = data.get("data")
        if not d:
            return 0.0, 0.0

        outer = float(d.get("f164", 0) or 0)
        inner = float(d.get("f165", 0) or 0)
        return outer, inner
    except Exception as e:
        logger.debug(f"获取 {code} 内外盘失败: {e}")
        return 0.0, 0.0


def _fetch_single_quote(code: str) -> Optional[QuoteData]:
    """从东方财富 API 获取单只股票行情"""
    secid = _code_to_secid(code)
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={secid}"
        f"&fields=f43,f44,f45,f46,f47,f48,f50,f57,f58,f60,f116,f117,f127,f128,f129,f162,f167,f169,f170"
        f"&_={int(time.time() * 1000)}"
    )
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com",
    })
    try:
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        d = data.get("data")
        if not d:
            return None

        # f43=最新价(分), f44=最高, f45=最低, f46=今开
        # f47=成交量(手), f48=成交额, f57=代码, f58=名称
        # f60=昨收, f169=涨跌额, f170=涨跌幅(%)
        # 注意：价格字段单位是分，需要除以 100
        def price_val(v):
            if v is None or v == "-":
                return 0.0
            return float(v) / 100

        def safe_float(v, div=1):
            if v is None or v == "-":
                return 0.0
            return float(v) / div

        # 获取更多财务数据
        financial_data = _fetch_financial_data(code)

        # 计算涨跌停价
        pre_close_price = price_val(d.get("f60"))
        limit_up, limit_down = _calculate_limit_prices(code, pre_close_price)

        # 获取内外盘数据
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
            turnover_rate=safe_float(d.get("f168"), 100),  # f168=换手率
            amplitude=safe_float(d.get("f50"), 100),      # f50=振幅
            volume_ratio=safe_float(d.get("f52"), 100),    # f52=量比
            # 新增专业字段
            high_52w=financial_data.get("high_52w", 0.0),
            low_52w=financial_data.get("low_52w", 0.0),
            avg_volume_5d=financial_data.get("avg_volume_5d", 0.0),
            avg_volume_10d=financial_data.get("avg_volume_10d", 0.0),
            eps=financial_data.get("eps", 0.0),
            bps=financial_data.get("bps", 0.0),
            revenue=financial_data.get("revenue", 0.0),
            revenue_growth=financial_data.get("revenue_growth", 0.0),
            net_profit=financial_data.get("net_profit", 0.0),
            net_profit_growth=financial_data.get("net_profit_growth", 0.0),
            gross_margin=financial_data.get("gross_margin", 0.0),
            net_margin=financial_data.get("net_margin", 0.0),
            roe=financial_data.get("roe", 0.0),
            debt_ratio=financial_data.get("debt_ratio", 0.0),
            total_shares=financial_data.get("total_shares", 0.0),
            circulating_shares=financial_data.get("circulating_shares", 0.0),
            pe_ttm=financial_data.get("pe_ttm", 0.0),
            ps_ratio=financial_data.get("ps_ratio", 0.0),
            dividend_yield=financial_data.get("dividend_yield", 0.0),
            limit_up=limit_up,
            limit_down=limit_down,
            outer_volume=outer_volume,
            inner_volume=inner_volume,
        )
    except Exception as e:
        logger.debug(f"获取 {code} 行情失败: {e}")
        return None


def _fetch_financial_data(code: str) -> dict:
    """获取股票财务数据（52周高低、财务指标等）"""
    result = {}

    try:
        # 1. 获取K线数据计算52周高低和平均成交量
        secid = _code_to_secid(code)
        url = (
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={secid}"
            f"&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt=101&fqt=1&end=20500101&lmt=250"
            f"&_={int(time.time() * 1000)}"
        )
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com",
        })
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        klines = data.get("data", {}).get("klines", [])
        if klines:
            # 解析K线数据
            volumes = []
            highs = []
            lows = []
            for k in klines[-250:]:  # 最近250个交易日（约1年）
                parts = k.split(",")
                if len(parts) >= 6:
                    volumes.append(float(parts[5]))
                    highs.append(float(parts[3]))
                    lows.append(float(parts[4]))

            # 计算52周高低
            result["high_52w"] = max(highs) if highs else 0.0
            result["low_52w"] = min(lows) if lows else 0.0

            # 计算平均成交量
            result["avg_volume_5d"] = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else 0.0
            result["avg_volume_10d"] = sum(volumes[-10:]) / 10 if len(volumes) >= 10 else 0.0
    except Exception as e:
        logger.debug(f"获取 {code} K线数据失败: {e}")

    try:
        # 2. 获取财务指标数据
        # 东方财富财务指标接口
        market = "SH" if code.startswith("6") else "SZ"
        finance_url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_F10_FINANCE_MAINFINADATA"
            f"&sty=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&p=1&ps=1&sr=-1&st=REPORT_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        req = Request(finance_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com",
        })
        with urlopen(req, timeout=5) as resp:
            finance_data = json.loads(resp.read())

        if finance_data.get("result") and finance_data["result"].get("data"):
            items = finance_data["result"]["data"]
            if items:
                latest = items[0]
                # 每股收益
                result["eps"] = latest.get("EPSJB", 0) or 0
                # 每股净资产
                result["bps"] = latest.get("BPS", 0) or 0
                # 营业总收入
                result["revenue"] = latest.get("TOTALOPERATEREVE", 0) or 0
                # 营收同比增长(%)
                result["revenue_growth"] = latest.get("TOTALOPERATEREVETZ", 0) or 0
                # 净利润
                result["net_profit"] = latest.get("PARENTNETPROFIT", 0) or 0
                # 净利润同比增长(%)
                result["net_profit_growth"] = latest.get("PARENTNETPROFITTZ", 0) or 0
                # 毛利率
                result["gross_margin"] = latest.get("XSMLL", 0) or 0
                # 净利率
                result["net_margin"] = latest.get("XSJLL", 0) or 0
                # ROE
                result["roe"] = latest.get("ROEJQ", 0) or 0
                # 资产负债率
                result["debt_ratio"] = latest.get("ZCFZL", 0) or 0
    except Exception as e:
        logger.debug(f"获取 {code} 财务指标失败: {e}")

    try:
        # 3. 获取股本信息
        share_url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_F10_EH_EQUITY"
            f"&sty=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&p=1&ps=1&sr=-1&st=END_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        req = Request(share_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com",
        })
        with urlopen(req, timeout=5) as resp:
            share_data = json.loads(resp.read())

        if share_data.get("result") and share_data["result"].get("data"):
            items = share_data["result"]["data"]
            if items:
                latest = items[0]
                # 总股本
                result["total_shares"] = latest.get("TOTAL_SHARES", 0) or 0
                # 流通股本
                result["circulating_shares"] = latest.get("FREE_SHARES", 0) or 0
    except Exception as e:
        logger.debug(f"获取 {code} 股本信息失败: {e}")

    try:
        # 4. 获取估值指标
        valuation_url = (
            f"https://datacenter.eastmoney.com/securities/api/data/get"
            f"?type=RPT_VALUEANALYSIS_DET"
            f"&sty=ALL"
            f"&filter=(SECURITY_CODE=%22{code}%22)"
            f"&p=1&ps=1&sr=-1&st=TRADE_DATE"
            f"&_={int(time.time() * 1000)}"
        )
        req = Request(valuation_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com",
        })
        with urlopen(req, timeout=5) as resp:
            valuation_data = json.loads(resp.read())

        if valuation_data.get("result") and valuation_data["result"].get("data"):
            items = valuation_data["result"]["data"]
            if items:
                latest = items[0]
                # 市盈率TTM
                result["pe_ttm"] = latest.get("PE_TTM", 0) or 0
                # 市销率
                result["ps_ratio"] = latest.get("PS_TTM", 0) or 0
                # 股息率
                result["dividend_yield"] = latest.get("DVY_TTM", 0) or 0
    except Exception as e:
        logger.debug(f"获取 {code} 估值指标失败: {e}")

    return result


def _fetch_batch_quotes(codes: list[str]) -> dict[str, QuoteData]:
    """批量获取行情（逐个请求，但复用连接）"""
    result = {}
    for code in codes:
        quote = _fetch_single_quote(code)
        if quote and quote.price > 0:
            result[code] = quote
    return result


class QuoteService:
    """后台实时行情服务（单例）

    - 后台线程持续轮询订阅的股票
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
        self._callbacks: list[Callable[[dict[str, QuoteData]], None]] = []
        self._update_count = 0
        self._last_update: Optional[float] = None

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
            # 清理不再订阅的缓存
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
        """启动后台行情采集"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="quote-service"
        )
        self._thread.start()
        logger.info(f"行情服务启动: 间隔={self._interval}秒")

    def stop(self):
        """停止行情采集"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
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
        """执行一次行情采集"""
        with self._lock:
            codes = list(self._subscriptions)
        if not codes:
            return

        quotes = _fetch_batch_quotes(codes)
        if not quotes:
            return

        with self._lock:
            self._cache.update(quotes)

        with self._stats_lock:
            self._update_count += 1
            self._last_update = time.time()

        # 通知回调
        for cb in self._callbacks:
            try:
                cb(quotes)
            except Exception as e:
                logger.error(f"行情回调异常: {e}")

        logger.debug(f"行情更新: {len(quotes)} 只, 第 {self._update_count} 次")


# ── 全局单例 ──
_quote_service: Optional[QuoteService] = None
_service_lock = threading.Lock()


def get_quote_service(interval: float = 5.0) -> QuoteService:
    """获取全局行情服务单例（线程安全）"""
    global _quote_service
    if _quote_service is None:
        with _service_lock:
            if _quote_service is None:
                _quote_service = QuoteService(interval=interval)
                return _quote_service
    # 已存在时校验参数
    if _quote_service._interval != interval:
        logger.warning(
            f"QuoteService 已存在(interval={_quote_service._interval})，"
            f"忽略新参数 interval={interval}"
        )
    return _quote_service
