"""测试条件单迁移到统一执行协议"""
import json
from datetime import datetime, timedelta

import pytest

from config.datetime_utils import now_beijing
from engine.alert_engine import Alert
from engine.conditional_order import ConditionalOrderEngine, ConditionalOrderRule
from engine.models import Direction, OrderType, PaperConfig
from engine.operations_store import OperationsStore
from engine.paper_commands import PaperCommandClient
from utils.db import get_connection


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_conditional.db")


@pytest.fixture
def engine(db_path):
    """初始化数据库表和 ConditionalOrderEngine"""
    conn = get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conditional_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_rule_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            direction TEXT NOT NULL,
            order_type TEXT NOT NULL,
            price REAL,
            volume INTEGER NOT NULL,
            max_amount REAL DEFAULT 0,
            enabled INTEGER DEFAULT 0,
            cooldown INTEGER DEFAULT 300,
            last_triggered_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conditional_order_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conditional_order_id INTEGER,
            alert_rule_id INTEGER,
            code TEXT NOT NULL,
            action TEXT NOT NULL,
            order_id TEXT,
            reason TEXT NOT NULL,
            quote_price REAL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_equity_curve (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            cash REAL NOT NULL,
            portfolio_value REAL NOT NULL,
            total_value REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            volume INTEGER NOT NULL,
            avg_price REAL NOT NULL,
            current_price REAL
        );
    """)
    conn.execute(
        "INSERT INTO paper_equity_curve (timestamp, cash, portfolio_value, total_value) VALUES (?, 100000.0, 0.0, 100000.0)",
        [now_beijing().isoformat()],
    )
    conn.commit()
    conn.close()

    # 初始化 OperationsStore 表
    store = OperationsStore(db_path)
    store.close()

    config = PaperConfig(db_path=db_path, initial_cash=100000.0)
    return ConditionalOrderEngine(db_path=db_path, config=config)


def test_conditional_order_enqueues_command(engine, db_path):
    """测试条件单触发时提交 command 而非直接创建订单"""
    # 创建条件单规则
    rule = engine.create_rule(
        alert_rule_id=1,
        code="600000",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        volume=100,
        enabled=True,
        cooldown=0,
    )

    # 模拟预警触发
    alert = Alert(
        rule_id=1,
        code="600000",
        name="价格突破",
        condition="price_above",
        threshold=10.0,
        current_value=10.5,
        message="价格突破",
    )

    # 提供行情数据
    class Quote:
        price = 10.5

    quotes = {"600000": Quote()}

    # 执行条件单
    events = engine.handle_alerts([alert], quotes)

    # 验证事件
    assert len(events) == 1
    event = events[0]
    assert event.action == "created_order"
    assert "已提交订单命令" in event.reason
    assert event.order_id is not None  # 这是 command_id

    # 验证 command 已入队（通过事件中的 command_id）
    assert event.order_id.startswith("cmd_")  # 这是 command_id


def test_conditional_order_cooldown_respected(engine, db_path):
    """测试冷却期内不重复触发"""
    # 创建带冷却期的条件单
    rule = engine.create_rule(
        alert_rule_id=2,
        code="600001",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        volume=100,
        enabled=True,
        cooldown=300,  # 5分钟冷却期
    )

    alert = Alert(
        rule_id=2,
        code="600001",
        name="价格突破",
        condition="price_above",
        threshold=10.0,
        current_value=10.5,
        message="价格突破",
    )

    class Quote:
        price = 10.5

    quotes = {"600001": Quote()}

    # 第一次触发
    events1 = engine.handle_alerts([alert], quotes)
    assert len(events1) == 1
    assert events1[0].action == "created_order"

    # 第二次触发（冷却期内）
    events2 = engine.handle_alerts([alert], quotes)
    assert len(events2) == 1
    assert events2[0].action == "skipped"
    assert "冷却期内跳过" in events2[0].reason


def test_conditional_order_sell(engine, db_path):
    """测试卖出条件单"""
    # 先建立持仓
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO paper_positions (code, volume, avg_price, current_price) VALUES (?, ?, ?, ?)",
        ("600002", 200, 10.0, 10.5),
    )
    conn.commit()
    conn.close()

    # 创建卖出条件单
    rule = engine.create_rule(
        alert_rule_id=3,
        code="600002",
        direction=Direction.SHORT,
        order_type=OrderType.MARKET,
        volume=100,
        enabled=True,
        cooldown=0,
    )

    alert = Alert(
        rule_id=3,
        code="600002",
        name="价格回落",
        condition="price_below",
        threshold=10.0,
        current_value=9.5,
        message="价格回落",
    )

    class Quote:
        price = 9.5

    quotes = {"600002": Quote()}

    events = engine.handle_alerts([alert], quotes)
    assert len(events) == 1
    assert events[0].action == "created_order"

    # 验证 command 已创建
    assert events[0].order_id.startswith("cmd_")


def test_conditional_order_risk_rejection(engine, db_path):
    """测试风控拒绝"""
    # 创建买入条件单，但现金不足
    conn = get_connection(db_path)
    conn.execute("DELETE FROM paper_equity_curve")
    conn.execute(
        "INSERT INTO paper_equity_curve (timestamp, cash, portfolio_value, total_value) VALUES (?, ?, ?, ?)",
        (now_beijing().isoformat(), 100.0, 0.0, 100.0),  # 只有100元现金
    )
    conn.commit()
    conn.close()

    rule = engine.create_rule(
        alert_rule_id=4,
        code="600003",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        volume=1000,  # 需要10500元
        enabled=True,
        cooldown=0,
    )

    alert = Alert(
        rule_id=4,
        code="600003",
        name="价格突破",
        condition="price_above",
        threshold=10.0,
        current_value=10.5,
        message="价格突破",
    )

    class Quote:
        price = 10.5

    quotes = {"600003": Quote()}

    events = engine.handle_alerts([alert], quotes)
    assert len(events) == 1
    assert events[0].action == "rejected"
    assert "资金不足" in events[0].reason or "现金" in events[0].reason or "余额" in events[0].reason

    # 验证没有 command 入队（通过 order_id 为 None 间接验证）
    assert events[0].order_id is None


def test_conditional_order_idempotency(engine, db_path):
    """测试条件单幂等性（通过冷却期实现）"""
    rule = engine.create_rule(
        alert_rule_id=5,
        code="600004",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        volume=100,
        enabled=True,
        cooldown=60,
    )

    alert = Alert(
        rule_id=5,
        code="600004",
        name="价格突破",
        condition="price_above",
        threshold=10.0,
        current_value=10.5,
        message="价格突破",
    )

    class Quote:
        price = 10.5

    quotes = {"600004": Quote()}

    # 第一次触发
    events1 = engine.handle_alerts([alert], quotes)
    assert events1[0].action == "created_order"

    # 立即再次触发（应被冷却期阻止）
    events2 = engine.handle_alerts([alert], quotes)
    assert events2[0].action == "skipped"

    # 验证只有一个 command（通过第二次被跳过间接验证）
    assert events1[0].order_id.startswith("cmd_")
    assert events2[0].order_id is None  # 跳过的没有 command_id
