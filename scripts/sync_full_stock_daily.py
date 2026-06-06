"""Synchronize full-market stock_daily coverage."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click

from config.logging import setup_logging
from data.sync.full_stock_daily import sync_full_stock_daily


def parse_codes(values: Sequence[str]) -> list[str]:
    codes: list[str] = []
    for value in values:
        for part in str(value or "").split(","):
            code = part.strip()
            if code:
                codes.append(code)
    return codes


@click.command()
@click.option("--codes", "-c", multiple=True, help="股票代码，可重复或逗号分隔；不填则同步 stock_info 全量")
@click.option("--count", default=260, show_default=True, type=int, help="每只股票拉取最近 N 根日线")
@click.option("--limit", default=0, show_default=True, type=int, help="最多同步 N 只股票；0 表示全量")
@click.option("--skip-existing", is_flag=True, help="跳过已有任意日线的股票")
@click.option("--no-update-existing", is_flag=True, help="不更新已有日期的 OHLCV/成交额")
@click.option("--progress-every", default=25, show_default=True, type=int, help="每处理 N 只写一次状态文件")
@click.option("--sleep", "sleep_sec", default=0.0, show_default=True, type=float, help="每只股票之间的暂停秒数")
@click.option("--workers", default=6, show_default=True, type=int, help="并发抓取线程数，写库仍在主线程顺序执行")
def main(
    codes: tuple[str, ...],
    count: int,
    limit: int,
    skip_existing: bool,
    no_update_existing: bool,
    progress_every: int,
    sleep_sec: float,
    workers: int,
) -> None:
    """补齐 stock_daily 全市场覆盖。"""
    setup_logging()
    target_codes = parse_codes(codes) or None
    summary = sync_full_stock_daily(
        codes=target_codes,
        count=count,
        limit=limit,
        skip_existing=skip_existing,
        update_existing=not no_update_existing,
        progress_every=progress_every,
        sleep_sec=sleep_sec,
        workers=workers,
    )

    click.echo(
        "summary: "
        f"target={summary.target_count} success={summary.success_count} fail={summary.fail_count} "
        f"snapshot={summary.snapshot_count} duration={summary.duration_sec}s"
    )
    coverage = summary.coverage
    click.echo(
        "coverage: "
        f"stock_info={coverage.get('stock_count')} "
        f"daily={coverage.get('daily_covered')} "
        f"pct={coverage.get('coverage_pct')}% "
        f"latest={coverage.get('latest_date')} "
        f"latest_daily={coverage.get('latest_date_covered')}"
    )
    failed = [item for item in summary.items if not item.success]
    for item in failed[:20]:
        click.echo(f"[{item.code}] failed: {item.error}")
    if len(failed) > 20:
        click.echo(f"... {len(failed) - 20} more failures in status file")
    if not summary.success:
        raise click.ClickException(f"full stock_daily sync incomplete: fail={summary.fail_count}")


if __name__ == "__main__":
    main()
