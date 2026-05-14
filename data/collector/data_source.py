"""数据源抽象层 — 统一接口定义

所有数据源（mootdx、腾讯、AKShare）实现此接口，
上层代码只依赖抽象，不依赖具体实现。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Quote:
    """标准化实时行情数据"""
    code: str
    name: str
    price: float | None
    open: float | None
    high: float | None
    low: float | None
    pre_close: float | None
    volume: float | None
    amount: float | None
    change_pct: float | None
    turnover_rate: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    market_cap: float | None = None
    bid1: float | None = None
    ask1: float | None = None
    bid1_vol: float | None = None
    ask1_vol: float | None = None
    bid2: float | None = None
    ask2: float | None = None
    bid2_vol: float | None = None
    ask2_vol: float | None = None
    bid3: float | None = None
    ask3: float | None = None
    bid3_vol: float | None = None
    ask3_vol: float | None = None
    bid4: float | None = None
    ask4: float | None = None
    bid4_vol: float | None = None
    ask4_vol: float | None = None
    bid5: float | None = None
    ask5: float | None = None
    bid5_vol: float | None = None
    ask5_vol: float | None = None


class DataSource(ABC):
    """数据源统一接口"""

    @abstractmethod
    async def get_realtime_quotes(self, codes: list[str]) -> list[Quote]:
        """批量获取实时行情"""
        ...

    @abstractmethod
    async def get_kline(self, code: str, frequency: int = 9,
                        start: int = 0, offset: int = 800) -> pd.DataFrame:
        """获取K线数据

        frequency: 1=1分钟, 5=5分钟, 15=15分钟, 30=30分钟,
                   60=60分钟, 9=日线, 10=周线, 11=月线
        """
        ...

    @abstractmethod
    async def get_minute(self, code: str) -> pd.DataFrame:
        """获取当日分时数据"""
        ...

    @abstractmethod
    async def get_finance(self, code: str) -> dict:
        """获取财务概况"""
        ...

    @abstractmethod
    async def get_xdxr(self, code: str) -> pd.DataFrame:
        """获取除权除息数据"""
        ...

    @abstractmethod
    async def get_f10(self, code: str, section: str | None = None) -> dict:
        """获取F10基本面数据"""
        ...
