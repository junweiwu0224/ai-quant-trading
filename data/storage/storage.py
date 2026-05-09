"""SQLite 数据库存储层"""
from datetime import date
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import Column, Date, Float, Integer, String, Text, UniqueConstraint, create_engine, text
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


class UserWatchlist(Base):
    """用户自选股表"""
    __tablename__ = "user_watchlist"

    code = Column(String(10), primary_key=True)
    added_at = Column(String(30))


class StrategyVersion(Base):
    """策略版本表"""
    __tablename__ = "strategy_version"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(50), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    label = Column(String(100))
    description = Column(String(500))
    params = Column(String(2000))  # JSON string
    code = Column(String(10000))   # 策略代码
    created_at = Column(String(30))
    is_current = Column(Integer, default=1)  # 1=当前版本, 0=历史版本

    __table_args__ = (
        UniqueConstraint("strategy_name", "version", name="uq_strategy_version"),
    )


class BacktestRecord(Base):
    """回测记录表"""
    __tablename__ = "backtest_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(50), nullable=False, index=True)
    label = Column(String(100))
    codes = Column(String(500))  # JSON array string
    start_date = Column(String(10))
    end_date = Column(String(10))
    initial_cash = Column(Float)
    total_return = Column(Float)
    annual_return = Column(Float)
    max_drawdown = Column(Float)
    sharpe_ratio = Column(Float)
    win_rate = Column(Float)
    total_trades = Column(Integer)
    params = Column(String(2000))  # JSON string
    result_json = Column(String(50000))  # 完整结果JSON
    created_at = Column(String(30))


class ChartDrawing(Base):
    """K线图画线数据表"""
    __tablename__ = "chart_drawings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)
    overlay_name = Column(String(50), nullable=False)  # straightLine/horizontalStraightLine/fibonacciLine
    points_json = Column(Text, nullable=False)  # JSON: [{timestamp, value}, ...]
    styles_json = Column(Text)  # JSON: {line: {color, size, style}}
    created_at = Column(String(30))
    updated_at = Column(String(30))


class AlertRule(Base):
    """预警规则表"""
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)
    condition = Column(String(30), nullable=False)  # price_above, change_below, etc.
    threshold = Column(Float, nullable=False)
    enabled = Column(Integer, default=1)  # 1=启用, 0=禁用
    name = Column(String(100), default="")
    cooldown = Column(Integer, default=300)  # 冷却秒数
    webhook_url = Column(String(500), default="")  # Webhook 推送地址
    created_at = Column(String(30))


class Conversation(Base):
    """LLM 对话历史表"""
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True)  # UUID
    title = Column(String(200), default="新对话")
    messages_json = Column(Text, default="[]")  # JSON: [{role, content, timestamp}]
    created_at = Column(String(30))
    updated_at = Column(String(30))


