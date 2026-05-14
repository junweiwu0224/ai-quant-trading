"""持仓与风控 API — 增强版"""
import asyncio
import csv
import io
import json
import os
import statistics
import tempfile
from datetime import date, datetime, timedelta
from enum import Enum
from math import sqrt
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from config.settings import LOG_DIR
from config.datetime_utils import now_beijing, now_beijing_iso, now_beijing_str, today_beijing, today_beijing_compact
from data.storage.storage import DataStorage
from data.collector.cache import TTLCache

router = APIRouter()

# ── TTL 缓存 ──
_portfolio_cache = TTLCache(max_size=200)


def _atomic_write(path: Path, content: str):
    """原子写入文件（先写临时文件，再 rename，防止并发写入损坏）"""
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise

_storage: Optional[DataStorage] = None


def _get_storage() -> DataStorage:
    global _storage
    if _storage is None:
        _storage = DataStorage()
    return _storage

INITIAL_EQUITY = 50000


# ══════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════

class PositionAction(str, Enum):
    NEW = "new"
    ADD = "add"
    REDUCE = "reduce"
    CLOSE = "close"


class PositionInfo(BaseModel):
    """持仓详情（扩展版）"""
    code: str
    name: str = ''
    volume: int
    avg_price: float
    current_price: float = 0
    market_value: float = 0
    pnl: float = 0
    pnl_pct: float = 0
    daily_pnl: float = 0
    daily_pnl_pct: float = 0
    position_pct: float = 0
    entry_date: str = ''
    holding_days: int = 0
    stop_loss_price: float = 0
    take_profit_price: float = 0
    stop_loss_triggered: bool = False
    take_profit_triggered: bool = False
    strategy_name: str = ''
    last_action: str = ''
    last_action_time: str = ''
    cost_amount: float = 0
    industry: str = ''
    pre_close: float = 0
    change_pct: float = 0
    turnover_rate: float = 0
    pe_ratio: float = 0
    pb_ratio: float = 0
    dividend_yield: float = 0


class StopLossInfo(BaseModel):
    code: str
    stop_loss_price: float = 0
    take_profit_price: float = 0
    stop_loss_pct: float = 0
    take_profit_pct: float = 0
    trailing_high: float = 0
    atr_stop_price: float = 0
    triggered: bool = False
    trigger_reason: str = ''


class RiskIndicators(BaseModel):
    var_95: float = 0
    var_99: float = 0
    volatility: float = 0
    beta: float = 0
    alpha: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0
    information_ratio: float = 0


class BenchmarkComparison(BaseModel):
    benchmark_code: str = "000300"
    benchmark_name: str = "沪深300"
    benchmark_return: float = 0
    portfolio_return: float = 0
    excess_return: float = 0
    tracking_error: float = 0


class CapitalUtilization(BaseModel):
    total_equity: float = 0
    cash: float = 0
    market_value: float = 0
    utilization_rate: float = 0
    cash_rate: float = 0
    position_count: int = 0
    max_single_pct: float = 0
    max_industry_pct: float = 0


class CorrelationItem(BaseModel):
    code_a: str
    code_b: str
    correlation: float = 0


class PortfolioSnapshot(BaseModel):
    """完整持仓快照"""
    cash: float = 0
    market_value: float = 0
    total_equity: float = 0
    positions: list[PositionInfo] = []
    total_pnl: float = 0
    total_pnl_pct: float = 0
    daily_pnl: float = 0
    daily_pnl_pct: float = 0
    cumulative_return: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    initial_equity: float = INITIAL_EQUITY
    risk: RiskIndicators = Field(default_factory=RiskIndicators)
    benchmark: BenchmarkComparison = Field(default_factory=BenchmarkComparison)
    capital: CapitalUtilization = Field(default_factory=CapitalUtilization)
    stop_loss_alerts: list[StopLossInfo] = []
    update_time: str = ''


class TradeRecord(BaseModel):
    time: str = ''
    code: str = ''
    direction: str = ''
    price: float = 0
    volume: int = 0
    entry_price: float = 0
    trade_id: int = 0
    equity: float = 0
    strategy_name: str = ''
    pnl: float = 0
    pnl_pct: float = 0
    commission: float = 0
    tax: float = 0


class TradeListResponse(BaseModel):
    trades: list[TradeRecord] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class StrategyGroup(BaseModel):
    strategy_name: str
    position_count: int = 0
    total_value: float = 0
    total_pnl: float = 0
    total_pnl_pct: float = 0
    positions: list[PositionInfo] = []


class ClosePositionRequest(BaseModel):
    code: str
    volume: Optional[int] = None


class BulkCloseRequest(BaseModel):
    codes: list[str] = []


# ══════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════

