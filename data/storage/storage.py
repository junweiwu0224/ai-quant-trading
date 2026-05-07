"""SQLite 数据库存储层"""
from datetime import date
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import Column, Date, Float, Integer, String, UniqueConstraint, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config.settings import DB_DIR, DB_PATH, DB_URL

Base = declarative_base()


class StockDaily(Base):
    """日K线数据表"""
    __tablename__ = "stock_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    amount = Column(Float)

    __table_args__ = (
        UniqueConstraint("code", "date", name="uq_stock_daily_code_date"),
    )


class StockInfo(Base):
    """股票基本信息表"""
    __tablename__ = "stock_info"

    code = Column(String(10), primary_key=True)
    name = Column(String(50))
    industry = Column(String(50))
    list_date = Column(String(10))


class DataStorage:
    """数据存储管理"""

    def __init__(self, db_url: str = DB_URL):
        self._engine = create_engine(db_url, echo=False)
        self._Session = sessionmaker(bind=self._engine)

    def init_db(self):
        """创建所有表"""
        DB_DIR.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self._engine)
        logger.info(f"数据库初始化完成: {DB_PATH}")

    def _get_session(self) -> Session:
        return self._Session()

    def save_stock_daily(self, code: str, df: pd.DataFrame) -> int:
        """保存日K线数据，跳过已存在的记录"""
        if df.empty:
            return 0

        session = self._get_session()
        try:
            existing = (
                session.query(StockDaily.date)
                .filter(StockDaily.code == code)
                .all()
            )
            existing_dates = {r.date for r in existing}

            new_rows = []
            for _, row in df.iterrows():
                row_date = pd.Timestamp(row["date"]).date()
                if row_date not in existing_dates:
                    new_rows.append(
                        StockDaily(
                            code=code,
                            date=row_date,
                            open=row.get("open"),
                            high=row.get("high"),
                            low=row.get("low"),
                            close=row.get("close"),
                            volume=row.get("volume"),
                            amount=row.get("amount"),
                        )
                    )

            if new_rows:
                session.add_all(new_rows)
                session.commit()
                logger.info(f"[{code}] 写入 {len(new_rows)} 条日K数据")
            return len(new_rows)
        except Exception as e:
            session.rollback()
            logger.error(f"[{code}] 保存日K数据失败: {e}")
            raise
        finally:
            session.close()

    def save_stock_info(self, df: pd.DataFrame) -> int:
        """保存股票基本信息，存在则更新"""
        if df.empty:
            return 0

        session = self._get_session()
        try:
            count = 0
            for _, row in df.iterrows():
                code = row["code"]
                existing = session.get(StockInfo, code)
                if existing:
                    existing.name = row.get("name", existing.name)
                    existing.industry = row.get("industry", existing.industry)
                    existing.list_date = row.get("list_date", existing.list_date)
                else:
                    session.add(
                        StockInfo(
                            code=code,
                            name=row.get("name"),
                            industry=row.get("industry"),
                            list_date=row.get("list_date"),
                        )
                    )
                count += 1
            session.commit()
            logger.info(f"写入 {count} 条股票信息")
            return count
        except Exception as e:
            session.rollback()
            logger.error(f"保存股票信息失败: {e}")
            raise
        finally:
            session.close()

    def get_stock_daily(
        self,
        code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """查询日K线数据，返回 DataFrame"""
        session = self._get_session()
        try:
            query = session.query(StockDaily).filter(StockDaily.code == code)
            if start_date:
                query = query.filter(StockDaily.date >= start_date)
            if end_date:
                query = query.filter(StockDaily.date <= end_date)
            query = query.order_by(StockDaily.date)

            rows = query.all()
            if not rows:
                return pd.DataFrame()

            return pd.DataFrame(
                [
                    {
                        "code": r.code,
                        "date": r.date,
                        "open": r.open,
                        "high": r.high,
                        "low": r.low,
                        "close": r.close,
                        "volume": r.volume,
                        "amount": r.amount,
                    }
                    for r in rows
                ]
            )
        finally:
            session.close()

    def get_all_stock_codes(self) -> list[str]:
        """获取所有已存储的股票代码"""
        session = self._get_session()
        try:
            rows = session.query(StockInfo.code).all()
            return [r.code for r in rows]
        finally:
            session.close()

    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表（含名称、行业），返回 DataFrame"""
        session = self._get_session()
        try:
            rows = session.query(StockInfo).all()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(
                [
                    {
                        "code": r.code,
                        "name": r.name or "",
                        "industry": r.industry or "",
                    }
                    for r in rows
                ]
            )
        finally:
            session.close()

    def get_latest_date(self, code: str) -> Optional[date]:
        """获取某只股票最新数据日期"""
        session = self._get_session()
        try:
            result = (
                session.query(StockDaily.date)
                .filter(StockDaily.code == code)
                .order_by(StockDaily.date.desc())
                .first()
            )
            return result[0] if result else None
        finally:
            session.close()
