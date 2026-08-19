"""模拟盘启动脚本"""
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click
from loguru import logger

from config.logging import setup_logging
from config.settings import DB_DIR
from engine.paper_engine import PaperConfig, PaperEngine
from engine.paper_ownership import PaperOwnership
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
@click.option("--account-id", default="paper-default", show_default=True, help="Paper 账户标识")
def main(strategy: str, codes: tuple, interval: int, cash: float, account_id: str):
    """启动模拟盘交易（风控始终启用）"""
    setup_logging()

    codes_list = list(codes)
    logger.info(f"策略: {strategy}, 标的: {codes_list}, 间隔: {interval}s, 资金: {cash:,.0f}")

    ownership = PaperOwnership(DB_DIR / "worker_leases.db", account_id=account_id)
    if ownership.acquire() is None:
        ownership.close()
        raise click.ClickException(f"Paper 账户已被其他 owner 占用: {account_id}")

    engine = None
    try:
        # 创建策略
        strategy_cls = STRATEGIES[strategy]
        strat = strategy_cls()

        # Paper CLI 不提供关闭风控的旁路。
        config = PaperConfig(
            interval_seconds=interval,
            enable_risk=True,
        )

        engine = PaperEngine(
            strategy=strat,
            codes=codes_list,
            config=config,
        )
        ownership.start_renewal(on_lost=engine.stop)

        # 如果有恢复的状态，覆盖初始资金
        if engine.portfolio.cash != cash and engine.portfolio.cash != 1_000_000:
            logger.info(f"使用恢复状态: 现金={engine.portfolio.cash:,.0f}")

        engine.run_loop()
    finally:
        ownership.release()
        ownership.close()


if __name__ == "__main__":
    main()