async def _load_equity_history() -> list[dict]:
    hit, cached = _portfolio_cache.get("equity_history")
    if hit:
        return cached
    history_file = LOG_DIR / "paper" / "equity_history.jsonl"
    if not history_file.exists():
        return []
    try:
        content = await asyncio.to_thread(history_file.read_text)
    except OSError:
        return []
    records = []
    for line in content.strip().split("\n"):
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    _portfolio_cache.set("equity_history", records, 300)  # 5 分钟
    return records


def _calc_metrics(history: list[dict]) -> tuple[float, float, float, float]:
    """计算累计收益率、当日盈亏、最大回撤、夏普比率"""
    if not history or len(history) < 2:
        return 0, 0, 0, 0

    equities = [r["equity"] for r in history]
    initial = equities[0]
    current = equities[-1]

    cum_return = (current - initial) / initial if initial > 0 else 0
    daily_pnl = current - equities[-2]

    peak = equities[0]
    max_dd = 0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

    returns = [(equities[i] - equities[i - 1]) / equities[i - 1] for i in range(1, len(equities)) if equities[i - 1] > 0]
    if len(returns) >= 2:
        mean_r = statistics.mean(returns)
        std_r = statistics.stdev(returns)
        sharpe = (mean_r - 0.02 / 252) / std_r * (252 ** 0.5) if std_r > 0 else 0
    else:
        sharpe = 0

    return cum_return, daily_pnl, max_dd, sharpe


def _calc_risk_indicators(
    history: list[dict],
    lookback_days: int = 60,
    benchmark_returns: list[float] | None = None,
) -> RiskIndicators:
    """计算高级风险指标"""
    if len(history) < 10:
        return RiskIndicators()

    equities = [r["equity"] for r in history[-lookback_days:]]
    returns = [(equities[i] - equities[i - 1]) / equities[i - 1]
               for i in range(1, len(equities)) if equities[i - 1] > 0]

    if len(returns) < 5:
        return RiskIndicators()

    mean_r = statistics.mean(returns)
    std_r = statistics.stdev(returns)
    annual_vol = std_r * sqrt(252)

    sharpe = (mean_r - 0.03 / 252) / std_r * sqrt(252) if std_r > 0 else 0

    downside = [r for r in returns if r < 0]
    downside_std = statistics.stdev(downside) if len(downside) >= 2 else 0
    sortino = (mean_r / downside_std * sqrt(252)) if downside_std > 0 else 0

    peak = equities[0]
    max_dd = 0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

    days = len(equities)
    annual_return = (equities[-1] / equities[0]) ** (252 / max(days, 1)) - 1 if days > 1 else 0
    calmar = annual_return / max_dd if max_dd > 0 else 0

    sorted_returns = sorted(returns)
    idx_95 = max(0, int(len(sorted_returns) * 0.05) - 1)
    idx_99 = max(0, int(len(sorted_returns) * 0.01) - 1)
    var_95 = abs(sorted_returns[idx_95]) if sorted_returns else 0
    var_99 = abs(sorted_returns[idx_99]) if sorted_returns else 0

    # Alpha / Beta / Information Ratio (需要基准收益率)
    alpha = beta = info_ratio = 0.0
    if benchmark_returns and len(benchmark_returns) >= 5:
        min_len = min(len(returns), len(benchmark_returns))
        port = returns[:min_len]
        bm = benchmark_returns[:min_len]
        excess = [p - b for p, b in zip(port, bm)]
        alpha = sum(excess) / len(excess) * 252
        cov_pb = sum((p - statistics.mean(port)) * (b - statistics.mean(bm)) for b, p in zip(bm, port)) / len(port)
        var_bm = sum((b - statistics.mean(bm)) ** 2 for b in bm) / len(bm)
        beta = cov_pb / var_bm if var_bm > 0 else 0
        te = statistics.stdev(excess) if len(excess) >= 2 else 0
        info_ratio = (statistics.mean(excess) / te * sqrt(252)) if te > 0 else 0

    return RiskIndicators(
        var_95=round(var_95, 4),
        var_99=round(var_99, 4),
        volatility=round(annual_vol, 4),
        max_drawdown=round(max_dd, 4),
        sharpe_ratio=round(sharpe, 2),
        sortino_ratio=round(sortino, 2),
        calmar_ratio=round(calmar, 2),
        beta=round(beta, 2),
        alpha=round(alpha, 4),
        information_ratio=round(info_ratio, 2),
    )


