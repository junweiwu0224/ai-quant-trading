"""统一的 SQLite 连接工具

所有 SQLite 连接必须通过此模块获取，确保：
- WAL 日志模式（支持并发读写）
- busy_timeout（写冲突时等待而非立即失败）
- row_factory = sqlite3.Row（统一字典访问）
"""
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine


def get_connection(db_path: str | Path, readonly: bool = False) -> sqlite3.Connection:
    """获取配置好 WAL + busy_timeout 的 SQLite 连接

    Args:
        db_path: 数据库文件路径
        readonly: 是否只读（只读连接可并发共享）

    Returns:
        已配置的 sqlite3.Connection
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    uri = f"file:{path}"
    if readonly:
        uri += "?mode=ro"

    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    if not readonly:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_engine_url(db_path: str | Path) -> str:
    """生成 SQLAlchemy 引擎 URL"""
    return f"sqlite:///{Path(db_path)}"


def create_sqlite_engine(db_path: str | Path, **kwargs):
    """创建配置好 WAL + busy_timeout 的 SQLAlchemy 引擎

    Args:
        db_path: 数据库文件路径
        **kwargs: 传递给 create_engine 的额外参数

    Returns:
        已配置 WAL 的 SQLAlchemy Engine
    """
    url = get_engine_url(db_path)
    engine = create_engine(
        url, echo=False,
        connect_args={"check_same_thread": False},
        **kwargs,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine
