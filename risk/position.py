"""仓位管理"""
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from strategy.base import Portfolio


@dataclass(frozen=True)
class PositionLimit:
    """仓位限制配置"""
    max_single_pct: float = 0.20      # 单票仓位上限 20%
    max_industry_pct: float = 0.40    # 行业集中度上限 40%
    max_total_positions: int = 10     # 最大持仓数
    min_trade_volume: int = 100       # 最小交易单位（A股1手=100股）


class PositionManager:
    """仓位管理器"""

    def __init__(self, limit: Optional[PositionLimit] = None):
        self._limit = limit or PositionLimit()

    def check_buy(
        self,
        code: str,
        price: float,
        volume: int,
        portfolio: Portfolio,
        prices: dict[str, float],
        industry_map: Optional[dict[str, str]] = None,
    ) -> tuple[bool, str]:
        """检查买入是否符合仓位规则

        Returns:
            (通过, 原因)
        """
        # 最小交易单位
        if volume < self._limit.min_trade_volume:
            return False, f"交易量 {volume} 低于最小单位 {self._limit.min_trade_volume}"

        if volume % self._limit.min_trade_volume != 0:
            return False, f"交易量 {volume} 不是 {self._limit.min_trade_volume} 的整数倍"

        total_equity = portfolio.get_total_equity(prices)
        if total_equity <= 0:
            return False, "总权益为零或负数"

        # 单票仓位上限
        buy_value = price * volume
        current_value = portfolio.get_position(code) * prices.get(code, 0)
        new_single_value = current_value + buy_value
        single_pct = new_single_value / total_equity

        if single_pct > self._limit.max_single_pct:
            return False, (
                f"单票仓位 {single_pct:.1%} 超过上限 {self._limit.max_single_pct:.0%}，"
                f"当前持有 {current_value:,.0f}，买入 {buy_value:,.0f}，总权益 {total_equity:,.0f}"
            )

        # 行业集中度
        if industry_map and code in industry_map:
            industry = industry_map[code]
            industry_value = new_single_value
            for c, pos in portfolio.positions.items():
                if c != code and industry_map.get(c) == industry and pos > 0:
                    industry_value += pos * prices.get(c, 0)
            industry_pct = industry_value / total_equity

            if industry_pct > self._limit.max_industry_pct:
                return False, (
                    f"行业 {industry} 集中度 {industry_pct:.1%} 超过上限 "
                    f"{self._limit.max_industry_pct:.0%}"
                )

        # 最大持仓数
        active_positions = sum(1 for v in portfolio.positions.values() if v > 0)
        if active_positions >= self._limit.max_total_positions and portfolio.get_position(code) == 0:
            return False, f"持仓数 {active_positions} 已达上限 {self._limit.max_total_positions}"

        return True, "通过"

    def calc_max_volume(
        self,
        code: str,
        price: float,
        portfolio: Portfolio,
        prices: dict[str, float],
    ) -> int:
        """计算单票可买最大手数"""
        total_equity = portfolio.get_total_equity(prices)
        if total_equity <= 0 or price <= 0:
            return 0

        current_value = portfolio.get_position(code) * prices.get(code, 0)
        max_value = total_equity * self._limit.max_single_pct - current_value
        if max_value <= 0:
            return 0

        max_shares = int(max_value / price)
        max_lots = max_shares // self._limit.min_trade_volume
        return max_lots * self._limit.min_trade_volume

    def calc_volatility_position(
        self,
        price: float,
        atr: float,
        total_equity: float,
        risk_per_trade: float = 0.01,
    ) -> int:
        """基于 ATR 波动率计算仓位

        Args:
            price: 当前价格
            atr: ATR 值
            total_equity: 总权益
            risk_per_trade: 单笔风险比例（默认 1%）

        Returns:
            建议买入股数（100的整数倍）
        """
        if atr <= 0 or price <= 0 or total_equity <= 0:
            return 0

        risk_amount = total_equity * risk_per_trade
        shares = int(risk_amount / atr)
        lots = shares // self._limit.min_trade_volume
        return lots * self._limit.min_trade_volume