async def _fetch_benchmark_closes(count: int) -> list[float]:
    """获取沪深300收盘价序列（5 分钟缓存）"""
    cache_key = f"bm_closes:{count}"
    hit, cached = _portfolio_cache.get(cache_key)
    if hit:
        return cached
    try:
        import time as _time
        from urllib.request import Request, urlopen

        url = (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            "?secid=1.000300"
            "&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
            "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt=101&fqt=1&end=20500101&lmt={count + 10}"
            f"&_={int(_time.time() * 1000)}"
        )
        req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com"})

        def _do():
            with urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())

        data = await asyncio.to_thread(_do)
        klines = data.get("data", {}).get("klines", [])
        if klines and len(klines) >= 2:
            result = [float(k.split(",")[2]) for k in klines]
            _portfolio_cache.set(cache_key, result, 300)
            return result
    except Exception:
        pass
    return []


async def _calc_benchmark_comparison(history: list[dict]) -> BenchmarkComparison:
    """基准对比（沪深300），自行获取基准数据"""
    bm_closes = await _fetch_benchmark_closes(len(history))
    return _calc_benchmark_comparison_from_closes_sync(history, bm_closes)


def _calc_benchmark_comparison_from_closes_sync(history: list[dict], bm_closes: list[float]) -> BenchmarkComparison:
    """基准对比（使用已获取的基准收盘价序列）"""
    if len(history) < 2:
        return BenchmarkComparison()

    portfolio_return = (history[-1]["equity"] - history[0]["equity"]) / history[0]["equity"]

    if bm_closes and len(bm_closes) >= 2:
        benchmark_return = (bm_closes[-1] - bm_closes[0]) / bm_closes[0]
        excess_return = portfolio_return - benchmark_return

        bm_returns = [(bm_closes[i] - bm_closes[i - 1]) / bm_closes[i - 1]
                      for i in range(1, len(bm_closes))]
        eqs = [r["equity"] for r in history]
        port_returns = [(eqs[i] - eqs[i - 1]) / eqs[i - 1]
                       for i in range(1, len(eqs)) if eqs[i - 1] > 0]
        min_len = min(len(port_returns), len(bm_returns))
        if min_len > 1:
            excess = [p - b for p, b in zip(port_returns[:min_len], bm_returns[:min_len])]
            avg_excess = sum(excess) / len(excess)
            tracking_error = (sum((e - avg_excess) ** 2 for e in excess) / len(excess)) ** 0.5 * (252 ** 0.5)
        else:
            tracking_error = 0

        return BenchmarkComparison(
            benchmark_return=round(benchmark_return, 4),
            portfolio_return=round(portfolio_return, 4),
            excess_return=round(excess_return, 4),
            tracking_error=round(tracking_error, 4),
        )

    return BenchmarkComparison(portfolio_return=round(portfolio_return, 4))


async def _load_paper_state(state_dir: str = str(LOG_DIR / "paper")) -> Optional[dict]:
    """加载模拟盘状态，文件不存在时返回默认初始状态"""
    state_file = Path(state_dir) / "portfolio_state.json"
    if not state_file.exists():
        return {"cash": 50000.0, "positions": {}, "avg_prices": {}, "trade_count": 0, "entry_dates": {}}
    try:
        content = await asyncio.to_thread(state_file.read_text)
        return json.loads(content)
    except (json.JSONDecodeError, OSError):
        return {"cash": 50000.0, "positions": {}, "avg_prices": {}, "trade_count": 0, "entry_dates": {}}


async def _load_trades_today(state_dir: str = str(LOG_DIR / "paper")) -> list[dict]:
    """加载今日交易记录"""
    log_file = Path(state_dir) / f"trades_{now_beijing():%Y%m%d}.jsonl"
    if not log_file.exists():
        return []
    try:
        content = await asyncio.to_thread(log_file.read_text)
    except OSError:
        return []
    trades = []
    for line in content.strip().split("\n"):
        if line:
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return trades


def _get_current_price(code: str) -> float:
    """获取最新收盘价（fallback）"""
    try:
        df = _get_storage().get_stock_daily(code)
        if not df.empty:
            return float(df.iloc[-1]["close"])
    except Exception as e:
        logger.warning(f"获取{code}价格失败: {e}")
    return 0.0


def _get_stock_names() -> dict[str, str]:
    """获取代码→名称映射（10 分钟缓存）"""
    hit, cached = _portfolio_cache.get("stock_names")
    if hit:
        return cached
    try:
        df = _get_storage().get_stock_list()
        if not df.empty:
            result = dict(zip(df["code"], df["name"]))
            _portfolio_cache.set("stock_names", result, 600)
            return result
    except Exception as e:
        logger.warning(f"获取股票名称映射失败: {e}")
    return {}


def _get_industry_map() -> dict[str, str]:
    """获取代码→行业映射（10 分钟缓存）"""
    hit, cached = _portfolio_cache.get("industry_map")
    if hit:
        return cached
    try:
        df = _get_storage().get_stock_list()
        if not df.empty:
            result = dict(zip(df["code"], df["industry"]))
            _portfolio_cache.set("industry_map", result, 600)
            return result
    except Exception:
        pass
    return {}


