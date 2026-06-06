"""SQLite 数据库存储层"""
import hashlib
import math
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from loguru import logger
from sqlalchemy import Column, Date, Float, Integer, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config.settings import DB_PATH, DB_URL
from utils.db import get_connection

Base = declarative_base()


def _to_prefix_code(code: str) -> str:
    """统一代码格式为交易所前缀: 600519 → sh600519, 000001 → sz000001

    已有前缀的原样返回。指数代码 (000xxx/399xxx) 不加前缀。
    """
    if not code:
        return code
    if code[:2] in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        return code.lower()
    # 纯数字：根据规则加前缀
    if code.startswith(("43", "83", "87", "88", "92")):
        return f"bj{code}"
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("0", "3", "9")):
        return f"sz{code}"
    return code


def _to_plain_code(code: str) -> str:
    """去掉交易所前缀，统一为 6 位代码"""
    if not code:
        return code
    if code[:2] in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        return code[2:]
    return code


def _normalize_storage_code(code: str) -> tuple[str | None, str | None]:
    """校验并规范化存储层股票代码，非法输入返回 (None, None)"""
    plain_code = _to_plain_code(str(code).strip())
    if len(plain_code) != 6 or not plain_code.isdigit():
        return None, None
    return _to_prefix_code(plain_code), plain_code


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _sanitize_json_value(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            return None
        integral_value = value.to_integral_value()
        if value == integral_value:
            try:
                return int(integral_value)
            except (TypeError, ValueError, OverflowError):
                return float(value)
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError):
            return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item") and not isinstance(value, (str, bytes, bytearray)):
        try:
            item = value.item()
        except Exception:
            item = value
        if item is not value:
            return _sanitize_json_value(item)
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key in sorted(value.keys(), key=lambda item: str(item)):
            sanitized[str(key)] = _sanitize_json_value(value[key])
        return sanitized
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, set):
        items = [_sanitize_json_value(item) for item in value]
        return sorted(items, key=lambda item: _json_stable_dumps(item))
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "__dict__"):
        return _sanitize_json_value(vars(value))
    return value if isinstance(value, (str, int, bool)) else str(value)


