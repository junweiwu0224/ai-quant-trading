"""Shared CLI helpers for AI signal daily coverage synchronization."""
from __future__ import annotations

from typing import Sequence

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


def run_signal_daily_sync(
    codes: tuple[str, ...],
    count: int,
    limit: int,
    generate_predictions: bool,
    min_success: int,
    source: str,
) -> None:
    setup_logging()
    target_codes = parse_codes(codes) or None
    summary = sync_qlib_daily(
        codes=target_codes,
        count=count,
        limit=limit,
        generate_predictions_cache=generate_predictions,
        min_success=min_success,
        status_source=source,
    )

    for item in summary.items:
        if item.success:
            click.echo(
                f"[{item.code}] rows={item.rows} written={item.written} latest={item.latest_date}"
            )
        else:
            click.echo(f"[{item.code}] failed: {item.error}")

    click.echo(f"summary: success={summary.success_count} fail={summary.fail_count}")
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
            f"AI signal daily sync below threshold: success={summary.success_count}, "
            f"fail={summary.fail_count}, min_success={min_success}"
        )
