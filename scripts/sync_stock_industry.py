"""Synchronize missing local stock industry metadata."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click

from config.logging import setup_logging
from data.sync.stock_industry import sync_stock_industries


def parse_codes(values: Sequence[str]) -> list[str]:
    codes: list[str] = []
    for value in values:
        for part in str(value or "").split(","):
            code = part.strip()
            if code:
                codes.append(code)
    return codes


@click.command()
@click.option("--codes", "-c", multiple=True, help="股票代码，可重复或逗号分隔；不填则扫描 stock_info 全量空行业")
@click.option("--batch-size", default=80, show_default=True, type=int, help="每批行业接口查询股票数")
@click.option("--dry-run", is_flag=True, help="只预览可补齐数量，不写入数据库")
def main(codes: tuple[str, ...], batch_size: int, dry_run: bool) -> None:
    """补齐 stock_info 中缺失的行业字段。"""
    setup_logging()
    summary = sync_stock_industries(
        codes=parse_codes(codes) or None,
        batch_size=batch_size,
        dry_run=dry_run,
    )
    click.echo(
        "summary: "
        f"target={summary.target_count} fetched={summary.fetched_count} "
        f"filled={summary.filled_count} updated={summary.updated_count} "
        f"dry_run={summary.dry_run}"
    )
    missing = [item for item in summary.items if item["status"] != "filled"]
    for item in missing[:20]:
        click.echo(f"[{item['code']}] missing industry")
    if len(missing) > 20:
        click.echo(f"... {len(missing) - 20} more missing")


if __name__ == "__main__":
    main()
