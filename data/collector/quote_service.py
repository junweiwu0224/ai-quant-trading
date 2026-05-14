"""后台实时行情服务 — 混合数据源架构

数据源分工：
  - mootdx（主源）：实时行情、K线、财务、F10
  - 腾讯财经（补充源）：估值、换手率、52周高低等缺失字段
  - 东方财富 datacenter（辅源）：行业分类、财务指标
  - 东方财富 push2delay（备用）：单只/缺失行情补位

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
    fetch_industry_batch,
    fetch_json,
    fetch_kline,
    get_client,
    normalize_stock_code,
)
from config.settings import DATA_SOURCE_MODE


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

# ── 高频降级日志节流 ──
_last_mootdx_fallback_log = 0.0


def _log_mootdx_fallback(count: int) -> None:
    global _last_mootdx_fallback_log
    now = time.time()
    if now - _last_mootdx_fallback_log < 60:
        return
    _last_mootdx_fallback_log = now
    logger.warning(f"mootdx 部分行情缺失，回退 push2delay({count}只)")


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
        # push2delay 内外盘成交量单位是股，转为手（÷100）
        return float(d.get("f164", 0) or 0) / 100, float(d.get("f165", 0) or 0) / 100
    except Exception:
        return 0.0, 0.0


def _fetch_batch_quotes_mootdx(codes: list[str], stock_info: dict[str, dict] | None = None) -> dict[str, QuoteData]:
    """通过 mootdx 批量获取行情（新数据源主路径）"""
    valid_codes = [code for code in (normalize_stock_code(c) for c in codes) if code]
    if not valid_codes:
        return {}
    try:
        from data.collector.mootdx_client import get_mootdx_manager
        from data.collector.field_mapper import map_mootdx_quote

        manager = get_mootdx_manager()
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            df = loop.run_until_complete(manager.quotes(valid_codes))
        finally:
            loop.close()

        if df is None or df.empty:
            return {}

        result = {}
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            mapped = map_mootdx_quote(row_dict)
            code = mapped.get("code", "")
            if not code:
                continue

            # 过滤无效价格（停牌）
            if mapped.get("price") is None:
                continue

            # 从 stock_info 补充名称和行业
            info = (stock_info or {}).get(code, {})
            name = mapped.get("name") or info.get("name", "")
            industry = info.get("industry", "")

            pre_close = mapped.get("pre_close") or 0
            limit_up, limit_down = calculate_limit_prices(code, pre_close)

            result[code] = QuoteData(
                code=code,
                name=name,
                price=mapped.get("price") or 0,
                open=mapped.get("open") or 0,
                high=mapped.get("high") or 0,
                low=mapped.get("low") or 0,
                pre_close=pre_close,
                volume=mapped.get("volume") or 0,
                amount=mapped.get("amount") or 0,
                change_pct=mapped.get("change_pct") or 0,
                timestamp=time.time(),
                industry=industry,
                limit_up=limit_up,
                limit_down=limit_down,
            )
        return result
    except Exception as e:
        logger.warning(f"mootdx 行情获取失败: {e}")
        return {}


def _fetch_financial_data_mootdx(code: str) -> dict:
    """通过 mootdx 获取财务数据（新数据源路径）"""
    hit, cached = _financial_cache.get(f"fin:{code}")
    if hit:
        return cached

    result = {}
    try:
        from data.collector.mootdx_client import get_mootdx_manager
        import asyncio

        manager = get_mootdx_manager()
        loop = asyncio.new_event_loop()
        try:
            # K线数据计算 52 周高低
            df_kline = loop.run_until_complete(manager.get_kline_full(code, frequency=9, total=250))
            if df_kline is not None and not df_kline.empty:
                if "high" in df_kline.columns:
                    result["high_52w"] = float(df_kline["high"].max())
                    result["low_52w"] = float(df_kline["low"].min())
                if "vol" in df_kline.columns:
                    vols = df_kline["vol"].tolist()
                    result["avg_volume_5d"] = sum(vols[-5:]) / 5 if len(vols) >= 5 else 0.0
                    result["avg_volume_10d"] = sum(vols[-10:]) / 10 if len(vols) >= 10 else 0.0

            # 财务概况
            df_fin = loop.run_until_complete(manager.finance(code))
            if df_fin is not None and not df_fin.empty:
                row = df_fin.iloc[0]
                result["total_shares"] = float(row.get("zongguben", 0) or 0)
                result["circulating_shares"] = float(row.get("liutongguben", 0) or 0)
                result["revenue"] = float(row.get("zhuyingshouru", 0) or 0)
                result["net_profit"] = float(row.get("jinglirun", 0) or 0)
                result["bps"] = float(row.get("meigujingzichan", 0) or 0)
                result["roe"] = 0  # mootdx finance 不直接提供 ROE

            # F10 财务分析（补充 PE/PS 等估值指标）
            f10 = loop.run_until_complete(manager.f10(code))
            if f10 and isinstance(f10, dict):
                fin_text = f10.get("财务分析", "")
                # 简单解析：mootdx F10 返回文本格式，后续可增强解析
                result["f10_text"] = fin_text[:500]  # 存摘要

        finally:
            loop.close()

    except Exception as e:
        logger.warning(f"mootdx 财务数据获取失败 {code}: {e}")

    _financial_cache.set(f"fin:{code}", result, ttl=1800)
    return result


def _fetch_batch_quotes_push2(codes: list[str]) -> dict[str, QuoteData]:
    """通过 push2delay 为缺失股票逐只补位行情（备用）"""
    if not codes:
        return {}

    result = {}
    for code in codes:
        quote = _fetch_single_quote_push2(code)
        if quote:
            result[code] = quote
    return result



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
            volume=float(d.get("f47", 0) or 0) / 100,
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
    """获取股票财务数据（根据 DATA_SOURCE_MODE 选择数据源）"""
    normalized = normalize_stock_code(code)
    if not normalized:
        return {}

    hit, cached = _financial_cache.get(f"fin:{normalized}")
    if hit:
        return cached

    if DATA_SOURCE_MODE == "new":
        primary_result = _fetch_financial_data_mootdx(normalized)
        fallback_result = _fetch_financial_data_legacy(normalized)
        result = {**fallback_result, **{k: v for k, v in primary_result.items() if v not in (None, "", 0, 0.0)}}
    else:
        result = _fetch_financial_data_legacy(normalized)

    _financial_cache.set(f"fin:{normalized}", result, ttl=1800)
    return result


def _fetch_financial_data_legacy(code: str) -> dict:
    """通过东方财富获取财务数据（legacy 模式）"""
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


def _enrich_with_tencent(result: dict[str, QuoteData], codes: list[str]):
    """用腾讯财经数据补充 PE/PB/市值/换手率/涨跌停价（mootdx 不提供这些字段）

    腾讯 API 字段映射（GBK编码，~分隔）：
      [1]=名称 [2]=代码 [3]=现价 [4]=昨收 [5]=开盘
      [32]=涨跌幅(%) [33]=最高 [34]=最低
      [38]=换手率(%) [39]=PE(动) [44]=流通市值(亿) [45]=总市值(亿)
      [46]=PB [47]=量比 [48]=跌停价 [52]=PE_TTM [53]=PE(静)
      [67]=52周最高 [68]=52周最低
    """
    if not codes:
        return
    try:
        symbols = []
        for code in codes:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            symbols.append(f"{prefix}{code}")

        for batch_start in range(0, len(symbols), 50):
            batch = symbols[batch_start:batch_start + 50]
            sym_str = ",".join(batch)
            url = f"https://qt.gtimg.cn/q={sym_str}"
            try:
                client = get_client()
                resp = client.get(url, timeout=5, headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://web.ifzq.gtimg.cn",
                })
                text = resp.content.decode("gbk", errors="ignore")
                for line in text.strip().split("\n"):
                    if "=" not in line or "~" not in line:
                        continue
                    parts = line.split("~")
                    if len(parts) < 50:
                        continue
                    code = parts[2] if len(parts) > 2 else ""
                    if code not in result:
                        continue
                    q = result[code]
                    try:
                        pe = float(parts[39]) if parts[39] else 0
                        pb = float(parts[46]) if parts[46] else 0
                        total_cap = float(parts[45]) if parts[45] else 0
                        float_cap = float(parts[44]) if parts[44] else 0
                        turnover = float(parts[38]) if parts[38] else 0
                        limit_down = float(parts[48]) if parts[48] else 0
                        pe_ttm = float(parts[52]) if parts[52] else 0
                        high_52w = float(parts[67]) if parts[67] else 0
                        low_52w = float(parts[68]) if parts[68] else 0

                        # 涨停价 = 跌停价 + 2*昨收价*涨跌幅比例（主板10%，创业板/科创板20%）
                        pre_close = q.pre_close
                        normalized_code = normalize_stock_code(code) or code
                        if pre_close and limit_down and limit_down > 0:
                            limit_pct = 0.20 if normalized_code.startswith(("300", "301", "688")) else 0.10
                            limit_up = round(pre_close * (1 + limit_pct), 2)
                        else:
                            limit_up = q.limit_up

                        result[code] = QuoteData(
                            **{**q.__dict__,
                               "pe_ratio": pe if pe else q.pe_ratio,
                               "pb_ratio": pb if pb else q.pb_ratio,
                               "market_cap": total_cap * 10000 if total_cap else q.market_cap,
                               "circulating_cap": float_cap * 10000 if float_cap else q.circulating_cap,
                               "turnover_rate": turnover if turnover else q.turnover_rate,
                               "limit_up": limit_up,
                               "limit_down": limit_down if limit_down else q.limit_down,
                               "high_52w": high_52w if high_52w else q.high_52w,
                               "low_52w": low_52w if low_52w else q.low_52w,
                               "pe_ttm": pe_ttm if pe_ttm else getattr(q, "pe_ttm", 0),
                               }
                        )
                    except (ValueError, IndexError):
                        pass
            except Exception as e:
                logger.debug(f"腾讯行情补充失败 batch: {e}")
    except Exception as e:
        logger.debug(f"腾讯行情补充异常: {e}")


def _fetch_batch_quotes(codes: list[str], stock_info: dict[str, dict] | None = None) -> dict[str, QuoteData]:
    """批量获取行情（mootdx 主源，腾讯和行业数据补充，push2delay 备用）"""
    valid_codes = [code for code in (normalize_stock_code(c) for c in codes) if code]
    if not valid_codes:
        return {}

    result = _fetch_batch_quotes_mootdx(valid_codes, stock_info)
    missing_codes = [code for code in valid_codes if code not in result]
    if missing_codes:
        _log_mootdx_fallback(len(missing_codes))
        fallback_result = _fetch_batch_quotes_push2(missing_codes)
        result = {**result, **fallback_result}

    if result:
        active_codes = [code for code in valid_codes if code in result]
        _enrich_with_tencent(result, active_codes)
        _enrich_with_industry(result, active_codes)
    return result



def _fetch_single_quote(code: str) -> Optional[QuoteData]:
    """获取单只股票行情（复用批量主路径并补充财务数据）"""
    normalized = normalize_stock_code(code)
    if not normalized:
        return None

    result = _fetch_batch_quotes([normalized])
    quote = result.get(normalized)
    if not quote:
        return None

    fin = _fetch_financial_data(normalized)
    if fin:
        return _merge_financial(quote, fin)
    return quote


def _merge_financial(quote: QuoteData, fin: dict) -> QuoteData:
    """合并财务数据到 QuoteData"""
    return QuoteData(
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


def get_financial_cache(code: str) -> dict | None:
    """获取预缓存的财务数据（供 stock_detail 等外部模块使用）"""
    normalized = normalize_stock_code(code)
    if not normalized:
        return None
    hit, cached = _financial_cache.get(f"fin:{normalized}")
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
                    normalize_stock_code(row["code"]): {"name": row.get("name", ""), "industry": row.get("industry", "")}
                    for _, row in df.iterrows()
                    if normalize_stock_code(row["code"])
                }
                logger.info(f"加载股票信息: {len(self._stock_info)} 只")
        except Exception as e:
            logger.warning(f"加载股票信息失败: {e}")

    def subscribe(self, codes: list[str]):
        """订阅股票行情"""
        normalized_codes = [code for code in (normalize_stock_code(c) for c in codes) if code]
        with self._lock:
            self._subscriptions.update(normalized_codes)
        logger.info(f"行情订阅: {normalized_codes}, 总计 {len(self._subscriptions)} 只")

    def unsubscribe(self, codes: list[str]):
        """取消订阅"""
        normalized_codes = [code for code in (normalize_stock_code(c) for c in codes) if code]
        with self._lock:
            for c in normalized_codes:
                self._subscriptions.discard(c)
                self._cache.pop(c, None)
        logger.info(f"取消订阅: {normalized_codes}, 剩余 {len(self._subscriptions)} 只")

    def set_codes(self, codes: list[str]):
        """设置订阅列表（替换）"""
        normalized_codes = {code for code in (normalize_stock_code(c) for c in codes) if code}
        with self._lock:
            self._subscriptions = set(normalized_codes)
            for c in list(self._cache.keys()):
                if c not in self._subscriptions:
                    del self._cache[c]
        logger.info(f"设置行情订阅: {len(normalized_codes)} 只股票")

    def on_update(self, callback: Callable[[dict[str, QuoteData]], None]):
        """注册行情更新回调"""
        self._callbacks.append(callback)

    def get_quote(self, code: str) -> Optional[QuoteData]:
        """获取单只股票最新行情"""
        normalized = normalize_stock_code(code)
        if not normalized:
            return None
        with self._lock:
            return self._cache.get(normalized)

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
        """执行一次行情采集（mootdx 主源，必要时回退 push2delay）"""
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