# ══════════════════════════════════════════
# 核心 API
# ══════════════════════════════════════════

@router.get("/snapshot", response_model=PortfolioSnapshot)
async def get_portfolio():
    """获取当前持仓快照（增强版）"""
    state = await _load_paper_state()
    if not state:
        return PortfolioSnapshot()

    positions = []
    total_mv = 0
    total_pnl = 0
    name_map = _get_stock_names()
    industry_map = _get_industry_map()

    # 优先使用 QuoteService 实时行情
    quote_map: dict = {}
    try:
        from data.collector.quote_service import get_quote_service
        qs = get_quote_service()
        quote_map = qs.get_all_quotes()
    except Exception:
        pass

    # 先算总权益
    cash = state.get("cash", 0)
    for code, vol in state.get("positions", {}).items():
        q = quote_map.get(code)
        if q and q.price > 0:
            total_mv += q.price * vol
        else:
            avg = state.get("avg_prices", {}).get(code, 0)
            price = _get_current_price(code) or avg
            total_mv += price * vol
    total_equity = cash + total_mv

    # 止损配置
    from risk.stoploss import StopLossConfig
    sl_config = StopLossConfig()

    for code, vol in state.get("positions", {}).items():
        avg_price = state.get("avg_prices", {}).get(code, 0)

        q = quote_map.get(code)
        if q and q.price > 0:
            current_price = q.price
            pre_close = q.pre_close
            change_pct = q.change_pct
            pe = q.pe_ratio
            pb = q.pb_ratio
            turnover = q.turnover_rate
            dividend = q.dividend_yield
        else:
            current_price = _get_current_price(code) or avg_price
            pre_close = current_price
            change_pct = 0
            pe = pb = turnover = dividend = 0

        mv = current_price * vol
        pnl = (current_price - avg_price) * vol
        pnl_pct = (current_price - avg_price) / avg_price if avg_price > 0 else 0
        daily_pnl = (current_price - pre_close) * vol if pre_close > 0 else 0
        daily_pnl_pct = (current_price - pre_close) / pre_close if pre_close > 0 else 0
        position_pct = mv / total_equity if total_equity > 0 else 0

        entry_date = state.get("entry_dates", {}).get(code, "")
        holding_days = 0
        if entry_date:
            try:
                holding_days = (date.today() - date.fromisoformat(entry_date)).days
            except ValueError:
                pass

        sl_info = state.get("stop_losses", {}).get(code, {})
        stop_loss_price = sl_info.get("stop_loss", round(avg_price * (1 - sl_config.fixed_stop_pct), 3))
        take_profit_price = sl_info.get("take_profit", round(avg_price * (1 + sl_config.take_profit_pct), 3))
        stop_loss_triggered = current_price <= stop_loss_price if stop_loss_price > 0 else False
        take_profit_triggered = current_price >= take_profit_price if take_profit_price > 0 else False

        action_info = state.get("position_actions", {}).get(code, {})
        strategy_name = state.get("strategies", {}).get(code, "")

        positions.append(PositionInfo(
            code=code,
            name=name_map.get(code, ''),
            volume=vol,
            avg_price=round(avg_price, 3),
            current_price=round(current_price, 3),
            market_value=round(mv, 2),
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 4),
            daily_pnl=round(daily_pnl, 2),
            daily_pnl_pct=round(daily_pnl_pct, 4),
            position_pct=round(position_pct, 4),
            entry_date=entry_date,
            holding_days=holding_days,
            stop_loss_price=round(stop_loss_price, 3),
            take_profit_price=round(take_profit_price, 3),
            stop_loss_triggered=stop_loss_triggered,
            take_profit_triggered=take_profit_triggered,
            strategy_name=strategy_name,
            last_action=action_info.get("action", ""),
            last_action_time=action_info.get("time", ""),
            cost_amount=round(avg_price * vol, 2),
            industry=industry_map.get(code, ""),
            pre_close=round(pre_close, 3),
            change_pct=round(change_pct, 4),
            turnover_rate=round(turnover, 2),
            pe_ratio=round(pe, 2),
            pb_ratio=round(pb, 2),
            dividend_yield=round(dividend, 2),
        ))
        total_mv += 0  # already calculated
        total_pnl += pnl

    # CapitalUtilization
    capital = CapitalUtilization(
        total_equity=round(total_equity, 2),
        cash=round(cash, 2),
        market_value=round(mv_total := sum(p.market_value for p in positions), 2),
        utilization_rate=round(mv_total / total_equity, 4) if total_equity > 0 else 0,
        cash_rate=round(cash / total_equity, 4) if total_equity > 0 else 0,
        position_count=len(positions),
        max_single_pct=round(max((p.position_pct for p in positions), default=0), 4),
    )

    # RiskIndicators + BenchmarkComparison（共用基准数据，避免双重请求）
    history = await _load_equity_history()
    bm_closes = await _fetch_benchmark_closes(len(history))
    bm_returns = [(bm_closes[i] - bm_closes[i - 1]) / bm_closes[i - 1]
                  for i in range(1, len(bm_closes))] if bm_closes and len(bm_closes) >= 2 else None
    risk = _calc_risk_indicators(history, benchmark_returns=bm_returns)
    benchmark = _calc_benchmark_comparison_from_closes_sync(history, bm_closes)

    # StopLossInfo alerts
    stop_loss_alerts = [
        StopLossInfo(
            code=p.code,
            stop_loss_price=p.stop_loss_price,
            take_profit_price=p.take_profit_price,
            triggered=True,
            trigger_reason="止损触发" if p.stop_loss_triggered else "止盈触发",
        )
        for p in positions if p.stop_loss_triggered or p.take_profit_triggered
    ]

    cum_return, daily_pnl_val, max_dd, sharpe = _calc_metrics(history)
    daily_pnl_pct_val = daily_pnl_val / (total_equity - daily_pnl_val) if (total_equity - daily_pnl_val) > 0 else 0

    return PortfolioSnapshot(
        cash=round(cash, 2),
        market_value=round(sum(p.market_value for p in positions), 2),
        total_equity=round(total_equity, 2),
        positions=positions,
        total_pnl=round(total_pnl, 2),
        total_pnl_pct=round(total_pnl / (total_equity - total_pnl), 4) if (total_equity - total_pnl) > 0 else 0,
        daily_pnl=round(daily_pnl_val, 2),
        daily_pnl_pct=round(daily_pnl_pct_val, 4),
        cumulative_return=round(cum_return, 4),
        max_drawdown=round(max_dd, 4),
        sharpe_ratio=round(sharpe, 2),
        initial_equity=INITIAL_EQUITY,
        risk=risk,
        benchmark=benchmark,
        capital=capital,
        stop_loss_alerts=stop_loss_alerts,
        update_time=now_beijing_iso(),
    )


