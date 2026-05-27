"""Sync representative A-share daily bars for local Qlib coverage."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click

from config.logging import setup_logging
from data.qlib.daily_sync import sync_qlib_daily


def parse_codes(values: Sequence[str]) -> list[str]:
    codes: list[str] = []
    for value in values:
        for part in str(value or "").split(","):
            code = part.strip()
            if code:
                codes.append(code)
    return codes


@click.command()
@click.option("--codes", "-c", multiple=True, help="股票代码，可重复或逗号分隔")
@click.option("--count", default=260, show_default=True, type=int, help="每只股票拉取的日线条数")
@click.option("--limit", default=80, show_default=True, type=int, help="默认覆盖池最多同步股票数")
@click.option("--generate-predictions", is_flag=True, help="同步后生成 Qlib 预测缓存")
@click.option("--min-success", default=2, show_default=True, type=int, help="生成预测所需最少成功股票数")
def main(codes: tuple[str, ...], count: int, limit: int, generate_predictions: bool, min_success: int) -> None:
    """同步 Qlib 机会池所需的代表性 A 股日线。"""
    setup_logging()
    target_codes = parse_codes(codes) or None
    summary = sync_qlib_daily(
        codes=target_codes,
        count=count,
        limit=limit,
        generate_predictions_cache=generate_predictions,
        min_success=min_success,
    )

    for item in summary.items:
        if item.success:
            click.echo(
                f"[{item.code}] rows={item.rows} written={item.written} latest={item.latest_date}"
            )
        else:
            click.echo(f"[{item.code}] failed: {item.error}")

    click.echo(
        f"summary: success={summary.success_count} fail={summary.fail_count}"
    )
    if summary.prediction_success is not None:
        click.echo(
            "predictions: "
            f"success={summary.prediction_success} "
            f"latest={summary.prediction_latest_date} "
            f"total={summary.prediction_total}"
        )
        if summary.prediction_message:
            click.echo(f"prediction_message: {summary.prediction_message}")

    if not summary.success:
        raise click.ClickException(
            f"Qlib daily sync below threshold: success={summary.success_count}, "
            f"fail={summary.fail_count}, min_success={min_success}"
        )


if __name__ == "__main__":
    main()
