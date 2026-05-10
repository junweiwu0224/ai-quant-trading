"""条件选股引擎

基于东方财富行情 API 实现全市场股票筛选。
支持 gt/lt/gte/lte/between/in 运算符。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from data.collector.http_client import fetch_json

# ── 东方财富字段映射 ──

_FIELD_MAP = {
    "code": "f12",
    "name": "f14",
    "price": "f2",
    "change_pct": "f3",
    "volume": "f5",
    "amount": "f6",
    "amplitude": "f7",
    "turnover_rate": "f8",
    "pe_ratio": "f9",
    "high": "f15",
    "low": "f16",
    "open": "f17",
    "market_cap": "f20",
    "circulating_cap": "f21",
    "pb_ratio": "f23",
    "industry": "f100",
    "volume_ratio": "f50",
}

# 反向映射：API 字段 → 业务字段
_REVERSE_MAP = {v: k for k, v in _FIELD_MAP.items()}

# 需要除以100的字段（API 返回值放大了100倍）
# 注意：f3/f7/f8 已经是百分比，f9/f23 已经是实际比率，无需再除
_DIV100_FIELDS: set[str] = set()

# 需要除以1e8的字段（市值单位：元→亿元）
_DIV1E8_FIELDS = {"market_cap", "circulating_cap"}


@dataclass(frozen=True)
class Filter:
    """单个筛选条件"""
    field: str
    op: str  # gt, lt, gte, lte, between, in
    value: Any

    def match(self, stock: dict) -> bool:
        val = stock.get(self.field)
        if val is None:
            # 数值比较操作：None 视为 0（停牌/缺失数据的股票仍可参与筛选）
            if self.op in ("gt", "lt", "gte", "lte", "between"):
                val = 0
            else:
                return False

        if self.op == "gt":
            return val > self.value
        elif self.op == "lt":
            return val < self.value
        elif self.op == "gte":
            return val >= self.value
        elif self.op == "lte":
            return val <= self.value
        elif self.op == "between":
            lo, hi = self.value
            return lo <= val <= hi
        elif self.op == "in":
            return val in self.value
        return False


# ── 预设策略 ──

PRESETS: dict[str, dict] = {
    "低估蓝筹": {
        "desc": "PE<20、PB<3、市值>200亿的价值股",
        "filters": [
            {"field": "pe_ratio", "op": "between", "value": [0, 20]},
            {"field": "pb_ratio", "op": "between", "value": [0, 3]},
            {"field": "market_cap", "op": "gt", "value": 200},
        ],
    },
    "放量突破": {
        "desc": "涨幅>3%、换手率>3%、振幅>4%的强势股",
        "filters": [
            {"field": "change_pct", "op": "gt", "value": 3},
            {"field": "turnover_rate", "op": "gt", "value": 3},
            {"field": "amplitude", "op": "gt", "value": 4},
        ],
    },
    "超跌反弹": {
        "desc": "跌幅>5%、PE<30、市值>50亿的超跌股",
        "filters": [
            {"field": "change_pct", "op": "lt", "value": -5},
            {"field": "pe_ratio", "op": "between", "value": [0, 30]},
            {"field": "market_cap", "op": "gt", "value": 50},
        ],
    },
    "高换手活跃": {
        "desc": "换手率>5%、振幅>3%、成交额>5亿的活跃股",
        "filters": [
            {"field": "turnover_rate", "op": "gt", "value": 5},
            {"field": "amplitude", "op": "gt", "value": 3},
            {"field": "amount", "op": "gt", "value": 5},
        ],
    },
    "小盘成长": {
        "desc": "市值<100亿、PE<50、涨幅>0%的小盘股",
        "filters": [
            {"field": "market_cap", "op": "between", "value": [10, 100]},
            {"field": "pe_ratio", "op": "between", "value": [0, 50]},
            {"field": "change_pct", "op": "gt", "value": 0},
        ],
    },
    "涨停潜力": {
        "desc": "涨幅>7%、换手率>5%、振幅>5%的涨停潜力股",
        "filters": [
            {"field": "change_pct", "op": "gt", "value": 7},
            {"field": "turnover_rate", "op": "gt", "value": 5},
            {"field": "amplitude", "op": "gt", "value": 5},
        ],
    },
}


_market_cache: list[dict] = []
_market_cache_ts: float = 0
_MARKET_CACHE_TTL = 60  # 60 秒缓存


def _fetch_market_stocks(max_pages: int = 60) -> list[dict]:
    """从东方财富 API 获取全市场股票行情

    API 限制每页最多 100 条，自动分页获取，结果缓存 60 秒。
    """
    global _market_cache, _market_cache_ts
    import time
    now = time.time()
    if _market_cache and (now - _market_cache_ts) < _MARKET_CACHE_TTL:
        return _market_cache

    # 移除 f50(volume_ratio)：该 API 返回的是原始成交量而非比率
    field_map = {k: v for k, v in _FIELD_MAP.items() if v != "f50"}
    fields = ",".join(field_map.values())
    reverse_map = {v: k for k, v in field_map.items()}
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
    page_size = 100  # API 硬限制

    all_stocks = []
    for pn in range(1, max_pages + 1):
        url = (
            f"https://push2delay.eastmoney.com/api/qt/clist/get"
            f"?pn={pn}&pz={page_size}&po=1&np=1&fltt=2&invt=2"
            f"&fid=f3&fs={fs}&fields={fields}"
        )
        data = fetch_json(url, timeout=10)
        items = ((data.get("data") or {}).get("diff") or [])
        if not items:
            break

        for item in items:
            stock = {}
            for api_field, biz_field in reverse_map.items():
                raw = item.get(api_field)
                if raw is None or raw == "-":
                    stock[biz_field] = None
                    continue

                # code 保持为字符串
                if biz_field == "code":
                    stock[biz_field] = str(raw)
                    continue

                try:
                    val = float(raw)
                    if biz_field in _DIV100_FIELDS:
                        val = round(val / 100, 2)
                    elif biz_field in _DIV1E8_FIELDS:
                        val = round(val / 1e8, 2)
                    stock[biz_field] = val
                except (ValueError, TypeError):
                    stock[biz_field] = raw if isinstance(raw, str) else None

            all_stocks.append(stock)

        if len(items) < page_size:
            break

    _market_cache = all_stocks
    _market_cache_ts = time.time()
    return all_stocks


class StockScreener:
    """条件选股引擎"""

    def __init__(self):
        self._cache: list[dict] = []
        self._cache_ts: float = 0

    def screen(
        self,
        filters: list[dict],
        sort_by: str = "change_pct",
        sort_desc: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """执行条件选股

        Args:
            filters: 条件列表 [{"field": "xx", "op": "gt", "value": 10}, ...]
            sort_by: 排序字段
            sort_desc: 是否降序
            page: 页码（从1开始）
            page_size: 每页数量

        Returns:
            {total, page, page_size, stocks: [...]}
        """
        # 获取全市场数据
        stocks = _fetch_market_stocks()
        if not stocks:
            return {"total": 0, "page": page, "page_size": page_size, "stocks": []}

        # 应用过滤条件
        filter_objs = []
        for f in filters:
            try:
                filter_objs.append(Filter(
                    field=f["field"],
                    op=f["op"],
                    value=f["value"],
                ))
            except (KeyError, TypeError) as e:
                logger.warning(f"无效过滤条件: {f}, 错误: {e}")

        filtered = stocks
        for fo in filter_objs:
            filtered = [s for s in filtered if fo.match(s)]

        # 排序
        if sort_by in _FIELD_MAP:
            filtered.sort(
                key=lambda s: s.get(sort_by) if s.get(sort_by) is not None else float('-inf'),
                reverse=sort_desc,
            )

        # 分页
        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        page_stocks = filtered[start:end]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "stocks": page_stocks,
        }

    def get_presets(self) -> dict:
        """获取所有预设策略"""
        return PRESETS

    def get_fields(self) -> list[dict]:
        """获取所有可用字段"""
        return [
            {"field": "code", "label": "股票代码", "type": "string"},
            {"field": "name", "label": "股票名称", "type": "string"},
            {"field": "industry", "label": "所属行业", "type": "string"},
            {"field": "price", "label": "最新价(元)", "type": "number"},
            {"field": "change_pct", "label": "涨跌幅(%)", "type": "number"},
            {"field": "pe_ratio", "label": "市盈率(动态)", "type": "number"},
            {"field": "pb_ratio", "label": "市净率", "type": "number"},
            {"field": "market_cap", "label": "总市值(亿)", "type": "number"},
            {"field": "circulating_cap", "label": "流通市值(亿)", "type": "number"},
            {"field": "turnover_rate", "label": "换手率(%)", "type": "number"},
            {"field": "amplitude", "label": "振幅(%)", "type": "number"},
            {"field": "high", "label": "最高价", "type": "number"},
            {"field": "low", "label": "最低价", "type": "number"},
            {"field": "open", "label": "开盘价", "type": "number"},
            {"field": "amount", "label": "成交额(万)", "type": "number"},
        ]