# ══════════════════════════════════════════
# 交易记录
# ══════════════════════════════════════════

@router.get("/trades")
async def get_trades():
    """获取今日交易记录"""
    return await _load_trades_today()


@router.get("/trades/recent")
async def get_recent_trades(limit: int = 20):
    """获取最近N笔交易（跨日期）"""
    state_dir = Path(str(LOG_DIR / "paper"))
    all_trades = []
    for f in sorted(state_dir.glob("trades_*.jsonl"), reverse=True):
        try:
            content = await asyncio.to_thread(f.read_text)
        except OSError:
            continue
        for line in content.strip().split("\n"):
            if line:
                try:
                    all_trades.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if len(all_trades) >= limit:
            break
    trades = sorted(all_trades, key=lambda t: t.get("time", ""), reverse=True)[:limit]
    # 补充股票名称
    try:
        df = _get_storage().get_stock_list()
        name_map = dict(zip(df["code"], df["name"])) if not df.empty else {}
        for t in trades:
            t["name"] = name_map.get(t.get("code", ""), "")
    except Exception:
        pass
    return trades


@router.get("/trades/history", response_model=TradeListResponse)
async def get_trade_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    code: Optional[str] = None,
    direction: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    """跨日期分页交易记录"""
    state_dir = Path(str(LOG_DIR / "paper"))
    all_trades = []

    for f in sorted(state_dir.glob("trades_*.jsonl")):
        file_date_str = f.stem.replace("trades_", "")
        if start_date and file_date_str < start_date.replace("-", ""):
            continue
        if end_date and file_date_str > end_date.replace("-", ""):
            continue

        try:
            content = await asyncio.to_thread(f.read_text)
        except OSError:
            continue
        for line in content.strip().split("\n"):
            if not line:
                continue
            try:
                trade = json.loads(line)
                if code and trade.get("code") != code:
                    continue
                if direction and trade.get("direction") != direction:
                    continue
                if trade.get("direction") == "short" and trade.get("entry_price", 0) > 0:
                    trade["pnl"] = round((trade["price"] - trade["entry_price"]) * trade["volume"], 2)
                    trade["pnl_pct"] = round((trade["price"] - trade["entry_price"]) / trade["entry_price"], 4) if trade["entry_price"] > 0 else 0
                all_trades.append(trade)
            except json.JSONDecodeError:
                continue

    all_trades.sort(key=lambda t: t.get("time", ""), reverse=True)
    total = len(all_trades)
    start_idx = (page - 1) * page_size
    page_trades = all_trades[start_idx:start_idx + page_size]

    return TradeListResponse(
        trades=[TradeRecord(**{k: t.get(k, v) for k, v in TradeRecord().model_dump().items()}) for t in page_trades],
        total=total,
        page=page,
        page_size=page_size,
    )


