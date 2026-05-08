"""数据库迁移脚本 - 初始化模拟盘数据库"""
import sqlite3
from pathlib import Path
from loguru import logger

from config.settings import PROJECT_ROOT


# 数据库路径
DB_PATH = PROJECT_ROOT / "data" / "paper_trading.db"


def get_connection(db_path: str = None) -> sqlite3.Connection:
    """获取数据库连接"""
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_path: str = None):
    """初始化数据库表结构"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        # 订单表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                code TEXT NOT NULL,
                direction TEXT NOT NULL,
                order_type TEXT NOT NULL DEFAULT 'market',
                price REAL,
                volume INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                filled_price REAL,
                filled_volume INTEGER DEFAULT 0,
                commission REAL DEFAULT 0,
                stamp_tax REAL DEFAULT 0,
                slippage REAL DEFAULT 0,
                strategy_name TEXT,
                signal_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 持仓表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                volume INTEGER NOT NULL,
                avg_price REAL NOT NULL,
                current_price REAL DEFAULT 0,
                market_value REAL DEFAULT 0,
                unrealized_pnl REAL DEFAULT 0,
                unrealized_pnl_pct REAL DEFAULT 0,
                stop_loss_price REAL,
                take_profit_price REAL,
                max_position_pct REAL DEFAULT 0.3,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code)
            )
        """)

        # 交易历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT UNIQUE NOT NULL,
                order_id TEXT,
                code TEXT NOT NULL,
                direction TEXT NOT NULL,
                price REAL NOT NULL,
                volume INTEGER NOT NULL,
                entry_price REAL DEFAULT 0,
                profit REAL DEFAULT 0,
                profit_pct REAL DEFAULT 0,
                commission REAL DEFAULT 0,
                stamp_tax REAL DEFAULT 0,
                equity_after REAL DEFAULT 0,
                strategy_name TEXT,
                signal_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 资金曲线表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_equity_curve (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                equity REAL NOT NULL,
                cash REAL NOT NULL,
                market_value REAL DEFAULT 0,
                benchmark_value REAL,
                drawdown REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 绩效统计表 (每日快照)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                total_equity REAL,
                daily_return REAL,
                cumulative_return REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                sortino_ratio REAL,
                calmar_ratio REAL,
                win_rate REAL,
                profit_loss_ratio REAL,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                avg_win REAL DEFAULT 0,
                avg_loss REAL DEFAULT 0,
                max_consecutive_wins INTEGER DEFAULT 0,
                max_consecutive_losses INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date)
            )
        """)

        # 风控事件表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                code TEXT,
                trigger_price REAL,
                action TEXT,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_code ON paper_orders(code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON paper_orders(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_created ON paper_orders(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_code ON paper_trades(code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_created ON paper_trades(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_equity_timestamp ON paper_equity_curve(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_performance_date ON paper_performance(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_events_type ON paper_risk_events(event_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_events_created ON paper_risk_events(created_at)")

        conn.commit()
        logger.info(f"数据库初始化完成: {DB_PATH}")

    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def drop_all_tables(db_path: str = None):
    """删除所有表（危险操作，仅用于测试）"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    tables = [
        "paper_orders",
        "paper_positions",
        "paper_trades",
        "paper_equity_curve",
        "paper_performance",
        "paper_risk_events",
    ]

    try:
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        logger.warning("所有表已删除")
    except Exception as e:
        logger.error(f"删除表失败: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--drop":
        confirm = input("确定要删除所有表吗？(yes/no): ")
        if confirm.lower() == "yes":
            drop_all_tables()
        else:
            print("已取消")
    else:
        init_database()
