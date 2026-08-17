"""Verify or restore an explicit-path local decision backup."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click

from backup.manager import BackupError, BackupManager


@click.command()
@click.option("--backup-dir", type=click.Path(path_type=Path), required=True, help="显式备份目录")
@click.option("--target-dir", type=click.Path(path_type=Path), required=False, help="显式隔离恢复目录（restore 必填）")
@click.option("--verify-only", is_flag=True, help="只校验 manifest、hash 和 SQLite 可读性")
@click.option("--dry-run", is_flag=True, help="等同于 verify-only，不创建恢复目录")
@click.option("--replay-decision-id", default="", help="恢复后只读重放指定 decision_id 的确定性报告")
def main(
    backup_dir: Path,
    target_dir: Path | None,
    verify_only: bool,
    dry_run: bool,
    replay_decision_id: str,
) -> None:
    """Verify or restore without connecting notification/provider services."""

    try:
        verification_only = verify_only or dry_run
        if not verification_only and target_dir is None:
            raise BackupError("--target-dir is required unless --verify-only or --dry-run is set")
        result = BackupManager().restore(
            backup_dir,
            target_dir,
            verify_only=verification_only,
            replay_decision_id=replay_decision_id or None,
        )
        result["mode"] = "dry-run" if dry_run else ("verify" if verify_only else "restore")
    except (BackupError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
