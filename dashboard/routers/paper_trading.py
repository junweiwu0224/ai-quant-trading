"""模拟盘完整API路由"""
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from config.datetime_utils import now_beijing, now_beijing_iso
from config.settings import DB_DIR
from typing import Optional
import uuid

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from engine.execution_protocol import Side
from engine.models import (
    Direction, OrderType, PaperConfig
)
from engine.order_manager import OrderManager
from engine.paper_commands import PaperCommandClient
from engine.paper_read_model import equity as paper_read_equity, positions as paper_read_positions, status as paper_read_status, trades as paper_read_trades
from engine.paper_projection import ensure_projection_schema
from engine.performance_analyzer import PerformanceAnalyzer
from engine.risk_manager import RiskManager
from utils.db import get_connection

router = APIRouter(tags=["模拟盘完整功能"])

# ────────────── 全局实例 ──────────────

_config = PaperConfig()
_order_manager = OrderManager(_config.db_path)
_performance_analyzer = PerformanceAnalyzer(_config.db_path)
_risk_manager = RiskManager(_config, _config.db_path)
_command_client = PaperCommandClient(operations_db=DB_DIR / "operations.db")


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
    """创建订单（V2 统一协议）"""
    try:
        if req.order_type != "market":
            raise ValueError("Phase 4 仅支持市价订单；限价协议尚未接入")
        side = Side.BUY if req.direction.lower() in {"buy", "long"} else Side.SELL
        idempotency_key = f"manual_order_{uuid.uuid4().hex[:16]}"
        acceptance = _command_client.enqueue_manual_order(
            instrument=req.code,
            side=side,
            quantity=req.volume,
            execution_run_id="manual",
            account_id="paper-default",
            idempotency_key=idempotency_key,
        )

        return {
            "success": True,
            "data": {
                "command_id": acceptance.command.id,
                "task_id": acceptance.task.id,
                "idempotency_key": idempotency_key,
                "status": acceptance.task.status,
                "code": req.code,
                "direction": req.direction,
                "volume": req.volume,
                "price": req.price,
            },
            "message": "订单已接受，等待 PaperWorker 执行",
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
    """Read scoped positions projection; never mutate it from the API."""
    try:
        rows = paper_read_positions(_config.db_path, "paper-default")
        return {"success": True, "data": rows, "source": "paper_ledger"}
    except Exception as e:
        logger.error(f"获取持仓列表失败: {e}")
        raise HTTPException(500, "获取持仓列表失败，请稍后重试")


@router.get("/positions/{code}")
async def get_position(code: str):
    """获取单只股票持仓详情"""
    try:
            rows = paper_read_positions(_config.db_path, "paper-default")
            row = next((item for item in rows if item["code"] == code), None)
            if not row:
                raise HTTPException(404, f"持仓不存在: {code}")
            return {"success": True, "data": row}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取持仓详情失败: {e}")
        raise HTTPException(500, "获取持仓详情失败，请稍后重试")


@router.put("/positions/{code}/stop-loss")
async def update_stop_loss(code: str, req: UpdateStopLossRequest):
    """更新止损止盈价格"""
    try:
        from engine.paper_read_model import status as paper_read_status
        run = paper_read_status(_config.db_path, "paper-default").get("execution_run_id")
        if not run:
            raise HTTPException(409, "模拟盘尚未绑定 ExecutionRun")
        with _get_db() as conn:
            conn.execute("INSERT INTO paper_position_controls(workspace_id, account_id, environment, execution_run_id, code, stop_loss_price, take_profit_price, updated_at) VALUES ('default', 'paper-default', 'paper', ?, ?, ?, ?, ?) ON CONFLICT(workspace_id, account_id, environment, execution_run_id, code) DO UPDATE SET stop_loss_price=excluded.stop_loss_price, take_profit_price=excluded.take_profit_price, updated_at=excluded.updated_at", (run, code, req.stop_loss_price, req.take_profit_price, now_beijing_iso()))
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
        rows = paper_read_positions(_config.db_path, "paper-default")
        row = next((item for item in rows if item["code"] == code), None)
        if not row:
            raise HTTPException(404, f"持仓不存在: {code}")
        position_volume = int(row["volume"])
        close_volume = int(volume or position_volume)
        if close_volume <= 0 or close_volume > position_volume:
            raise HTTPException(400, f"平仓数量({close_volume})超过持仓数量({position_volume})")
        idempotency_key = f"close_{code}_{uuid.uuid4().hex[:16]}"
        acceptance = _command_client.enqueue_manual_order(instrument=code, side=Side.SELL, quantity=close_volume, execution_run_id=paper_read_status(_config.db_path, "paper-default")["execution_run_id"], account_id="paper-default", idempotency_key=idempotency_key)
        return {"success": True, "command_id": acceptance.command.id, "task_id": acceptance.task.id, "status": acceptance.task.status, "message": "平仓订单已接受，等待 PaperWorker 执行"}
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
        rows = paper_read_equity(_config.db_path, "paper-default")
        if days > 0:
            cutoff = (now_beijing() - timedelta(days=days)).date().isoformat()
            rows = [row for row in rows if str(row.get("timestamp", ""))[:10] >= cutoff]
        performance = [{
            "date": str(row.get("timestamp", ""))[:10],
            "total_equity": row.get("equity", 0),
            "daily_return": 0,
            "cumulative_return": 0,
            "max_drawdown": row.get("drawdown", 0),
            "sharpe_ratio": 0,
            "win_rate": 0,
        } for row in rows]
        return {"success": True, "data": performance, "source": "paper_ledger"}
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
        curve = paper_read_equity(_config.db_path, "paper-default")
        if start_date:
            curve = [row for row in curve if str(row.get("timestamp", ""))[:10] >= start_date.isoformat()]
        if end_date:
            curve = [row for row in curve if str(row.get("timestamp", ""))[:10] <= end_date.isoformat()]
        return {"success": True, "data": curve, "source": "paper_ledger"}
    except Exception as e:
        logger.error(f"获取资金曲线失败: {e}")
        raise HTTPException(500, "获取资金曲线失败，请稍后重试")


@router.get("/drawdown")
async def get_drawdown_curve(
    days: int = Query(30, ge=1, le=365),
):
    """获取回撤曲线"""
    try:
        curve = paper_read_equity(_config.db_path, "paper-default")[-days:]
        peak = 0.0
        result = []
        for row in curve:
            equity = float(row.get("equity", 0))
            peak = max(peak, equity)
            result.append({"timestamp": row.get("timestamp"), "drawdown": round((peak - equity) / peak, 4) if peak else 0})
        return {"success": True, "data": result, "source": "paper_ledger"}
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
        rows = paper_read_trades(_config.db_path, "paper-default", limit=1000)
        filtered = []
        for row in rows:
            created_at = str(row.get("created_at", ""))
            if code and row.get("code") != code:
                continue
            if direction and row.get("direction") != direction:
                continue
            if start_date and created_at[:10] < start_date.isoformat():
                continue
            if end_date and created_at[:10] > end_date.isoformat():
                continue
            filtered.append({
                "trade_id": row.get("trade_id"),
                "order_id": row.get("trade_id"),
                "code": row.get("code"),
                "direction": row.get("direction"),
                "price": row.get("price", 0),
                "volume": row.get("volume", 0),
                "entry_price": 0,
                "profit": 0,
                "profit_pct": 0,
                "commission": row.get("commission", 0),
                "stamp_tax": row.get("stamp_tax", 0),
                "equity_after": 0,
                "strategy_name": "",
                "signal_reason": "",
                "created_at": created_at,
            })
        total = len(filtered)
        offset = (page - 1) * page_size
        return {"success": True, "data": {"items": filtered[offset:offset + page_size], "total": total, "page": page, "page_size": page_size, "total_pages": (total + page_size - 1) // page_size}}
    except Exception as e:
        logger.error(f"获取交易历史失败: {e}")
        raise HTTPException(500, "获取交易历史失败，请稍后重试")



@router.get("/trades-v2/stats")
async def get_trade_stats_v2(
    days: int = Query(30, ge=1, le=365),
):
    """获取交易统计"""
    try:
        rows = paper_read_trades(_config.db_path, "paper-default", limit=1000)
        cutoff = (now_beijing() - timedelta(days=days)).date().isoformat()
        rows = [row for row in rows if str(row.get("created_at", ""))[:10] >= cutoff]
        total_trades = len(rows)
        # Ledger facts do not fabricate realized P&L; that remains zero until a
        # dedicated realized-P&L projection is introduced.
        return {"success": True, "data": {"total_trades": total_trades, "winning_trades": 0, "losing_trades": 0, "total_profit": 0, "avg_win": 0, "avg_loss": 0, "win_rate": 0, "profit_loss_ratio": 0}, "source": "paper_ledger"}
    except Exception as e:
        logger.error(f"获取交易统计失败: {e}")
        raise HTTPException(500, "获取交易统计失败，请稍后重试")



@router.get("/trades-v2/export")
async def export_trades_v2(
    format: str = Query("csv", description="csv/pdf"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """导出 scoped ledger 成交记录，不读取 legacy paper_trades。"""
    try:
        rows = paper_read_trades(_config.db_path, "paper-default", limit=1000)
        records = []
        for row in rows:
            created_at = str(row.get("created_at", ""))
            if start_date and created_at[:10] < start_date.isoformat():
                continue
            if end_date and created_at[:10] > end_date.isoformat():
                continue
            records.append({
                "交易ID": row.get("trade_id"),
                "订单ID": row.get("trade_id"),
                "股票代码": row.get("code"),
                "方向": "买入" if row.get("direction") == "buy" else "卖出",
                "价格": row.get("price", 0),
                "数量": row.get("volume", 0),
                "入场价": 0,
                "盈亏": 0,
                "盈亏比例": "0.00%",
                "佣金": row.get("commission", 0),
                "印花税": row.get("stamp_tax", 0),
                "交易后权益": 0,
                "策略名称": "",
                "信号原因": "",
                "交易时间": created_at,
            })
        if format == "csv":
            import csv
            import io
            output = io.StringIO()
            if records:
                writer = csv.DictWriter(output, fieldnames=records[0].keys())
                writer.writeheader()
                writer.writerows(records)
            return {"success": True, "data": {"format": "csv", "content": output.getvalue(), "filename": f"trades_{now_beijing():%Y%m%d_%H%M%S}.csv"}, "source": "paper_ledger"}
        return {"success": True, "data": {"format": "json", "content": records, "filename": f"trades_{now_beijing():%Y%m%d_%H%M%S}.json"}, "source": "paper_ledger"}
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
