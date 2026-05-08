"""绩效归因分析 - Brinson 模型

分解投资组合收益为：
- 配置效应 (Allocation Effect): 行业权重偏离带来的收益
- 选择效应 (Selection Effect): 个股选择带来的收益
- 交互效应 (Interaction Effect): 配置与选择的交叉项
"""
from dataclasses import dataclass
from typing import Optional

from loguru import logger


@dataclass(frozen=True)
class SectorAttribution:
    """单个行业归因结果"""
    sector: str
    portfolio_weight: float
    benchmark_weight: float
    portfolio_return: float
    benchmark_return: float
    allocation_effect: float
    selection_effect: float
    interaction_effect: float
    total_effect: float


@dataclass(frozen=True)
class BrinsonResult:
    """Brinson 归因结果"""
    sectors: list[SectorAttribution]
    total_allocation: float
    total_selection: float
    total_interaction: float
    total_excess_return: float
    error: Optional[str] = None


def _get_sector_for_code(code: str, sector_map: dict[str, str]) -> str:
    """获取股票所属行业"""
    return sector_map.get(code, "其他")


def brinson_attribution(
    portfolio_trades: list[dict],
    portfolio_equity_curve: list[dict],
    benchmark_data: list[dict],
    sector_map: dict[str, str],
    initial_cash: float = 1_000_000,
) -> BrinsonResult:
    """Brinson 绩效归因分析

    Args:
        portfolio_trades: 交易记录列表
        portfolio_equity_curve: 权益曲线
        benchmark_data: 基准数据 [{date, close}]
        sector_map: 股票代码->行业映射
        initial_cash: 初始资金

    Returns:
        BrinsonResult
    """
    if not portfolio_trades:
        return BrinsonResult(
            sectors=[],
            total_allocation=0,
            total_selection=0,
            total_interaction=0,
            total_excess_return=0,
            error="无交易记录",
        )

    # 1. 计算各行业持仓权重和收益
    # 按行业统计持仓市值
    sector_positions: dict[str, float] = {}  # sector -> market_value
    sector_returns: dict[str, list[float]] = {}  # sector -> [returns]

    for trade in portfolio_trades:
        code = trade.get("code", "")
        sector = _get_sector_for_code(code, sector_map)
        amount = trade.get("price", 0) * trade.get("volume", 0)

        if sector not in sector_positions:
            sector_positions[sector] = 0.0
            sector_returns[sector] = []

        if trade.get("direction") == "long":
            sector_positions[sector] += amount
        else:
            sector_positions[sector] -= amount

        # 计算单笔收益
        if trade.get("entry_price") and trade.get("price"):
            ret = (trade["price"] - trade["entry_price"]) / trade["entry_price"]
            sector_returns[sector].append(ret)

    # 2. 计算行业权重
    total_market_value = sum(abs(v) for v in sector_positions.values())
    if total_market_value == 0:
        total_market_value = initial_cash

    portfolio_weights: dict[str, float] = {}
    portfolio_sector_returns: dict[str, float] = {}

    for sector, mv in sector_positions.items():
        portfolio_weights[sector] = abs(mv) / total_market_value
        returns = sector_returns.get(sector, [])
        portfolio_sector_returns[sector] = sum(returns) / len(returns) if returns else 0

    # 3. 基准权重和收益（简化：假设等权）
    all_sectors = set(portfolio_weights.keys())
    benchmark_weights: dict[str, float] = {}
    benchmark_sector_returns: dict[str, float] = {}

    # 使用基准数据计算收益
    if benchmark_data and len(benchmark_data) > 1:
        bm_start = benchmark_data[0].get("close", 1)
        bm_end = benchmark_data[-1].get("close", 1)
        bm_return = (bm_end - bm_start) / bm_start if bm_start > 0 else 0
    else:
        bm_return = 0

    # 简化处理：假设基准各行业等权，收益等于基准整体收益
    n_sectors = max(len(all_sectors), 1)
    for sector in all_sectors:
        benchmark_weights[sector] = 1.0 / n_sectors
        benchmark_sector_returns[sector] = bm_return

    # 4. 计算 Brinson 归因
    sectors = []
    total_allocation = 0.0
    total_selection = 0.0
    total_interaction = 0.0

    for sector in sorted(all_sectors):
        wp = portfolio_weights.get(sector, 0)
        wb = benchmark_weights.get(sector, 0)
        rp = portfolio_sector_returns.get(sector, 0)
        rb = benchmark_sector_returns.get(sector, 0)

        # Brinson 模型公式
        allocation = (wp - wb) * rb
        selection = wb * (rp - rb)
        interaction = (wp - wb) * (rp - rb)

        sectors.append(SectorAttribution(
            sector=sector,
            portfolio_weight=round(wp, 4),
            benchmark_weight=round(wb, 4),
            portfolio_return=round(rp * 100, 2),
            benchmark_return=round(rb * 100, 2),
            allocation_effect=round(allocation * 100, 4),
            selection_effect=round(selection * 100, 4),
            interaction_effect=round(interaction * 100, 4),
            total_effect=round((allocation + selection + interaction) * 100, 4),
        ))

        total_allocation += allocation
        total_selection += selection
        total_interaction += interaction

    total_excess = total_allocation + total_selection + total_interaction

    return BrinsonResult(
        sectors=sectors,
        total_allocation=round(total_allocation * 100, 4),
        total_selection=round(total_selection * 100, 4),
        total_interaction=round(total_interaction * 100, 4),
        total_excess_return=round(total_excess * 100, 4),
    )
