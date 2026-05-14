"""Tick 数据存储

提供 Tick 级数据的 SQLite 存储和查询。
当前为骨架实现，支持：
- tick_data 表（逐笔成交）
- 1m_bars 表（1分钟 K 线）
- 批量写入 / 按时间范围查询 / 聚合查询
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import Column, DateTime, Float, Integer, String, Index
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config.settings import DB_PATH
from utils.db import create_sqlite_engine

Base = declarative_base()


class TickRecord(Base):
    """逐笔成交记录"""
    __tablename__ = "tick_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)
    datetime = Column(DateTime, nullable=False, index=True)
    price = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)
    amount = Column(Float, default=0.0)
    bid_price = Column(Float, default=0.0)
    ask_price = Column(Float, default=0.0)
    bid_volume = Column(Integer, default=0)
    ask_volume = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_tick_code_dt", "code", "datetime"),
    )


class MinuteBarRecord(Base):
    """1分钟 K 线记录"""
    __tablename__ = "minute_bars"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)
    datetime = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)
    amount = Column(Float, default=0.0)

    __table_args__ = (
        Index("ix_minute_code_dt", "code", "datetime"),
    )


class TickStorage:
    """Tick 数据存储"""

    def __init__(self, db_path: Optional[str] = None):
        path = db_path or str(DB_PATH)
        self._engine = create_sqlite_engine(path)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)

    def save_ticks(self, code: str, ticks: list[dict]) -> int:
        """批量保存 Tick 数据

        Args:
            code: 股票代码
            ticks: Tick 字典列表，每项需包含 datetime/price/volume

        Returns:
            写入条数
        """
        if not ticks:
            return 0

        session: Session = self._session_factory()
        try:
            records = [
                TickRecord(
                    code=code,
                    datetime=t["datetime"],
                    price=t["price"],
                    volume=t["volume"],
                    amount=t.get("amount", 0),
                    bid_price=t.get("bid_price", 0),
                    ask_price=t.get("ask_price", 0),
                    bid_volume=t.get("bid_volume", 0),
                    ask_volume=t.get("ask_volume", 0),
                )
                for t in ticks
            ]
            session.add_all(records)
            session.commit()
            logger.info(f"[TickStorage] 保存 {len(records)} 条 Tick: {code}")
            return len(records)
        except Exception as e:
            session.rollback()
            logger.error(f"[TickStorage] 保存 Tick 失败: {e}")
            return 0
        finally:
            session.close()

    def save_minute_bars(self, code: str, bars: list[dict]) -> int:
        """批量保存分钟 K 线

        Args:
            code: 股票代码
            bars: K 线字典列表

        Returns:
            写入条数
        """
        if not bars:
            return 0

        session: Session = self._session_factory()
        try:
            records = [
                MinuteBarRecord(
                    code=code,
                    datetime=b["datetime"],
                    open=b["open"],
                    high=b["high"],
                    low=b["low"],
                    close=b["close"],
                    volume=b["volume"],
                    amount=b.get("amount", 0),
                )
                for b in bars
            ]
            session.add_all(records)
            session.commit()
            logger.info(f"[TickStorage] 保存 {len(records)} 条分钟K线: {code}")
            return len(records)
        except Exception as e:
            session.rollback()
            logger.error(f"[TickStorage] 保存分钟K线失败: {e}")
            return 0
        finally:
            session.close()

    def get_ticks(
        self, code: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        """查询 Tick 数据

        Args:
            code: 股票代码
            start: 开始时间
            end: 结束时间

        Returns:
            DataFrame with columns: datetime, price, volume, amount, bid_price, ask_price
        """
        session: Session = self._session_factory()
        try:
            rows = (
                session.query(TickRecord)
                .filter(
                    TickRecord.code == code,
                    TickRecord.datetime >= start,
                    TickRecord.datetime <= end,
                )
                .order_by(TickRecord.datetime)
                .all()
            )
            if not rows:
                return pd.DataFrame()

            return pd.DataFrame([
                {
                    "datetime": r.datetime,
                    "price": r.price,
                    "volume": r.volume,
                    "amount": r.amount,
                    "bid_price": r.bid_price,
                    "ask_price": r.ask_price,
                }
                for r in rows
            ])
        finally:
            session.close()

    def get_minute_bars(
        self, code: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        """查询分钟 K 线

        Args:
            code: 股票代码
            start: 开始时间
            end: 结束时间

        Returns:
            DataFrame with columns: datetime, open, high, low, close, volume, amount
        """
        session: Session = self._session_factory()
        try:
            rows = (
                session.query(MinuteBarRecord)
                .filter(
                    MinuteBarRecord.code == code,
                    MinuteBarRecord.datetime >= start,
                    MinuteBarRecord.datetime <= end,
                )
                .order_by(MinuteBarRecord.datetime)
                .all()
            )
            if not rows:
                return pd.DataFrame()

            return pd.DataFrame([
                {
                    "datetime": r.datetime,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                    "amount": r.amount,
                }
                for r in rows
            ])
        finally:
            session.close()

    def get_tick_count(self, code: str) -> int:
        """获取某股票的 Tick 数据总量"""
        session: Session = self._session_factory()
        try:
            return session.query(TickRecord).filter(
                TickRecord.code == code
            ).count()
        finally:
            session.close()

    def get_minute_bar_count(self, code: str) -> int:
        """获取某股票的分钟 K 线数据总量"""
        session: Session = self._session_factory()
        try:
            return session.query(MinuteBarRecord).filter(
                MinuteBarRecord.code == code
            ).count()
        finally:
            session.close()

    def get_data_range(self, code: str) -> dict:
        """获取某股票的数据时间范围

        Returns:
            {"tick": {"start": ..., "end": ..., "count": ...},
             "minute": {"start": ..., "end": ..., "count": ...}}
        """
        session: Session = self._session_factory()
        try:
            result = {}

            # Tick 范围
            tick = session.query(
                TickRecord.datetime
            ).filter(TickRecord.code == code).order_by(TickRecord.datetime).first()
            tick_end = session.query(
                TickRecord.datetime
            ).filter(TickRecord.code == code).order_by(TickRecord.datetime.desc()).first()
            tick_count = session.query(TickRecord).filter(TickRecord.code == code).count()

            result["tick"] = {
                "start": tick[0].isoformat() if tick else None,
                "end": tick_end[0].isoformat() if tick_end else None,
                "count": tick_count,
            }

            # 分钟线范围
            minute = session.query(
                MinuteBarRecord.datetime
            ).filter(MinuteBarRecord.code == code).order_by(MinuteBarRecord.datetime).first()
            minute_end = session.query(
                MinuteBarRecord.datetime
            ).filter(MinuteBarRecord.code == code).order_by(MinuteBarRecord.datetime.desc()).first()
            minute_count = session.query(MinuteBarRecord).filter(
                MinuteBarRecord.code == code
            ).count()

            result["minute"] = {
                "start": minute[0].isoformat() if minute else None,
                "end": minute_end[0].isoformat() if minute_end else None,
                "count": minute_count,
            }

            return result
        finally:
            session.close()
