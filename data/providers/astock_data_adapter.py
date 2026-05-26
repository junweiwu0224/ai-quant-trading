"""A-Stock data adapter for analyst consensus and valuation snapshots."""
from __future__ import annotations

import asyncio
import json
import re
import statistics
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
from loguru import logger

from data.collector.cache import TTLCache
from data.collector.data_source import DataSource, Quote
from data.collector.field_mapper import map_mootdx_quote
from data.collector.http_client import (
    code_to_secid,
    fetch_json,
    fetch_json_tencent,
)


_STOCK_CODE_RE = re.compile(r"^(?:[sS][hH]|[sS][zZ])?(\d{6})$")


def normalize_stock_code(code: str) -> str | None:
    normalized = str(code or "").strip()
    match = _STOCK_CODE_RE.fullmatch(normalized)
    return match.group(1) if match else None


def _get_mootdx_manager():
    from data.collector.mootdx_client import get_mootdx_manager

    return get_mootdx_manager()


def _frequency_to_period(period: str) -> str:
    return str(period or "day").lower()


def _fetch_kline_mootdx(code: str, count: int = 250, frequency: int = 9) -> dict[str, Any] | None:
    try:
        manager = _get_mootdx_manager()
        loop = asyncio.new_event_loop()
        try:
            df = loop.run_until_complete(manager.get_kline_full(code, frequency=frequency, total=count))
        finally:
            loop.close()

        if df is None or df.empty:
            return None

        klines_raw: list[list[str]] = []
        for _, row in df.iterrows():
            klines_raw.append(
                [
                    str(row.get("datetime", row.get("date", ""))),
                    str(row.get("open", 0)),
                    str(row.get("close", 0)),
                    str(row.get("high", 0)),
                    str(row.get("low", 0)),
                    str(row.get("vol", 0)),
                ]
            )
        return {"klines_raw": klines_raw, "name": ""}
    except Exception as exc:
        logger.warning(f"mootdx K线失败({code}): {exc}")
        return None


def fetch_kline(code: str, count: int = 250, period: str = "day") -> dict[str, Any] | None:
    """获取 K 线原始数据，返回 old shape for stock_detail consumers."""
    from config.settings import DATA_SOURCE_MODE

    normalized = normalize_stock_code(code)
    if not normalized:
        return None
    code = normalized

    freq_map = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "60m": 60,
        "day": 9,
        "daily": 9,
        "week": 10,
        "weekly": 10,
        "month": 11,
        "monthly": 11,
    }
    freq = freq_map.get(_frequency_to_period(period), 9)

    if DATA_SOURCE_MODE == "new":
        result = _fetch_kline_mootdx(code, count, freq)
        if result:
            return result
        logger.debug(f"mootdx K线为空({code})，回退push2his")

    secid = code_to_secid(code)
    klt_map = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "60m": 60,
        "day": 101,
        "daily": 101,
        "week": 102,
        "weekly": 102,
        "month": 103,
        "monthly": 103,
    }
    klt = klt_map.get(_frequency_to_period(period), 101)

    klines_raw: list[list[str]] = []
    name = ""
    try:
        url = (
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={secid}"
            f"&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt={klt}&fqt=1&end=20500101&lmt={count}"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(url, timeout=5)
        d = data.get("data") or {}
        name = d.get("name", "")
        for k in d.get("klines", []):
            parts = k.split(",")
            if len(parts) >= 6:
                parts[5] = str(float(parts[5]) / 100)
                klines_raw.append(parts)
    except Exception as exc:
        logger.debug(f"push2his K线失败({code}): {exc}")

    if not klines_raw:
        try:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            period_map = {
                "day": "day",
                "daily": "day",
                "week": "week",
                "weekly": "week",
                "month": "month",
                "monthly": "month",
            }
            tp = period_map.get(_frequency_to_period(period), "day")
            turl = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},{tp},,,{count},qfq"
            tdata = fetch_json_tencent(turl, timeout=8)
            stock_data = (tdata.get("data") or {}).get(f"{prefix}{code}", {})
            klines = stock_data.get(f"qfq{tp}") or stock_data.get(tp) or []
            for k in klines:
                if len(k) >= 6:
                    klines_raw.append(
                        [
                            str(k[0]),
                            str(k[1]),
                            str(k[2]),
                            str(k[3]),
                            str(k[4]),
                            str(float(k[5]) / 100),
                        ]
                    )
        except Exception as exc:
            logger.debug(f"腾讯K线回退失败({code}): {exc}")

    if not klines_raw:
        return None

    return {"klines_raw": klines_raw, "name": name}