def _json_dumps(value) -> str:
    return json.dumps(
        _sanitize_json_value(value if value is not None else {}),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_stable_dumps(value) -> str:
    return json.dumps(
        _sanitize_json_value(value if value is not None else {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _payload_hash(payload) -> str:
    return hashlib.sha256(_json_stable_dumps(payload).encode("utf-8")).hexdigest()


def _json_loads(value: str | None, fallback=None):
    if not value:
        return {} if fallback is None else fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {} if fallback is None else fallback


def _normalize_ledger_code(code: str) -> str:
    raw_code = str(code or "").strip()
    plain_code = _to_plain_code(raw_code)
    if len(plain_code) == 6 and plain_code.isdigit():
        return plain_code
    return raw_code


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


class WorkspaceWatchlist(Base):
    """工作区自选股表"""
    __tablename__ = "workspace_watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(36), nullable=False, index=True)
    code = Column(String(10), nullable=False, index=True)
    added_at = Column(String(30))

    __table_args__ = (
        UniqueConstraint("workspace_id", "code", name="uq_workspace_watchlist_workspace_code"),
    )


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
    workspace_id = Column(String(36), index=True, default="")
    surface = Column(String(32), nullable=False, default="llm", index=True)
    title = Column(String(200), default="新对话")
    messages_json = Column(Text, default="[]")  # JSON: [{role, content, timestamp}]
    created_at = Column(String(30))
    updated_at = Column(String(30))


class DataSourceVersion(Base):
    """数据源版本表"""
    __tablename__ = "data_source_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False, index=True)
    version = Column(String(100), nullable=False)
    active = Column(Integer, default=1, index=True)
    metadata_json = Column("metadata", Text, default="{}")
    created_at = Column(String(30))
    updated_at = Column(String(30))

    __table_args__ = (
        UniqueConstraint("source", "version", name="uq_data_source_version"),
    )


class DataSnapshot(Base):
    """数据快照表"""
    __tablename__ = "data_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), nullable=False, index=True)
    domain = Column(String(50), nullable=False, index=True)
    source = Column(String(50), nullable=False, index=True)
    source_version = Column(String(100))
    payload_json = Column("payload", Text, nullable=False)
    payload_hash = Column(String(64), nullable=False, index=True)
    quality_status = Column(String(20), default="ok", index=True)
    created_at = Column(String(30), index=True)


class DataQualityRecord(Base):
    """数据质量记录表"""
    __tablename__ = "data_quality_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), nullable=False, index=True)
    domain = Column(String(50), nullable=False, index=True)
    check_name = Column(String(80), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    details_json = Column("details", Text, default="{}")
    diff_count = Column(Integer, default=0)
    created_at = Column(String(30), index=True)


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

            # user_watchlist.workspace_id + id
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_watchlist'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(user_watchlist)")
                cols = {row[1] for row in cursor.fetchall()}
                # 旧匿名表保留兼容；新工作区表用于登录用户。
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workspace_watchlist'")
            if not cursor.fetchone():
                cursor.execute(
                    """CREATE TABLE workspace_watchlist (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        workspace_id TEXT NOT NULL,
                        code TEXT NOT NULL,
                        added_at TEXT,
                        UNIQUE(workspace_id, code)
                    )"""
                )
                logger.info("迁移: 创建 workspace_watchlist 表")

            # conversations.workspace_id
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(conversations)")
                cols = {row[1] for row in cursor.fetchall()}
                if "workspace_id" not in cols:
                    cursor.execute("ALTER TABLE conversations ADD COLUMN workspace_id TEXT DEFAULT ''")
                    logger.info("迁移: conversations 添加 workspace_id 列")
                if "surface" not in cols:
                    cursor.execute("ALTER TABLE conversations ADD COLUMN surface TEXT DEFAULT 'llm'")
                    logger.info("迁移: conversations 添加 surface 列")
                cursor.execute("UPDATE conversations SET surface = 'llm' WHERE surface IS NULL OR surface = ''")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_conversations_surface ON conversations(surface)")

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='data_source_versions'")
            if not cursor.fetchone():
                cursor.execute(
                    """CREATE TABLE data_source_versions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source TEXT NOT NULL,
                        version TEXT NOT NULL,
                        active INTEGER DEFAULT 1,
                        metadata TEXT DEFAULT '{}',
                        created_at TEXT,
                        updated_at TEXT,
                        UNIQUE(source, version)
                    )"""
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_source_versions_source ON data_source_versions(source)")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_source_versions_active ON data_source_versions(active)")
                logger.info("迁移: 创建 data_source_versions 表")
            else:
                cursor.execute("PRAGMA table_info(data_source_versions)")
                cols = {row[1] for row in cursor.fetchall()}
                if "updated_at" not in cols:
                    cursor.execute("ALTER TABLE data_source_versions ADD COLUMN updated_at TEXT")
                    cursor.execute("UPDATE data_source_versions SET updated_at = created_at WHERE updated_at IS NULL")
                    logger.info("迁移: data_source_versions 添加 updated_at 列")

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='data_snapshots'")
            if not cursor.fetchone():
                cursor.execute(
                    """CREATE TABLE data_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT NOT NULL,
                        domain TEXT NOT NULL,
                        source TEXT NOT NULL,
                        source_version TEXT,
                        payload TEXT NOT NULL,
                        payload_hash TEXT NOT NULL DEFAULT '',
                        quality_status TEXT DEFAULT 'ok',
                        created_at TEXT
                    )"""
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_snapshots_code ON data_snapshots(code)")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_snapshots_domain ON data_snapshots(domain)")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_snapshots_source ON data_snapshots(source)")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_snapshots_payload_hash ON data_snapshots(payload_hash)")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_snapshots_created_at ON data_snapshots(created_at)")
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_data_snapshots_code_domain_created ON data_snapshots(code, domain, created_at)"
                )
                logger.info("迁移: 创建 data_snapshots 表")
            else:
                cursor.execute("PRAGMA table_info(data_snapshots)")
                cols = {row[1] for row in cursor.fetchall()}
                if "payload_hash" not in cols:
                    cursor.execute("ALTER TABLE data_snapshots ADD COLUMN payload_hash TEXT DEFAULT ''")
                    logger.info("迁移: data_snapshots 添加 payload_hash 列")
                cursor.execute(
                    "SELECT id, payload FROM data_snapshots WHERE payload_hash IS NULL OR payload_hash = ''"
                )
                for snapshot_id, payload_json in cursor.fetchall():
                    payload = _json_loads(payload_json)
                    cursor.execute(
                        "UPDATE data_snapshots SET payload_hash = ? WHERE id = ?",
                        (_payload_hash(payload), snapshot_id),
                    )
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_snapshots_payload_hash ON data_snapshots(payload_hash)")

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='data_quality_records'")
            if not cursor.fetchone():
                cursor.execute(
                    """CREATE TABLE data_quality_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT NOT NULL,
                        domain TEXT NOT NULL,
                        check_name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        details TEXT DEFAULT '{}',
                        diff_count INTEGER DEFAULT 0,
                        created_at TEXT
                    )"""
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_records_code ON data_quality_records(code)")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_records_domain ON data_quality_records(domain)")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_records_check_name ON data_quality_records(check_name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_records_status ON data_quality_records(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_records_created_at ON data_quality_records(created_at)")
                logger.info("迁移: 创建 data_quality_records 表")

            conn.commit()
        except Exception as e:
            logger.warning(f"列迁移跳过: {e}")
        finally:
            conn.close()

    def _get_session(self) -> Session:
        return self._Session()

    def save_stock_daily(self, code: str, df: pd.DataFrame, update_existing: bool = False) -> int:
        """保存日K线数据，默认跳过已存在记录，可选择更新已有日期。"""
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
            existing_by_date: dict[date, StockDaily] = {}
            for row in existing_rows:
                if row.code != prefixed_code:
                    duplicate = (
                        session.query(StockDaily)
                        .filter(StockDaily.code == prefixed_code, StockDaily.date == row.date)
                        .first()
                    )
                    if duplicate:
                        existing_by_date[row.date] = duplicate
                        session.delete(row)
                        continue
                    row.code = prefixed_code
                canonical_dates.add(row.date)
                existing_by_date[row.date] = row

            new_rows = []
            updated = 0
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
                    canonical_dates.add(row_date)
                elif update_existing:
                    existing = existing_by_date.get(row_date)
                    if existing is None:
                        continue
                    changed = False
                    for field in ("open", "high", "low", "close", "volume", "amount", "adj_factor"):
                        if field not in row:
                            continue
                        value = row.get(field)
                        if pd.isna(value):
                            continue
                        if field == "amount" and float(value or 0) == 0 and (existing.amount or 0) != 0:
                            continue
                        if getattr(existing, field) != value:
                            setattr(existing, field, value)
                            changed = True
                    if changed:
                        updated += 1

            if new_rows:
                session.add_all(new_rows)
            session.commit()
            if new_rows:
                logger.info(f"[{prefixed_code}] 写入 {len(new_rows)} 条日K数据")
            if updated:
                logger.info(f"[{prefixed_code}] 更新 {updated} 条日K数据")
            return len(new_rows) + updated
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

    def get_global_latest_date(self) -> Optional[date]:
        """获取全库日K最新数据日期"""
        session = self._get_session()
        try:
            result = (
                session.query(StockDaily.date)
                .order_by(StockDaily.date.desc())
                .first()
            )
            return result[0] if result else None
        finally:
            session.close()

    def get_stock_daily_coverage(self) -> dict[str, Any]:
        """返回 stock_daily 相对 stock_info 的覆盖情况。"""
        plain_info_expr = (
            "CASE WHEN lower(substr(code, 1, 2)) IN ('sh', 'sz', 'bj') "
            "THEN substr(code, 3) ELSE code END"
        )
        plain_daily_expr = (
            "CASE WHEN lower(substr(code, 1, 2)) IN ('sh', 'sz', 'bj') "
            "THEN substr(code, 3) ELSE code END"
        )
        sql = text(
            f"""
            WITH info AS (
                SELECT DISTINCT {plain_info_expr} AS plain_code
                FROM stock_info
                WHERE code IS NOT NULL AND code != ''
            ),
            daily AS (
                SELECT
                    {plain_daily_expr} AS plain_code,
                    MAX(date) AS latest_date,
                    COUNT(*) AS row_count
                FROM stock_daily
                WHERE close IS NOT NULL
                GROUP BY {plain_daily_expr}
            ),
            latest AS (
                SELECT MAX(latest_date) AS latest_date FROM daily
            )
            SELECT
                (SELECT COUNT(*) FROM info) AS stock_count,
                (SELECT COUNT(*) FROM daily) AS daily_covered,
                (SELECT latest_date FROM latest) AS latest_date,
                (
                    SELECT COUNT(*)
                    FROM daily, latest
                    WHERE daily.latest_date = latest.latest_date
                ) AS latest_date_covered,
                COALESCE((SELECT SUM(row_count) FROM daily), 0) AS row_count
            """
        )
        with self._engine.connect() as conn:
            row = conn.execute(sql).mappings().first() or {}
        stock_count = int(row.get("stock_count") or 0)
        daily_covered = int(row.get("daily_covered") or 0)
        latest_date_covered = int(row.get("latest_date_covered") or 0)
        return {
            "stock_count": stock_count,
            "daily_covered": daily_covered,
            "daily_missing": max(stock_count - daily_covered, 0),
            "coverage_pct": round(daily_covered / stock_count * 100, 2) if stock_count else None,
            "latest_date": str(row.get("latest_date") or "") or None,
            "latest_date_covered": latest_date_covered,
            "latest_date_coverage_pct": round(latest_date_covered / stock_count * 100, 2) if stock_count else None,
            "row_count": int(row.get("row_count") or 0),
        }

    def get_latest_market_rows(self, limit: int | None = None) -> list[dict[str, Any]]:
        """返回每只股票最新/上一交易日行情，用于本地市场雷达兜底。"""
        plain_expr = (
            "CASE WHEN lower(substr(code, 1, 2)) IN ('sh', 'sz', 'bj') "
            "THEN substr(code, 3) ELSE code END"
        )
        prefixed_expr = (
            "CASE "
            "WHEN l.plain_code LIKE '43%' OR l.plain_code LIKE '83%' OR l.plain_code LIKE '87%' "
            "OR l.plain_code LIKE '88%' OR l.plain_code LIKE '92%' THEN 'bj' || l.plain_code "
            "WHEN l.plain_code LIKE '6%' THEN 'sh' || l.plain_code "
            "ELSE 'sz' || l.plain_code END"
        )
        limit_sql = " LIMIT :limit" if limit else ""
        sql = text(
            f"""
            WITH normalized AS (
                SELECT
                    {plain_expr} AS plain_code,
                    CASE WHEN lower(substr(code, 1, 2)) IN ('sh', 'sz', 'bj') THEN 1 ELSE 0 END AS pref_score,
                    date, open, high, low, close, volume, amount
                FROM stock_daily
                WHERE close IS NOT NULL
            ),
            deduped AS (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY plain_code, date
                        ORDER BY pref_score DESC
                    ) AS date_rn
                FROM normalized
            ),
            ranked AS (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY plain_code
                        ORDER BY date DESC
                    ) AS rn
                FROM deduped
                WHERE date_rn = 1
            ),
            latest AS (
                SELECT * FROM ranked WHERE rn = 1
            ),
            previous AS (
                SELECT * FROM ranked WHERE rn = 2
            )
            SELECT
                l.plain_code AS code,
                COALESCE(si_pref.name, si_plain.name, '') AS name,
                COALESCE(si_pref.industry, si_plain.industry, '') AS industry,
                l.date AS date,
                l.open AS open,
                l.high AS high,
                l.low AS low,
                l.close AS close,
                l.volume AS volume,
                l.amount AS amount,
                p.date AS prev_date,
                p.close AS prev_close
            FROM latest l
            LEFT JOIN previous p ON p.plain_code = l.plain_code
            LEFT JOIN stock_info si_pref ON si_pref.code = {prefixed_expr}
            LEFT JOIN stock_info si_plain ON si_plain.code = l.plain_code
            ORDER BY l.date DESC, l.plain_code
            {limit_sql}
            """
        )
        params = {"limit": int(limit)} if limit else {}
        with self._engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [dict(row) for row in rows]

    def get_latest_market_rows_for_codes(self, codes: list[str]) -> list[dict[str, Any]]:
        """返回指定股票最新/上一交易日行情，避免小列表场景扫描全市场。"""
        plain_codes: list[str] = []
        seen: set[str] = set()
        storage_codes: list[str] = []
        for code in codes or []:
            plain = _to_plain_code(code)
            if plain and plain not in seen:
                seen.add(plain)
                plain_codes.append(plain)
                for candidate in {plain, _to_prefix_code(plain)}:
                    if candidate:
                        storage_codes.append(candidate)
        if not plain_codes:
            return []

        plain_expr = (
            "CASE WHEN lower(substr(code, 1, 2)) IN ('sh', 'sz', 'bj') "
            "THEN substr(code, 3) ELSE code END"
        )
        prefixed_expr = (
            "CASE "
            "WHEN l.plain_code LIKE '43%' OR l.plain_code LIKE '83%' OR l.plain_code LIKE '87%' "
            "OR l.plain_code LIKE '88%' OR l.plain_code LIKE '92%' THEN 'bj' || l.plain_code "
            "WHEN l.plain_code LIKE '6%' THEN 'sh' || l.plain_code "
            "ELSE 'sz' || l.plain_code END"
        )
        placeholders = ", ".join(f":code_{index}" for index in range(len(storage_codes)))
        params = {f"code_{index}": code for index, code in enumerate(storage_codes)}
        sql = text(
            f"""
            WITH normalized AS (
                SELECT
                    {plain_expr} AS plain_code,
                    CASE WHEN lower(substr(sd.code, 1, 2)) IN ('sh', 'sz', 'bj') THEN 1 ELSE 0 END AS pref_score,
                    sd.date, sd.open, sd.high, sd.low, sd.close, sd.volume, sd.amount
                FROM stock_daily sd
                WHERE sd.close IS NOT NULL
                  AND sd.code IN ({placeholders})
            ),
            deduped AS (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY plain_code, date
                        ORDER BY pref_score DESC
                    ) AS date_rn
                FROM normalized
            ),
            ranked AS (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY plain_code
                        ORDER BY date DESC
                    ) AS rn
                FROM deduped
                WHERE date_rn = 1
            ),
            latest AS (
                SELECT * FROM ranked WHERE rn = 1
            ),
            previous AS (
                SELECT * FROM ranked WHERE rn = 2
            )
            SELECT
                l.plain_code AS code,
                COALESCE(si_pref.name, si_plain.name, '') AS name,
                COALESCE(si_pref.industry, si_plain.industry, '') AS industry,
                l.date AS date,
                l.open AS open,
                l.high AS high,
                l.low AS low,
                l.close AS close,
                l.volume AS volume,
                l.amount AS amount,
                p.date AS prev_date,
                p.close AS prev_close
            FROM latest l
            LEFT JOIN previous p ON p.plain_code = l.plain_code
            LEFT JOIN stock_info si_pref ON si_pref.code = {prefixed_expr}
            LEFT JOIN stock_info si_plain ON si_plain.code = l.plain_code
            ORDER BY l.plain_code
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [dict(row) for row in rows]

    def get_market_breadth(self) -> dict[str, Any]:
        """返回本地 stock_daily 覆盖池的最新交易日涨跌广度。"""
        plain_daily_expr = (
            "CASE WHEN lower(substr(sd.code, 1, 2)) IN ('sh', 'sz', 'bj') "
            "THEN substr(sd.code, 3) ELSE sd.code END"
        )
        plain_info_expr = (
            "CASE WHEN lower(substr(code, 1, 2)) IN ('sh', 'sz', 'bj') "
            "THEN substr(code, 3) ELSE code END"
        )
        sql = text(
            f"""
            WITH latest_day AS (
                SELECT MAX(date) AS date FROM stock_daily WHERE close IS NOT NULL
            ),
            previous_day AS (
                SELECT MAX(sd.date) AS date
                FROM stock_daily sd, latest_day
                WHERE sd.close IS NOT NULL AND sd.date < latest_day.date
            ),
            info AS (
                SELECT COUNT(DISTINCT {plain_info_expr}) AS stock_count
                FROM stock_info
                WHERE code IS NOT NULL AND code != ''
            ),
            latest_raw AS (
                SELECT
                    {plain_daily_expr} AS plain_code,
                    CASE WHEN lower(substr(sd.code, 1, 2)) IN ('sh', 'sz', 'bj') THEN 1 ELSE 0 END AS pref_score,
                    sd.close
                FROM stock_daily sd, latest_day
                WHERE sd.date = latest_day.date AND sd.close IS NOT NULL
            ),
            latest AS (
                SELECT plain_code, close
                FROM (
                    SELECT *,
                        ROW_NUMBER() OVER (PARTITION BY plain_code ORDER BY pref_score DESC) AS rn
                    FROM latest_raw
                )
                WHERE rn = 1
            ),
            previous_raw AS (
                SELECT
                    {plain_daily_expr} AS plain_code,
                    CASE WHEN lower(substr(sd.code, 1, 2)) IN ('sh', 'sz', 'bj') THEN 1 ELSE 0 END AS pref_score,
                    sd.close
                FROM stock_daily sd, previous_day
                WHERE sd.date = previous_day.date AND sd.close IS NOT NULL
            ),
            previous AS (
                SELECT plain_code, close
                FROM (
                    SELECT *,
                        ROW_NUMBER() OVER (PARTITION BY plain_code ORDER BY pref_score DESC) AS rn
                    FROM previous_raw
                )
                WHERE rn = 1
            ),
            paired AS (
                SELECT
                    l.plain_code,
                    l.close AS latest_close,
                    p.close AS prev_close,
                    CASE
                        WHEN p.close IS NULL OR p.close = 0 THEN NULL
                        ELSE (l.close / p.close - 1) * 100
                    END AS change_pct
                FROM latest l
                LEFT JOIN previous p ON p.plain_code = l.plain_code
            )
            SELECT
                (SELECT date FROM latest_day) AS latest_date,
                (SELECT date FROM previous_day) AS previous_date,
                (SELECT stock_count FROM info) AS stock_count,
                COUNT(*) AS effective_count,
                SUM(CASE WHEN change_pct > 0 THEN 1 ELSE 0 END) AS up_count,
                SUM(CASE WHEN change_pct < 0 THEN 1 ELSE 0 END) AS down_count,
                SUM(CASE WHEN change_pct = 0 THEN 1 ELSE 0 END) AS flat_count,
                SUM(CASE WHEN change_pct IS NULL THEN 1 ELSE 0 END) AS no_prev_count,
                SUM(CASE WHEN change_pct >= 9.9 THEN 1 ELSE 0 END) AS limit_up,
                SUM(CASE WHEN change_pct <= -9.9 THEN 1 ELSE 0 END) AS limit_down,
                AVG(change_pct) AS avg_change_pct
            FROM paired
            """
        )
        with self._engine.connect() as conn:
            row = conn.execute(sql).mappings().first() or {}

        effective_count = int(row.get("effective_count") or 0)
        stock_count = int(row.get("stock_count") or 0)
        up_count = int(row.get("up_count") or 0)
        down_count = int(row.get("down_count") or 0)
        flat_count = int(row.get("flat_count") or 0)
        no_prev_count = int(row.get("no_prev_count") or 0)
        directional_total = up_count + down_count + flat_count
        return {
            "total_stocks": stock_count,
            "effective_count": effective_count,
            "stock_count": stock_count,
            "daily_covered": stock_count if stock_count else 0,
            "daily_missing": 0 if stock_count else 0,
            "coverage_pct": 100.0 if stock_count else None,
            "latest_date": str(row.get("latest_date") or "") or None,
            "previous_date": str(row.get("previous_date") or "") or None,
            "latest_date_covered": effective_count,
            "latest_date_missing": max(stock_count - effective_count, 0),
            "latest_date_coverage_pct": round(effective_count / stock_count * 100, 2) if stock_count else None,
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "no_prev_count": no_prev_count,
            "limit_up": int(row.get("limit_up") or 0),
            "limit_down": int(row.get("limit_down") or 0),
            "avg_change_pct": round(float(row.get("avg_change_pct") or 0), 2) if directional_total else None,
            "up_ratio": round(up_count / directional_total * 100, 2) if directional_total else None,
        }

    # ── 数据来源与质量台账 ──

    def save_data_source_version(
        self,
        source: str,
        version: str,
        active: bool = True,
        metadata: dict | None = None,
    ) -> int:
        """保存或更新数据源版本，返回版本记录 ID"""
        session = self._get_session()
        try:
            now = _now_iso()
            row = (
                session.query(DataSourceVersion)
                .filter(DataSourceVersion.source == source, DataSourceVersion.version == version)
                .first()
            )
            if row:
                row.active = 1 if active else 0
                if metadata is not None:
                    row.metadata_json = _json_dumps(metadata)
                row.updated_at = now
            else:
                row = DataSourceVersion(
                    source=source,
                    version=version,
                    active=1 if active else 0,
                    metadata_json=_json_dumps(metadata),
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            session.commit()
            return row.id
        except Exception as e:
            session.rollback()
            logger.error(f"保存数据源版本失败: {e}")
            raise
        finally:
            session.close()

    def get_data_source_versions(self, source: str | None = None, active_only: bool = False) -> list[dict]:
        """查询数据源版本列表"""
        session = self._get_session()
        try:
            query = session.query(DataSourceVersion)
            if source:
                query = query.filter(DataSourceVersion.source == source)
            if active_only:
                query = query.filter(DataSourceVersion.active == 1)
            rows = query.order_by(DataSourceVersion.source, DataSourceVersion.id).all()
            return [
                {
                    "id": row.id,
                    "source": row.source,
                    "version": row.version,
                    "active": bool(row.active),
                    "metadata": _json_loads(row.metadata_json),
                    "created_at": row.created_at,
                    "updated_at": row.updated_at or row.created_at,
                }
                for row in rows
            ]
        finally:
            session.close()

    def save_data_snapshot(
        self,
        code: str,
        domain: str,
        source: str,
        source_version: str,
        payload: dict,
        quality_status: str = "ok",
    ) -> int:
        """保存一条数据快照，返回快照 ID"""
        session = self._get_session()
        try:
            payload_json = _json_dumps(payload)
            row = DataSnapshot(
                code=_normalize_ledger_code(code),
                domain=domain,
                source=source,
                source_version=source_version,
                payload_json=payload_json,
                payload_hash=_payload_hash(payload),
                quality_status=quality_status,
                created_at=_now_iso(),
            )
            session.add(row)
            session.commit()
            return row.id
        except Exception as e:
            session.rollback()
            logger.error(f"保存数据快照失败: {e}")
            raise
        finally:
            session.close()

    def get_latest_data_snapshot(self, code: str, domain: str) -> dict | None:
        """获取指定代码和业务域的最新数据快照"""
        plain_code = _normalize_ledger_code(code)
        prefixed_code = _to_prefix_code(plain_code)
        session = self._get_session()
        try:
            row = (
                session.query(DataSnapshot)
                .filter(DataSnapshot.code.in_([plain_code, prefixed_code]), DataSnapshot.domain == domain)
                .order_by(DataSnapshot.id.desc())
                .first()
            )
            if not row:
                return None
            return {
                "id": row.id,
                "code": row.code,
                "domain": row.domain,
                "source": row.source,
                "source_version": row.source_version,
                "payload": _json_loads(row.payload_json),
                "payload_hash": row.payload_hash,
                "quality_status": row.quality_status,
                "created_at": row.created_at,
            }
        finally:
            session.close()

    def save_data_quality_record(
        self,
        code: str,
        domain: str,
        check_name: str,
        status: str,
        details: dict | None = None,
        diff_count: int = 0,
    ) -> int:
        """保存一条数据质量检查记录，返回记录 ID"""
        session = self._get_session()
        try:
            sanitized_details = _sanitize_json_value(details)
            inferred_diff_count = diff_count
            if inferred_diff_count in (None, 0) and isinstance(sanitized_details, dict):
                inferred_diff_count = sanitized_details.get("diff_count", 0) or 0
            row = DataQualityRecord(
                code=_normalize_ledger_code(code),
                domain=domain,
                check_name=check_name,
                status=status,
                details_json=_json_dumps(sanitized_details),
                diff_count=int(inferred_diff_count or 0),
                created_at=_now_iso(),
            )
            session.add(row)
            session.commit()
            return row.id
        except Exception as e:
            session.rollback()
            logger.error(f"保存数据质量记录失败: {e}")
            raise
        finally:
            session.close()

    def get_data_quality_summary(self, domain: str | None = None) -> dict:
        """汇总数据质量记录，支持按业务域过滤"""
        session = self._get_session()
        try:
            query = session.query(DataQualityRecord)
            if domain:
                query = query.filter(DataQualityRecord.domain == domain)
            rows = query.all()

            by_status: dict[str, int] = {}
            by_domain: dict[str, int] = {}
            shadow_diff_count = 0
            for row in rows:
                by_status[row.status] = by_status.get(row.status, 0) + 1
                by_domain[row.domain] = by_domain.get(row.domain, 0) + 1
                if row.check_name == "shadow_compare":
                    shadow_diff_count += int(row.diff_count or 0)

            latest_created_at = max((row.created_at for row in rows if row.created_at), default=None)
            return {
                "domain": domain,
                "total": len(rows),
                "by_status": dict(sorted(by_status.items())),
                "by_domain": dict(sorted(by_domain.items())),
                "shadow_diff_count": shadow_diff_count,
                "latest_created_at": latest_created_at,
            }
        finally:
            session.close()

    def get_data_source_health(self) -> dict:
        """汇总数据源可用性和最新版本信息"""
        session = self._get_session()
        try:
            rows = session.query(DataSourceVersion).order_by(DataSourceVersion.source, DataSourceVersion.id).all()
            sources: dict[str, dict] = {}
            for row in rows:
                row_seen_at = row.updated_at or row.created_at
                source_health = sources.setdefault(
                    row.source,
                    {
                        "latest_version": None,
                        "active_versions": [],
                        "version_count": 0,
                        "last_seen_at": None,
                        "latest_version_id": None,
                        "_latest_seen_at": None,
                    },
                )
                source_health["version_count"] += 1
                if row_seen_at and (
                    source_health["_latest_seen_at"] is None
                    or row_seen_at > source_health["_latest_seen_at"]
                    or (row_seen_at == source_health["_latest_seen_at"] and (source_health["latest_version_id"] or 0) < row.id)
                ):
                    source_health["latest_version"] = row.version
                    source_health["_latest_seen_at"] = row_seen_at
                    source_health["latest_version_id"] = row.id
                if row_seen_at and (
                    source_health["last_seen_at"] is None
                    or row_seen_at > source_health["last_seen_at"]
                ):
                    source_health["last_seen_at"] = row_seen_at
                if row.active:
                    source_health["active_versions"].append(row.version)

            active_sources = [
                source
                for source, source_health in sources.items()
                if source_health["active_versions"]
            ]
            for source_health in sources.values():
                source_health.pop("_latest_seen_at", None)
                source_health.pop("latest_version_id", None)
            return {
                "total_sources": len(sources),
                "total_active_sources": len(active_sources),
                "sources": sources,
            }
        finally:
            session.close()

    # ── 自选股管理 ──

    def _next_watchlist_id(self, session) -> int:
        row = session.execute(text("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM user_watchlist")).mappings().first()
        return int(row["next_id"]) if row and row["next_id"] else 1

    def add_to_watchlist(self, code: str, workspace_id: str = "") -> bool:
        """添加自选股，返回是否新增（False=已存在）"""
        prefixed_code, plain_code = _normalize_storage_code(code)
        if not prefixed_code or not plain_code:
            return False
        session = self._get_session()
        try:
            if workspace_id:
                existing = (
                    session.query(WorkspaceWatchlist)
                    .filter(
                        WorkspaceWatchlist.workspace_id == workspace_id,
                        WorkspaceWatchlist.code.in_([prefixed_code, plain_code]),
                    )
                    .first()
                )
                if existing:
                    existing.code = prefixed_code
                    session.commit()
                    return False
                session.add(WorkspaceWatchlist(
                    workspace_id=workspace_id,
                    code=prefixed_code,
                    added_at=str(pd.Timestamp.now()),
                ))
            else:
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
                session.add(UserWatchlist(
                    code=prefixed_code,
                    added_at=str(pd.Timestamp.now()),
                ))
            session.commit()
            logger.info(f"自选股添加: {prefixed_code}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"添加自选股失败: {e}")
            raise
        finally:
            session.close()

    def remove_from_watchlist(self, code: str, workspace_id: str = "") -> bool:
        """删除自选股，返回是否存在"""
        prefixed_code = _to_prefix_code(code)
        plain_code = _to_plain_code(code)
        session = self._get_session()
        try:
            if workspace_id:
                rows = (
                    session.query(WorkspaceWatchlist)
                    .filter(
                        WorkspaceWatchlist.workspace_id == workspace_id,
                        WorkspaceWatchlist.code.in_([prefixed_code, plain_code]),
                    )
                    .all()
                )
            else:
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

    def get_watchlist(self, workspace_id: str = "") -> list[str]:
        """获取自选股代码列表"""
        session = self._get_session()
        try:
            if workspace_id:
                query = session.query(WorkspaceWatchlist.code).filter(
                    WorkspaceWatchlist.workspace_id == workspace_id
                ).order_by(WorkspaceWatchlist.added_at)
            else:
                query = session.query(UserWatchlist.code).order_by(UserWatchlist.added_at)
            rows = query.all()
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

    def get_watchlist_with_info(self, workspace_id: str = "") -> list[dict]:
        """获取自选股列表（含名称、行业、最新价、数据日期）"""
        session = self._get_session()
        try:
            if workspace_id:
                query = session.query(WorkspaceWatchlist.code).filter(
                    WorkspaceWatchlist.workspace_id == workspace_id
                ).order_by(WorkspaceWatchlist.added_at)
            else:
                query = session.query(UserWatchlist.code).order_by(UserWatchlist.added_at)
            rows = query.all()
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
            daily_rows_by_code = {}
            for row in latest_rows:
                plain_code = _to_plain_code(row.code)
                daily_rows_by_code.setdefault(plain_code, []).append(row)

            latest_prices = {}
            previous_prices = {}
            for plain_code, daily_rows in daily_rows_by_code.items():
                ordered_rows = sorted(
                    daily_rows,
                    key=lambda item: (item.date, item.code == _to_prefix_code(plain_code)),
                    reverse=True,
                )
                latest = ordered_rows[0]
                latest_prices[plain_code] = {"price": latest.close, "date": latest.date}

                for row in ordered_rows[1:]:
                    if row.date < latest.date and row.close not in (None, 0):
                        previous_prices[plain_code] = row.close
                        break

            return [
                {
                    "code": plain_code,
                    "name": info_map.get(plain_code, {}).get("name", ""),
                    "industry": info_map.get(plain_code, {}).get("industry", ""),
                    "price": latest_prices.get(plain_code, {}).get("price"),
                    "latest_price": latest_prices.get(plain_code, {}).get("price"),
                    "change_pct": (
                        round(
                            (
                                (latest_prices[plain_code]["price"] - previous_prices[plain_code])
                                / previous_prices[plain_code]
                            ) * 100,
                            2,
                        )
                        if plain_code in latest_prices
                        and plain_code in previous_prices
                        and latest_prices[plain_code].get("price") is not None
                        else None
                    ),
                    "latest_date": str(latest_prices[plain_code]["date"]) if plain_code in latest_prices else None,
                }
                for plain_code in ordered_codes
            ]
        finally:
            session.close()

    def get_watchlist_workspaces(self) -> list[str]:
        """列出所有存在自选股的工作区 ID（含匿名空工作区）"""
        session = self._get_session()
        try:
            rows = session.query(WorkspaceWatchlist.workspace_id).distinct().all()
            workspaces = []
            seen = set()
            for row in rows:
                wid = row.workspace_id or ""
                if wid in seen:
                    continue
                seen.add(wid)
                workspaces.append(wid)
            return workspaces
        finally:
            session.close()

    def get_all_watchlist_codes(self) -> list[tuple[str, list[str]]]:
        """返回所有工作区及其自选股代码列表。"""
        result = []
        for workspace_id in self.get_watchlist_workspaces():
            result.append((workspace_id, self.get_watchlist(workspace_id)))
        default_codes = self.get_watchlist("")
        if default_codes:
            result.append(("", default_codes))
        return result

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

    def list_conversations(self, limit: int = 50, workspace_id: str = "", surface: str = "llm") -> list[dict]:
        """获取对话列表"""
        session = self._get_session()
        try:
            surface_value = surface or "llm"
            query = session.query(Conversation).order_by(Conversation.updated_at.desc())
            query = query.filter(Conversation.workspace_id == (workspace_id or ""))
            query = query.filter(Conversation.surface == surface_value)
            rows = query.limit(limit).all()
            return [{"id": r.id, "title": r.title, "created_at": r.created_at, "updated_at": r.updated_at} for r in rows]
        finally:
            session.close()

    def get_conversation(self, conv_id: str, workspace_id: str = "", surface: str = "llm") -> dict | None:
        """获取单个对话（含消息）"""
        session = self._get_session()
        try:
            surface_value = surface or "llm"
            query = session.query(Conversation).filter(Conversation.id == conv_id)
            query = query.filter(Conversation.workspace_id == (workspace_id or ""))
            query = query.filter(Conversation.surface == surface_value)
            r = query.first()
            if not r:
                return None
            return {"id": r.id, "title": r.title, "messages": _json_loads(r.messages_json, []), "created_at": r.created_at, "updated_at": r.updated_at}
        finally:
            session.close()

    def save_conversation(self, conv_id: str, title: str, messages: list, workspace_id: str = "", surface: str = "llm") -> None:
        """创建或更新对话"""
        session = self._get_session()
        try:
            surface_value = surface or "llm"
            now = _now_iso()
            payload = _json_dumps(messages or [])
            query = session.query(Conversation).filter(Conversation.id == conv_id)
            query = query.filter(Conversation.workspace_id == (workspace_id or ""))
            query = query.filter(Conversation.surface == surface_value)
            existing = query.first()
            if existing:
                existing.title = title
                existing.messages_json = payload
                existing.updated_at = now
            else:
                session.add(Conversation(
                    id=conv_id,
                    workspace_id=workspace_id or "",
                    surface=surface_value,
                    title=title,
                    messages_json=payload,
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"保存对话失败: {e}")
        finally:
            session.close()

    def delete_conversation(self, conv_id: str, workspace_id: str = "", surface: str = "llm") -> bool:
        """删除对话"""
        session = self._get_session()
        try:
            surface_value = surface or "llm"
            query = session.query(Conversation).filter(Conversation.id == conv_id)
            query = query.filter(Conversation.workspace_id == (workspace_id or ""))
            query = query.filter(Conversation.surface == surface_value)
            count = query.delete()
            session.commit()
            return count > 0
        except Exception as e:
            session.rollback()
            logger.error(f"删除对话失败: {e}")
            return False
        finally:
            session.close()