# ══════════════════════════════════════════
# 风控与风险
# ══════════════════════════════════════════

@router.get("/risk")
async def get_risk():
    """获取风控状态"""
    state = await _load_paper_state()
    if not state:
        return {"status": "无数据"}

    cash = state.get("cash", 0)
    positions = state.get("positions", {})
    total_mv = sum(state.get("avg_prices", {}).get(c, 0) * v for c, v in positions.items())
    total_equity = cash + total_mv

    position_details = []
    for code, vol in positions.items():
        avg = state.get("avg_prices", {}).get(code, 0)
        mv = avg * vol
        pct = mv / total_equity if total_equity > 0 else 0
        position_details.append({
            "code": code,
            "volume": vol,
            "value": round(mv, 2),
            "pct": round(pct, 4),
        })

    return {
        "total_equity": round(total_equity, 2),
        "cash": round(cash, 2),
        "cash_pct": round(cash / total_equity, 4) if total_equity > 0 else 0,
        "position_count": len(positions),
        "positions": position_details,
    }


@router.get("/risk/advanced")
async def get_risk_advanced(lookback_days: int = 60):
    """高级风险指标"""
    history = await _load_equity_history()
    bm_closes = await _fetch_benchmark_closes(len(history))
    bm_returns = [(bm_closes[i] - bm_closes[i - 1]) / bm_closes[i - 1]
                  for i in range(1, len(bm_closes))] if bm_closes and len(bm_closes) >= 2 else None
    return _calc_risk_indicators(history, lookback_days, benchmark_returns=bm_returns)


@router.get("/drawdown-curve")
async def get_drawdown_curve():
    """回撤曲线时间序列"""
    history = await _load_equity_history()
    if not history:
        return []

    result = []
    peak = 0
    for point in history:
        eq = point.get("equity", 0)
        if eq > peak:
            peak = eq
        dd_pct = (-(peak - eq) / peak * 100) if peak > 0 else 0
        result.append({
            "date": point.get("date", ""),
            "drawdown_pct": round(dd_pct, 4),
            "equity": eq,
        })
    return result


# ══════════════════════════════════════════
# 权益与基准
# ══════════════════════════════════════════

@router.get("/equity-history")
async def get_equity_history(days: int = 0):
    """获取权益历史数据（days>0 时只返回最近 N 天）"""
    history_file = LOG_DIR / "paper" / "equity_history.jsonl"
    if not history_file.exists():
        return []
    content = await asyncio.to_thread(history_file.read_text)
    records = []
    for line in content.strip().split("\n"):
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if days > 0 and len(records) > days:
        records = records[-days:]
    return records


@router.get("/benchmark")
async def get_benchmark(days: int = 60):
    """基准对比"""
    history = await _load_equity_history()
    return await _calc_benchmark_comparison(history[-days:] if days else history)


@router.get("/capital-utilization")
async def get_capital_utilization():
    """资金利用率"""
    snapshot = await get_portfolio()
    return snapshot.capital


# ══════════════════════════════════════════
# 行业与策略
# ══════════════════════════════════════════

@router.get("/industry-distribution")
async def get_industry_distribution():
    """获取持仓行业分布"""
    state = await _load_paper_state()
    if not state:
        return []

    positions = state.get("positions", {})
    if not positions:
        return []

    try:
        industry_map = _get_industry_map()
        industry_data = {}
        for code, vol in positions.items():
            avg_price = state.get("avg_prices", {}).get(code, 0)
            current_price = _get_current_price(code)
            if current_price <= 0:
                current_price = avg_price
            mv = current_price * vol

            industry = industry_map.get(code, "未知") or "未知"
            if industry not in industry_data:
                industry_data[industry] = {"industry": industry, "count": 0, "value": 0}
            industry_data[industry]["count"] += 1
            industry_data[industry]["value"] += mv

        return sorted(industry_data.values(), key=lambda x: x["value"], reverse=True)
    except Exception as e:
        logger.error(f"行业分布查询失败: {e}")
        return []


@router.get("/strategies")
async def get_strategy_groups():
    """按策略分组的持仓"""
    snapshot = await get_portfolio()
    groups: dict[str, list[PositionInfo]] = {}

    for p in snapshot.positions:
        key = p.strategy_name or "未分配"
        groups.setdefault(key, []).append(p)

    result = []
    for name, positions in groups.items():
        total_value = sum(p.market_value for p in positions)
        total_pnl = sum(p.pnl for p in positions)
        total_cost = sum(p.cost_amount for p in positions)
        result.append(StrategyGroup(
            strategy_name=name,
            position_count=len(positions),
            total_value=round(total_value, 2),
            total_pnl=round(total_pnl, 2),
            total_pnl_pct=round(total_pnl / total_cost, 4) if total_cost > 0 else 0,
            positions=positions,
        ))

    return sorted(result, key=lambda g: g.total_value, reverse=True)


