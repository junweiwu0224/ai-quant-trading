"""Audit local stock_info metadata integrity without modifying the database."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import click

from config.settings import DB_PATH, PROJECT_ROOT
from config.logging import setup_logging
from data.storage.storage import DataStorage, STOCK_INFO_CLEANUP_CONFIRMATION


def _file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_test_results_path(path: Path, message: str) -> Path:
    resolved = path.resolve()
    test_results_dir = (PROJECT_ROOT / "test-results").resolve()
    if not resolved.is_relative_to(test_results_dir):
        raise click.ClickException(message)
    return resolved


def _create_cleanup_backup(source_path: Path, output_path: Path | None = None) -> dict[str, str]:
    source = source_path.resolve()
    if not source.exists():
        raise click.ClickException(f"真实数据库不存在: {source}")
    output = output_path or Path("test-results/data-display-audit/stock-info-cleanup-backup.db")
    backup_path = _ensure_test_results_path(output, "backup output 必须位于 test-results 目录下")
    if backup_path == source:
        raise click.ClickException("backup output 不能指向真实数据库")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, backup_path)
    return {
        "source": str(source),
        "path": str(backup_path),
        "sha256": _file_sha256(source),
    }


@click.command()
@click.option("--sample-limit", default=20, show_default=True, type=int, help="每类问题最多展示样本数")
@click.option("--json", "as_json", is_flag=True, help="输出完整 JSON 摘要")
@click.option("--cleanup-preview", is_flag=True, help="只读预演可清理的历史错前缀重复行")
@click.option("--cleanup-apply", is_flag=True, help="执行错前缀重复行合并删除；必须同时传入确认词")
@click.option("--shadow-apply", is_flag=True, help="复制当前数据库到影子库后在副本上执行清理")
@click.option(
    "--shadow-output",
    type=click.Path(path_type=Path),
    default=Path("test-results/data-display-audit/stock-info-shadow-cleanup.db"),
    show_default=True,
    help="影子清理数据库副本输出路径",
)
@click.option("--confirm", default="", help="执行清理所需确认词")
def main(
    sample_limit: int,
    as_json: bool,
    cleanup_preview: bool,
    cleanup_apply: bool,
    shadow_apply: bool,
    shadow_output: Path,
    confirm: str,
) -> None:
    """只读审计 stock_info 的重复代码、错误前缀和行业覆盖。"""
    setup_logging()
    if shadow_apply:
        if confirm != STOCK_INFO_CLEANUP_CONFIRMATION:
            raise click.ClickException(f"必须传入 --confirm {STOCK_INFO_CLEANUP_CONFIRMATION}")
        source_path = DB_PATH.resolve()
        shadow_path = _ensure_test_results_path(shadow_output, "shadow output 必须位于 test-results 目录下")
        if shadow_path == source_path:
            raise click.ClickException("shadow output 不能指向真实数据库")
        if not source_path.exists():
            raise click.ClickException(f"真实数据库不存在: {source_path}")

        source_hash_before = _file_sha256(source_path)
        shadow_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, shadow_path)
        result = DataStorage(db_url=f"sqlite:///{shadow_path}").cleanup_stock_info_wrong_prefix_duplicates(
            apply=True,
            confirmation=confirm,
            sample_limit=sample_limit,
        )
        source_hash_after = _file_sha256(source_path)
        result = {
            **result,
            "shadow": {
                "source": str(source_path),
                "output": str(shadow_path),
                "original_untouched": source_hash_before == source_hash_after,
            },
        }
        if as_json:
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
            return
        post_audit = result.get("post_audit") or {}
        click.echo(
            "shadow apply: "
            f"source={source_path} output={shadow_path} "
            f"original_untouched={result['shadow']['original_untouched']} "
            f"candidates={result['candidate_count']} merged_fields={result['merged_field_count']} "
            f"deleted_rows={result['deleted_row_count']} skipped={result['skipped_count']} "
            f"wrong_prefix_after={post_audit.get('wrong_prefix_count')}"
        )
        return

    storage = DataStorage()
    if cleanup_apply:
        if confirm != STOCK_INFO_CLEANUP_CONFIRMATION:
            raise click.ClickException(f"必须传入 --confirm {STOCK_INFO_CLEANUP_CONFIRMATION}")
        backup = _create_cleanup_backup(DB_PATH)
        result = storage.cleanup_stock_info_wrong_prefix_duplicates(
            apply=True,
            confirmation=confirm,
            sample_limit=sample_limit,
        )
        result = {**result, "backup": backup}
        if as_json:
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
            return
        click.echo(
            "cleanup apply: "
            f"mode={result['mode']} candidates={result['candidate_count']} "
            f"merged_fields={result['merged_field_count']} "
            f"deleted_rows={result['deleted_row_count']} skipped={result['skipped_count']} "
            f"backup={backup['path']}"
        )
        for item in (result.get("changes") or [])[:sample_limit]:
            merged = ",".join(item.get("merged_fields") or []) or "-"
            click.echo(f"- deleted {item['code']} keep {item['keep_code']} merged={merged}")
        return

    if cleanup_preview:
        preview = storage.preview_stock_info_cleanup(sample_limit=sample_limit)
        if as_json:
            click.echo(json.dumps(preview, ensure_ascii=False, indent=2))
            return
        click.echo(
            "cleanup preview: "
            f"mode={preview['mode']} scope={preview['scope']} "
            f"candidates={preview['candidate_count']} ready={preview['cleanup_ready_count']} "
            f"merge_required={preview['merge_required_count']} "
            f"skipped_no_canonical={preview['skipped_no_canonical_count']}"
        )
        for item in (preview.get("candidates") or [])[:sample_limit]:
            click.echo(
                f"- {item['action']} {item['code']} keep {item['keep_code']} "
                f"reason={item['reason']}"
            )
        return

    audit = storage.audit_stock_info_integrity(sample_limit=sample_limit)
    if as_json:
        click.echo(json.dumps(audit, ensure_ascii=False, indent=2))
        return

    click.echo(
        "summary: "
        f"rows={audit['total_rows']} distinct={audit['distinct_plain_count']} "
        f"duplicates={audit['duplicate_plain_count']} extra_rows={audit['duplicate_extra_row_count']} "
        f"wrong_prefix={audit['wrong_prefix_count']} legacy_plain={audit['legacy_plain_count']} "
        f"raw_blank_industry={audit['blank_industry_count']} "
        f"merged_blank_industry={audit['merged_blank_industry_count']}"
    )

    wrong_prefix_examples = audit.get("wrong_prefix_examples") or []
    if wrong_prefix_examples:
        click.echo("wrong prefix examples:")
        for item in wrong_prefix_examples[:sample_limit]:
            click.echo(f"- {item['code']} -> {item['expected_code']}")

    duplicate_groups = audit.get("duplicate_groups") or []
    if duplicate_groups:
        click.echo("duplicate examples:")
        for item in duplicate_groups[:sample_limit]:
            click.echo(f"- {item['plain_code']}: {', '.join(item['codes'])}")

    merged_blank_examples = audit.get("merged_blank_industry_examples") or []
    if merged_blank_examples:
        click.echo("merged blank industry examples:")
        for item in merged_blank_examples[:sample_limit]:
            click.echo(f"- {item['plain_code']} {item.get('name') or ''}".rstrip())


if __name__ == "__main__":
    main()
