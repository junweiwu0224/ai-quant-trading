"""SQLite 数据库存储层"""
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import Column, Date, Float, Integer, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config.settings import DB_PATH, DB_URL
from utils.db import get_connection

Base = declarative_base()


def _to_prefix_code(code: str) -> str:
    """统一代码格式为 sh/sz 前缀: 600519 → sh600519, 000001 → sz000001

    已有前缀的原样返回。指数代码 (000xxx/399xxx) 不加前缀。
    """
    if not code:
        return code
    if code[:2] in ("sh", "sz", "SH", "SZ"):
        return code.lower()
    # 纯数字：根据规则加前缀
    if code.startswith(("6", "9")):
        return f"sh{code}"
    if code.startswith(("0", "3")):
        return f"sz{code}"
    return code


def _to_plain_code(code: str) -> str:
    """去掉 sh/sz 前缀，统一为 6 位代码"""
    if not code:
        return code
    if code[:2] in ("sh", "sz", "SH", "SZ"):
        return code[2:]
    return code


def _normalize_storage_code(code: str) -> tuple[str | None, str | None]:
    """校验并规范化存储层股票代码，非法输入返回 (None, None)"""
    plain_code = _to_plain_code(str(code).strip())
    if len(plain_code) != 6 or not plain_code.isdigit():
        return None, None
    return _to_prefix_code(plain_code), plain_code


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
    adj_factor = Column(Float, default=1.0)  # 复权因子: 不复权价 / 前复权价

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
    status = Column(String(20), default="active")  # active/suspended/delisted/st


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
        from utils.db import create_sqlite_engine

        self._db_url = db_url
        self._db_path: Path | None = None

        if db_url == "sqlite:///:memory:":
            self._engine = create_engine(
                db_url,
                echo=False,
                connect_args={"check_same_thread": False},
            )
        else:
            if db_url.startswith("sqlite:///"):
                self._db_path = Path(db_url.removeprefix("sqlite:///"))
            else:
                self._db_path = Path("data/db/quant.db")
            self._engine = create_sqlite_engine(self._db_path)

        self._Session = sessionmaker(bind=self._engine)
        self.init_db()

    def init_db(self):
        """创建所有表"""
        if self._db_path is not None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self._engine)
        if self._db_path is not None:
            self._migrate_columns()
        logger.info(f"数据库初始化完成: {self._db_url}")

    def _migrate_columns(self):
        """增量迁移：为已有表添加新列"""
        conn = get_connection(self._db_path)
        try:
            cursor = conn.cursor()

            # alert_rules.webhook_url
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alert_rules'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(alert_rules)")
                cols = {row[1] for row in cursor.fetchall()}
                if "webhook_url" not in cols:
                    cursor.execute("ALTER TABLE alert_rules ADD COLUMN webhook_url TEXT DEFAULT ''")
                    logger.info("迁移: alert_rules 添加 webhook_url 列")

            # stock_daily.adj_factor
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_daily'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(stock_daily)")
                cols = {row[1] for row in cursor.fetchall()}
                if "adj_factor" not in cols:
                    cursor.execute("ALTER TABLE stock_daily ADD COLUMN adj_factor REAL DEFAULT 1.0")
                    logger.info("迁移: stock_daily 添加 adj_factor 列")

            # stock_info.status
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_info'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(stock_info)")
                cols = {row[1] for row in cursor.fetchall()}
                if "status" not in cols:
                    cursor.execute("ALTER TABLE stock_info ADD COLUMN status TEXT DEFAULT 'active'")
                    logger.info("迁移: stock_info 添加 status 列")

            conn.commit()
        except Exception as e:
            logger.warning(f"列迁移跳过: {e}")
        finally:
            conn.close()

    def _get_session(self) -> Session:
        return self._Session()

    def save_stock_daily(self, code: str, df: pd.DataFrame) -> int:
        """保存日K线数据，跳过已存在的记录"""
        if df.empty:
            return 0
        prefixed_code, plain_code = _normalize_storage_code(code)
        if not prefixed_code or not plain_code:
            return 0

        session = self._get_session()
        try:
            existing_rows = (
                session.query(StockDaily)
                .filter(StockDaily.code.in_([prefixed_code, plain_code]))
                .all()
            )
            canonical_dates = set()
            for row in existing_rows:
                if row.code != prefixed_code:
                    duplicate = (
                        session.query(StockDaily)
                        .filter(StockDaily.code == prefixed_code, StockDaily.date == row.date)
                        .first()
                    )
                    if duplicate:
                        session.delete(row)
                        continue
                    row.code = prefixed_code
                canonical_dates.add(row.date)

            new_rows = []
            for _, row in df.iterrows():
                row_date = pd.Timestamp(row["date"]).date()
                if row_date not in canonical_dates:
                    new_rows.append(
                        StockDaily(
                            code=prefixed_code,
                            date=row_date,
                            open=row.get("open"),
                            high=row.get("high"),
                            low=row.get("low"),
                            close=row.get("close"),
                            volume=row.get("volume"),
                            amount=row.get("amount"),
                            adj_factor=row.get("adj_factor", 1.0),
                        )
                    )

            if new_rows:
                session.add_all(new_rows)
            session.commit()
            if new_rows:
                logger.info(f"[{prefixed_code}] 写入 {len(new_rows)} 条日K数据")
            return len(new_rows)
        except Exception as e:
            session.rollback()
            logger.error(f"[{prefixed_code}] 保存日K数据失败: {e}")
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
                prefixed_code = _to_prefix_code(row["code"])
                plain_code = _to_plain_code(row["code"])
                existing_rows = (
                    session.query(StockInfo)
                    .filter(StockInfo.code.in_([prefixed_code, plain_code]))
                    .all()
                )
                existing = next((item for item in existing_rows if item.code == prefixed_code), None)
                if existing is None and existing_rows:
                    existing = existing_rows[0]
                    existing.code = prefixed_code
                if existing:
                    existing.name = row.get("name", existing.name)
                    existing.industry = row.get("industry", existing.industry)
                    existing.list_date = row.get("list_date", existing.list_date)
                    for duplicate in existing_rows:
                        if duplicate is existing:
                            continue
                        if not existing.name and duplicate.name:
                            existing.name = duplicate.name
                        if not existing.industry and duplicate.industry:
                            existing.industry = duplicate.industry
                        if not existing.list_date and duplicate.list_date:
                            existing.list_date = duplicate.list_date
                        session.delete(duplicate)
                else:
                    session.add(
                        StockInfo(
                            code=prefixed_code,
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
                prefixed_code = _to_prefix_code(code)
                plain_code = _to_plain_code(code)
                existing_rows = (
                    session.query(StockInfo)
                    .filter(StockInfo.code.in_([prefixed_code, plain_code]))
                    .all()
                )
                existing = next((row for row in existing_rows if row.code == prefixed_code), None)
                if existing is None and existing_rows:
                    existing = existing_rows[0]
                    existing.code = prefixed_code
                if existing:
                    existing.industry = industry
                    for duplicate in existing_rows:
                        if duplicate is existing:
                            continue
                        if not existing.name and duplicate.name:
                            existing.name = duplicate.name
                        if not existing.list_date and duplicate.list_date:
                            existing.list_date = duplicate.list_date
                        session.delete(duplicate)
                else:
                    session.add(StockInfo(code=prefixed_code, name="", industry=industry, list_date=""))
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
        prefixed_code = _to_prefix_code(code)
        plain_code = _to_plain_code(code)
        session = self._get_session()
        try:
            query = session.query(StockDaily).filter(StockDaily.code.in_([prefixed_code, plain_code]))
            if start_date:
                query = query.filter(StockDaily.date >= start_date)
            if end_date:
                query = query.filter(StockDaily.date <= end_date)
            rows = query.order_by(StockDaily.date, StockDaily.code.desc()).all()
            if not rows:
                return pd.DataFrame()

            rows_by_date: dict[date, StockDaily] = {}
            for row in rows:
                existing = rows_by_date.get(row.date)
                if existing is None or (existing.code != prefixed_code and row.code == prefixed_code):
                    rows_by_date[row.date] = row

            return pd.DataFrame(
                [
                    {
                        "code": plain_code,
                        "date": row_date,
                        "open": row.open,
                        "high": row.high,
                        "low": row.low,
                        "close": row.close,
                        "volume": row.volume,
                        "amount": row.amount,
                    }
                    for row_date, row in sorted(rows_by_date.items())
                ]
            )
        finally:
            session.close()

    def get_all_stock_codes(self) -> list[str]:
        """获取所有已存储的股票代码"""
        session = self._get_session()
        try:
            rows = session.query(StockInfo.code).all()
            codes = []
            seen = set()
            for row in rows:
                plain_code = _to_plain_code(row.code)
                if plain_code in seen:
                    continue
                seen.add(plain_code)
                codes.append(plain_code)
            return codes
        finally:
            session.close()

    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表（含名称、行业），返回 DataFrame"""
        session = self._get_session()
        try:
            rows = session.query(StockInfo).all()
            if not rows:
                return pd.DataFrame()

            info_map = {}
            for row in rows:
                plain_code = _to_plain_code(row.code)
                existing = info_map.get(plain_code)
                merged = {
                    "code": plain_code,
                    "name": row.name or "",
                    "industry": row.industry or "",
                }
                if existing is None:
                    info_map[plain_code] = merged
                    continue
                if not existing["name"] and merged["name"]:
                    existing["name"] = merged["name"]
                if not existing["industry"] and merged["industry"]:
                    existing["industry"] = merged["industry"]

            return pd.DataFrame(list(info_map.values()))
        finally:
            session.close()

    def get_latest_date(self, code: str) -> Optional[date]:
        """获取某只股票最新数据日期"""
        prefixed_code = _to_prefix_code(code)
        plain_code = _to_plain_code(code)
        session = self._get_session()
        try:
            result = (
                session.query(StockDaily.date)
                .filter(StockDaily.code.in_([prefixed_code, plain_code]))
                .order_by(StockDaily.date.desc())
                .first()
            )
            return result[0] if result else None
        finally:
            session.close()

    # ── 自选股管理 ──

    def add_to_watchlist(self, code: str) -> bool:
        """添加自选股，返回是否新增（False=已存在）"""
        prefixed_code, plain_code = _normalize_storage_code(code)
        if not prefixed_code or not plain_code:
            return False
        session = self._get_session()
        try:
            existing_rows = (
                session.query(UserWatchlist)
                .filter(UserWatchlist.code.in_([prefixed_code, plain_code]))
                .all()
            )
            existing = next((row for row in existing_rows if row.code == prefixed_code), None)
            if existing is None and existing_rows:
                existing = existing_rows[0]
                existing.code = prefixed_code
            if existing:
                for duplicate in existing_rows:
                    if duplicate is existing:
                        continue
                    session.delete(duplicate)
                session.commit()
                return False
            session.add(UserWatchlist(code=prefixed_code, added_at=str(pd.Timestamp.now())))
            session.commit()
            logger.info(f"自选股添加: {prefixed_code}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"添加自选股失败: {e}")
            raise
        finally:
            session.close()

    def remove_from_watchlist(self, code: str) -> bool:
        """删除自选股，返回是否存在"""
        prefixed_code = _to_prefix_code(code)
        plain_code = _to_plain_code(code)
        session = self._get_session()
        try:
            rows = (
                session.query(UserWatchlist)
                .filter(UserWatchlist.code.in_([prefixed_code, plain_code]))
                .all()
            )
            if not rows:
                return False
            for row in rows:
                session.delete(row)
            session.commit()
            logger.info(f"自选股删除: {prefixed_code}")
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
            rows = session.query(UserWatchlist.code).order_by(UserWatchlist.added_at).all()
            codes = []
            seen = set()
            for row in rows:
                plain_code = _to_plain_code(row.code)
                if plain_code in seen:
                    continue
                seen.add(plain_code)
                codes.append(plain_code)
            return codes
        finally:
            session.close()

    def get_watchlist_with_info(self) -> list[dict]:
        """获取自选股列表（含名称、行业、最新价、数据日期）"""
        session = self._get_session()
        try:
            rows = session.query(UserWatchlist.code).order_by(UserWatchlist.added_at).all()
            if not rows:
                return []

            ordered_codes = []
            seen_codes = set()
            for row in rows:
                plain_code = _to_plain_code(row.code)
                if plain_code in seen_codes:
                    continue
                seen_codes.add(plain_code)
                ordered_codes.append(plain_code)

            candidate_codes = set(ordered_codes) | {_to_prefix_code(code) for code in ordered_codes}
            info_rows = (
                session.query(StockInfo)
                .filter(StockInfo.code.in_(candidate_codes))
                .all()
            )
            info_map = {}
            for row in info_rows:
                plain_code = _to_plain_code(row.code)
                existing = info_map.get(plain_code)
                merged = {
                    "name": row.name or "",
                    "industry": row.industry or "",
                }
                if existing is None:
                    info_map[plain_code] = merged
                    continue
                if not existing["name"] and merged["name"]:
                    existing["name"] = merged["name"]
                if not existing["industry"] and merged["industry"]:
                    existing["industry"] = merged["industry"]

            latest_rows = (
                session.query(StockDaily.code, StockDaily.close, StockDaily.date)
                .filter(StockDaily.code.in_(candidate_codes))
                .order_by(StockDaily.date.desc())
                .all()
            )
            latest_prices = {}
            latest_prefixed = {}
            for row in latest_rows:
                plain_code = _to_plain_code(row.code)
                row_is_prefixed = row.code == _to_prefix_code(plain_code)
                existing_date = latest_prices.get(plain_code, {}).get("date")
                if existing_date is None or row.date > existing_date:
                    latest_prices[plain_code] = {"price": row.close, "date": row.date}
                    latest_prefixed[plain_code] = row_is_prefixed
                    continue
                if row.date == existing_date and row_is_prefixed and not latest_prefixed.get(plain_code, False):
                    latest_prices[plain_code] = {"price": row.close, "date": row.date}
                    latest_prefixed[plain_code] = True

            return [
                {
                    "code": plain_code,
                    "name": info_map.get(plain_code, {}).get("name", ""),
                    "industry": info_map.get(plain_code, {}).get("industry", ""),
                    "latest_price": latest_prices.get(plain_code, {}).get("price"),
                    "latest_date": str(latest_prices[plain_code]["date"]) if plain_code in latest_prices else None,
                }
                for plain_code in ordered_codes
            ]
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
        import json as _json
        session = self._get_session()
        try:
            r = session.query(Conversation).filter(Conversation.id == conv_id).first()
            if not r:
                return None
            return {"id": r.id, "title": r.title, "messages": _json.loads(r.messages_json), "created_at": r.created_at, "updated_at": r.updated_at}
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
