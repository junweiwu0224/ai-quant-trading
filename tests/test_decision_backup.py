from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from backup import manager as backup_module
from backup.manager import BackupError, BackupManager, BackupVerificationError
from decision.domain import evaluate_decision
from decision.store import DecisionStore, content_hash, report_fingerprint, stable_json
from scripts.backup_decisions import main as backup_cli
from scripts.restore_decisions import main as restore_cli


class RecordingBarrier:
    def __init__(self) -> None:
        self.events: list[str] = []

    def pause(self) -> None:
        self.events.append("pause")

    def wait_for_safe_point(self) -> None:
        self.events.append("safe-point")

    def resume(self) -> None:
        self.events.append("resume")


@pytest.fixture
def fixture_database(tmp_path: Path) -> Path:
    database = tmp_path / "decisions.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE decisions (id TEXT PRIMARY KEY, action TEXT NOT NULL)")
        connection.execute("INSERT INTO decisions VALUES (?, ?)", ("decision-1", "watch"))
        connection.commit()
    finally:
        connection.close()
    return database


def _content_addressed_file(directory: Path, content: bytes) -> Path:
    digest = hashlib.sha256(content).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / digest
    path.write_bytes(content)
    return path


def _plain_database(path: Path, value: str) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_table VALUES (?)", (value,))
        connection.commit()
    finally:
        connection.close()
    return path


def _decision_database(
    tmp_path: Path,
    *,
    member_quality: str = "ok",
    coverage: int = 30,
    member_stale: bool = False,
    snapshot_quality: str = "ok",
    previous_action: str | None = None,
) -> tuple[DecisionStore, dict[str, object], dict[str, object], dict[str, object]]:
    store = DecisionStore(tmp_path / "decision-db" / "decisions.db")
    portfolio = store.create_portfolio("workspace-1", "CN", "测试组合")
    version = store.create_version(
        "workspace-1",
        portfolio["id"],
        {"strategies": [{"strategy_name": "momentum", "version": "v1", "weight": 1, "enabled": True}]},
    )
    member = store.add_member("workspace-1", portfolio["id"], "600519")
    snapshot = store.create_snapshot(
        "workspace-1",
        version["id"],
        {
            "market": "CN",
            "portfolio_id": portfolio["id"],
            "portfolio_version_id": version["id"],
            "members": [{
                "membership_id": member["id"],
                "symbol": "600519",
                "coverage": coverage,
                "quality_status": member_quality,
                "stale": member_stale,
                "strategy_outputs": [{
                    "strategy_name": "momentum",
                    "strategy_version": "v1",
                    "normalized_score": 72,
                    "confidence": 1,
                    "data_quality": 1,
                }],
            }],
            "provider": "Tushare Pro",
            "provider_status": "integrated",
            "updated_at": "2026-08-14T01:00:00+00:00",
            "coverage_pct": 100,
            "field_sources": {"close": "Tushare Pro"},
            "provider_health": {"Tushare Pro": {"healthy": True, "validated": True, "coverage_pct": 100}},
            "stale": member_quality == "stale" or member_stale,
            "fallback_reason": "",
            "adapter": {"market": "CN", "granularities": ["1d"]},
        },
        "Tushare Pro",
        snapshot_quality,
    )
    run = store.create_run("workspace-1", portfolio["id"], version["id"], snapshot["id"], "manual:1", "manual", "manual")
    evaluation = evaluate_decision(
        snapshot["payload"]["members"][0]["strategy_outputs"],
        {"momentum": {"enabled": True, "weight": 1, "version": "v1"}},
        previous_action=previous_action,
        data_stale=member_quality == "stale",
        data_invalid=member_quality == "invalid" or coverage < 30,
        confirmed=True,
    )
    decision = store.record_decision(run["id"], member["id"], {"symbol": "600519", **evaluation.as_dict()})
    report = store.create_report(run, snapshot, version, [decision], "manual")
    store.complete_run(run["id"])
    return store, decision, report, snapshot