@router.get("/correlation")
async def get_correlation(lookback_days: int = 60):
    """持仓相关性矩阵"""
    state = await _load_paper_state()
    if not state or not state.get("positions"):
        return []

    codes = list(state["positions"].keys())
    if len(codes) < 2:
        return []

    storage = _get_storage()
    end = date.today()
    start = end - timedelta(days=lookback_days * 2)

    returns_by_code: dict[str, list[float]] = {}
    for code in codes:
        try:
            df = storage.get_stock_daily(code)
            if df.empty or len(df) < 10:
                continue
            closes = df["close"].tolist()
            rets = [(closes[i] - closes[i - 1]) / closes[i - 1]
                    for i in range(1, len(closes)) if closes[i - 1] > 0]
            returns_by_code[code] = rets
        except Exception:
            continue

    result = []
    valid_codes = list(returns_by_code.keys())
    for i in range(len(valid_codes)):
        for j in range(i + 1, len(valid_codes)):
            ra = returns_by_code[valid_codes[i]]
            rb = returns_by_code[valid_codes[j]]
            min_len = min(len(ra), len(rb))
            if min_len < 5:
                continue
            ra_trim = ra[:min_len]
            rb_trim = rb[:min_len]
            mean_a = statistics.mean(ra_trim)
            mean_b = statistics.mean(rb_trim)
            cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(ra_trim, rb_trim)) / min_len
            std_a = statistics.stdev(ra_trim)
            std_b = statistics.stdev(rb_trim)
            corr = cov / (std_a * std_b) if std_a > 0 and std_b > 0 else 0
            result.append(CorrelationItem(
                code_a=valid_codes[i],
                code_b=valid_codes[j],
                correlation=round(corr, 4),
            ))

    return result


# ══════════════════════════════════════════
# 搜索与筛选
# ══════════════════════════════════════════

@router.get("/search")
async def search_positions(
    q: str = "",
    industry: Optional[str] = None,
    strategy: Optional[str] = None,
    sort_by: str = "market_value",
    sort_order: str = "desc",
):
    """持仓搜索/筛选"""
    snapshot = await get_portfolio()
    positions = snapshot.positions

    if q:
        q_lower = q.lower()
        positions = [p for p in positions
                     if q_lower in p.code.lower() or q_lower in p.name.lower()]

    if industry:
        positions = [p for p in positions if p.industry == industry]

    if strategy:
        positions = [p for p in positions if p.strategy_name == strategy]

    reverse = sort_order == "desc"
    valid_sort_fields = {
        "market_value", "pnl", "pnl_pct", "daily_pnl", "daily_pnl_pct",
        "position_pct", "holding_days", "current_price", "volume",
    }
    if sort_by in valid_sort_fields:
        positions.sort(key=lambda p: getattr(p, sort_by, 0), reverse=reverse)

    return positions


# ══════════════════════════════════════════
# 平仓操作
# ══════════════════════════════════════════

@router.post("/close")
async def close_position(req: ClosePositionRequest):
    """单只/部分平仓"""
    from dashboard.routers.paper_control import _manager
    if not _manager.is_running or not _manager._engine:
        raise HTTPException(409, "模拟盘未运行")

    engine = _manager._engine
    portfolio = engine.portfolio
    code = req.code
    vol = portfolio.positions.get(code, 0)

    if vol <= 0:
        raise HTTPException(400, f"未持有 {code}")

    sell_vol = min(req.volume or vol, vol)

    try:
        from data.collector.quote_service import get_quote_service
        quote = get_quote_service().get_quote(code)
        price = quote.price if quote and quote.price > 0 else _get_current_price(code)
    except Exception:
        price = _get_current_price(code)

    if price <= 0:
        raise HTTPException(400, f"无法获取 {code} 当前价格")

    engine._strategy.sell(code, price, sell_vol)
    return {"message": f"已提交卖出 {code} {sell_vol}股 @ {price:.2f}"}


