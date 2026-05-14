"""模拟盘完整API路由"""
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from config.datetime_utils import now_beijing, now_beijing_iso, now_beijing_str, today_beijing, today_beijing_compact
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from engine.models import (
    Direction, OrderStatus, OrderType,
    PaperConfig, PaperOrder, PaperPosition, PaperTrade
)
from engine.order_manager import OrderManager
from engine.performance_analyzer import PerformanceAnalyzer
from engine.risk_manager import RiskManager
from utils.db import get_connection

router = APIRouter(tags=["模拟盘完整功能"])

# ────────────── 全局实例 ──────────────

_config = PaperConfig()
_order_manager = OrderManager(_config.db_path)
_performance_analyzer = PerformanceAnalyzer(_config.db_path)
_risk_manager = RiskManager(_config, _config.db_path)


@contextmanager
def _get_db():
    """获取数据库连接的上下文管理器（自动关闭，已配置 WAL + busy_timeout）"""
    conn = get_connection(_config.db_path)
    try:
        yield conn
    finally:
        conn.close()


# ────────────── 请求模型 ──────────────

class CreateOrderRequest(BaseModel):
    """创建订单请求"""
    code: str = Field(..., description="股票代码")
    direction: str = Field(..., description="buy/sell")
    order_type: str = Field(default="market", description="market/limit/stop_loss/take_profit")
    price: Optional[float] = Field(None, description="限价/止损价/止盈价")
    volume: int = Field(..., gt=0, description="数量")
    strategy_name: Optional[str] = Field(None, description="策略名称")
    signal_reason: Optional[str] = Field(None, description="信号原因")


class UpdateStopLossRequest(BaseModel):
    """更新止损止盈请求"""
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None


class UpdateRiskRulesRequest(BaseModel):
    """更新风控规则请求"""
    max_position_pct: Optional[float] = Field(None, ge=0, le=1)
    max_positions: Optional[int] = Field(None, ge=1)
    max_drawdown: Optional[float] = Field(None, ge=0, le=1)
    max_daily_loss: Optional[float] = Field(None, ge=0, le=1)


# ────────────── 订单 API ──────────────

@router.post("/orders")
async def create_order(req: CreateOrderRequest):
    """创建订单（市价/限价/止损/止盈）"""
    try:
        direction = Direction.from_value(req.direction)
        order_type = OrderType(req.order_type)

        order = _order_manager.create_order(
            code=req.code,
            direction=direction,
            order_type=order_type,
            volume=req.volume,
            price=req.price,
            strategy_name=req.strategy_name,
            signal_reason=req.signal_reason,
        )

        return {
            "success": True,
            "data": order.to_dict(),
            "message": "订单创建成功",
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"创建订单失败: {e}")
        raise HTTPException(500, "创建订单失败，请稍后重试")