def test_backup_uses_barrier_and_records_online_sqlite_payload(fixture_database: Path, tmp_path: Path) -> None:
    attachments = tmp_path / "attachments"
    attachment = _content_addressed_file(attachments, b"report payload")
    output = tmp_path / "backup"
    barrier = RecordingBarrier()

    manifest = BackupManager(barrier).backup(
        output,
        [fixture_database],
        [attachments],
        metadata={"fixture": "decision-backup"},
    )

    assert barrier.events == ["pause", "safe-point", "resume"]
    assert manifest["manifest_version"] == 1
    assert manifest["sqlite_version"] == sqlite3.sqlite_version
    assert manifest["metadata"] == {"fixture": "decision-backup"}
    assert manifest["file_count"] == 2
    assert manifest["databases"][0]["version"] == sqlite3.sqlite_version
    assert manifest["databases"][0]["sha256"] == manifest["databases"][0]["files"][0]["sha256"]
    assert manifest["artifacts"][0]["files"][0]["sha256"] == hashlib.sha256(attachment.read_bytes()).hexdigest()

    backed_up_database = output / manifest["databases"][0]["backup_path"]
    connection = sqlite3.connect(backed_up_database)
    try:
        assert connection.execute("SELECT action FROM decisions WHERE id='decision-1'").fetchone() == ("watch",)
    finally:
        connection.close()
    assert (output / manifest["artifacts"][0]["files"][0]["path"]).read_bytes() == b"report payload"


