"""Generate a historical local-Qlib prediction cache from stock_daily."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click

from config.logging import setup_logging
from config.settings import DB_PATH, QLIB_PRED_CACHE
from data.qlib.predictor import FULL_UNIVERSE_PREDICTION_LIMIT, generate_historical_predictions


@click.command()
@click.option("--db-path", type=click.Path(path_type=Path), default=DB_PATH, show_default=True, help="quant.db 路径")
@click.option("--cache-path", type=click.Path(path_type=Path), default=QLIB_PRED_CACHE, show_default=True, help="预测缓存输出路径")
@click.option("--start", "start_date", required=True, help="历史预测开始日期，YYYY-MM-DD")
@click.option("--end", "end_date", required=True, help="历史预测结束日期，YYYY-MM-DD")
@click.option("--lookback", default=60, show_default=True, type=int, help="每个预测日向前看的交易日数量")
@click.option("--limit", default=FULL_UNIVERSE_PREDICTION_LIMIT, show_default=True, type=int, help="每天最多写入的股票数量")
@click.option("--min-history-days", default=20, show_default=True, type=int, help="单只股票生成分数所需最少历史天数")
@click.option("--min-universe-size", default=2, show_default=True, type=int, help="每天最少可评分股票数")
def main(
    db_path: Path,
    cache_path: Path,
    start_date: str,
    end_date: str,
    lookback: int,
    limit: int,
    min_history_days: int,
    min_universe_size: int,
) -> None:
    """生成覆盖回测区间的逐日 Qlib 分数缓存。"""
    setup_logging()
    summary = generate_historical_predictions(
        db_path=db_path,
        cache_path=cache_path,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback,
        limit=limit,
        min_history_days=min_history_days,
        min_universe_size=min_universe_size,
    )
    click.echo(
        "historical predictions: "
        f"success={summary.success} latest={summary.latest_date} "
        f"total={summary.total} cache={summary.cache_path}"
    )
    if summary.message:
        click.echo(f"message: {summary.message}")
    if not summary.success:
        raise click.ClickException(summary.message or "historical prediction generation failed")


if __name__ == "__main__":
    main()