@router.get("/orders")
async def get_orders(
    status: Optional[str] = Query(None, description="订单状态筛选"),
    code: Optional[str] = Query(None, description="股票代码筛选"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    """获取订单列表"""
    try:
        result = _order_manager.get_orders(
            status=status,
            code=code,
            start_date=datetime.combine(start_date, datetime.min.time()) if start_date else None,
            end_date=datetime.combine(end_date, datetime.max.time()) if end_date else None,
            page=page,
            page_size=page_size,
        )

        return {
            "success": True,
            "data": result,
        }
    except Exception as e:
        logger.error(f"获取订单列表失败: {e}")
        raise HTTPException(500, "获取订单列表失败，请稍后重试")


@router.get("/orders/{order_id}")
async def get_order(order_id: str):
    """获取订单详情"""
    try:
        order = _order_manager.get_order(order_id)
        if not order:
            raise HTTPException(404, f"订单不存在: {order_id}")

        return {
            "success": True,
            "data": order.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取订单详情失败: {e}")
        raise HTTPException(500, "获取订单详情失败，请稍后重试")


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    """撤销订单"""
    try:
        order = _order_manager.cancel_order(order_id)
        return {
            "success": True,
            "data": order.to_dict(),
            "message": "订单已撤销",
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"撤销订单失败: {e}")
        raise HTTPException(500, "撤销订单失败，请稍后重试")


# ────────────── 持仓 API ──────────────

@router.get("/positions")
async def get_positions():
    """获取当前持仓列表"""
    try:
        with _get_db() as conn:
            cursor = conn.execute("SELECT * FROM paper_positions ORDER BY updated_at DESC")
            rows = cursor.fetchall()

            positions = [{
                "code": row["code"],
                "volume": row["volume"],
                "avg_price": row["avg_price"],
                "current_price": row["current_price"],
                "market_value": row["market_value"],
                "unrealized_pnl": row["unrealized_pnl"],
                "unrealized_pnl_pct": row["unrealized_pnl_pct"],
                "stop_loss_price": row["stop_loss_price"],
                "take_profit_price": row["take_profit_price"],
            } for row in rows]

        return {
            "success": True,
            "data": positions,
        }
    except Exception as e:
        logger.error(f"获取持仓列表失败: {e}")
        raise HTTPException(500, "获取持仓列表失败，请稍后重试")


@router.get("/positions/{code}")
async def get_position(code: str):
    """获取单只股票持仓详情"""
    try:
        with _get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM paper_positions WHERE code = ?",
                (code,)
            )
            row = cursor.fetchone()

            if not row:
                raise HTTPException(404, f"持仓不存在: {code}")

            position = {
                "code": row["code"],
                "volume": row["volume"],
                "avg_price": row["avg_price"],
                "current_price": row["current_price"],
                "market_value": row["market_value"],
                "unrealized_pnl": row["unrealized_pnl"],
                "unrealized_pnl_pct": row["unrealized_pnl_pct"],
                "stop_loss_price": row["stop_loss_price"],
                "take_profit_price": row["take_profit_price"],
            }

        return {
            "success": True,
            "data": position,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取持仓详情失败: {e}")
        raise HTTPException(500, "获取持仓详情失败，请稍后重试")


@router.put("/positions/{code}/stop-loss")
async def update_stop_loss(code: str, req: UpdateStopLossRequest):
    """更新止损止盈价格"""
    try:
        with _get_db() as conn:
            # 检查持仓是否存在
            cursor = conn.execute(
                "SELECT * FROM paper_positions WHERE code = ?",
                (code,)
            )
            row = cursor.fetchone()

            if not row:
                raise HTTPException(404, f"持仓不存在: {code}")

            # 更新止损止盈价格
            conn.execute(
                """UPDATE paper_positions SET
                stop_loss_price = ?, take_profit_price = ?, updated_at = ?
                WHERE code = ?""",
                (
                    req.stop_loss_price,
                    req.take_profit_price,
                    now_beijing_iso(),
                    code,
                )
            )
            conn.commit()

        return {
            "success": True,
            "message": "止损止盈价格已更新",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新止损止盈价格失败: {e}")
        raise HTTPException(500, "更新止损止盈价格失败，请稍后重试")


@router.post("/positions/{code}/close")
async def close_position(code: str, volume: Optional[int] = None):
    """平仓（全部或部分）"""
    try:
        with _get_db() as conn:
            # 检查持仓是否存在
            cursor = conn.execute(
                "SELECT * FROM paper_positions WHERE code = ?",
                (code,)
            )
            row = cursor.fetchone()

            if not row:
                raise HTTPException(404, f"持仓不存在: {code}")

            position_volume = row["volume"]
            close_volume = volume if volume else position_volume

            if close_volume > position_volume:
                raise HTTPException(400, f"平仓数量({close_volume})超过持仓数量({position_volume})")

            # 创建卖出订单
            order = _order_manager.create_order(
                code=code,
                direction=Direction.SHORT,
                order_type=OrderType.MARKET,
                volume=close_volume,
                strategy_name="manual",
                signal_reason="手动平仓",
            )

        return {
            "success": True,
            "data": order.to_dict(),
            "message": "平仓订单已创建",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"平仓失败: {e}")
        raise HTTPException(500, "平仓失败，请稍后重试")


# ────────────── 绩效 API ──────────────

@router.get("/performance")
async def get_performance(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """获取绩效统计"""
    try:
        metrics = _performance_analyzer.calculate_metrics(
            initial_cash=_config.initial_cash,
        )

        return {
            "success": True,
            "data": metrics.to_dict(),
        }
    except Exception as e:
        logger.error(f"获取绩效统计失败: {e}")
        raise HTTPException(500, "获取绩效统计失败，请稍后重试")


@router.get("/performance/daily")
async def get_daily_performance(
    days: int = Query(30, ge=1, le=365),
):
    """获取每日绩效历史"""
    try:
        with _get_db() as conn:
            start_date = (date.today() - timedelta(days=days)).isoformat()
            cursor = conn.execute(
                "SELECT * FROM paper_performance WHERE date >= ? ORDER BY date ASC",
                (start_date,)
            )
            rows = cursor.fetchall()

            performance = []
            for row in rows:
                performance.append({
                    "date": row["date"],
                    "total_equity": row["total_equity"],
                    "daily_return": row["daily_return"],
                    "cumulative_return": row["cumulative_return"],
                    "max_drawdown": row["max_drawdown"],
                    "sharpe_ratio": row["sharpe_ratio"],
                    "win_rate": row["win_rate"],
                })

        return {
            "success": True,
            "data": performance,
        }
    except Exception as e:
        logger.error(f"获取每日绩效历史失败: {e}")
        raise HTTPException(500, "获取每日绩效历史失败，请稍后重试")


# ────────────── 资金曲线 API ──────────────

@router.get("/equity-curve-v2")
async def get_equity_curve_v2(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    interval: str = Query("1d", description="1m/5m/15m/1h/1d"),
):
    """获取资金曲线（完整版）"""
    try:
        curve = _performance_analyzer.get_equity_curve(
            start_date=start_date,
            end_date=end_date,
            interval=interval,
        )

        return {
            "success": True,
            "data": curve,
        }
    except Exception as e:
        logger.error(f"获取资金曲线失败: {e}")
        raise HTTPException(500, "获取资金曲线失败，请稍后重试")


@router.get("/drawdown")
async def get_drawdown_curve(
    days: int = Query(30, ge=1, le=365),
):
    """获取回撤曲线"""
    try:
        curve = _performance_analyzer.get_drawdown_curve(days=days)

        return {
            "success": True,
            "data": curve,
        }
    except Exception as e:
        logger.error(f"获取回撤曲线失败: {e}")
        raise HTTPException(500, "获取回撤曲线失败，请稍后重试")


# ────────────── 交易历史 API ──────────────

@router.get("/trades-v2")
async def get_trades_v2(
    code: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    """获取交易历史"""
    try:
        with _get_db() as conn:
            conditions = []
            params = []

            if code:
                conditions.append("code = ?")
                params.append(code)

            if direction:
                conditions.append("direction = ?")
                params.append(direction)

            if start_date:
                conditions.append("created_at >= ?")
                params.append(start_date.isoformat())

            if end_date:
                conditions.append("created_at <= ?")
                params.append(end_date.isoformat())

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # 获取总数
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM paper_trades WHERE {where_clause}",
                params
            )
            total = cursor.fetchone()[0]

            # 获取分页数据
            offset = (page - 1) * page_size
            cursor = conn.execute(
                f"SELECT * FROM paper_trades WHERE {where_clause} "
                f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [page_size, offset]
            )
            rows = cursor.fetchall()

            trades = []
            for row in rows:
                trades.append({
                    "trade_id": row["trade_id"],
                    "order_id": row["order_id"],
                    "code": row["code"],
                    "direction": row["direction"],
                    "price": row["price"],
                    "volume": row["volume"],
                    "entry_price": row["entry_price"],
                    "profit": row["profit"],
                    "profit_pct": row["profit_pct"],
                    "commission": row["commission"],
                    "stamp_tax": row["stamp_tax"],
                    "equity_after": row["equity_after"],
                    "strategy_name": row["strategy_name"],
                    "signal_reason": row["signal_reason"],
                    "created_at": row["created_at"],
                })

        return {
            "success": True,
            "data": {
                "items": trades,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
            },
        }
    except Exception as e:
        logger.error(f"获取交易历史失败: {e}")
        raise HTTPException(500, "获取交易历史失败，请稍后重试")


@router.get("/trades-v2/stats")
async def get_trade_stats_v2(
    days: int = Query(30, ge=1, le=365),
):
    """获取交易统计"""
    try:
        with _get_db() as conn:
            start_date = (now_beijing() - timedelta(days=days)).isoformat()

            # 总交易次数
            cursor = conn.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE created_at >= ?",
                (start_date,)
            )
            total_trades = cursor.fetchone()[0]

            # 盈利交易次数
            cursor = conn.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE created_at >= ? AND profit > 0",
                (start_date,)
            )
            winning_trades = cursor.fetchone()[0]

            # 亏损交易次数
            cursor = conn.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE created_at >= ? AND profit < 0",
                (start_date,)
            )
            losing_trades = cursor.fetchone()[0]

            # 总盈亏
            cursor = conn.execute(
                "SELECT SUM(profit) FROM paper_trades WHERE created_at >= ?",
                (start_date,)
            )
            total_profit = cursor.fetchone()[0] or 0

            # 平均盈利
            cursor = conn.execute(
                "SELECT AVG(profit) FROM paper_trades WHERE created_at >= ? AND profit > 0",
                (start_date,)
            )
            avg_win = cursor.fetchone()[0] or 0

            # 平均亏损
            cursor = conn.execute(
                "SELECT AVG(ABS(profit)) FROM paper_trades WHERE created_at >= ? AND profit < 0",
                (start_date,)
            )
            avg_loss = cursor.fetchone()[0] or 0

            # 胜率
            win_rate = winning_trades / total_trades if total_trades > 0 else 0

            # 盈亏比
            profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        return {
            "success": True,
            "data": {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "total_profit": round(total_profit, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "win_rate": round(win_rate, 4),
                "profit_loss_ratio": round(profit_loss_ratio, 4),
            },
        }
    except Exception as e:
        logger.error(f"获取交易统计失败: {e}")
        raise HTTPException(500, "获取交易统计失败，请稍后重试")


@router.get("/trades-v2/export")
async def export_trades_v2(
    format: str = Query("csv", description="csv/pdf"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """导出交易记录"""
    try:
        with _get_db() as conn:
            conditions = []
            params = []

            if start_date:
                conditions.append("created_at >= ?")
                params.append(start_date.isoformat())

            if end_date:
                conditions.append("created_at <= ?")
                params.append(end_date.isoformat())

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor = conn.execute(
                f"SELECT * FROM paper_trades WHERE {where_clause} ORDER BY created_at DESC",
                params
            )
            rows = cursor.fetchall()

            trades = []
            for row in rows:
                trades.append({
                    "交易ID": row["trade_id"],
                    "订单ID": row["order_id"],
                    "股票代码": row["code"],
                    "方向": "买入" if row["direction"] == "buy" else "卖出",
                    "价格": row["price"],
                    "数量": row["volume"],
                    "入场价": row["entry_price"],
                    "盈亏": row["profit"],
                    "盈亏比例": f"{row['profit_pct']:.2f}%",
                    "佣金": row["commission"],
                    "印花税": row["stamp_tax"],
                    "交易后权益": row["equity_after"],
                    "策略名称": row["strategy_name"],
                    "信号原因": row["signal_reason"],
                    "交易时间": row["created_at"],
                })

        if format == "csv":
            # 返回CSV格式
            import csv
            import io

            output = io.StringIO()
            if trades:
                writer = csv.DictWriter(output, fieldnames=trades[0].keys())
                writer.writeheader()
                writer.writerows(trades)

            return {
                "success": True,
                "data": {
                    "format": "csv",
                    "content": output.getvalue(),
                    "filename": f"trades_{now_beijing():%Y%m%d_%H%M%S}.csv",
                },
            }
        else:
            # 返回JSON格式
            return {
                "success": True,
                "data": {
                    "format": "json",
                    "content": trades,
                    "filename": f"trades_{now_beijing():%Y%m%d_%H%M%S}.json",
                },
            }
    except Exception as e:
        logger.error(f"导出交易记录失败: {e}")
        raise HTTPException(500, "导出交易记录失败，请稍后重试")


# ────────────── 风控 API ──────────────

@router.get("/risk/events")
async def get_risk_events(
    event_type: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
):
    """获取风控事件"""
    try:
        events = _risk_manager.get_risk_events(
            event_type=event_type,
            days=days,
        )

        return {
            "success": True,
            "data": events,
        }
    except Exception as e:
        logger.error(f"获取风控事件失败: {e}")
        raise HTTPException(500, "获取风控事件失败，请稍后重试")


@router.get("/risk/rules")
async def get_risk_rules():
    """获取风控规则配置"""
    try:
        rules = _risk_manager.get_risk_rules()

        return {
            "success": True,
            "data": rules,
        }
    except Exception as e:
        logger.error(f"获取风控规则失败: {e}")
        raise HTTPException(500, "获取风控规则失败，请稍后重试")


@router.put("/risk/rules")
async def update_risk_rules(req: UpdateRiskRulesRequest):
    """更新风控规则"""
    try:
        rules = {}
        if req.max_position_pct is not None:
            rules["max_position_pct"] = req.max_position_pct
        if req.max_positions is not None:
            rules["max_positions"] = req.max_positions
        if req.max_drawdown is not None:
            rules["max_drawdown"] = req.max_drawdown
        if req.max_daily_loss is not None:
            rules["max_daily_loss"] = req.max_daily_loss

        _risk_manager.update_risk_rules(rules)

        return {
            "success": True,
            "message": "风控规则已更新",
        }
    except Exception as e:
        logger.error(f"更新风控规则失败: {e}")
        raise HTTPException(500, "更新风控规则失败，请稍后重试")


# ────────────── 月度收益热力图 API ──────────────

@router.get("/performance/monthly-heatmap")
async def get_monthly_heatmap():
    """获取月度收益热力图"""
    try:
        monthly_returns = _performance_analyzer.get_monthly_returns()

        return {
            "success": True,
            "data": monthly_returns,
        }
    except Exception as e:
        logger.error(f"获取月度收益热力图失败: {e}")
        raise HTTPException(500, "获取月度收益热力图失败，请稍后重试")


@router.get("/performance/return-distribution")
async def get_return_distribution(
    bins: int = Query(20, ge=5, le=50),
):
    """获取收益分布"""
    try:
        distribution = _performance_analyzer.get_return_distribution(bins=bins)

        return {
            "success": True,
            "data": distribution,
        }
    except Exception as e:
        logger.error(f"获取收益分布失败: {e}")
        raise HTTPException(500, "获取收益分布失败，请稍后重试")


@router.get("/performance/weekday-effect")
async def get_weekday_effect():
    """获取星期效应"""
    try:
        weekday_effect = _performance_analyzer.get_weekday_effect()

        return {
            "success": True,
            "data": weekday_effect,
        }
    except Exception as e:
        logger.error(f"获取星期效应失败: {e}")
        raise HTTPException(500, "获取星期效应失败，请稍后重试")
