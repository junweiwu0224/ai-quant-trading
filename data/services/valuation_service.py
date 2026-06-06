"""Valuation service built on analyst consensus data."""
from __future__ import annotations

import asyncio
import inspect
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loguru import logger

from data.collector.cache import TTLCache
from data.providers.astock_data_adapter import AStockDataAdapter, ForecastSummary, normalize_stock_code
from data.storage.storage import DataStorage


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _fmt_pct(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except Exception:
        return None


def _latest_non_empty(*values):
    for value in values:
        if value not in (None, "", 0, 0.0):
            return value
    return None


@dataclass(frozen=True)
class ValuationQuoteContext:
    code: str
    name: str
    industry: str
    sector: str
    price: float | None
    pe_ttm: float | None
    pb_ratio: float | None
    roe: float | None
    market_cap: float | None
    circulating_cap: float | None
    source: str


class ValuationService:
    """Build valuation snapshots and watchlist ranking tables."""

    def __init__(self, storage: DataStorage | None = None) -> None:
        self.storage = storage or DataStorage()
        self.adapter = AStockDataAdapter()
        self._snapshot_cache = TTLCache(max_size=600)
        self._watchlist_cache = TTLCache(max_size=120)
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="valuation")

    def _normalize_code(self, code: str) -> str | None:
        return normalize_stock_code(code)

    def _load_quote_context(self, code: str) -> ValuationQuoteContext:
        normalized = self._normalize_code(code)
        if not normalized:
            raise ValueError("股票代码非法")

        name = ""
        industry = ""
        sector = ""
        price = None
        pe_ttm = None
        pb_ratio = None
        roe = None
        market_cap = None
        circulating_cap = None
        source = "storage"

        stock_list = self.storage.get_stock_list()
        if not stock_list.empty:
            matched = stock_list[stock_list["code"] == normalized]
            if not matched.empty:
                row = matched.iloc[0]
                name = str(row.get("name") or "")
                industry = str(row.get("industry") or "")

        latest_df = self.storage.get_stock_daily(normalized)
        if not latest_df.empty:
            last_row = latest_df.iloc[-1]
            price = _safe_float(last_row.get("close"))

        try:
            from data.collector.quote_service import get_quote_service

            quote = get_quote_service().get_quote(normalized)
            if quote:
                source = "realtime"
                name = _latest_non_empty(quote.name, name) or name
                industry = _latest_non_empty(quote.industry, industry) or industry
                sector = _latest_non_empty(quote.sector, sector) or sector
                price = _safe_float(quote.price) or price
                pe_ttm = _safe_float(getattr(quote, "pe_ttm", None)) or _safe_float(getattr(quote, "pe_ratio", None)) or pe_ttm
                pb_ratio = _safe_float(getattr(quote, "pb_ratio", None)) or pb_ratio
                roe = _safe_float(getattr(quote, "roe", None)) or roe
                market_cap = _safe_float(getattr(quote, "market_cap", None)) or market_cap
                circulating_cap = _safe_float(getattr(quote, "circulating_cap", None)) or circulating_cap
        except Exception as exc:
            logger.debug(f"获取实时行情上下文失败 {normalized}: {exc}")

        return ValuationQuoteContext(
            code=normalized,
            name=name or normalized,
            industry=industry,
            sector=sector,
            price=price,
            pe_ttm=pe_ttm,
            pb_ratio=pb_ratio,
            roe=roe,
            market_cap=market_cap,
            circulating_cap=circulating_cap,
            source=source,
        )

    def _load_qlib_signal(self, code: str) -> dict[str, Any]:
        try:
            from dashboard.routers.datahub import _load_qlib_context

            ctx = _load_qlib_context(top_limit=300)
            return dict((ctx.get("items") or {}).get(code) or {})
        except Exception:
            return {}

    def _build_local_forecast_summary(
        self,
        context: ValuationQuoteContext,
        *,
        report_limit: int = 8,
    ) -> ForecastSummary | None:
        df = self.storage.get_stock_daily(context.code)
        if df.empty or len(df) < 30:
            return None

        closes = [float(v) for v in df["close"].tolist() if v not in (None, 0)]
        if len(closes) < 30:
            return None

        current_price = context.price or closes[-1]
        start_20 = closes[-21] if len(closes) >= 21 else closes[0]
        start_60 = closes[-61] if len(closes) >= 61 else closes[0]
        momentum_20 = (closes[-1] / start_20 - 1) * 100 if start_20 else 0
        momentum_60 = (closes[-1] / start_60 - 1) * 100 if start_60 else momentum_20
        returns = [
            closes[idx] / closes[idx - 1] - 1
            for idx in range(max(1, len(closes) - 60), len(closes))
            if closes[idx - 1]
        ]
        volatility = statistics.pstdev(returns) * (252 ** 0.5) * 100 if len(returns) >= 5 else 0
        qlib = self._load_qlib_signal(context.code)
        qlib_score = _safe_float(qlib.get("qlib_score"))
        qlib_rank = int(qlib.get("qlib_rank") or 0)
        signal_provider = str(qlib.get("signal_provider") or "local_momentum")
        signal_confidence = str(qlib.get("signal_confidence") or "unverified")
        signal_validated = signal_confidence.startswith("validated")

        trend_growth = momentum_60 * 0.55 + momentum_20 * 0.45
        if qlib_score is not None:
            signal_weight = 10 if signal_validated else 4
            trend_growth += (qlib_score - 0.5) * signal_weight
        growth_next_year_pct = round(max(-30, min(60, trend_growth)), 2)
        growth_this_year_pct = round(max(-30, min(55, trend_growth * 0.75)), 2)
        growth_next_two_year_pct = round(max(-30, min(55, growth_next_year_pct * 0.82)), 2)

        risk_discount = min(0.18, max(0, volatility - 22) / 220)
        signal_premium_weight = 0.08 if signal_validated else 0.025
        signal_premium = ((qlib_score or 0.5) - 0.5) * signal_premium_weight
        target_price = round(float(current_price) * (1 + growth_next_year_pct / 100 * 0.38 + signal_premium - risk_discount), 2)
        if target_price <= 0:
            target_price = None

        pe_ttm = context.pe_ttm
        forecast_this_year_pe = pe_ttm
        forecast_next_year_pe = pe_ttm
        forecast_next_two_year_pe = pe_ttm
        forecast_this_year_eps = round(current_price / forecast_this_year_pe, 3) if current_price and forecast_this_year_pe else None
        forecast_next_year_eps = None
        forecast_next_two_year_eps = None
        if forecast_this_year_eps is not None:
            forecast_next_year_eps = round(forecast_this_year_eps * (1 + growth_next_year_pct / 100), 3)
            forecast_next_two_year_eps = round(forecast_next_year_eps * (1 + growth_next_two_year_pct / 100), 3)

        if signal_validated and qlib_rank and qlib_rank <= 10 and growth_next_year_pct >= 15:
            rating = "重点跟踪"
        elif growth_next_year_pct >= 8:
            rating = "跟踪"
        elif growth_next_year_pct <= -8:
            rating = "谨慎"
        else:
            rating = "观察"

        latest_date = str(df.iloc[-1].get("date") or "")[:10]
        title = f"{context.name} 本地研究预测预览"
        signal_bits = [
            f"20日动量 {round(momentum_20, 2)}%",
            f"60日动量 {round(momentum_60, 2)}%",
        ]
        if qlib_rank:
            signal_bits.append(f"AI信号({signal_provider})排名 #{qlib_rank}")
        if not signal_validated:
            signal_bits.append("AI信号未验证，仅作候选排序")
        report = {
            "title": title,
            "org": "本地行情+AI信号",
            "author": "local-derived",
            "date": latest_date,
            "rating": rating,
            "target_price": target_price,
            "this_year_eps": forecast_this_year_eps,
            "next_year_eps": forecast_next_year_eps,
            "next_two_year_eps": forecast_next_two_year_eps,
            "this_year_pe": forecast_this_year_pe,
            "next_year_pe": forecast_next_year_pe,
            "next_two_year_pe": forecast_next_two_year_pe,
            "actual_last_year_eps": None,
            "summary": "；".join(signal_bits),
            "encode_url": "",
            "source": "local_derived",
            "source_note": "由本地日线趋势、波动率和AI信号推导，不等同券商研报；未验证信号已降权",
        }

        return ForecastSummary(
            code=context.code,
            stock_name=context.name,
            report_count=1,
            latest_report_date=latest_date,
            latest_rating=rating,
            latest_org="本地行情+AI信号",
            target_price=target_price,
            actual_last_year_eps=None,
            forecast_this_year_eps=forecast_this_year_eps,
            forecast_next_year_eps=forecast_next_year_eps,
            forecast_next_two_year_eps=forecast_next_two_year_eps,
            forecast_this_year_pe=forecast_this_year_pe,
            forecast_next_year_pe=forecast_next_year_pe,
            forecast_next_two_year_pe=forecast_next_two_year_pe,
            growth_this_year_pct=growth_this_year_pct,
            growth_next_year_pct=growth_next_year_pct,
            growth_next_two_year_pct=growth_next_two_year_pct,
            consensus_label="本地预测",
            reports=[report][: max(1, min(report_limit, 20))],
        )

    def _valuation_bucket(self, growth_pct: float | None, peg: float | None) -> str:
        if growth_pct is None or growth_pct <= 0:
            return "增长缺失"
        if peg is None:
            return "PEG缺失"
        if peg <= 1:
            return "高性价比"
        if peg <= 2:
            return "合理区间"
        return "偏贵"

    def _calc_peg(self, pe: float | None, growth_pct: float | None) -> float | None:
        if pe is None or growth_pct is None or growth_pct <= 0:
            return None
        try:
            return round(pe / growth_pct, 2)
        except Exception:
            return None

    def build_snapshot(self, code: str, report_limit: int = 8) -> dict[str, Any]:
        normalized = self._normalize_code(code)
        if not normalized:
            raise ValueError("股票代码非法")

        cache_key = f"snapshot:{normalized}:{report_limit}"
        hit, cached = self._snapshot_cache.get(cache_key)
        if hit:
            return cached

        context = self._load_quote_context(normalized)
        summary_payload = self._load_valuation_payload(normalized, report_limit=report_limit)
        summary = self._summary_from_payload(summary_payload)
        if summary is None:
            summary = self._build_local_forecast_summary(context, report_limit=report_limit)
        elif int(summary.report_count or 0) <= 0:
            summary = self._build_local_forecast_summary(context, report_limit=report_limit) or summary
        if summary is None:
            raise ValueError("无法生成估值快照")

        snapshot = self._compose_snapshot(context, summary, report_limit=report_limit)
        snapshot = self._persist_snapshot(snapshot)
        self._snapshot_cache.set(cache_key, snapshot, ttl=300)
        return snapshot

    def build_center(self, codes: list[str], limit: int = 50, max_wait_sec: float | None = None) -> dict[str, Any]:
        normalized_codes = [code for code in (self._normalize_code(c) for c in codes) if code]
        if not normalized_codes:
            return {"items": [], "total": 0, "sorted_by": "peg_next_year"}

        cache_key = f"center:{','.join(sorted(normalized_codes))}:{limit}"
        hit, cached = self._watchlist_cache.get(cache_key)
        if hit:
            return cached

        items: list[dict[str, Any]] = []
        futures = []
        for code in normalized_codes[: max(1, min(limit, 80))]:
            futures.append(self._pool.submit(self._safe_build_snapshot, code, 5))

        if max_wait_sec is not None and max_wait_sec > 0:
            pending = set(futures)
            try:
                for fut in as_completed(pending, timeout=max_wait_sec):
                    item = fut.result()
                    if item:
                        items.append(item)
                    if len(items) >= limit:
                        break
            except TimeoutError:
                pass
            finally:
                for fut in pending:
                    if not fut.done():
                        fut.cancel()
        else:
            for fut in futures:
                item = fut.result()
                if item:
                    items.append(item)

        def sort_key(item: dict[str, Any]):
            peg = item.get("peg_next_year")
            growth = item.get("growth_next_year_pct")
            upside = item.get("upside_pct")
            peg_sort = peg if isinstance(peg, (int, float)) and math.isfinite(float(peg)) else 1e9
            growth_sort = -(growth or -1e9)
            upside_sort = -(upside or -1e9)
            return (peg_sort, growth_sort, upside_sort)

        items.sort(key=sort_key)
        for index, item in enumerate(items, start=1):
            item["rank"] = index

        result = {
            "items": items[:limit],
            "total": len(items),
            "sorted_by": "peg_next_year",
        }
        self._watchlist_cache.set(cache_key, result, ttl=300)
        return result

    def build_filtered_center(
        self,
        codes: list[str],
        *,
        limit: int = 50,
        max_wait_sec: float | None = None,
        max_peg: float | None = None,
        min_growth: float | None = None,
        min_upside: float | None = None,
        min_reports: int = 0,
        bucket: str = "",
        industry: str = "",
    ) -> dict[str, Any]:
        center = self.build_center(codes, limit=max(limit, 80), max_wait_sec=max_wait_sec)
        items = list(center.get("items", []))

        def keep(item: dict[str, Any]) -> bool:
            if max_peg is not None:
                peg = _safe_float(item.get("peg_next_year"))
                if peg is None or peg > max_peg:
                    return False
            if min_growth is not None:
                growth = _safe_float(item.get("growth_next_year_pct"))
                if growth is None or growth < min_growth:
                    return False
            if min_upside is not None:
                upside = _safe_float(item.get("upside_pct"))
                if upside is None or upside < min_upside:
                    return False
            if min_reports and int(item.get("report_count") or 0) < min_reports:
                return False
            if bucket and str(item.get("valuation_bucket") or "") != bucket:
                return False
            if industry and industry not in str(item.get("industry") or ""):
                return False
            return True

        filtered = [item for item in items if keep(item)]
        for index, item in enumerate(filtered, start=1):
            item["rank"] = index
        return {
            **center,
            "items": filtered[:limit],
            "total": len(filtered),
            "unfiltered_total": len(items),
            "filters": {
                "max_peg": max_peg,
                "min_growth": min_growth,
                "min_upside": min_upside,
                "min_reports": min_reports,
                "bucket": bucket,
                "industry": industry,
            },
        }

    def build_industry_summary(self, codes: list[str], limit: int = 80) -> dict[str, Any]:
        center = self.build_center(codes, limit=limit)
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in center.get("items", []):
            industry = str(item.get("industry") or "未分类")
            groups.setdefault(industry, []).append(item)

        summaries: list[dict[str, Any]] = []
        for industry, items in groups.items():
            pegs = [_safe_float(item.get("peg_next_year")) for item in items]
            pegs = [peg for peg in pegs if peg is not None]
            growths = [_safe_float(item.get("growth_next_year_pct")) for item in items]
            growths = [growth for growth in growths if growth is not None]
            upsides = [_safe_float(item.get("upside_pct")) for item in items]
            upsides = [upside for upside in upsides if upside is not None]
            covered = [item for item in items if int(item.get("report_count") or 0) > 0]
            high_quality = [
                item for item in items
                if _safe_float(item.get("peg_next_year")) is not None
                and _safe_float(item.get("peg_next_year")) <= 1
                and (_safe_float(item.get("growth_next_year_pct")) or 0) >= 15
            ]
            summaries.append({
                "industry": industry,
                "count": len(items),
                "coverage_pct": round(len(covered) / len(items) * 100, 1) if items else 0,
                "median_peg": round(statistics.median(pegs), 2) if pegs else None,
                "median_growth": round(statistics.median(growths), 2) if growths else None,
                "median_upside": round(statistics.median(upsides), 2) if upsides else None,
                "cheap_growth_count": len(high_quality),
                "top_codes": [
                    {
                        "code": item.get("code"),
                        "name": item.get("name"),
                        "peg_next_year": item.get("peg_next_year"),
                        "growth_next_year_pct": item.get("growth_next_year_pct"),
                    }
                    for item in sorted(
                        items,
                        key=lambda item: (
                            _safe_float(item.get("peg_next_year")) if _safe_float(item.get("peg_next_year")) is not None else 999999,
                            -(_safe_float(item.get("growth_next_year_pct")) or -999999),
                        ),
                    )[:3]
                ],
            })

        summaries.sort(
            key=lambda item: (
                -(item.get("cheap_growth_count") or 0),
                item.get("median_peg") if item.get("median_peg") is not None else 999999,
                -item.get("count", 0),
            )
        )
        return {
            "items": summaries,
            "total": len(summaries),
            "source_total": center.get("total", 0),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def build_peer_comparison(self, code: str, limit: int = 12) -> dict[str, Any]:
        target = self.build_snapshot(code, report_limit=5)
        industry = str(target.get("industry") or "")
        stock_list = self.storage.get_stock_list()
        peer_codes: list[str] = []
        if industry and not stock_list.empty:
            matched = stock_list[stock_list["industry"].astype(str).str.contains(industry, na=False)]
            peer_codes = [str(row.get("code")) for _, row in matched.head(max(limit * 3, 20)).iterrows()]
        if target["code"] not in peer_codes:
            peer_codes.insert(0, target["code"])

        center = self.build_center(peer_codes, limit=max(limit, 12))
        peers = center.get("items", [])
        target_code = target["code"]
        target_peer = next((item for item in peers if item.get("code") == target_code), target)

        pegs = [_safe_float(item.get("peg_next_year")) for item in peers]
        pegs = sorted([peg for peg in pegs if peg is not None])
        target_peg = _safe_float(target_peer.get("peg_next_year"))
        peg_percentile = None
        if pegs and target_peg is not None:
            peg_percentile = round((sum(1 for peg in pegs if peg <= target_peg) / len(pegs)) * 100, 1)

        return {
            "target": target_peer,
            "industry": industry,
            "peers": peers[:limit],
            "summary": {
                "peer_count": len(peers),
                "median_peg": round(statistics.median(pegs), 2) if pegs else None,
                "target_peg_percentile": peg_percentile,
                "target_rank": next((idx for idx, item in enumerate(peers, start=1) if item.get("code") == target_code), None),
            },
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _safe_build_snapshot(self, code: str, report_limit: int) -> dict[str, Any] | None:
        try:
            return self.build_snapshot(code, report_limit=report_limit)
        except Exception as exc:
            logger.debug(f"构建估值快照失败 {code}: {exc}")
            return None

    def _compose_snapshot(
        self,
        context: ValuationQuoteContext,
        summary: ForecastSummary,
        *,
        report_limit: int = 8,
    ) -> dict[str, Any]:
        current_price = context.price
        pe_ttm = context.pe_ttm
        if pe_ttm is None and summary.forecast_this_year_pe is not None:
            pe_ttm = summary.forecast_this_year_pe

        growth_this_year_pct = _fmt_pct(summary.growth_this_year_pct)
        growth_next_year_pct = _fmt_pct(summary.growth_next_year_pct)
        growth_next_two_year_pct = _fmt_pct(summary.growth_next_two_year_pct)

        peg_this_year = self._calc_peg(pe_ttm, growth_this_year_pct)
        peg_next_year = self._calc_peg(pe_ttm, growth_next_year_pct)
        peg_next_two_year = self._calc_peg(pe_ttm, growth_next_two_year_pct)

        target_price = summary.target_price
        upside_pct = None
        if current_price and target_price:
            try:
                upside_pct = round((target_price / current_price - 1) * 100, 2)
            except Exception:
                upside_pct = None

        report_rows = []
        for row in summary.reports[: max(1, min(report_limit, 20))]:
            report_rows.append(
                {
                    "title": row.get("title", ""),
                    "org": row.get("org", ""),
                    "author": row.get("author", ""),
                    "date": row.get("date", ""),
                    "rating": row.get("rating", ""),
                    "target_price": row.get("target_price"),
                    "this_year_eps": row.get("this_year_eps"),
                    "next_year_eps": row.get("next_year_eps"),
                    "this_year_pe": row.get("this_year_pe"),
                    "next_year_pe": row.get("next_year_pe"),
                    "summary": row.get("summary", ""),
                    "source": row.get("source", ""),
                    "source_note": row.get("source_note", ""),
                    "url": (
                        f"https://data.eastmoney.com/report/zw/stock.jshtml?encodeUrl={row.get('encode_url', '')}"
                        if row.get("encode_url")
                        else ""
                    ),
                }
            )

        has_local_report = any((row.get("source") == "local_derived") for row in report_rows)
        return {
            "code": context.code,
            "name": summary.stock_name or context.name,
            "industry": context.industry,
            "sector": context.sector,
            "quote_source": context.source,
            "price": current_price,
            "pe_ttm": pe_ttm,
            "pb_ratio": context.pb_ratio,
            "roe": context.roe,
            "market_cap": context.market_cap,
            "circulating_cap": context.circulating_cap,
            "analyst_count": summary.report_count,
            "latest_report_date": summary.latest_report_date,
            "latest_rating": summary.latest_rating,
            "latest_org": summary.latest_org,
            "report_count": summary.report_count,
            "report_source": "local_derived" if has_local_report else "analyst_consensus",
            "report_source_note": "本地日线趋势、波动率和AI信号推导" if has_local_report else "东方财富研报共识",
            "current_year_eps": summary.forecast_this_year_eps,
            "next_year_eps": summary.forecast_next_year_eps,
            "next_two_year_eps": summary.forecast_next_two_year_eps,
            "current_year_pe": summary.forecast_this_year_pe,
            "next_year_pe": summary.forecast_next_year_pe,
            "next_two_year_pe": summary.forecast_next_two_year_pe,
            "growth_this_year_pct": growth_this_year_pct,
            "growth_next_year_pct": growth_next_year_pct,
            "growth_next_two_year_pct": growth_next_two_year_pct,
            "peg_this_year": peg_this_year,
            "peg_next_year": peg_next_year,
            "peg_next_two_year": peg_next_two_year,
            "valuation_bucket": self._valuation_bucket(growth_next_year_pct, peg_next_year),
            "target_price": target_price,
            "upside_pct": upside_pct,
            "consensus_label": summary.consensus_label,
            "reports": report_rows,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _persist_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        has_local_report = any((row.get("source") == "local_derived") for row in snapshot.get("reports", []))
        source = "local_derived" if has_local_report else getattr(self.adapter, "SOURCE_NAME", "astock")
        source_version = "stock_daily+signal+momentum" if has_local_report else getattr(self.adapter, "SOURCE_VERSION", "unknown")
        enriched = dict(snapshot)
        enriched.update(
            {
                "source": source,
                "source_version": source_version,
                "quality_status": "ok",
            }
        )
        try:
            self.storage.save_data_source_version(
                source,
                source_version,
                active=True,
                metadata={"adapter": self.adapter.__class__.__name__, "domain": "valuation"},
            )
            self.storage.save_data_snapshot(
                code=str(enriched.get("code") or ""),
                domain="valuation",
                source=source,
                source_version=source_version,
                payload=enriched,
                quality_status="ok",
            )
            latest = self.storage.get_latest_data_snapshot(str(enriched.get("code") or ""), "valuation")
            if latest:
                enriched["snapshot_at"] = latest.get("created_at")
                enriched["payload_hash"] = latest.get("payload_hash")
        except Exception as exc:
            logger.debug(f"保存估值快照台账失败 {enriched.get('code')}: {exc}")
            latest = self.storage.get_latest_data_snapshot(str(enriched.get("code") or ""), "valuation")
            if latest:
                enriched.update(
                    {
                        "source": latest.get("source") or source,
                        "source_version": latest.get("source_version") or source_version,
                        "quality_status": latest.get("quality_status") or "unknown",
                        "snapshot_at": latest.get("created_at"),
                        "payload_hash": latest.get("payload_hash"),
                    }
                )
        return enriched

    async def get_valuation_snapshot(self, code: str, report_limit: int = 8) -> dict[str, Any]:
        return await asyncio.to_thread(self.build_snapshot, code, report_limit)

    def _load_valuation_payload(self, code: str, report_limit: int) -> dict[str, Any]:
        try:
            payload = self.adapter.get_valuation_snapshot(code, report_limit=max(report_limit, 8))
            if inspect.isawaitable(payload):
                return asyncio.run(payload)
            if isinstance(payload, dict):
                return payload
            return {}
        except RuntimeError:
            summary = self.adapter.build_summary(code, page_size=max(report_limit, 8))
            if summary is None:
                return {}
            return {
                "code": summary.code,
                "stock_name": summary.stock_name,
                "report_count": summary.report_count,
                "latest_report_date": summary.latest_report_date,
                "latest_rating": summary.latest_rating,
                "latest_org": summary.latest_org,
                "target_price": summary.target_price,
                "actual_last_year_eps": summary.actual_last_year_eps,
                "forecast_this_year_eps": summary.forecast_this_year_eps,
                "forecast_next_year_eps": summary.forecast_next_year_eps,
                "forecast_next_two_year_eps": summary.forecast_next_two_year_eps,
                "forecast_this_year_pe": summary.forecast_this_year_pe,
                "forecast_next_year_pe": summary.forecast_next_year_pe,
                "forecast_next_two_year_pe": summary.forecast_next_two_year_pe,
                "growth_this_year_pct": summary.growth_this_year_pct,
                "growth_next_year_pct": summary.growth_next_year_pct,
                "growth_next_two_year_pct": summary.growth_next_two_year_pct,
                "consensus_label": summary.consensus_label,
                "reports": summary.reports,
            }

    def _summary_from_payload(self, payload: dict[str, Any]) -> ForecastSummary | None:
        if not payload:
            return None
        try:
            return ForecastSummary(
                code=str(payload.get("code") or ""),
                stock_name=str(payload.get("stock_name") or ""),
                report_count=int(payload.get("report_count") or 0),
                latest_report_date=str(payload.get("latest_report_date") or ""),
                latest_rating=str(payload.get("latest_rating") or ""),
                latest_org=str(payload.get("latest_org") or ""),
                target_price=payload.get("target_price"),
                actual_last_year_eps=payload.get("actual_last_year_eps"),
                forecast_this_year_eps=payload.get("forecast_this_year_eps"),
                forecast_next_year_eps=payload.get("forecast_next_year_eps"),
                forecast_next_two_year_eps=payload.get("forecast_next_two_year_eps"),
                forecast_this_year_pe=payload.get("forecast_this_year_pe"),
                forecast_next_year_pe=payload.get("forecast_next_year_pe"),
                forecast_next_two_year_pe=payload.get("forecast_next_two_year_pe"),
                growth_this_year_pct=payload.get("growth_this_year_pct"),
                growth_next_year_pct=payload.get("growth_next_year_pct"),
                growth_next_two_year_pct=payload.get("growth_next_two_year_pct"),
                consensus_label=str(payload.get("consensus_label") or ""),
                reports=list(payload.get("reports") or []),
            )
        except Exception:
            return None
