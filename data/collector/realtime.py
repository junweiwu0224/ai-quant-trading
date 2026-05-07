"""实时行情采集"""
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import akshare as ak
import pandas as pd
from loguru import logger

from config.settings import AKSHARE_RETRY_COUNT, AKSHARE_RETRY_DELAY


@dataclass(frozen=True)
class RealtimeQuote:
    """实时行情快照"""
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
    timestamp: datetime


class RealtimeCollector:
    """实时行情采集器"""

    def __init__(self):
        self._cache: dict[str, RealtimeQuote] = {}
        self._last_fetch: Optional[datetime] = None

    def _retry(self, func, *args, **kwargs):
        for attempt in range(1, AKSHARE_RETRY_COUNT + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"实时行情获取失败 (第{attempt}次): {e}")
                if attempt < AKSHARE_RETRY_COUNT:
                    time.sleep(AKSHARE_RETRY_DELAY * attempt)
                else:
                    raise

    def fetch_realtime(self, codes: Optional[list[str]] = None) -> dict[str, RealtimeQuote]:
        """获取实时行情

        Args:
            codes: 股票代码列表，None 则获取全部

        Returns:
            {code: RealtimeQuote}
        """
        logger.info("获取实时行情...")
        df = self._retry(ak.stock_zh_a_spot_em)

        if df.empty:
            logger.warning("实时行情为空")
            return {}

        # 标准化列名
        col_map = {
            "代码": "code",
            "名称": "name",
            "最新价": "price",
            "今开": "open",
            "最高": "high",
            "最低": "low",
            "昨收": "pre_close",
            "成交量": "volume",
            "成交额": "amount",
            "涨跌幅": "change_pct",
        }
        df = df.rename(columns=col_map)

        # 过滤指定股票
        if codes:
            df = df[df["code"].isin(codes)]

        now = datetime.now()
        quotes = {}
        for _, row in df.iterrows():
            try:
                price = float(row["price"]) if pd.notna(row["price"]) else 0.0
                if price <= 0:
                    continue

                quote = RealtimeQuote(
                    code=str(row["code"]),
                    name=str(row["name"]),
                    price=price,
                    open=float(row.get("open", 0) or 0),
                    high=float(row.get("high", 0) or 0),
                    low=float(row.get("low", 0) or 0),
                    pre_close=float(row.get("pre_close", 0) or 0),
                    volume=float(row.get("volume", 0) or 0),
                    amount=float(row.get("amount", 0) or 0),
                    change_pct=float(row.get("change_pct", 0) or 0),
                    timestamp=now,
                )
                quotes[quote.code] = quote
            except (ValueError, TypeError) as e:
                logger.debug(f"解析行情数据失败 [{row.get('code', '?')}]: {e}")
                continue

        self._cache = quotes
        self._last_fetch = now
        logger.info(f"获取到 {len(quotes)} 只股票实时行情")
        return quotes

    def get_quote(self, code: str) -> Optional[RealtimeQuote]:
        """获取单只股票行情（优先缓存）"""
        return self._cache.get(code)

    def get_prices(self, codes: Optional[list[str]] = None) -> dict[str, float]:
        """获取价格字典 {code: price}"""
        if codes:
            return {c: q.price for c, q in self._cache.items() if c in codes}
        return {c: q.price for c, q in self._cache.items()}

    @property
    def last_fetch_time(self) -> Optional[datetime]:
        return self._last_fetch

    @property
    def cached_quotes(self) -> dict[str, RealtimeQuote]:
        return dict(self._cache)
