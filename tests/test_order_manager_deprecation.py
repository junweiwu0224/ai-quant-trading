"""
Phase 2.6: 移除旧订单路径测试

验证 OrderManager 的旧写入方法已被废弃，并正确抛出 NotImplementedError。
保留只读查询方法继续可用。
"""
from pathlib import Path

import pytest

from engine.models import Direction, OrderType
from engine.order_manager import OrderManager


def test_create_order_is_deprecated(tmp_path: Path):
    """验证 create_order() 已废弃"""
    db_path = tmp_path / "paper.db"
    manager = OrderManager(str(db_path))
    
    with pytest.raises(NotImplementedError, match="create_order.*已废弃"):
        manager.create_order(
            code="600000.SH",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            volume=100,
        )


def test_match_orders_is_deprecated(tmp_path: Path):
    """验证 match_orders() 已废弃"""
    db_path = tmp_path / "paper.db"
    manager = OrderManager(str(db_path))
    
    with pytest.raises(NotImplementedError, match="match_orders.*已废弃"):
        from engine.models import PaperConfig
        manager.match_orders({}, PaperConfig())


def test_should_match_is_deprecated(tmp_path: Path):
    """验证 _should_match() 已废弃"""
    db_path = tmp_path / "paper.db"
    manager = OrderManager(str(db_path))
    
    from engine.models import PaperOrder
    order = PaperOrder(
        order_id="TEST",
        code="600000.SH",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        volume=100,
    )
    
    with pytest.raises(NotImplementedError, match="_should_match.*已废弃"):
        manager._should_match(order, None)


def test_execute_order_is_deprecated(tmp_path: Path):
    """验证 _execute_order() 已废弃"""
    db_path = tmp_path / "paper.db"
    manager = OrderManager(str(db_path))
    
    from engine.models import PaperOrder, PaperConfig
    order = PaperOrder(
        order_id="TEST",
        code="600000.SH",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        volume=100,
    )
    
    with pytest.raises(NotImplementedError, match="_execute_order.*已废弃"):
        manager._execute_order(order, None, PaperConfig())


def test_save_order_is_deprecated(tmp_path: Path):
    """验证 _save_order() 已废弃"""
    db_path = tmp_path / "paper.db"
    manager = OrderManager(str(db_path))
    
    from engine.models import PaperOrder
    order = PaperOrder(
        order_id="TEST",
        code="600000.SH",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        volume=100,
    )
    
    with pytest.raises(NotImplementedError, match="_save_order.*已废弃"):
        manager._save_order(order)


def test_readonly_methods_still_work(tmp_path: Path):
    """验证只读查询方法仍然可用"""
    db_path = tmp_path / "paper.db"
    manager = OrderManager(str(db_path))
    
    # get_orders() 应该可用
    result = manager.get_orders(status="pending", page=1, page_size=10)
    assert "items" in result
    assert "total" in result
    
    # get_pending_orders() 应该可用
    pending = manager.get_pending_orders()
    assert isinstance(pending, list)
    
    # get_order() 应该可用（查询不存在的订单返回 None）
    order = manager.get_order("NONEXISTENT")
    assert order is None


def test_idempotent_methods_still_work(tmp_path: Path):
    """验证幂等创建方法仍然可用（用于恢复）"""
    db_path = tmp_path / "paper.db"
    manager = OrderManager(str(db_path))
    
    from engine.models import PaperOrder, OrderStatus
    
    orders = [
        PaperOrder(
            order_id="RECOVERY-001",
            code="600000.SH",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            volume=100,
            status=OrderStatus.PENDING,
        )
    ]
    
    # create_orders_idempotently() 应该可用（用于恢复场景）
    result = manager.create_orders_idempotently(
        orders,
        operation_id="test_recovery_op",
    )
    assert len(result) == 1
    assert result[0].order_id == "RECOVERY-001"
    
    # 再次调用应该返回相同订单（幂等）
    result2 = manager.create_orders_idempotently(
        orders,
        operation_id="test_recovery_op",
    )
    assert len(result2) == 1
    assert result2[0].order_id == "RECOVERY-001"
