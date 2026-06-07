"""Sync representative A-share daily bars for AI signal coverage."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click

from scripts.signal_daily_sync_cli import parse_codes, run_signal_daily_sync


@click.command()
@click.option("--codes", "-c", multiple=True, help="股票代码，可重复或逗号分隔")
@click.option("--count", default=260, show_default=True, type=int, help="每只股票拉取的日线条数")
@click.option("--limit", default=80, show_default=True, type=int, help="默认 AI 信号覆盖池最多同步股票数")
@click.option("--generate-predictions", is_flag=True, help="同步后生成 AI 信号缓存")
@click.option("--min-success", default=2, show_default=True, type=int, help="生成信号所需最少成功股票数")
def main(codes: tuple[str, ...], count: int, limit: int, generate_predictions: bool, min_success: int) -> None:
    """同步 AI 信号覆盖池所需的代表性 A 股日线。"""
    run_signal_daily_sync(
        codes=codes,
        count=count,
        limit=limit,
        generate_predictions=generate_predictions,
        min_success=min_success,
        source="signal_cli",
    )


if __name__ == "__main__":
    main()
