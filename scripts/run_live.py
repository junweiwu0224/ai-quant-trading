"""实盘交易启动脚本"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config.logging import setup_logging
from engine.broker import SimulatedBroker
from engine.live_engine import LiveConfig, LiveTradingEngine
from strategy.dual_ma import DualMAStrategy
from strategy.bollinger import BollingerStrategy
from strategy.momentum import MomentumStrategy

STRATEGIES = {
    "dual_ma": DualMAStrategy,
    "bollinger": BollingerStrategy,
    "momentum": MomentumStrategy,
}


@click.command()
@click.option("--strategy", "-s", type=click.Choice(STRATEGIES.keys()), default="dual_ma", help="策略名称")
@click.option("--codes", "-c", multiple=True, required=True, help="股票代码")
@click.option("--interval", "-i", default=30, help="轮询间隔（秒）")
@click.option("--cash", default=1_000_000, help="初始资金（模拟盘）")
@click.option("--live", is_flag=True, help="实盘模式（V2 Live disabled）")
def main(strategy: str, codes: tuple, interval: int, cash: float, live: bool):
    """启动实盘/模拟盘交易"""
    if live:
        raise click.ClickException("V2 Live disabled")

    setup_logging()

    codes_list = list(codes)
    logger.info(f"[模拟盘] 策略: {strategy}, 标的: {codes_list}, 间隔: {interval}s")

    strategy_cls = STRATEGIES[strategy]
    strat = strategy_cls()

    config = LiveConfig(
        interval_seconds=interval,
        enable_risk=True,
        dry_run=True,
    )

    broker = SimulatedBroker(initial_cash=cash)

    engine = LiveTradingEngine(
        strategy=strat,
        codes=codes_list,
        broker=broker,
        config=config,
    )

    engine.run_loop()


if __name__ == "__main__":
    main()