def test_restore_verify_only_then_restores_to_isolated_directory(fixture_database: Path, tmp_path: Path) -> None:
    attachments = tmp_path / "attachments"
    _content_addressed_file(attachments, b"immutable evidence")
    backup_dir = tmp_path / "backup"
    target_dir = tmp_path / "isolated-restore"
    manager = BackupManager()
    manifest = manager.backup(backup_dir, [fixture_database], [attachments])

    verification = manager.restore(backup_dir, target_dir, verify_only=True)
    assert verification["ok"] is True
    assert verification["status"] == "verified"
    assert verification["files_verified"] == manifest["file_count"]
    assert not target_dir.exists()

    result = manager.restore(backup_dir, target_dir)
    assert result["status"] == "restored"
    restored_database = Path(result["databases"][0]["path"])
    assert restored_database == target_dir / manifest["databases"][0]["restore_path"]
    connection = sqlite3.connect(restored_database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM decisions").fetchone() == (1,)
    finally:
        connection.close()
    assert Path(result["artifacts"][0]["path"]).is_dir()


def test_restore_rejects_payload_hash_corruption(fixture_database: Path, tmp_path: Path) -> None:
    attachment = _content_addressed_file(tmp_path / "attachments", b"original")
    backup_dir = tmp_path / "backup"
    manager = BackupManager()
    manifest = manager.backup(backup_dir, [fixture_database], [attachment.parent])
    payload = backup_dir / manifest["artifacts"][0]["files"][0]["path"]
    payload.write_bytes(b"tampered")

    with pytest.raises(BackupVerificationError, match="hash or size mismatch"):
        manager.restore(backup_dir, tmp_path / "restore", verify_only=True)


@pytest.mark.parametrize(
    ("member_quality", "coverage", "member_stale", "snapshot_quality", "previous_action", "expected"),
    [
        ("stale", 30, True, "stale", "buy_candidate", {"action": "buy_candidate", "stale": 1, "valid": 1}),
        ("invalid", 10, True, "invalid", None, {"action": "decision_invalid", "stale": 0, "valid": 0}),
    ],
)
def test_restore_replay_preserves_frozen_quality_semantics(
    tmp_path: Path,
    member_quality: str,
    coverage: int,
    member_stale: bool,
    snapshot_quality: str,
    previous_action: str | None,
    expected: dict[str, int | str],
) -> None:
    store, decision, report, _ = _decision_database(
        tmp_path,
        member_quality=member_quality,
        coverage=coverage,
        member_stale=member_stale,
        snapshot_quality=snapshot_quality,
        previous_action=previous_action,
    )
    manager = BackupManager()
    backup_dir = tmp_path / "backup"
    manager.backup(backup_dir, [store.database])

    result = manager.restore(
        backup_dir,
        tmp_path / "restore",
        replay_decision_id=str(decision["id"]),
    )

    assert result["replay"]["match"] is True
    assert result["replay"]["stored_report_hash"] == report["report_hash"]
    connection = sqlite3.connect(Path(result["databases"][0]["path"]))
    try:
        assert connection.execute(
            "SELECT action, stale, valid FROM decisions WHERE id=?",
            (decision["id"],),
        ).fetchone() == (expected["action"], expected["stale"], expected["valid"])
    finally:
        connection.close()


def test_backup_verifies_persisted_validation_artifact(tmp_path: Path) -> None:
    store, _, report, _ = _decision_database(tmp_path)
    version_id = str(report["body"]["portfolio_version_id"])
    validation = store.save_validation(
        version_id,
        {
            "version_id": version_id,
            "passed": False,
            "reasons": ["benchmark_total_return_series_required"],
            "execution_contract": {"execution_rule": "signal_at_close_then_next_tradable_bar_open"},
        },
    )
    assert validation["validation"]["version_id"] == version_id

    backup_dir = tmp_path / "backup"
    BackupManager().backup(backup_dir, [store.database])
    result = BackupManager().restore(backup_dir, tmp_path / "restore", verify_only=True)

    decision_database = next(item for item in result["databases"] if item["decision_schema"])
    assert decision_database["validation_artifacts"] == "verified"
    assert decision_database["reference_counts"]["validations"] == 1


def test_restore_rejects_snapshot_payload_hash_corruption(tmp_path: Path) -> None:
    store, _, _, snapshot = _decision_database(tmp_path)
    connection = sqlite3.connect(store.database)
    try:
        payload = json.loads(connection.execute(
            "SELECT payload_json FROM decision_snapshots WHERE id=?",
            (snapshot["id"],),
        ).fetchone()[0])
        payload["provider_health"]["Tushare Pro"]["coverage_pct"] = 99
        connection.execute(
            "UPDATE decision_snapshots SET payload_json=? WHERE id=?",
            (stable_json(payload), snapshot["id"]),
        )
        connection.commit()
    finally:
        connection.close()

    backup_dir = tmp_path / "backup"
    BackupManager().backup(backup_dir, [store.database])

    with pytest.raises(BackupVerificationError, match="snapshot payload hash mismatch"):
        BackupManager().restore(backup_dir, tmp_path / "restore", verify_only=True)


def test_restore_rejects_report_hash_and_reference_corruption(tmp_path: Path) -> None:
    store, decision, _, _ = _decision_database(tmp_path)
    connection = sqlite3.connect(store.database)
    try:
        connection.execute(
            "UPDATE decision_reports SET report_hash=? WHERE decision_run_id=(SELECT decision_run_id FROM decisions WHERE id=?)",
            ("0" * 64, decision["id"]),
        )
        connection.commit()
    finally:
        connection.close()

    backup_dir = tmp_path / "backup"
    BackupManager().backup(backup_dir, [store.database])

    with pytest.raises(BackupVerificationError, match="report hash mismatch"):
        BackupManager().restore(backup_dir, tmp_path / "restore", verify_only=True)


def test_restore_rejects_completed_run_without_report(tmp_path: Path) -> None:
    store, decision, _, _ = _decision_database(tmp_path)
    connection = sqlite3.connect(store.database)
    try:
        connection.execute(
            "DELETE FROM decision_reports WHERE decision_run_id=(SELECT decision_run_id FROM decisions WHERE id=?)",
            (decision["id"],),
        )
        connection.commit()
    finally:
        connection.close()

    backup_dir = tmp_path / "backup"
    BackupManager().backup(backup_dir, [store.database])

    with pytest.raises(BackupVerificationError, match="missing reports"):
        BackupManager().restore(backup_dir, tmp_path / "restore", verify_only=True)


def test_restore_rejects_report_data_quality_drift_even_with_recomputed_report_hash(tmp_path: Path) -> None:
    store, decision, _, _ = _decision_database(tmp_path)
    connection = sqlite3.connect(store.database)
    try:
        row = connection.execute(
            "SELECT body_json FROM decision_reports WHERE decision_run_id=(SELECT decision_run_id FROM decisions WHERE id=?)",
            (decision["id"],),
        ).fetchone()
        body = json.loads(row[0])
        body["data_quality"]["coverage_pct"] = 99
        connection.execute(
            "UPDATE decision_reports SET body_json=?, report_hash=? WHERE decision_run_id=(SELECT decision_run_id FROM decisions WHERE id=?)",
            (stable_json(body), content_hash(report_fingerprint(body)), decision["id"]),
        )
        connection.commit()
    finally:
        connection.close()

    backup_dir = tmp_path / "backup"
    BackupManager().backup(backup_dir, [store.database])

    with pytest.raises(BackupVerificationError, match="data_quality does not match frozen snapshot"):
        BackupManager().restore(
            backup_dir,
            tmp_path / "restore",
            replay_decision_id=str(decision["id"]),
            verify_only=True,
        )


def test_restore_rejects_missing_content_addressed_attachment(fixture_database: Path, tmp_path: Path) -> None:
    attachment = _content_addressed_file(tmp_path / "attachments", b"immutable evidence")
    backup_dir = tmp_path / "backup"
    manager = BackupManager()
    manifest = manager.backup(backup_dir, [fixture_database], [attachment.parent])
    (backup_dir / manifest["artifacts"][0]["files"][0]["path"]).unlink()

    with pytest.raises(BackupVerificationError, match="not a regular file"):
        manager.restore(backup_dir, tmp_path / "restore", verify_only=True)


def test_content_addressed_name_mismatch_releases_barrier(fixture_database: Path, tmp_path: Path) -> None:
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / ("0" * 64)).write_bytes(b"not the declared content")
    barrier = RecordingBarrier()

    with pytest.raises(BackupError, match="content-addressed artifact name"):
        BackupManager(barrier).backup(tmp_path / "backup", [fixture_database], [attachments])

    assert barrier.events == ["pause", "safe-point", "resume"]