_DATACENTER_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
_DATACENTER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://emweb.securities.eastmoney.com/",
}


def fetch_industry_batch(codes: list[str]) -> dict[str, dict[str, str]]:
    """从东方财富 F10 API 批量获取行业分类"""
    valid_codes = [code for code in (normalize_stock_code(c) for c in codes) if code]
    if not valid_codes:
        return {}
    try:
        code_list = ",".join(f'"{c}"' for c in valid_codes)
        params = {
            "reportName": "RPT_F10_BASIC_ORGINFO",
            "columns": "SECURITY_CODE,INDUSTRYCSRC1,BOARD_NAME_LEVEL",
            "filter": f"(SECURITY_CODE in ({code_list}))",
            "pageSize": len(valid_codes),
            "pageNumber": 1,
            "source": "HSF10",
            "client": "PC",
        }
        data = fetch_json(_DATACENTER_URL, params=params, timeout=10, headers=_DATACENTER_HEADERS)
        result: dict[str, dict[str, str]] = {}
        for row in (data.get("result", {}) or {}).get("data", []) or []:
            code = row.get("SECURITY_CODE", "")
            if not code:
                continue
            industry = row.get("INDUSTRYCSRC1", "")
            board_level = row.get("BOARD_NAME_LEVEL", "")
            parts = [p.strip() for p in board_level.split("-") if p.strip()] if board_level else []
            sector = parts[1] if len(parts) >= 2 else ""
            concepts = parts[2] if len(parts) >= 3 else ""
            result[code] = {"industry": industry, "sector": sector, "concepts": concepts}
        return result
    except Exception as exc:
        logger.warning(f"批量获取行业数据失败: {exc}")
        return {}


def _fetch_concepts_single(code: str) -> str:
    try:
        secid = code_to_secid(code)
        url = (
            f"https://push2delay.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}&fields=f57,f129"
            f"&ut=fa5fd1943c7b386f172d6893dbbd1d0c"
            f"&_={int(time.time() * 1000)}"
        )
        data = fetch_json(url, timeout=5)
        return str((data.get("data") or {}).get("f129") or "")
    except Exception:
        return ""


def fetch_concepts_batch(codes: list[str]) -> dict[str, str]:
    """并发获取多只股票概念，返回 {code: "概念1,概念2,..."}"""
    if not codes:
        return {}
    from concurrent.futures import ThreadPoolExecutor, as_completed

    result: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(len(codes), 10)) as pool:
        futures = {pool.submit(_fetch_concepts_single, c): c for c in codes}
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                concepts = fut.result()
                if concepts:
                    result[code] = concepts
            except Exception:
                pass
    return result


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _median(values: list[float]) -> float | None:
    cleaned = [float(v) for v in values if v is not None]
    if not cleaned:
        return None
    try:
        return float(statistics.median(cleaned))
    except Exception:
        return None


def _mode_text(values: list[str]) -> str:
    cleaned = [v for v in values if isinstance(v, str) and v.strip()]
    if not cleaned:
        return ""
    try:
        return statistics.mode(cleaned)
    except Exception:
        return cleaned[0]


