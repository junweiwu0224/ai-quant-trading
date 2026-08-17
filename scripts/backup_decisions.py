"""Create an explicit-path local decision backup."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click

from backup.manager import BackupError, BackupManager


def _emit(value: object) -> None:
    click.echo(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


@click.command()
@click.option("--output-dir", type=click.Path(path_type=Path), required=True, help="显式备份输出目录")
@click.option(
    "--database",
    "database_paths",
    type=click.Path(path_type=Path),
    multiple=True,
    required=True,
    help="显式 SQLite 数据库路径，可重复传入",
)
@click.option(
    "--artifact-dir",
    "artifact_dirs",
    type=click.Path(path_type=Path),
    multiple=True,
    help="显式内容附件目录，可重复传入",
)
@click.option("--metadata-json", default="{}", show_default=True, help="写入 manifest 的 JSON metadata")
@click.option("--dry-run", is_flag=True, help="只校验显式路径，不连接数据库、不复制文件")
def main(
    output_dir: Path,
    database_paths: tuple[Path, ...],
    artifact_dirs: tuple[Path, ...],
    metadata_json: str,
    dry_run: bool,
) -> None:
    """Create a local backup; no project database defaults are used."""

    manager = BackupManager()
    try:
        metadata = json.loads(metadata_json)
        if dry_run:
            result = manager.validate_inputs(output_dir, database_paths, artifact_dirs)
            result["mode"] = "dry-run"
        else:
            result = {"mode": "backup", "manifest": manager.backup(output_dir, database_paths, artifact_dirs, metadata=metadata)}
    except (BackupError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(str(exc)) from exc
    _emit(result)


if __name__ == "__main__":
    main()