def test_multiple_databases_require_coordination_by_default(fixture_database: Path, tmp_path: Path) -> None:
    second_database = _plain_database(tmp_path / "events.db", "event")

    with pytest.raises(BackupError, match="multiple database backup requires a Worker WriteBarrier"):
        BackupManager().backup(tmp_path / "backup", [fixture_database, second_database])

    runner = CliRunner()
    result = runner.invoke(
        backup_cli,
        [
            "--output-dir",
            str(tmp_path / "cli-backup"),
            "--database",
            str(fixture_database),
            "--database",
            str(second_database),
        ],
    )
    assert result.exit_code != 0
    assert "Worker WriteBarrier" in result.output


def test_cli_does_not_expose_an_uncoordinated_backup_bypass(fixture_database: Path, tmp_path: Path) -> None:
    second_database = _plain_database(tmp_path / "events.db", "event")

    result = CliRunner().invoke(
        backup_cli,
        [
            "--output-dir",
            str(tmp_path / "cli-backup"),
            "--database",
            str(fixture_database),
            "--database",
            str(second_database),
            "--allow-uncoordinated",
        ],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_existing_cross_database_manifest_still_requires_a_worker_barrier(
    fixture_database: Path,
    tmp_path: Path,
) -> None:
    second_database = _plain_database(tmp_path / "events.db", "event")
    output = tmp_path / "backup"
    barrier = RecordingBarrier()
    BackupManager(barrier).backup(output, [fixture_database, second_database])

    with pytest.raises(BackupError, match="multiple database backup requires a Worker WriteBarrier"):
        BackupManager().backup(output, [fixture_database, second_database])


def test_existing_manifest_is_verified_and_corruption_is_rebuilt(fixture_database: Path, tmp_path: Path) -> None:
    attachments = tmp_path / "attachments"
    attachment = _content_addressed_file(attachments, b"original")
    backup_dir = tmp_path / "backup"
    manager = BackupManager()
    original = manager.backup(backup_dir, [fixture_database], [attachments])
    manifest_path = backup_dir / "manifest.json"
    original_bytes = manifest_path.read_bytes()

    reused = manager.backup(backup_dir, [fixture_database], [attachments], metadata={"ignored": True})
    assert reused == original
    assert manifest_path.read_bytes() == original_bytes

    payload = backup_dir / original["artifacts"][0]["files"][0]["path"]
    payload.write_bytes(b"corrupt")
    rebuilt = manager.backup(backup_dir, [fixture_database], [attachments])
    assert rebuilt["file_list_sha256"] == original["file_list_sha256"]
    assert payload.read_bytes() == attachment.read_bytes()
    assert not list(backup_dir.parent.glob(f".{backup_dir.name}.previous-*"))


def test_existing_manifest_with_unexpected_root_file_is_rebuilt(fixture_database: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backup"
    manager = BackupManager()
    manager.backup(backup_dir, [fixture_database])
    unexpected = backup_dir / "unexpected.txt"
    unexpected.write_text("tampered", encoding="utf-8")

    manager.backup(backup_dir, [fixture_database])

    assert not unexpected.exists()
    assert json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))["databases"]


