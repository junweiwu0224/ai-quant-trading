import json
from pathlib import Path

from click.testing import CliRunner

from scripts.audit_stock_info import _create_cleanup_backup, _file_sha256, main


def test_audit_stock_info_cli_prints_json_summary(monkeypatch):
    class FakeStorage:
        def audit_stock_info_integrity(self, sample_limit=20):
            return {
                "total_rows": 2,
                "distinct_plain_count": 1,
                "duplicate_plain_count": 1,
                "duplicate_extra_row_count": 1,
                "wrong_prefix_count": 1,
                "legacy_plain_count": 0,
                "blank_industry_count": 1,
                "merged_blank_industry_count": 0,
                "duplicate_groups": [
                    {
                        "plain_code": "920000",
                        "expected_code": "bj920000",
                        "row_count": 2,
                        "codes": ["sz920000", "bj920000"],
                    }
                ],
                "wrong_prefix_examples": [
                    {"code": "sz920000", "plain_code": "920000", "expected_code": "bj920000"}
                ],
            }

    monkeypatch.setattr("scripts.audit_stock_info.DataStorage", lambda: FakeStorage())

    result = CliRunner().invoke(main, ["--json", "--sample-limit", "1"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["duplicate_plain_count"] == 1
    assert payload["wrong_prefix_examples"] == [
        {"code": "sz920000", "plain_code": "920000", "expected_code": "bj920000"}
    ]


def test_audit_stock_info_cli_prints_cleanup_preview(monkeypatch):
    class FakeStorage:
        def preview_stock_info_cleanup(self, sample_limit=20):
            return {
                "mode": "preview_only",
                "scope": "wrong_prefix_duplicates",
                "candidate_count": 1,
                "cleanup_ready_count": 1,
                "merge_required_count": 0,
                "skipped_no_canonical_count": 0,
                "candidates": [
                    {
                        "plain_code": "920000",
                        "code": "sz920000",
                        "keep_code": "bj920000",
                        "action": "delete_duplicate_row",
                        "reason": "wrong_prefix_duplicate",
                        "cleanup_ready": True,
                        "unique_fields": [],
                    }
                ],
            }

    monkeypatch.setattr("scripts.audit_stock_info.DataStorage", lambda: FakeStorage())

    result = CliRunner().invoke(main, ["--cleanup-preview", "--sample-limit", "1"])

    assert result.exit_code == 0
    assert "cleanup preview: mode=preview_only scope=wrong_prefix_duplicates candidates=1 ready=1 merge_required=0 skipped_no_canonical=0" in result.output
    assert "- delete_duplicate_row sz920000 keep bj920000 reason=wrong_prefix_duplicate" in result.output


def test_audit_stock_info_cli_rejects_cleanup_apply_without_confirmation(monkeypatch):
    class FakeStorage:
        def cleanup_stock_info_wrong_prefix_duplicates(self, **kwargs):
            raise AssertionError("cleanup should not run without confirmation")

    monkeypatch.setattr("scripts.audit_stock_info.DataStorage", lambda: FakeStorage())

    result = CliRunner().invoke(main, ["--cleanup-apply"])

    assert result.exit_code != 0
    assert "必须传入 --confirm MERGE_AND_DELETE_STOCK_INFO_DUPLICATES" in result.output


def test_audit_stock_info_cli_applies_cleanup_with_explicit_confirmation(monkeypatch):
    calls = {}
    source_db = Path("data/db/quant.db")
    backup_db = Path("test-results/data-display-audit/stock-info-cleanup-backup.db")

    class FakeStorage:
        def cleanup_stock_info_wrong_prefix_duplicates(self, **kwargs):
            calls.update(kwargs)
            return {
                "mode": "applied",
                "applied": True,
                "candidate_count": 2,
                "merged_field_count": 3,
                "deleted_row_count": 2,
                "skipped_count": 0,
                "post_audit": {"wrong_prefix_count": 0, "duplicate_extra_row_count": 0},
                "changes": [
                    {"code": "sz920000", "keep_code": "bj920000", "merged_fields": ["name"], "deleted": True}
                ],
            }

    monkeypatch.setattr("scripts.audit_stock_info.DataStorage", lambda: FakeStorage())
    monkeypatch.setattr("scripts.audit_stock_info.DB_PATH", source_db)
    monkeypatch.setattr("scripts.audit_stock_info._create_cleanup_backup", lambda source_path, output_path=None: {
        "source": str(source_db.resolve()),
        "path": str(backup_db.resolve()),
        "sha256": "abc123",
    })

    result = CliRunner().invoke(
        main,
        [
            "--cleanup-apply",
            "--confirm",
            "MERGE_AND_DELETE_STOCK_INFO_DUPLICATES",
            "--sample-limit",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert calls == {
        "apply": True,
        "confirmation": "MERGE_AND_DELETE_STOCK_INFO_DUPLICATES",
        "sample_limit": 1,
    }
    assert "cleanup apply: mode=applied candidates=2 merged_fields=3 deleted_rows=2 skipped=0" in result.output
    assert f"backup={backup_db.resolve()}" in result.output
    assert "- deleted sz920000 keep bj920000 merged=name" in result.output


def test_audit_stock_info_cli_shadow_apply_copies_db_and_applies_only_to_shadow(monkeypatch, tmp_path):
    source_db = tmp_path / "source.db"
    source_db.write_bytes(b"sqlite shadow source")
    shadow_db = tmp_path / "test-results" / "shadow.db"
    created_urls = []

    class FakeStorage:
        def __init__(self, db_url=None):
            created_urls.append(db_url)

        def cleanup_stock_info_wrong_prefix_duplicates(self, **kwargs):
            assert created_urls[-1] == f"sqlite:///{shadow_db}"
            return {
                "mode": "applied",
                "applied": True,
                "candidate_count": 2,
                "merged_field_count": 3,
                "deleted_row_count": 2,
                "skipped_count": 0,
                "post_audit": {"wrong_prefix_count": 0, "duplicate_extra_row_count": 0},
                "changes": [],
            }

    monkeypatch.setattr("scripts.audit_stock_info.DB_PATH", source_db)
    monkeypatch.setattr("scripts.audit_stock_info.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("scripts.audit_stock_info.DataStorage", FakeStorage)

    result = CliRunner().invoke(
        main,
        [
            "--shadow-apply",
            "--shadow-output",
            str(shadow_db),
            "--confirm",
            "MERGE_AND_DELETE_STOCK_INFO_DUPLICATES",
        ],
    )

    assert result.exit_code == 0
    assert created_urls == [f"sqlite:///{shadow_db}"]
    assert shadow_db.read_bytes() == b"sqlite shadow source"
    assert "shadow apply: source=" in result.output
    assert "original_untouched=True" in result.output
    assert "wrong_prefix_after=0" in result.output


def test_audit_stock_info_cli_shadow_apply_requires_confirmation(monkeypatch, tmp_path):
    source_db = tmp_path / "source.db"
    source_db.write_bytes(b"sqlite shadow source")

    monkeypatch.setattr("scripts.audit_stock_info.DB_PATH", source_db)

    result = CliRunner().invoke(main, ["--shadow-apply"])

    assert result.exit_code != 0
    assert "必须传入 --confirm MERGE_AND_DELETE_STOCK_INFO_DUPLICATES" in result.output


def test_audit_stock_info_cli_shadow_apply_rejects_output_outside_test_results(monkeypatch, tmp_path):
    source_db = tmp_path / "source.db"
    source_db.write_bytes(b"sqlite shadow source")
    outside_output = tmp_path / "outside.db"

    monkeypatch.setattr("scripts.audit_stock_info.DB_PATH", source_db)
    monkeypatch.setattr("scripts.audit_stock_info.PROJECT_ROOT", tmp_path)

    result = CliRunner().invoke(
        main,
        [
            "--shadow-apply",
            "--shadow-output",
            str(outside_output),
            "--confirm",
            "MERGE_AND_DELETE_STOCK_INFO_DUPLICATES",
        ],
    )

    assert result.exit_code != 0
    assert "shadow output 必须位于 test-results 目录下" in result.output
    assert not outside_output.exists()


def test_create_cleanup_backup_copies_source_inside_test_results(monkeypatch, tmp_path):
    source_db = tmp_path / "source.db"
    source_db.write_bytes(b"sqlite source")
    output_db = tmp_path / "test-results" / "backup.db"

    monkeypatch.setattr("scripts.audit_stock_info.PROJECT_ROOT", tmp_path)

    backup = _create_cleanup_backup(source_db, output_db)

    assert backup == {
        "source": str(source_db.resolve()),
        "path": str(output_db.resolve()),
        "sha256": _file_sha256(source_db),
    }
    assert output_db.read_bytes() == b"sqlite source"