@router.post("/close-all")
async def close_all_positions(req: BulkCloseRequest):
    """批量/全部平仓"""
    from dashboard.routers.paper_control import _manager
    if not _manager.is_running or not _manager._engine:
        raise HTTPException(409, "模拟盘未运行")

    engine = _manager._engine
    portfolio = engine.portfolio
    codes = req.codes if req.codes else [c for c, v in portfolio.positions.items() if v > 0]

    try:
        from data.collector.quote_service import get_quote_service
        qs = get_quote_service()
    except Exception:
        qs = None

    results = []
    for code in codes:
        vol = portfolio.positions.get(code, 0)
        if vol <= 0:
            continue
        quote = qs.get_quote(code) if qs else None
        price = quote.price if quote and quote.price > 0 else _get_current_price(code)
        if price > 0:
            engine._strategy.sell(code, price, vol)
            results.append({"code": code, "volume": vol, "price": round(price, 2)})

    return {"message": f"已提交 {len(results)} 笔卖出委托", "orders": results}


# ══════════════════════════════════════════
# 止损止盈设置
# ══════════════════════════════════════════

class StopLossUpdateRequest(BaseModel):
    code: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@router.post("/stoploss")
async def update_stoploss(req: StopLossUpdateRequest):
    """更新止损止盈价格"""
    state = await _load_paper_state()
    if not state:
        raise HTTPException(404, "无持仓状态")

    state_dir = Path(str(LOG_DIR / "paper"))
    state_file = state_dir / "portfolio_state.json"

    stop_losses = state.get("stop_losses", {})
    if req.code not in stop_losses:
        stop_losses[req.code] = {}

    if req.stop_loss is not None:
        stop_losses[req.code]["stop_loss"] = req.stop_loss
    if req.take_profit is not None:
        stop_losses[req.code]["take_profit"] = req.take_profit

    state["stop_losses"] = stop_losses
    _atomic_write(state_file, json.dumps(state, ensure_ascii=False, indent=2))

    return {"message": f"已更新 {req.code} 止损止盈", "stop_losses": stop_losses[req.code]}


# ══════════════════════════════════════════
# 导出
# ══════════════════════════════════════════

@router.get("/export")
async def export_portfolio(
    format: str = "csv",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """导出持仓和交易数据"""
    snapshot = await get_portfolio()

    if format == "json":
        trades = await _load_trades_today()
        data = {
            "snapshot": snapshot.model_dump(),
            "trades": trades,
        }
        content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=portfolio.json"},
        )
    else:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "代码", "名称", "持仓量", "成本价", "现价", "市值",
            "盈亏", "盈亏%", "当日盈亏", "持仓占比", "建仓日期",
            "持仓天数", "止损价", "止盈价", "行业", "策略",
        ])
        for p in snapshot.positions:
            writer.writerow([
                p.code, p.name, p.volume, p.avg_price, p.current_price,
                p.market_value, p.pnl, f"{p.pnl_pct:.2%}", p.daily_pnl,
                f"{p.position_pct:.2%}", p.entry_date, p.holding_days,
                p.stop_loss_price, p.take_profit_price, p.industry,
                p.strategy_name,
            ])
        content = buf.getvalue()
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8-sig")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=portfolio.csv"},
        )


# ══════════════════════════════════════════
# 持仓快照
# ══════════════════════════════════════════

@router.get("/snapshots")
async def get_snapshots(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 30,
):
    """历史持仓快照列表"""
    snapshot_file = LOG_DIR / "paper" / "portfolio_snapshots.jsonl"
    if not snapshot_file.exists():
        return {"snapshots": [], "total": 0}

    try:
        content = await asyncio.to_thread(snapshot_file.read_text)
    except OSError:
        return {"snapshots": [], "total": 0}

    records = []
    for line in content.strip().split("\n"):
        if line:
            try:
                rec = json.loads(line)
                d = rec.get("date", "")
                if start_date and d < start_date:
                    continue
                if end_date and d > end_date:
                    continue
                records.append(rec)
            except json.JSONDecodeError:
                continue

    records.sort(key=lambda r: r.get("date", ""), reverse=True)
    total = len(records)
    start_idx = (page - 1) * page_size
    page_records = records[start_idx:start_idx + page_size]

    return {"snapshots": page_records, "total": total, "page": page, "page_size": page_size}


@router.post("/snapshots/save")
async def save_snapshot():
    """手动保存当前持仓快照"""
    state = await _load_paper_state()
    if not state:
        raise HTTPException(404, "无持仓状态")

    snapshot_file = LOG_DIR / "paper" / "portfolio_snapshots.jsonl"
    today_str = date.today().isoformat()

    entry = {
        "date": today_str,
        "time": now_beijing_iso(),
        "cash": state.get("cash", 0),
        "positions": dict(state.get("positions", {})),
        "avg_prices": dict(state.get("avg_prices", {})),
    }

    content = json.dumps(entry, ensure_ascii=False) + "\n"
    await asyncio.to_thread(lambda: _append_file(snapshot_file, content))

    return {"message": f"快照已保存 ({today_str})"}


def _append_file(path: Path, content: str):
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)