def test_cli_accepts_multiple_attachment_roots_and_restores_all_files(
    fixture_database: Path,
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "reports"
    second_dir = tmp_path / "evidence"
    first_file = _content_addressed_file(first_dir, b"report")
    second_file = _content_addressed_file(second_dir, b"evidence")
    backup_dir = tmp_path / "backup"

    result = CliRunner().invoke(
        backup_cli,
        [
            "--output-dir",
            str(backup_dir),
            "--database",
            str(fixture_database),
            "--artifact-dir",
            str(first_dir),
            "--artifact-dir",
            str(second_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    assert [item["source"] for item in manifest["artifacts"]] == [str(first_dir), str(second_dir)]

    restored = BackupManager().restore(backup_dir, tmp_path / "restore")
    restored_artifacts = [Path(item["path"]) for item in restored["artifacts"]]
    assert (restored_artifacts[0] / first_file.name).read_bytes() == b"report"
    assert (restored_artifacts[1] / second_file.name).read_bytes() == b"evidence"


def test_artifact_file_added_during_backup_is_detected(
    fixture_database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_dir = tmp_path / "attachments"
    _content_addressed_file(artifact_dir, b"first")
    original_copy = backup_module._copy_file_with_hash
    added = artifact_dir / "nested" / "added.json"

    def copy_and_mutate(source: Path, destination: Path) -> tuple[str, int]:
        result = original_copy(source, destination)
        if source.parent == artifact_dir:
            added.parent.mkdir(parents=True, exist_ok=True)
            added.write_bytes(b"added-after-enumeration")
        return result

    monkeypatch.setattr(backup_module, "_copy_file_with_hash", copy_and_mutate)
    with pytest.raises(BackupError, match="artifact directory changed during backup"):
        BackupManager().backup(tmp_path / "backup", [fixture_database], [artifact_dir])


def test_verify_only_without_target_is_read_only_and_restore_requires_target(
    fixture_database: Path,
    tmp_path: Path,
) -> None:
    backup_dir = tmp_path / "backup"
    manager = BackupManager()
    manager.backup(backup_dir, [fixture_database])

    verification = manager.restore(backup_dir, verify_only=True)
    assert verification["status"] == "verified"
    assert verification["target_dir"] is None

    result = CliRunner().invoke(restore_cli, ["--backup-dir", str(backup_dir), "--verify-only"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["target_dir"] is None

    with pytest.raises(BackupError, match="target_dir is required"):
        manager.restore(backup_dir)

    outside = tmp_path / "outside"
    outside.mkdir()
    target_link = tmp_path / "restore-link"
    target_link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(BackupError, match="must not be a symlink"):
        manager.restore(backup_dir, target_link)


def test_manifest_restore_path_collision_is_rejected_without_target_write(
    fixture_database: Path,
    tmp_path: Path,
) -> None:
    second_database = _plain_database(tmp_path / "events.db", "event")
    backup_dir = tmp_path / "backup"
    barrier = RecordingBarrier()
    manager = BackupManager(barrier)
    manifest = manager.backup(backup_dir, [fixture_database, second_database])
    manifest["databases"][1]["restore_path"] = manifest["databases"][0]["restore_path"]
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    target = tmp_path / "restore"

    with pytest.raises(BackupVerificationError, match="duplicate database restore path"):
        manager.restore(backup_dir, target, verify_only=True)
    assert not target.exists()
