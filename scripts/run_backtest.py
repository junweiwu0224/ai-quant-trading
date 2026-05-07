"""回测入口"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from config.logging import setup_logging
from engine.backtest_engine import BacktestEngine, BacktestConfig
from strategy.dual_ma import DualMAStrategy
from strategy.bollinger import BollingerStrategy
from strategy.momentum import MomentumStrategy

STRATEGIES = {
    "dual_ma": DualMAStrategy,
    "bollinger": BollingerStrategy,
    "momentum": MomentumStrategy,
}


@click.command()
@click.option("--code", "-c", default="000001", help="股票代码")
@click.option("--strategy", "-s", default="dual_ma", type=click.Choice(STRATEGIES.keys()), help="策略名称")
@click.option("--start", default="20240101", help="起始日期 (YYYYMMDD)")
@click.option("--end", default="20260507", help="结束日期 (YYYYMMDD)")
@click.option("--cash", default=1000000, type=float, help="初始资金")
def backtest(code, strategy, start, end, cash):
    """运行回测"""
    setup_logging()

    config = BacktestConfig(initial_cash=cash)
    engine = BacktestEngine(config)
    strat = STRATEGIES[strategy]()

    result = engine.run(strat, [code], start, end)

    print("\n=== 回测报告 ===")
    for k, v in result.summary().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    backtest()
