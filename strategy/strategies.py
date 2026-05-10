"""共享策略注册表 — 消除 backtest / optimization 重复定义"""
from strategy.dual_ma import DualMAStrategy
from strategy.bollinger import BollingerStrategy
from strategy.momentum import MomentumStrategy
from strategy.rsi import RSIStrategy
from strategy.macd import MACDStrategy
from strategy.kdj import KDJStrategy

STRATEGIES = {
    "dual_ma": DualMAStrategy,
    "bollinger": BollingerStrategy,
    "momentum": MomentumStrategy,
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "kdj": KDJStrategy,
}