class DataStorage:
    """数据存储管理"""

    def __init__(self, db_url: str = DB_URL):
        self._engine = create_engine(db_url, echo=False)
        self._Session = sessionmaker(bind=self._engine)
        self.init_db()

    def init_db(self):
        """创建所有表"""
        DB_DIR.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self._engine)
        self._migrate_columns()
        logger.info(f"数据库初始化完成: {DB_PATH}")

    def _migrate_columns(self):
        """增量迁移：为已有表添加新列"""
        import sqlite3
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            # alert_rules.webhook_url
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alert_rules'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(alert_rules)")
                cols = {row[1] for row in cursor.fetchall()}
                if "webhook_url" not in cols:
                    cursor.execute("ALTER TABLE alert_rules ADD COLUMN webhook_url TEXT DEFAULT ''")
                    logger.info("迁移: alert_rules 添加 webhook_url 列")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"列迁移跳过: {e}")

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

    def update_stock_industry(self, industry_map: dict[str, str]) -> int:
        """批量更新股票行业信息，industry_map: {code: industry}"""
        if not industry_map:
            return 0
        session = self._get_session()
        try:
            count = 0
            for code, industry in industry_map.items():
                existing = session.get(StockInfo, code)
                if existing:
                    existing.industry = industry
                    count += 1
                else:
                    session.add(StockInfo(code=code, name="", industry=industry, list_date=""))
                    count += 1
            session.commit()
            logger.info(f"更新 {count} 条行业数据")
            return count
        except Exception as e:
            session.rollback()
            logger.error(f"更新行业数据失败: {e}")
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

    # ── 自选股管理 ──

    def add_to_watchlist(self, code: str) -> bool:
        """添加自选股，返回是否新增（False=已存在）"""
        session = self._get_session()
        try:
            existing = session.get(UserWatchlist, code)
            if existing:
                return False
            session.add(UserWatchlist(code=code, added_at=str(pd.Timestamp.now())))
            session.commit()
            logger.info(f"自选股添加: {code}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"添加自选股失败: {e}")
            raise
        finally:
            session.close()

    def remove_from_watchlist(self, code: str) -> bool:
        """删除自选股，返回是否存在"""
        session = self._get_session()
        try:
            row = session.get(UserWatchlist, code)
            if not row:
                return False
            session.delete(row)
            session.commit()
            logger.info(f"自选股删除: {code}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"删除自选股失败: {e}")
            raise
        finally:
            session.close()

    def get_watchlist(self) -> list[str]:
        """获取自选股代码列表"""
        session = self._get_session()
        try:
            rows = session.query(UserWatchlist.code).all()
            return [r.code for r in rows]
        finally:
            session.close()

    def get_watchlist_with_info(self) -> list[dict]:
        """获取自选股列表（含名称、行业、最新价、数据日期）"""
        session = self._get_session()
        try:
            # 单次 JOIN 查询获取自选股 + 股票信息
            rows = (
                session.query(
                    UserWatchlist.code,
                    StockInfo.name,
                    StockInfo.industry,
                )
                .outerjoin(StockInfo, UserWatchlist.code == StockInfo.code)
                .all()
            )
            if not rows:
                return []

            # 批量获取最新价格（每个 code 一次查询，但避免了 N*2 次）
            codes = [r.code for r in rows]
            latest_prices = {}
            for code in codes:
                latest = (
                    session.query(StockDaily.close, StockDaily.date)
                    .filter(StockDaily.code == code)
                    .order_by(StockDaily.date.desc())
                    .first()
                )
                if latest:
                    latest_prices[code] = {"price": latest.close, "date": str(latest.date)}

            return [{
                "code": r.code,
                "name": r.name or "",
                "industry": r.industry or "",
                "latest_price": latest_prices.get(r.code, {}).get("price"),
                "latest_date": latest_prices.get(r.code, {}).get("date"),
            } for r in rows]
        finally:
            session.close()

    # ── 画线工具 CRUD ──

    def get_drawings(self, code: str) -> list[dict]:
        """获取指定股票的所有画线"""
        session = self._get_session()
        try:
            rows = session.query(ChartDrawing).filter(ChartDrawing.code == code).all()
            return [{
                "id": r.id,
                "code": r.code,
                "overlay_name": r.overlay_name,
                "points": r.points_json,
                "styles": r.styles_json,
                "created_at": r.created_at,
            } for r in rows]
        finally:
            session.close()

    def save_drawing(self, code: str, overlay_name: str, points_json: str,
                     styles_json: str = "", created_at: str = "") -> int:
        """保存一条画线"""
        session = self._get_session()
        try:
            drawing = ChartDrawing(
                code=code,
                overlay_name=overlay_name,
                points_json=points_json,
                styles_json=styles_json,
                created_at=created_at,
                updated_at=created_at,
            )
            session.add(drawing)
            session.commit()
            return drawing.id
        except Exception as e:
            session.rollback()
            logger.error(f"保存画线失败: {e}")
            raise
        finally:
            session.close()

    def delete_drawing(self, drawing_id: int) -> bool:
        """删除一条画线"""
        session = self._get_session()
        try:
            row = session.get(ChartDrawing, drawing_id)
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"删除画线失败: {e}")
            raise
        finally:
            session.close()

    def delete_all_drawings(self, code: str) -> int:
        """删除指定股票的所有画线"""
        session = self._get_session()
        try:
            count = session.query(ChartDrawing).filter(ChartDrawing.code == code).delete()
            session.commit()
            return count
        except Exception as e:
            session.rollback()
            logger.error(f"清空画线失败: {e}")
            raise
        finally:
            session.close()

    # ── 预警规则 CRUD ──

    def get_alert_rules(self, enabled_only: bool = False) -> list[dict]:
        """获取所有预警规则"""
        session = self._get_session()
        try:
            query = session.query(AlertRule)
            if enabled_only:
                query = query.filter(AlertRule.enabled == 1)
            rows = query.order_by(AlertRule.id.desc()).all()
            return [
                {
                    "id": r.id, "code": r.code, "condition": r.condition,
                    "threshold": r.threshold, "enabled": bool(r.enabled),
                    "name": r.name or "", "cooldown": r.cooldown,
                    "webhook_url": r.webhook_url or "",
                    "created_at": r.created_at or "",
                }
                for r in rows
            ]
        finally:
            session.close()

    def add_alert_rule(self, code: str, condition: str, threshold: float,
                       name: str = "", cooldown: int = 300, webhook_url: str = "") -> int:
        """添加预警规则，返回 ID"""
        from config.datetime_utils import now_beijing_iso
        session = self._get_session()
        try:
            rule = AlertRule(
                code=code, condition=condition, threshold=threshold,
                enabled=1, name=name, cooldown=cooldown, webhook_url=webhook_url,
                created_at=now_beijing_iso(),
            )
            session.add(rule)
            session.commit()
            return rule.id
        except Exception as e:
            session.rollback()
            logger.error(f"添加预警规则失败: {e}")
            raise
        finally:
            session.close()

    def update_alert_rule(self, rule_id: int, **kwargs) -> bool:
        """更新预警规则"""
        session = self._get_session()
        try:
            rule = session.query(AlertRule).filter(AlertRule.id == rule_id).first()
            if not rule:
                return False
            for key, val in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, val)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"更新预警规则失败: {e}")
            return False
        finally:
            session.close()

    def delete_alert_rule(self, rule_id: int) -> bool:
        """删除预警规则"""
        session = self._get_session()
        try:
            count = session.query(AlertRule).filter(AlertRule.id == rule_id).delete()
            session.commit()
            return count > 0
        except Exception as e:
            session.rollback()
            logger.error(f"删除预警规则失败: {e}")
            return False
        finally:
            session.close()

    # ── 对话历史 ──

    def list_conversations(self, limit: int = 50) -> list[dict]:
        """获取对话列表"""
        session = self._get_session()
        try:
            rows = session.query(Conversation).order_by(Conversation.updated_at.desc()).limit(limit).all()
            return [{"id": r.id, "title": r.title, "created_at": r.created_at, "updated_at": r.updated_at} for r in rows]
        finally:
            session.close()

    def get_conversation(self, conv_id: str) -> dict | None:
        """获取单个对话（含消息）"""
        session = self._get_session()
        try:
            r = session.query(Conversation).filter(Conversation.id == conv_id).first()
            if not r:
                return None
            return {"id": r.id, "title": r.title, "messages": json.loads(r.messages_json), "created_at": r.created_at, "updated_at": r.updated_at}
        finally:
            session.close()

    def save_conversation(self, conv_id: str, title: str, messages: list) -> None:
        """创建或更新对话"""
        import json as _json
        from datetime import datetime
        now = datetime.now().isoformat()
        session = self._get_session()
        try:
            existing = session.query(Conversation).filter(Conversation.id == conv_id).first()
            if existing:
                existing.title = title
                existing.messages_json = _json.dumps(messages, ensure_ascii=False)
                existing.updated_at = now
            else:
                session.add(Conversation(
                    id=conv_id, title=title,
                    messages_json=_json.dumps(messages, ensure_ascii=False),
                    created_at=now, updated_at=now,
                ))
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"保存对话失败: {e}")
        finally:
            session.close()

    def delete_conversation(self, conv_id: str) -> bool:
        """删除对话"""
        session = self._get_session()
        try:
            count = session.query(Conversation).filter(Conversation.id == conv_id).delete()
            session.commit()
            return count > 0
        except Exception as e:
            session.rollback()
            logger.error(f"删除对话失败: {e}")
            return False
        finally:
            session.close()
