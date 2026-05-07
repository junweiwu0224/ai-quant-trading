"""模拟盘启动脚本"""
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config.logging import setup_logging
from engine.paper_engine import PaperConfig, PaperEngine
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
@click.option("--codes", "-c", multiple=True, required=True, help="股票代码（可多次指定）")
@click.option("--interval", "-i", default=30, help="行情轮询间隔（秒）")
@click.option("--cash", default=1_000_000, help="初始资金")
@click.option("--no-risk", is_flag=True, help="禁用风控")
def main(strategy: str, codes: tuple, interval: int, cash: float, no_risk: bool):
    """启动模拟盘交易"""
    setup_logging()

    codes_list = list(codes)
    logger.info(f"策略: {strategy}, 标的: {codes_list}, 间隔: {interval}s, 资金: {cash:,.0f}")

    # 创建策略
    strategy_cls = STRATEGIES[strategy]
    strat = strategy_cls()

    # 配置
    config = PaperConfig(
        interval_seconds=interval,
        enable_risk=not no_risk,
    )

    # 启动
    engine = PaperEngine(
        strategy=strat,
        codes=codes_list,
        config=config,
    )

    # 如果有恢复的状态，覆盖初始资金
    if engine.portfolio.cash != cash and engine.portfolio.cash != 1_000_000:
        logger.info(f"使用恢复状态: 现金={engine.portfolio.cash:,.0f}")

    engine.run_loop()


if __name__ == "__main__":
    main()