@dataclass(frozen=True)
class ForecastSummary:
    code: str
    stock_name: str
    report_count: int
    latest_report_date: str
    latest_rating: str
    latest_org: str
    target_price: float | None
    actual_last_year_eps: float | None
    forecast_this_year_eps: float | None
    forecast_next_year_eps: float | None
    forecast_next_two_year_eps: float | None
    forecast_this_year_pe: float | None
    forecast_next_year_pe: float | None
    forecast_next_two_year_pe: float | None
    growth_this_year_pct: float | None
    growth_next_year_pct: float | None
    growth_next_two_year_pct: float | None
    consensus_label: str
    reports: list[dict[str, Any]]


class AStockDataAdapter(DataSource):
    """Analyst consensus adapter based on Eastmoney reportapi."""

    SOURCE_NAME = "astock"
    SOURCE_VERSION = "datacenter+qt+reportapi"

    def __init__(self) -> None:
        self._forecast_cache = TTLCache(max_size=600)

    def fetch_report_rows(self, code: str, page_size: int = 20) -> list[dict[str, Any]]:
        normalized = normalize_stock_code(code)
        if not normalized:
            return []

        cache_key = f"report-rows:{normalized}:{page_size}"
        hit, cached = self._forecast_cache.get(cache_key)
        if hit:
            return cached

        query = urlencode(
            {
                "industryCode": "*",
                "pageSize": max(1, min(int(page_size), 50)),
                "industry": "*",
                "rating": "*",
                "ratingChange": "*",
                "beginTime": "2020-01-01",
                "endTime": "",
                "pageNo": 1,
                "fields": "",
                "qType": 0,
                "orgCode": "",
                "code": normalized,
                "rcode": "",
                "p": 1,
                "pageNum": 1,
                "pageSize": max(1, min(int(page_size), 50)),
                "_": int(time.time() * 1000),
            }
        )
        url = f"https://reportapi.eastmoney.com/report/list?{query}"
        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://data.eastmoney.com",
            },
        )

        try:
            with urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.warning(f"获取研报数据失败 {normalized}: {exc}")
            return []
        except Exception as exc:
            logger.warning(f"获取研报数据异常 {normalized}: {exc}")
            return []

        rows = payload.get("data") or []
        if not isinstance(rows, list):
            rows = []

        result: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            result.append(
                {
                    "title": row.get("title", ""),
                    "stock_code": row.get("stockCode") or normalized,
                    "stock_name": row.get("stockName", ""),
                    "org": row.get("orgSName", ""),
                    "author": row.get("researcher", ""),
                    "date": str(row.get("publishDate", ""))[:10],
                    "rating": row.get("emRatingName", ""),
                    "target_price": _safe_float(row.get("indvAimPriceT") or row.get("indvAimPriceL")),
                    "this_year_eps": _safe_float(row.get("predictThisYearEps")),
                    "next_year_eps": _safe_float(row.get("predictNextYearEps")),
                    "next_two_year_eps": _safe_float(row.get("predictNextTwoYearEps")),
                    "this_year_pe": _safe_float(row.get("predictThisYearPe")),
                    "next_year_pe": _safe_float(row.get("predictNextYearPe")),
                    "next_two_year_pe": _safe_float(row.get("predictNextTwoYearPe")),
                    "actual_last_year_eps": _safe_float(row.get("actualLastYearEps")),
                    "actual_last_two_year_eps": _safe_float(row.get("actualLastTwoYearEps")),
                    "summary": str(row.get("content", "") or "")[:220],
                    "encode_url": row.get("encodeUrl", ""),
                }
            )

        self._forecast_cache.set(cache_key, result, ttl=1800)
        return result

    def build_summary(self, code: str, page_size: int = 20) -> ForecastSummary | None:
        normalized = normalize_stock_code(code)
        if not normalized:
            return None

        rows = self.fetch_report_rows(normalized, page_size=page_size)
        if not rows:
            return ForecastSummary(
                code=normalized,
                stock_name="",
                report_count=0,
                latest_report_date="",
                latest_rating="",
                latest_org="",
                target_price=None,
                actual_last_year_eps=None,
                forecast_this_year_eps=None,
                forecast_next_year_eps=None,
                forecast_next_two_year_eps=None,
                forecast_this_year_pe=None,
                forecast_next_year_pe=None,
                forecast_next_two_year_pe=None,
                growth_this_year_pct=None,
                growth_next_year_pct=None,
                growth_next_two_year_pct=None,
                consensus_label="暂无研报",
                reports=[],
            )

        latest_row = max(rows, key=lambda item: item.get("date") or "")
        stock_name = str(latest_row.get("stock_name") or "")
        report_dates = [row.get("date") or "" for row in rows if row.get("date")]
        ratings = [str(row.get("rating") or "") for row in rows if row.get("rating")]
        orgs = [str(row.get("org") or "") for row in rows if row.get("org")]

        target_price = _median([row.get("target_price") for row in rows if row.get("target_price") is not None])
        actual_last_year_eps = _median([row.get("actual_last_year_eps") for row in rows if row.get("actual_last_year_eps") is not None])
        forecast_this_year_eps = _median([row.get("this_year_eps") for row in rows if row.get("this_year_eps") is not None])
        forecast_next_year_eps = _median([row.get("next_year_eps") for row in rows if row.get("next_year_eps") is not None])
        forecast_next_two_year_eps = _median([row.get("next_two_year_eps") for row in rows if row.get("next_two_year_eps") is not None])
        forecast_this_year_pe = _median([row.get("this_year_pe") for row in rows if row.get("this_year_pe") is not None])
        forecast_next_year_pe = _median([row.get("next_year_pe") for row in rows if row.get("next_year_pe") is not None])
        forecast_next_two_year_pe = _median([row.get("next_two_year_pe") for row in rows if row.get("next_two_year_pe") is not None])

        growth_this_year_pct = self._calc_growth_pct(forecast_this_year_eps, actual_last_year_eps)
        growth_next_year_pct = self._calc_growth_pct(forecast_next_year_eps, forecast_this_year_eps)
        growth_next_two_year_pct = self._calc_growth_pct(forecast_next_two_year_eps, forecast_next_year_eps)

        latest_report_date = max(report_dates) if report_dates else ""
        latest_rating = _mode_text(ratings)
        latest_org = _mode_text(orgs)
        consensus_label = self._build_consensus_label(growth_next_year_pct, forecast_next_year_pe)

        report_rows = sorted(rows, key=lambda item: item.get("date") or "", reverse=True)

        return ForecastSummary(
            code=normalized,
            stock_name=stock_name,
            report_count=len(rows),
            latest_report_date=latest_report_date,
            latest_rating=latest_rating,
            latest_org=latest_org,
            target_price=target_price,
            actual_last_year_eps=actual_last_year_eps,
            forecast_this_year_eps=forecast_this_year_eps,
            forecast_next_year_eps=forecast_next_year_eps,
            forecast_next_two_year_eps=forecast_next_two_year_eps,
            forecast_this_year_pe=forecast_this_year_pe,
            forecast_next_year_pe=forecast_next_year_pe,
            forecast_next_two_year_pe=forecast_next_two_year_pe,
            growth_this_year_pct=growth_this_year_pct,
            growth_next_year_pct=growth_next_year_pct,
            growth_next_two_year_pct=growth_next_two_year_pct,
            consensus_label=consensus_label,
            reports=report_rows,
        )

    async def get_realtime_quotes(self, codes: list[str]):
        valid_codes = [code for code in (normalize_stock_code(c) for c in codes) if code]
        if not valid_codes:
            return []

        manager = _get_mootdx_manager()
        df = await manager.quotes(valid_codes)
        if df is None or df.empty:
            return []

        result: list[Quote] = []
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            mapped = map_mootdx_quote(row_dict)
            code = str(mapped.get("code") or row_dict.get("code") or "")
            if not code:
                continue
            result.append(
                Quote(
                    code=code,
                    name=str(mapped.get("name") or row_dict.get("name") or ""),
                    price=mapped.get("price"),
                    open=mapped.get("open"),
                    high=mapped.get("high"),
                    low=mapped.get("low"),
                    pre_close=mapped.get("pre_close"),
                    volume=mapped.get("volume"),
                    amount=mapped.get("amount"),
                    change_pct=mapped.get("change_pct"),
                    turnover_rate=_safe_float(row_dict.get("turnover_rate") or row_dict.get("turnover")),
                    pe_ratio=_safe_float(row_dict.get("pe_ratio") or row_dict.get("pe")),
                    pb_ratio=_safe_float(row_dict.get("pb_ratio") or row_dict.get("pb")),
                    market_cap=_safe_float(row_dict.get("market_cap")),
                    bid1=mapped.get("bid1"),
                    ask1=mapped.get("ask1"),
                    bid1_vol=mapped.get("bid1_vol"),
                    ask1_vol=mapped.get("ask1_vol"),
                    bid2=mapped.get("bid2"),
                    ask2=mapped.get("ask2"),
                    bid2_vol=mapped.get("bid2_vol"),
                    ask2_vol=mapped.get("ask2_vol"),
                    bid3=mapped.get("bid3"),
                    ask3=mapped.get("ask3"),
                    bid3_vol=mapped.get("bid3_vol"),
                    ask3_vol=mapped.get("ask3_vol"),
                    bid4=mapped.get("bid4"),
                    ask4=mapped.get("ask4"),
                    bid4_vol=mapped.get("bid4_vol"),
                    ask4_vol=mapped.get("ask4_vol"),
                    bid5=mapped.get("bid5"),
                    ask5=mapped.get("ask5"),
                    bid5_vol=mapped.get("bid5_vol"),
                    ask5_vol=mapped.get("ask5_vol"),
                )
            )
        return result

    async def get_kline(self, code: str, frequency: int = 9, start: int = 0, offset: int = 800):
        normalized = normalize_stock_code(code)
        if not normalized:
            return pd.DataFrame()

        manager = _get_mootdx_manager()
        df = await manager.bars(normalized, frequency=frequency, start=start, offset=offset)
        if df is None or df.empty:
            return pd.DataFrame()

        out = df.copy()
        rename_map = {}
        if "datetime" in out.columns:
            rename_map["datetime"] = "date"
        if "date" in out.columns:
            rename_map["date"] = "date"
        out = out.rename(columns=rename_map)
        if "vol" in out.columns and "volume" not in out.columns:
            out["volume"] = out["vol"]
        if "amount" not in out.columns:
            out["amount"] = 0
        for col in ["date", "open", "close", "high", "low", "volume", "amount"]:
            if col not in out.columns:
                out[col] = None
        return out[["date", "open", "close", "high", "low", "volume", "amount"]]

    async def get_minute(self, code: str):
        normalized = normalize_stock_code(code)
        if not normalized:
            return pd.DataFrame()

        manager = _get_mootdx_manager()
        df = await manager.minute(normalized)
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        if "datetime" in out.columns and "time" not in out.columns:
            out = out.rename(columns={"datetime": "time"})
        return out

    async def get_finance(self, code: str):
        normalized = normalize_stock_code(code)
        if not normalized:
            return {}

        manager = _get_mootdx_manager()
        result: dict[str, Any] = {}

        try:
            kline_df = await manager.get_kline_full(normalized, frequency=9, total=250)
            if kline_df is not None and not kline_df.empty:
                if "high" in kline_df.columns:
                    result["high_52w"] = float(kline_df["high"].max())
                    result["low_52w"] = float(kline_df["low"].min())
                if "vol" in kline_df.columns:
                    vols = [float(v) for v in kline_df["vol"].tolist() if v is not None]
                    result["avg_volume_5d"] = sum(vols[-5:]) / 5 if len(vols) >= 5 else 0.0
                    result["avg_volume_10d"] = sum(vols[-10:]) / 10 if len(vols) >= 10 else 0.0
        except Exception as exc:
            logger.debug(f"获取 {normalized} K线财务辅助数据失败: {exc}")

        try:
            df_fin = await manager.finance(normalized)
            if df_fin is not None and not df_fin.empty:
                row = df_fin.iloc[0]
                result["total_shares"] = float(row.get("zongguben", 0) or 0)
                result["circulating_shares"] = float(row.get("liutongguben", 0) or 0)
                result["revenue"] = float(row.get("zhuyingshouru", 0) or 0)
                result["net_profit"] = float(row.get("jinglirun", 0) or 0)
                result["bps"] = float(row.get("meigujingzichan", 0) or 0)
                result["roe"] = float(row.get("roe", 0) or 0)
        except Exception as exc:
            logger.debug(f"获取 {normalized} 财务概况失败: {exc}")

        try:
            f10 = await manager.f10(normalized)
            if isinstance(f10, dict):
                fin_text = f10.get("财务分析", "")
                if fin_text:
                    result["f10_text"] = str(fin_text)[:500]
        except Exception as exc:
            logger.debug(f"获取 {normalized} F10 失败: {exc}")

        return result

    async def get_xdxr(self, code: str):
        normalized = normalize_stock_code(code)
        if not normalized:
            return pd.DataFrame()

        manager = _get_mootdx_manager()
        df = await manager.xdxr(normalized)
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        if "datetime" in out.columns and "date" not in out.columns:
            out = out.rename(columns={"datetime": "date"})
        return out

    async def get_f10(self, code: str, section: str | None = None):
        normalized = normalize_stock_code(code)
        if not normalized:
            return {}

        manager = _get_mootdx_manager()
        f10 = await manager.f10(normalized)
        if not isinstance(f10, dict):
            return {}
        if section:
            if section in f10:
                return {section: f10.get(section)}
            return {}
        return f10

    async def get_valuation_snapshot(self, code: str, report_limit: int = 8) -> dict[str, Any]:
        snapshot = self.build_summary(code, page_size=max(8, report_limit))
        if snapshot is None:
            raise ValueError("无法生成估值快照")
        return {
            "code": snapshot.code,
            "stock_name": snapshot.stock_name,
            "report_count": snapshot.report_count,
            "latest_report_date": snapshot.latest_report_date,
            "latest_rating": snapshot.latest_rating,
            "latest_org": snapshot.latest_org,
            "target_price": snapshot.target_price,
            "actual_last_year_eps": snapshot.actual_last_year_eps,
            "forecast_this_year_eps": snapshot.forecast_this_year_eps,
            "forecast_next_year_eps": snapshot.forecast_next_year_eps,
            "forecast_next_two_year_eps": snapshot.forecast_next_two_year_eps,
            "forecast_this_year_pe": snapshot.forecast_this_year_pe,
            "forecast_next_year_pe": snapshot.forecast_next_year_pe,
            "forecast_next_two_year_pe": snapshot.forecast_next_two_year_pe,
            "growth_this_year_pct": snapshot.growth_this_year_pct,
            "growth_next_year_pct": snapshot.growth_next_year_pct,
            "growth_next_two_year_pct": snapshot.growth_next_two_year_pct,
            "consensus_label": snapshot.consensus_label,
            "reports": snapshot.reports[: max(1, min(report_limit, 20))],
        }

    def _calc_growth_pct(self, current: float | None, base: float | None) -> float | None:
        if current is None or base is None:
            return None
        if base == 0:
            return None
        try:
            return round((current / abs(base) - 1) * 100, 2)
        except Exception:
            return None

    def _build_consensus_label(self, growth_next_year_pct: float | None, forward_pe: float | None) -> str:
        if growth_next_year_pct is None or growth_next_year_pct <= 0:
            return "增长缺失"
        if forward_pe is None:
            return "有预测但缺PE"
        peg = forward_pe / growth_next_year_pct if growth_next_year_pct else None
        if peg is None:
            return "缺少 PEG"
        if peg <= 1:
            return "高性价比"
        if peg <= 2:
            return "合理区间"
        return "估值偏贵"
