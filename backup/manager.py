"""Explicit-path SQLite online backup and isolated restore verification.

This module intentionally has no dependency on the decision runtime, a
notification adapter, a market provider, or project database configuration.
Callers provide every input path and may provide a write barrier that pauses
new runs and outbox claims before the SQLite online backup starts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol, runtime_checkable


MANIFEST_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
BACKUP_FORMAT = "ai-quant-decision-backup"
RECOVERY_DRILL_FORMAT = "ai-quant-decision-recovery-drill"
RECOVERY_DRILL_VERSION = 1
# Kept as an import-compatible name for older callers.  Worker lease state is
# now included in backups; no SQLite database is excluded automatically.
TRANSIENT_WORKER_DATABASE_NAMES: frozenset[str] = frozenset()
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_HASH_NAME_RE = re.compile(r"^(?:sha256[-_:])?([0-9a-f]{64})$", re.IGNORECASE)
_CHUNK_SIZE = 1024 * 1024
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REAL_DATABASE_ROOT = (_PROJECT_ROOT / "data" / "db").resolve()
_SOURCE_BACKUP_PACKAGE = (_PROJECT_ROOT / "backup").resolve()
_DATA_QUALITY_KEYS = (
    "provider",
    "provider_status",
    "updated_at",
    "captured_at",
    "coverage_pct",
    "field_sources",
    "provider_health",
    "stale",
    "fallback_reason",
    "adapter",
)
_QUALITY_STATUSES = {"ok", "stale", "invalid"}


class BackupError(RuntimeError):
    """Raised when a backup or restore cannot satisfy its invariants."""


class BackupVerificationError(BackupError):
    """Raised when a backup manifest, payload hash, or SQLite file is invalid."""


@runtime_checkable
class WriteBarrier(Protocol):
    """Minimal pause/safe-point/resume seam owned by the future Worker.

    Implementations should pause new decision runs and Outbox claims in
    ``pause``, wait until existing database transactions reach a safe point in
    ``wait_for_safe_point``, and release the pause in ``resume``. The backup
    manager does not know how the Worker implements those operations. It also
    takes SQLite-level write locks while copying, so writers which do not
    participate in the in-process barrier cannot change one database between
    the snapshots of a cross-file backup.
    """

    def pause(self) -> None:
        """Prevent new writes that could invalidate the backup boundary."""

    def wait_for_safe_point(self) -> None:
        """Wait for in-flight writes to reach a safe point."""

    def resume(self) -> None:
        """Release the write barrier after the manifest is durable."""


class NoopWriteBarrier:
    """No-op barrier used only when backing up one standalone SQLite file."""

    def pause(self) -> None:
        return None

    def wait_for_safe_point(self) -> None:
        return None

    def resume(self) -> None:
        return None


FenceCheck = Callable[[], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _mtime_iso(mtime_ns: int) -> str:
    return datetime.fromtimestamp(mtime_ns / 1_000_000_000, timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _as_path(value: str | os.PathLike[str]) -> Path:
    try:
        return Path(value).expanduser()
    except TypeError as exc:
        raise TypeError(f"path must be str or os.PathLike, got {type(value).__name__}") from exc


def _as_path_tuple(values: Iterable[str | os.PathLike[str]], label: str) -> tuple[Path, ...]:
    if isinstance(values, (str, bytes, os.PathLike)):
        raise TypeError(f"{label} must be an iterable of explicit paths")
    try:
        return tuple(_as_path(value) for value in values)
    except TypeError as exc:
        raise TypeError(f"{label} must be an iterable of explicit paths") from exc


def _guard_explicit_path(
    value: str | os.PathLike[str],
    label: str,
    *,
    allow_repository_database: bool = False,
) -> Path:
    raw = _as_path(value)
    if raw.is_symlink():
        raise BackupError(f"{label} must not be a symlink: {raw}")
    resolved = raw.resolve(strict=False)
    if not allow_repository_database and (resolved == _REAL_DATABASE_ROOT or resolved.is_relative_to(_REAL_DATABASE_ROOT)):
        raise BackupError(f"refusing to access the repository data/db path: {resolved}")
    return resolved


def _reject_source_package_path(path: Path, label: str) -> None:
    """Keep generated backup/restore data out of the importable source package."""

    if path == _SOURCE_BACKUP_PACKAGE or path.is_relative_to(_SOURCE_BACKUP_PACKAGE):
        raise BackupError(f"{label} must not be inside the source backup package: {path}")


def _safe_component(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return (cleaned or fallback)[:120]


def _safe_relative_path(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise BackupVerificationError(f"{label} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise BackupVerificationError(f"{label} is not a safe relative path: {value!r}")
    if "\\" in value:
        raise BackupVerificationError(f"{label} must use POSIX separators: {value!r}")
    if path.as_posix() != value:
        raise BackupVerificationError(f"{label} is not canonical: {value!r}")
    return path


def _ensure_regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise BackupVerificationError(f"{label} is not a regular file: {path}")


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _copy_file_with_hash(source: Path, destination: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_handle, destination.open("wb") as destination_handle:
        for chunk in iter(lambda: source_handle.read(_CHUNK_SIZE), b""):
            destination_handle.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _directory_digest(records: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: str(item["relative_path"])):
        line = f"{record['relative_path']}\0{record['size']}\0{record['sha256']}\n"
        digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def _metadata_copy(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")
    try:
        return json.loads(json.dumps(dict(metadata), ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise TypeError("metadata must be JSON serializable") from exc


def _declared_filename_hash(name: str) -> str | None:
    match = _HASH_NAME_RE.fullmatch(name)
    return match.group(1).lower() if match else None


def _read_only_uri(path: Path) -> str:
    return f"{path.as_uri()}?mode=ro"


def _json_value(raw: Any, label: str) -> Any:
    if not isinstance(raw, str):
        raise BackupVerificationError(f"{label} is not valid JSON text")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BackupVerificationError(f"{label} is not valid JSON: {exc}") from exc


def _json_object(raw: Any, label: str) -> dict[str, Any]:
    value = _json_value(raw, label)
    if not isinstance(value, Mapping):
        raise BackupVerificationError(f"{label} must contain a JSON object")
    return dict(value)


def _json_list(raw: Any, label: str) -> list[Any]:
    value = _json_value(raw, label)
    if not isinstance(value, list):
        raise BackupVerificationError(f"{label} must contain a JSON array")
    return value


def _snapshot_data_quality(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in _DATA_QUALITY_KEYS if key in payload}


def _replay_quality_flags(member: Mapping[str, Any], label: str) -> tuple[bool, bool]:
    """Mirror DecisionRuntime's frozen member quality interpretation.

    ``quality_status`` is authoritative for stale-vs-invalid.  In particular,
    an invalid member may still carry a historical ``stale`` marker, but that
    marker must not turn an invalid input into a stale replay.
    """

    quality_status = member.get("quality_status")
    if quality_status not in _QUALITY_STATUSES:
        raise BackupVerificationError(f"{label}.quality_status is invalid")
    coverage = member.get("coverage", 0)
    if isinstance(coverage, bool) or not isinstance(coverage, (int, float)):
        raise BackupVerificationError(f"{label}.coverage is invalid")
    return quality_status == "stale", quality_status == "invalid" or coverage < 30


def _decision_payload_from_row(row: sqlite3.Row, label: str) -> dict[str, Any]:
    reason_codes = _json_list(row["reason_codes_json"], f"{label}.reason_codes_json")
    contributions = _json_list(row["contributions_json"], f"{label}.contributions_json")
    return {
        "symbol": row["symbol"],
        "action": row["action"],
        "score": row["score"],
        "valid": bool(row["valid"]),
        "stale": bool(row["stale"]),
        "risk_veto": bool(row["risk_veto"]),
        "reason_codes": reason_codes,
        "contributions": contributions,
        "previous_action": row["previous_action"],
        "confirmed": bool(row["confirmed"]),
    }


def _assert_sqlite_readable(path: Path) -> None:
    _ensure_regular_file(path, "SQLite payload")
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(_read_only_uri(path), uri=True, timeout=10.0)
        connection.execute("PRAGMA foreign_keys=ON")
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            detail = result[0] if result else "no result"
            raise BackupVerificationError(f"SQLite integrity_check failed for {path}: {detail}")
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
    except sqlite3.Error as exc:
        raise BackupVerificationError(f"SQLite payload is not readable: {path}: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def _verify_decision_references(path: Path) -> dict[str, Any]:
    """Validate frozen hashes and the complete decision/report reference graph."""

    from decision.store import content_hash, report_fingerprint

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(_read_only_uri(path), uri=True, timeout=10.0)
        connection.row_factory = sqlite3.Row
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_rows:
            raise BackupVerificationError(f"SQLite foreign-key check failed for {path}")
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {"decision_runs", "decisions", "decision_reports", "decision_snapshots", "decision_versions"}
        if "decision_runs" not in tables:
            return {"decision_schema": False, "foreign_keys": True, "references": "not_applicable"}
        if not required.issubset(tables):
            missing = sorted(required - tables)
            raise BackupVerificationError(f"decision schema is incomplete: missing {missing}")

        portfolios = {
            row["id"]: row
            for row in connection.execute("SELECT id, workspace_id FROM decision_portfolios").fetchall()
        }
        versions = {
            row["id"]: row
            for row in connection.execute(
                "SELECT id, portfolio_id, config_json, config_hash FROM decision_versions"
            ).fetchall()
        }
        snapshots = {
            row["id"]: row
            for row in connection.execute(
                "SELECT id, workspace_id, portfolio_version_id, payload_json, payload_hash, source, quality_status FROM decision_snapshots"
            ).fetchall()
        }
        runs = {
            row["id"]: row
            for row in connection.execute(
                "SELECT id, workspace_id, portfolio_id, portfolio_version_id, snapshot_id, trigger, report_type, status FROM decision_runs"
            ).fetchall()
        }
        decisions = connection.execute(
            "SELECT * FROM decisions ORDER BY decision_run_id, id"
        ).fetchall()
        reports = connection.execute(
            "SELECT id, decision_run_id, report_type, body_json, report_hash FROM decision_reports ORDER BY decision_run_id, id"
        ).fetchall()
        validations = (
            connection.execute(
                "SELECT portfolio_version_id, validation_json, validation_hash FROM decision_validations"
            ).fetchall()
            if "decision_validations" in tables
            else []
        )

        for version_id, version in versions.items():
            config = _json_object(version["config_json"], f"decision_versions[{version_id}].config_json")
            if version["config_hash"] != content_hash(config):
                raise BackupVerificationError(f"portfolio version config hash mismatch: {version_id}")

        for validation in validations:
            version_id = str(validation["portfolio_version_id"])
            if version_id not in versions:
                raise BackupVerificationError(f"validation references missing portfolio version: {version_id}")
            payload = _json_object(validation["validation_json"], f"decision_validations[{version_id}].validation_json")
            if not isinstance(validation["validation_hash"], str) or not _HASH_RE.fullmatch(validation["validation_hash"]):
                raise BackupVerificationError(f"validation hash is invalid: {version_id}")
            if validation["validation_hash"] != content_hash(payload):
                raise BackupVerificationError(f"validation payload hash mismatch: {version_id}")

        snapshot_payloads: dict[str, dict[str, Any]] = {}
        for snapshot_id, snapshot in snapshots.items():
            payload = _json_object(snapshot["payload_json"], f"decision_snapshots[{snapshot_id}].payload_json")
            if snapshot["payload_hash"] != content_hash(payload):
                raise BackupVerificationError(f"snapshot payload hash mismatch: {snapshot_id}")
            version_id = snapshot["portfolio_version_id"]
            if version_id not in versions:
                raise BackupVerificationError(f"snapshot references missing portfolio version: {snapshot_id}")
            if payload.get("portfolio_version_id") not in {None, version_id}:
                raise BackupVerificationError(f"snapshot portfolio version reference mismatch: {snapshot_id}")
            members = payload.get("members", [])
            if not isinstance(members, list):
                raise BackupVerificationError(f"snapshot members must be a list: {snapshot_id}")
            member_ids: set[str] = set()
            for member_index, member in enumerate(members):
                if not isinstance(member, Mapping):
                    raise BackupVerificationError(f"snapshot member is not an object: {snapshot_id}[{member_index}]")
                member_id = member.get("membership_id")
                if not isinstance(member_id, str) or not member_id:
                    raise BackupVerificationError(f"snapshot member id is invalid: {snapshot_id}[{member_index}]")
                if member_id in member_ids:
                    raise BackupVerificationError(f"duplicate snapshot member reference: {snapshot_id}:{member_id}")
                member_ids.add(member_id)
                _replay_quality_flags(member, f"snapshot {snapshot_id} member {member_id}")
            snapshot_payloads[snapshot_id] = payload

        run_decisions: dict[str, list[sqlite3.Row]] = {run_id: [] for run_id in runs}
        for decision in decisions:
            run_id = decision["decision_run_id"]
            if run_id not in run_decisions:
                raise BackupVerificationError(f"decision references missing run: {decision['id']}")
            if not isinstance(decision["payload_hash"], str) or not _HASH_RE.fullmatch(decision["payload_hash"]):
                raise BackupVerificationError(f"decision payload hash is invalid: {decision['id']}")
            if decision["payload_hash"] != content_hash(_decision_payload_from_row(decision, f"decision {decision['id']}")):
                raise BackupVerificationError(f"decision payload hash mismatch: {decision['id']}")
            run_decisions[run_id].append(decision)

        for run_id, run in runs.items():
            portfolio = portfolios.get(run["portfolio_id"])
            version = versions.get(run["portfolio_version_id"])
            snapshot = snapshots.get(run["snapshot_id"])
            if portfolio is None or version is None or snapshot is None:
                raise BackupVerificationError(f"decision reference check failed for run: {run_id}")
            if version["portfolio_id"] != run["portfolio_id"]:
                raise BackupVerificationError(f"run portfolio/version reference mismatch: {run_id}")
            if snapshot["portfolio_version_id"] != run["portfolio_version_id"]:
                raise BackupVerificationError(f"run snapshot/version reference mismatch: {run_id}")
            if portfolio["workspace_id"] != run["workspace_id"] or snapshot["workspace_id"] != run["workspace_id"]:
                raise BackupVerificationError(f"run workspace reference mismatch: {run_id}")

        reports_by_run: dict[str, list[sqlite3.Row]] = {run_id: [] for run_id in runs}
        for report in reports:
            run_id = report["decision_run_id"]
            run = runs.get(run_id)
            if run is None:
                raise BackupVerificationError(f"report references missing run: {report['id']}")
            body = _json_object(report["body_json"], f"decision_reports[{report['id']}].body_json")
            expected_references = {
                "run_id": run_id,
                "report_type": run["report_type"],
                "portfolio_id": run["portfolio_id"],
                "portfolio_version_id": run["portfolio_version_id"],
                "input_hash": snapshots[run["snapshot_id"]]["payload_hash"],
                "version_hash": versions[run["portfolio_version_id"]]["config_hash"],
                "source": snapshots[run["snapshot_id"]]["source"],
                "quality_status": snapshots[run["snapshot_id"]]["quality_status"],
                "trigger": run["trigger"],
            }
            for key, expected in expected_references.items():
                if body.get(key) != expected:
                    raise BackupVerificationError(f"report reference mismatch: {report['id']}:{key}")
            expected_quality = _snapshot_data_quality(snapshot_payloads[run["snapshot_id"]])
            if body.get("data_quality") != expected_quality:
                raise BackupVerificationError(f"report data_quality does not match frozen snapshot: {report['id']}")
            if not isinstance(report["report_hash"], str) or not _HASH_RE.fullmatch(report["report_hash"]):
                raise BackupVerificationError(f"report hash is invalid: {report['id']}")
            if report["report_hash"] != content_hash(report_fingerprint(body)):
                raise BackupVerificationError(f"report hash mismatch: {report['id']}")

            body_decisions = body.get("decisions")
            if not isinstance(body_decisions, list):
                raise BackupVerificationError(f"report decisions must be a list: {report['id']}")
            expected_decisions = run_decisions[run_id]
            expected_by_id = {str(item["id"]): item for item in expected_decisions}
            body_by_id: dict[str, Mapping[str, Any]] = {}
            for item in body_decisions:
                if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                    raise BackupVerificationError(f"report decision reference is invalid: {report['id']}")
                item_id = item["id"]
                if item_id in body_by_id:
                    raise BackupVerificationError(f"duplicate report decision reference: {report['id']}:{item_id}")
                body_by_id[item_id] = item
            if set(body_by_id) != set(expected_by_id):
                raise BackupVerificationError(f"report decision references are incomplete: {report['id']}")
            for decision_id, decision in expected_by_id.items():
                expected_payload = _decision_payload_from_row(decision, f"decision {decision_id}")
                expected_report_values = {
                    "membership_id": decision["membership_id"],
                    **expected_payload,
                }
                actual = body_by_id[decision_id]
                for key, expected in expected_report_values.items():
                    if actual.get(key) != expected:
                        raise BackupVerificationError(f"report decision reference mismatch: {report['id']}:{decision_id}:{key}")
            snapshot_members = snapshot_payloads[run["snapshot_id"]].get("members", [])
            snapshot_member_ids = [str(item["membership_id"]) for item in snapshot_members]
            report_member_ids = [str(item.get("membership_id")) for item in body_decisions]
            if len(report_member_ids) != len(set(report_member_ids)) or set(snapshot_member_ids) != set(report_member_ids):
                raise BackupVerificationError(f"report/snapshot member references are incomplete: {report['id']}")
            reports_by_run[run_id].append(report)

        missing_reports = [run_id for run_id, run in runs.items() if run["status"] == "completed" and not reports_by_run[run_id]]
        if missing_reports:
            raise BackupVerificationError(f"completed decision runs missing reports: {missing_reports}")

        counts = {
            "orphan_decisions": 0,
            "orphan_reports": 0,
            "orphan_snapshots": 0,
            "orphan_versions": 0,
            "snapshots": len(snapshots),
            "versions": len(versions),
            "runs": len(runs),
            "decisions": len(decisions),
            "reports": len(reports),
            "validations": len(validations),
        }
        return {
            "decision_schema": True,
            "foreign_keys": True,
            "references": "verified",
            "validation_artifacts": "verified" if "decision_validations" in tables else "not_present",
            "reference_counts": counts,
        }
    except sqlite3.Error as exc:
        raise BackupVerificationError(f"decision reference check failed for {path}: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def _replay_report_from_database(path: Path, decision_id: str) -> dict[str, Any]:
    """Replay one stored report using only its frozen snapshot and version."""

    from decision.domain import evaluate_decision
    from decision.store import content_hash, report_fingerprint

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(_read_only_uri(path), uri=True, timeout=10.0)
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT r.body_json, r.report_hash, run.snapshot_id, run.portfolio_version_id,
                   run.portfolio_id, run.trigger
            FROM decisions d
            JOIN decision_runs run ON run.id=d.decision_run_id
            JOIN decision_reports r ON r.decision_run_id=run.id
            WHERE d.id=?
            ORDER BY r.created_at DESC
            LIMIT 1
            """,
            (decision_id,),
        ).fetchone()
        if row is None:
            raise BackupVerificationError(f"decision_id not found in restored database: {decision_id}")
        snapshot_row = connection.execute("SELECT * FROM decision_snapshots WHERE id=?", (row["snapshot_id"],)).fetchone()
        version_row = connection.execute("SELECT * FROM decision_versions WHERE id=?", (row["portfolio_version_id"],)).fetchone()
        if snapshot_row is None or version_row is None:
            raise BackupVerificationError("frozen snapshot or portfolio version is missing")
        report_body = _json_object(row["body_json"], "decision report body")
        snapshot = _json_object(snapshot_row["payload_json"], "decision snapshot payload")
        config = _json_object(version_row["config_json"], "portfolio version config")
        if version_row["config_hash"] != content_hash(config):
            raise BackupVerificationError("portfolio version config hash mismatch")
        if snapshot_row["payload_hash"] != content_hash(snapshot):
            raise BackupVerificationError("snapshot payload hash mismatch")
        data_quality = _snapshot_data_quality(snapshot)
        if report_body.get("data_quality") != data_quality:
            raise BackupVerificationError("report data_quality does not match frozen snapshot")
        if row["report_hash"] != content_hash(report_fingerprint(report_body)):
            raise BackupVerificationError("report hash mismatch")
        weights = {str(item.get("strategy_name")): item for item in config.get("strategies", [])}
        members = snapshot.get("members", [])
        if not isinstance(members, list):
            raise BackupVerificationError("snapshot members must be a list")
        members_by_id: dict[str, Mapping[str, Any]] = {}
        for index, member in enumerate(members):
            if not isinstance(member, Mapping):
                raise BackupVerificationError(f"snapshot member is not an object: {index}")
            membership_id = member.get("membership_id")
            if not isinstance(membership_id, str) or membership_id in members_by_id:
                raise BackupVerificationError(f"snapshot member reference is invalid: {membership_id}")
            members_by_id[membership_id] = member

        report_decisions = report_body.get("decisions")
        if not isinstance(report_decisions, list):
            raise BackupVerificationError("report decisions must be a list")
        decisions: list[dict[str, Any]] = []
        for original in report_decisions:
            if not isinstance(original, Mapping):
                raise BackupVerificationError("report decision reference is invalid")
            membership_id = original.get("membership_id")
            member = members_by_id.get(str(membership_id))
            if not isinstance(membership_id, str) or member is None:
                raise BackupVerificationError(f"report decision reference missing for snapshot member: {membership_id}")
            data_stale, data_invalid = _replay_quality_flags(member, f"snapshot member {membership_id}")
            evaluation = evaluate_decision(
                member.get("strategy_outputs", []),
                weights,
                previous_action=member.get("previous_action", original.get("previous_action")),
                data_stale=data_stale,
                data_invalid=data_invalid,
                confirmed=bool(original.get("confirmed", True)),
            )
            decisions.append({"membership_id": membership_id, "symbol": member.get("symbol"), **evaluation.as_dict()})
        replay_body = {
            "report_type": report_body.get("report_type"),
            "portfolio_id": row["portfolio_id"],
            "portfolio_version_id": row["portfolio_version_id"],
            "input_hash": snapshot_row["payload_hash"],
            "version_hash": version_row["config_hash"],
            "source": snapshot_row["source"],
            "quality_status": snapshot_row["quality_status"],
            "data_quality": data_quality,
            "trigger": row["trigger"],
            "run_key": report_body.get("run_key"),
            "schedule_slot": report_body.get("schedule_slot"),
            "trade_date": report_body.get("trade_date"),
            "decisions": decisions,
        }
        # These projections are frozen report facts.  Keep them in the
        # restore replay so adding an auditable context field cannot make
        # an otherwise identical report appear corrupted.
        for key in ("market", "market_capabilities", "strategy_weights", "evidence", "validation", "eligibility"):
            if key in report_body:
                replay_body[key] = report_body[key]
        replay_hash = content_hash(report_fingerprint(replay_body))
        result = {
            "decision_id": decision_id,
            "stored_report_hash": row["report_hash"],
            "replay_report_hash": replay_hash,
            "match": replay_hash == row["report_hash"],
            "input_hash": snapshot_row["payload_hash"],
            "version_hash": version_row["config_hash"],
        }
        if not result["match"]:
            raise BackupVerificationError(
                "replayed report does not match stored report: "
                f"{decision_id} ({replay_hash} != {row['report_hash']})"
            )
        return result
    except sqlite3.Error as exc:
        raise BackupVerificationError(f"report replay failed: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def _find_replay_database(paths: Iterable[Path], decision_id: str) -> Path:
    candidates: list[Path] = []
    for path in paths:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(_read_only_uri(path), uri=True, timeout=10.0)
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if {"decision_runs", "decision_reports", "decisions"}.issubset(tables):
                found = connection.execute("SELECT 1 FROM decisions WHERE id=? LIMIT 1", (decision_id,)).fetchone()
                if found is not None:
                    candidates.append(path)
        except sqlite3.Error as exc:
            raise BackupVerificationError(f"cannot locate replay database: {path}: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()
    if not candidates:
        raise BackupVerificationError(f"decision_id not found in restored database: {decision_id}")
    if len(candidates) > 1:
        raise BackupVerificationError(f"decision_id is present in multiple restored databases: {decision_id}")
    return candidates[0]


def _first_replay_decision_id(paths: Iterable[Path]) -> str | None:
    """Return a stable local sample for a scheduled recovery drill."""

    candidates: list[str] = []
    for path in paths:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(_read_only_uri(path), uri=True, timeout=10.0)
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='decisions' LIMIT 1"
            ).fetchone()
            if table is None:
                continue
            row = connection.execute("SELECT id FROM decisions ORDER BY id LIMIT 1").fetchone()
            if row is not None and row[0] is not None:
                candidates.append(str(row[0]))
        except sqlite3.Error as exc:
            raise BackupVerificationError(f"cannot select a replay decision: {path}: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()
    return min(candidates) if candidates else None


def _latest_backup_directory(backup_root: Path) -> Path:
    """Pick the latest explicitly named backup without consulting external state."""

    if not backup_root.exists() or not backup_root.is_dir():
        raise BackupVerificationError(f"daily backup root is not a directory: {backup_root}")
    candidates = sorted(
        (
            path
            for path in backup_root.iterdir()
            if path.is_dir() and not path.is_symlink() and (path / MANIFEST_FILENAME).is_file()
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    if not candidates:
        raise BackupVerificationError(f"daily backup root contains no manifest directories: {backup_root}")
    return candidates[0].resolve()


def _iter_regular_files(directory: Path, error_type: type[BackupError] = BackupError) -> Iterator[tuple[Path, Path]]:
    for root, directory_names, file_names in os.walk(directory, followlinks=False):
        root_path = Path(root)
        for name in directory_names:
            candidate = root_path / name
            if candidate.is_symlink():
                raise error_type(f"artifact directory contains a symlink: {candidate}")
        directory_names.sort()
        for name in sorted(file_names):
            candidate = root_path / name
            if candidate.is_symlink() or not candidate.is_file():
                raise error_type(f"artifact directory contains a non-regular file: {candidate}")
            yield candidate, candidate.relative_to(directory)


def _iter_payload_files(directory: Path) -> Iterator[Path]:
    for file_path, _ in _iter_regular_files(directory, BackupVerificationError):
        yield file_path


def _payload_files(backup_dir: Path) -> set[str]:
    paths: set[str] = set()
    for root_name in ("databases", "artifacts"):
        root = backup_dir / root_name
        if not root.exists():
            continue
        if root.is_symlink() or not root.is_dir():
            raise BackupVerificationError(f"backup payload root is not a directory: {root}")
        for file_path in _iter_payload_files(root):
            paths.add(file_path.relative_to(backup_dir).as_posix())
    return paths


class BackupManager:
    """Create and verify local backups using explicit input paths only."""

    def __init__(
        self,
        write_barrier: WriteBarrier | None = None,
        *,
        fence_check: FenceCheck | None = None,
        _live_database_paths: Iterable[str | os.PathLike[str]] = (),
    ) -> None:
        if fence_check is not None and not callable(fence_check):
            raise TypeError("fence_check must be callable")
        live_database_paths = frozenset(
            _as_path(path).resolve(strict=False) for path in _as_path_tuple(_live_database_paths, "_live_database_paths")
        )
        if live_database_paths and (write_barrier is None or isinstance(write_barrier, NoopWriteBarrier)):
            raise BackupError("live Worker database paths require an explicit Worker WriteBarrier")
        if any(path.name != "worker_leases.db" for path in live_database_paths):
            raise BackupError("only the Worker lease database may use the controlled live database path")
        self.write_barrier = write_barrier
        self.fence_check = fence_check
        self._live_database_paths = live_database_paths

    def _check_fence(self) -> None:
        if self.fence_check is not None:
            self.fence_check()

    def _validated_inputs(
        self,
        output_dir: str | os.PathLike[str],
        database_paths: Iterable[str | os.PathLike[str]],
        artifact_dirs: Iterable[str | os.PathLike[str]],
    ) -> tuple[Path, tuple[Path, ...], tuple[Path, ...]]:
        output = _guard_explicit_path(output_dir, "output_dir")
        _reject_source_package_path(output, "output_dir")
        databases = tuple(
            _guard_explicit_path(path, "database path", allow_repository_database=True)
            for path in _as_path_tuple(database_paths, "database_paths")
        )
        artifacts = tuple(_guard_explicit_path(path, "artifact directory") for path in _as_path_tuple(artifact_dirs, "artifact_dirs"))
        if not databases:
            raise BackupError("at least one explicit database path is required")
        if len(set(databases)) != len(databases):
            raise BackupError("database_paths must not contain duplicates")
        if len(set(artifacts)) != len(artifacts):
            raise BackupError("artifact_dirs must not contain duplicates")
        for database in databases:
            if not database.exists() or not database.is_file():
                raise BackupError(f"database path is not a regular file: {database}")
        for artifact in artifacts:
            if not artifact.exists() or not artifact.is_dir():
                raise BackupError(f"artifact directory is not a directory: {artifact}")
        for artifact in artifacts:
            if output == artifact or output.is_relative_to(artifact):
                raise BackupError(f"output_dir must not be inside an artifact directory: {output}")
        for database in databases:
            if output == database or output == database.parent:
                raise BackupError(f"output_dir must not be the database path or its directory: {output}")
        if output.exists():
            if not output.is_dir():
                raise BackupError(f"output_dir is not a directory: {output}")
            manifest_path = output / MANIFEST_FILENAME
            if manifest_path.is_symlink():
                raise BackupError(f"manifest must not be a symlink: {manifest_path}")
            if any(output.iterdir()) and not manifest_path.is_file():
                raise BackupError(f"output_dir must be absent, empty, or contain a manifest: {output}")
        return output, databases, artifacts

    def validate_inputs(
        self,
        output_dir: str | os.PathLike[str],
        database_paths: Iterable[str | os.PathLike[str]],
        artifact_dirs: Iterable[str | os.PathLike[str]] = (),
    ) -> dict[str, Any]:
        """Validate a dry-run request without connecting to or copying any source."""

        output, databases, artifacts = self._validated_inputs(output_dir, database_paths, artifact_dirs)
        barrier = self._select_write_barrier(databases)
        return {
            "output_dir": str(output),
            "database_paths": [str(path) for path in databases],
            "artifact_dirs": [str(path) for path in artifacts],
            "barrier_mode": self._barrier_mode(barrier),
            "would_create_output": not output.exists(),
        }

    @contextmanager
    def _write_barrier(self, barrier: WriteBarrier) -> Iterator[None]:
        paused = False
        try:
            self._check_fence()
            barrier.pause()
            paused = True
            barrier.wait_for_safe_point()
            self._check_fence()
            yield
        finally:
            if paused:
                barrier.resume()

    @staticmethod
    @contextmanager
    def _database_write_locks(
        databases: tuple[Path, ...],
        *,
        excluded_paths: frozenset[Path] = frozenset(),
    ) -> Iterator[None]:
        """Hold a stable SQLite write fence across every source database.

        The in-process Worker barrier protects cooperative writers.  These
        ``BEGIN IMMEDIATE`` transactions are the second half of the seam: a
        Dashboard/API writer that does not know about that condition cannot
        commit a change in the middle of a multi-file backup.  The only
        controlled exception is the live Worker lease path, whose renewal
        must remain writable during a long backup.  Databases are acquired in
        path order so two local backup attempts cannot deadlock each other.
        """

        connections: list[sqlite3.Connection] = []
        try:
            for database in sorted(databases, key=lambda path: str(path)):
                if database in excluded_paths:
                    continue
                connection: sqlite3.Connection | None = None
                try:
                    connection = sqlite3.connect(str(database), timeout=30.0)
                    connection.execute("PRAGMA busy_timeout=30000")
                    connection.execute("BEGIN IMMEDIATE")
                except sqlite3.Error as exc:
                    if connection is not None:
                        connection.close()
                    raise BackupError(f"could not lock SQLite database for backup: {database}: {exc}") from exc
                assert connection is not None
                connections.append(connection)
            yield
        finally:
            for connection in reversed(connections):
                try:
                    connection.rollback()
                finally:
                    connection.close()

    def _select_write_barrier(self, databases: tuple[Path, ...]) -> WriteBarrier:
        """Require a Worker-owned barrier before every cross-database backup."""

        if self.write_barrier is not None:
            if not isinstance(self.write_barrier, WriteBarrier):
                raise TypeError("write_barrier must implement the Worker WriteBarrier protocol")
            if len(databases) > 1 and isinstance(self.write_barrier, NoopWriteBarrier):
                raise BackupError("multiple database backup requires a Worker WriteBarrier")
            return self.write_barrier
        if len(databases) > 1:
            raise BackupError("multiple database backup requires a Worker WriteBarrier")
        return NoopWriteBarrier()

    @staticmethod
    def _barrier_mode(barrier: WriteBarrier) -> str:
        return "uncoordinated" if isinstance(barrier, NoopWriteBarrier) else "coordinated"

    @staticmethod
    def _manifest_matches_inputs(
        manifest: Mapping[str, Any],
        databases: tuple[Path, ...],
        artifacts: tuple[Path, ...],
    ) -> bool:
        database_records = manifest.get("databases")
        artifact_records = manifest.get("artifacts")
        if not isinstance(database_records, list) or not isinstance(artifact_records, list):
            return False
        database_sources = [item.get("source") for item in database_records if isinstance(item, Mapping)]
        artifact_sources = [item.get("source") for item in artifact_records if isinstance(item, Mapping)]
        return database_sources == [str(path) for path in databases] and artifact_sources == [str(path) for path in artifacts]

    @staticmethod
    def _existing_manifest(
        output: Path,
        databases: tuple[Path, ...],
        artifacts: tuple[Path, ...],
    ) -> dict[str, Any] | None:
        """Return a verified existing manifest, or signal that it needs rebuilding."""

        if not output.exists():
            return None
        manifest_path = output / MANIFEST_FILENAME
        if manifest_path.is_symlink():
            raise BackupError(f"manifest must not be a symlink: {manifest_path}")
        if not manifest_path.is_file():
            return None
        try:
            manifest = BackupManager._load_manifest(output)
            BackupManager._verify_backup_payload(output, manifest)
        except BackupVerificationError:
            return None
        if not BackupManager._manifest_matches_inputs(manifest, databases, artifacts):
            raise BackupError("existing manifest does not match the explicit backup inputs")
        return manifest

    @staticmethod
    def _publish_staging(staging: Path, output: Path) -> None:
        """Publish a new backup while retaining a corrupt previous directory until success."""

        retired: Path | None = None
        if output.exists():
            if not output.is_dir():
                raise BackupError(f"output_dir changed during backup: {output}")
            if any(output.iterdir()):
                retired = Path(tempfile.mkdtemp(prefix=f".{output.name}.previous-", dir=str(output.parent)))
                retired.rmdir()
            else:
                output.rmdir()
            if retired is not None:
                output.replace(retired)
        try:
            staging.replace(output)
        except Exception:
            if retired is not None and not output.exists() and retired.exists():
                retired.replace(output)
            raise
        if retired is not None:
            shutil.rmtree(retired, ignore_errors=True)

    @staticmethod
    def _sqlite_backup(source: Path, destination: Path) -> tuple[str, int, os.stat_result]:
        return BackupManager._sqlite_backup_impl(source, destination)

    @staticmethod
    def _sqlite_backup_impl(
        source: Path,
        destination: Path,
    ) -> tuple[str, int, os.stat_result]:
        source_before = source.stat()
        source_connection: sqlite3.Connection | None = None
        destination_connection: sqlite3.Connection | None = None
        try:
            source_connection = sqlite3.connect(_read_only_uri(source), uri=True, timeout=30.0)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination_connection = sqlite3.connect(str(destination), timeout=30.0)
            source_connection.backup(destination_connection, pages=-1, sleep=0.01)
            destination_connection.commit()
            # A WAL source can copy its persistent journal-mode flag into the
            # destination.  Normalize only the isolated payload so no
            # unlisted ``-wal``/``-shm`` sidecars survive publication.
            journal_mode = destination_connection.execute("PRAGMA journal_mode=DELETE").fetchone()
            if not journal_mode or str(journal_mode[0]).lower() != "delete":
                raise BackupError(f"could not normalize backup journal mode for {destination}")
        except sqlite3.Error as exc:
            raise BackupError(f"SQLite online backup failed for {source}: {exc}") from exc
        finally:
            if source_connection is not None:
                source_connection.close()
            if destination_connection is not None:
                destination_connection.close()
        digest, size = _hash_file(destination)
        _assert_sqlite_readable(destination)
        return digest, size, source_before

    def backup(
        self,
        output_dir: str | os.PathLike[str],
        database_paths: Iterable[str | os.PathLike[str]],
        artifact_dirs: Iterable[str | os.PathLike[str]] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an atomic local backup and return its JSON-serializable manifest."""

        self._check_fence()
        output, databases, artifacts = self._validated_inputs(output_dir, database_paths, artifact_dirs)
        if not self._live_database_paths.issubset(set(databases)):
            raise BackupError("controlled live Worker database paths must be included in database_paths")
        metadata_copy = _metadata_copy(metadata)
        barrier = self._select_write_barrier(databases)
        existing = self._existing_manifest(output, databases, artifacts)
        if existing is not None:
            self._check_fence()
            return existing
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=str(output.parent)))
        published = False
        try:
            with self._write_barrier(barrier):
                with self._database_write_locks(databases, excluded_paths=self._live_database_paths):
                    self._check_fence()
                    captured_at = _utc_now()
                    files: list[dict[str, Any]] = []
                    database_records: list[dict[str, Any]] = []
                    artifact_records: list[dict[str, Any]] = []

                    for index, source in enumerate(databases):
                        self._check_fence()
                        component = f"{index:03d}-{_safe_component(source.name, 'database')}"
                        backup_relative = PurePosixPath("databases") / component
                        destination = staging / Path(*backup_relative.parts)
                        digest, size, source_stat = self._sqlite_backup(source, destination)
                        source_after = source.stat()
                        # Lease renewal is intentionally concurrent; SQLite's
                        # online backup provides its point-in-time payload.
                        if source not in self._live_database_paths and (
                            source_stat.st_size,
                            source_stat.st_mtime_ns,
                        ) != (source_after.st_size, source_after.st_mtime_ns):
                            raise BackupError(f"database changed during backup: {source}")
                        self._check_fence()
                        file_record = {
                            "path": backup_relative.as_posix(),
                            "relative_path": source.name,
                            "kind": "database",
                            "owner": f"database:{index}",
                            "sha256": digest,
                            "size": size,
                            "captured_at": captured_at,
                            "source_mtime_ns": source_stat.st_mtime_ns,
                            "source_modified_at": _mtime_iso(source_stat.st_mtime_ns),
                        }
                        files.append(file_record)
                        database_records.append(
                            {
                                "index": index,
                                "source": str(source),
                                "name": source.name,
                                "backup_path": backup_relative.as_posix(),
                                "restore_path": backup_relative.as_posix(),
                                "version": sqlite3.sqlite_version,
                                "sqlite_version": sqlite3.sqlite_version,
                                "sha256": digest,
                                "size": size,
                                "captured_at": captured_at,
                                "time": captured_at,
                                "source_size": source_stat.st_size,
                                "source_mtime_ns": source_stat.st_mtime_ns,
                                "source_modified_at": _mtime_iso(source_stat.st_mtime_ns),
                                "files": [dict(file_record)],
                            }
                        )

                    for index, source_dir in enumerate(artifacts):
                        self._check_fence()
                        component = f"{index:03d}-{_safe_component(source_dir.name, 'artifacts')}"
                        backup_root = PurePosixPath("artifacts") / component
                        artifact_files: list[dict[str, Any]] = []
                        source_total_size = 0
                        source_files = tuple(_iter_regular_files(source_dir))
                        for source_file, source_relative in source_files:
                            self._check_fence()
                            source_stat_before = source_file.stat()
                            backup_relative = backup_root / PurePosixPath(source_relative.as_posix())
                            destination = staging / Path(*backup_relative.parts)
                            digest, size = _copy_file_with_hash(source_file, destination)
                            source_stat_after = source_file.stat()
                            if (source_stat_before.st_size, source_stat_before.st_mtime_ns) != (
                                source_stat_after.st_size,
                                source_stat_after.st_mtime_ns,
                            ):
                                raise BackupError(f"artifact changed during backup: {source_file}")
                            declared_hash = _declared_filename_hash(source_relative.name)
                            if declared_hash is not None and declared_hash != digest:
                                raise BackupError(
                                    f"content-addressed artifact name does not match its content: {source_file}"
                                )
                            file_record = {
                                "path": backup_relative.as_posix(),
                                "relative_path": source_relative.as_posix(),
                                "kind": "artifact",
                                "owner": f"artifact:{index}",
                                "sha256": digest,
                                "size": size,
                                "captured_at": captured_at,
                                "source_mtime_ns": source_stat_before.st_mtime_ns,
                                "source_modified_at": _mtime_iso(source_stat_before.st_mtime_ns),
                                "content_addressed": declared_hash is not None,
                                "declared_hash": declared_hash,
                            }
                            artifact_files.append(file_record)
                            files.append(file_record)
                            source_total_size += size

                        current_source_files = tuple(_iter_regular_files(source_dir))
                        if tuple(relative for _, relative in current_source_files) != tuple(
                            relative for _, relative in source_files
                        ):
                            raise BackupError(f"artifact directory changed during backup: {source_dir}")
                        self._check_fence()

                        aggregate = _directory_digest(artifact_files)
                        artifact_records.append(
                            {
                                "index": index,
                                "source": str(source_dir),
                                "name": source_dir.name,
                                "backup_root": backup_root.as_posix(),
                                "restore_root": backup_root.as_posix(),
                                "sha256": aggregate,
                                "content_hash": aggregate,
                                "size": source_total_size,
                                "file_count": len(artifact_files),
                                "captured_at": captured_at,
                                "time": captured_at,
                                "files": [dict(item) for item in artifact_files],
                            }
                        )

                    self._check_fence()
                    manifest = {
                        "format": BACKUP_FORMAT,
                        "version": MANIFEST_VERSION,
                        "manifest_version": MANIFEST_VERSION,
                        "created_at": captured_at,
                        "sqlite_version": sqlite3.sqlite_version,
                        "consistency": {
                            "mode": self._barrier_mode(barrier),
                            "barrier": type(barrier).__name__,
                            "database_lock": "sqlite-begin-immediate",
                        },
                        "metadata": metadata_copy,
                        "databases": database_records,
                        "artifacts": artifact_records,
                        "files": files,
                        "file_count": len(files),
                        "total_size": sum(int(item["size"]) for item in files),
                        "file_list_sha256": _directory_digest(files),
                    }
                    manifest_path = staging / MANIFEST_FILENAME
                    with manifest_path.open("w", encoding="utf-8") as handle:
                        handle.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
                        handle.write("\n")
                        handle.flush()
                        os.fsync(handle.fileno())
                    self._check_fence()
                    self._publish_staging(staging, output)
                    published = True
            self._check_fence()
            return manifest
        finally:
            if not published and staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _load_manifest(backup_dir: Path) -> dict[str, Any]:
        manifest_path = backup_dir / MANIFEST_FILENAME
        _ensure_regular_file(manifest_path, "manifest")
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupVerificationError(f"cannot read manifest: {manifest_path}: {exc}") from exc
        if not isinstance(value, dict):
            raise BackupVerificationError("manifest root must be an object")
        if value.get("format") != BACKUP_FORMAT:
            raise BackupVerificationError("unsupported backup manifest format")
        manifest_version = value.get("manifest_version", value.get("version"))
        if isinstance(manifest_version, bool) or not isinstance(manifest_version, int) or manifest_version != MANIFEST_VERSION:
            raise BackupVerificationError("unsupported backup manifest version")
        version = value.get("version", manifest_version)
        if isinstance(version, bool) or not isinstance(version, int) or version != manifest_version:
            raise BackupVerificationError("manifest version fields are inconsistent")
        for key in ("databases", "artifacts", "files"):
            if not isinstance(value.get(key), list):
                raise BackupVerificationError(f"manifest field {key!r} must be a list")
        if not isinstance(value.get("metadata", {}), dict):
            raise BackupVerificationError("manifest metadata must be an object")
        consistency = value.get("consistency")
        if consistency is not None:
            if not isinstance(consistency, Mapping):
                raise BackupVerificationError("manifest consistency must be an object")
            if consistency.get("mode") not in {"coordinated", "uncoordinated"}:
                raise BackupVerificationError("manifest consistency mode is invalid")
            if not isinstance(consistency.get("barrier"), str) or not consistency.get("barrier"):
                raise BackupVerificationError("manifest consistency barrier is invalid")
        return value

    @staticmethod
    def _verify_file_record(backup_dir: Path, record: Mapping[str, Any], label: str) -> tuple[str, int]:
        path = _safe_relative_path(record.get("path"), f"{label}.path")
        if path.parts[0] not in {"databases", "artifacts"}:
            raise BackupVerificationError(f"{label}.path is outside the payload roots")
        if record.get("kind") not in {"database", "artifact"}:
            raise BackupVerificationError(f"{label}.kind is invalid")
        relative = _safe_relative_path(record.get("relative_path"), f"{label}.relative_path")
        if record.get("kind") == "database" and len(relative.parts) != 1:
            raise BackupVerificationError(f"{label}.relative_path must be a database filename")
        expected_hash = record.get("sha256")
        if not isinstance(expected_hash, str) or not _HASH_RE.fullmatch(expected_hash):
            raise BackupVerificationError(f"{label}.sha256 is invalid")
        expected_size = record.get("size")
        if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
            raise BackupVerificationError(f"{label}.size is invalid")
        actual_path = backup_dir / Path(*path.parts)
        _ensure_regular_file(actual_path, label)
        actual_hash, actual_size = _hash_file(actual_path)
        if actual_hash != expected_hash or actual_size != expected_size:
            raise BackupVerificationError(f"payload hash or size mismatch: {actual_path}")
        if record.get("kind") == "artifact":
            declared = _declared_filename_hash(relative.name)
            if declared is not None and declared != actual_hash:
                raise BackupVerificationError(f"content-addressed artifact hash mismatch: {actual_path}")
            declared_from_manifest = record.get("declared_hash")
            if declared_from_manifest is not None:
                if not isinstance(declared_from_manifest, str) or not _HASH_RE.fullmatch(declared_from_manifest):
                    raise BackupVerificationError(f"declared artifact hash is invalid: {actual_path}")
                if declared_from_manifest != actual_hash:
                    raise BackupVerificationError(f"declared artifact hash mismatch: {actual_path}")
        return path.as_posix(), actual_size

    @staticmethod
    def _verify_backup_payload(backup_dir: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
        allowed_root_entries = {MANIFEST_FILENAME, "databases", "artifacts"}
        try:
            root_entries = {entry.name for entry in backup_dir.iterdir()}
        except OSError as exc:
            raise BackupVerificationError(f"cannot inspect backup directory: {backup_dir}: {exc}") from exc
        unexpected_root_entries = sorted(root_entries - allowed_root_entries)
        if unexpected_root_entries:
            raise BackupVerificationError(f"backup contains unexpected root entries: {unexpected_root_entries}")
        records = manifest["files"]
        if not manifest["databases"]:
            raise BackupVerificationError("backup manifest must contain at least one database")
        file_map: dict[str, Mapping[str, Any]] = {}
        total_size = 0
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                raise BackupVerificationError(f"manifest files[{index}] must be an object")
            path, size = BackupManager._verify_file_record(backup_dir, record, f"files[{index}]")
            if path in file_map:
                raise BackupVerificationError(f"duplicate manifest payload path: {path}")
            file_map[path] = record
            total_size += size

        file_count = manifest.get("file_count")
        total_size_field = manifest.get("total_size")
        if (
            isinstance(file_count, bool)
            or not isinstance(file_count, int)
            or file_count != len(records)
            or isinstance(total_size_field, bool)
            or not isinstance(total_size_field, int)
            or total_size_field != total_size
        ):
            raise BackupVerificationError("manifest file count or total size is inconsistent")
        if manifest.get("file_list_sha256") != _directory_digest(records):
            raise BackupVerificationError("manifest file list digest mismatch")
        if _payload_files(backup_dir) != set(file_map):
            raise BackupVerificationError("backup payload file list does not match the manifest")

        database_results: list[dict[str, Any]] = []
        referenced_paths: set[str] = set()
        database_backup_paths: set[str] = set()
        database_restore_paths: set[str] = set()
        for index, database in enumerate(manifest["databases"]):
            if not isinstance(database, Mapping):
                raise BackupVerificationError(f"databases[{index}] must be an object")
            if not isinstance(database.get("version"), str) or not database.get("version"):
                raise BackupVerificationError(f"databases[{index}].version is missing")
            database_path = _safe_relative_path(database.get("backup_path"), f"databases[{index}].backup_path")
            if database_path.parts[0] != "databases":
                raise BackupVerificationError(f"databases[{index}].backup_path must be under databases/")
            restore_path = _safe_relative_path(database.get("restore_path"), f"databases[{index}].restore_path")
            if restore_path.parts[0] != "databases":
                raise BackupVerificationError(f"databases[{index}].restore_path must be under databases/")
            if database_path.as_posix() in database_backup_paths:
                raise BackupVerificationError(f"duplicate database backup path: {database_path}")
            if restore_path.as_posix() in database_restore_paths:
                raise BackupVerificationError(f"duplicate database restore path: {restore_path}")
            database_backup_paths.add(database_path.as_posix())
            database_restore_paths.add(restore_path.as_posix())
            database_record = file_map.get(database_path.as_posix())
            if database_record is None or database_record.get("kind") != "database":
                raise BackupVerificationError(f"database payload is not listed in files: {database_path}")
            nested_files = database.get("files")
            if not isinstance(nested_files, list) or len(nested_files) != 1:
                raise BackupVerificationError(f"databases[{index}].files must contain one SQLite file")
            nested = nested_files[0]
            if not isinstance(nested, Mapping) or nested.get("path") != database_path.as_posix():
                raise BackupVerificationError(f"databases[{index}].files is inconsistent")
            if any(
                nested.get(key) != database_record.get(key)
                for key in ("path", "relative_path", "sha256", "size", "kind")
            ):
                raise BackupVerificationError(f"databases[{index}].files hash or kind is inconsistent")
            if (
                database.get("sha256") != database_record.get("sha256")
                or database.get("size") != database_record.get("size")
                or isinstance(database.get("size"), bool)
                or not isinstance(database.get("size"), int)
            ):
                raise BackupVerificationError(f"databases[{index}] hash or size summary is inconsistent")
            actual_path = backup_dir / Path(*database_path.parts)
            _assert_sqlite_readable(actual_path)
            referenced_paths.add(database_path.as_posix())
            references = _verify_decision_references(actual_path)
            database_results.append(
                {
                    "path": database_path.as_posix(),
                    "sha256": database_record["sha256"],
                    "size": database_record["size"],
                    "sqlite_readable": True,
                    **references,
                }
            )

        artifact_results: list[dict[str, Any]] = []
        artifact_backup_roots: list[PurePosixPath] = []
        artifact_restore_roots: list[PurePosixPath] = []
        for index, artifact in enumerate(manifest["artifacts"]):
            if not isinstance(artifact, Mapping):
                raise BackupVerificationError(f"artifacts[{index}] must be an object")
            root = _safe_relative_path(artifact.get("backup_root"), f"artifacts[{index}].backup_root")
            if root.parts[0] != "artifacts":
                raise BackupVerificationError(f"artifacts[{index}].backup_root must be under artifacts/")
            restore_root = _safe_relative_path(artifact.get("restore_root"), f"artifacts[{index}].restore_root")
            if restore_root.parts[0] != "artifacts":
                raise BackupVerificationError(f"artifacts[{index}].restore_root must be under artifacts/")
            if any(
                previous == root
                or previous.is_relative_to(root)
                or root.is_relative_to(previous)
                for previous in artifact_backup_roots
            ):
                raise BackupVerificationError(f"overlapping artifact backup roots: {root}")
            if any(
                root == restore_root
                or root.is_relative_to(restore_root)
                or restore_root.is_relative_to(root)
                for root in artifact_restore_roots
            ):
                raise BackupVerificationError(f"overlapping artifact restore roots: {restore_root}")
            artifact_backup_roots.append(root)
            artifact_restore_roots.append(restore_root)
            nested_files = artifact.get("files")
            if not isinstance(nested_files, list):
                raise BackupVerificationError(f"artifacts[{index}].files must be a list")
            nested_paths: list[str] = []
            nested_size = 0
            for nested_index, nested in enumerate(nested_files):
                if not isinstance(nested, Mapping):
                    raise BackupVerificationError(f"artifacts[{index}].files[{nested_index}] must be an object")
                relative = _safe_relative_path(nested.get("relative_path"), f"artifacts[{index}].files[{nested_index}]")
                expected_path = (root / relative).as_posix()
                if nested.get("path") != expected_path:
                    raise BackupVerificationError(f"artifact file path is inconsistent: {expected_path}")
                if expected_path not in file_map or file_map[expected_path].get("kind") != "artifact":
                    raise BackupVerificationError(f"artifact payload is not listed in files: {expected_path}")
                top_level = file_map[expected_path]
                if any(nested.get(key) != top_level.get(key) for key in ("sha256", "size", "kind", "relative_path")):
                    raise BackupVerificationError(f"artifact file hash or reference is inconsistent: {expected_path}")
                nested_paths.append(relative.as_posix())
                nested_size += int(nested["size"])
                if expected_path in referenced_paths:
                    raise BackupVerificationError(f"payload is referenced more than once: {expected_path}")
                referenced_paths.add(expected_path)
            if len(set(nested_paths)) != len(nested_paths):
                raise BackupVerificationError(f"duplicate artifact relative path in artifacts[{index}]")
            if (
                isinstance(artifact.get("file_count"), bool)
                or not isinstance(artifact.get("file_count"), int)
                or artifact.get("file_count") != len(nested_files)
                or isinstance(artifact.get("size"), bool)
                or not isinstance(artifact.get("size"), int)
                or artifact.get("size") != nested_size
            ):
                raise BackupVerificationError(f"artifacts[{index}] count or size summary is inconsistent")
            aggregate = _directory_digest(nested_files)
            if artifact.get("sha256") != aggregate or artifact.get("content_hash") != aggregate:
                raise BackupVerificationError(f"artifacts[{index}] content digest mismatch")
            artifact_results.append(
                {
                    "path": root.as_posix(),
                    "file_count": len(nested_files),
                    "size": nested_size,
                    "content_hash": aggregate,
                }
            )

        if referenced_paths != set(file_map):
            missing = sorted(set(file_map) - referenced_paths)
            extra = sorted(referenced_paths - set(file_map))
            raise BackupVerificationError(
                f"manifest payload references are incomplete: missing={missing}, extra={extra}"
            )

        return {
            "files_verified": len(records),
            "total_size": total_size,
            "databases": database_results,
            "artifacts": artifact_results,
        }

    @staticmethod
    def _validate_restore_path(value: Any, prefix: str, label: str) -> PurePosixPath:
        path = _safe_relative_path(value, label)
        if path.parts[0] != prefix:
            raise BackupVerificationError(f"{label} must be under {prefix}/")
        return path

    def restore(
        self,
        backup_dir: str | os.PathLike[str],
        target_dir: str | os.PathLike[str] | None = None,
        verify_only: bool = False,
        replay_decision_id: str | None = None,
    ) -> dict[str, Any]:
        """Verify a backup and optionally restore it into an empty isolated directory."""

        self._check_fence()
        backup = _guard_explicit_path(backup_dir, "backup_dir")
        target = None if target_dir is None else _guard_explicit_path(target_dir, "target_dir")
        if target is not None:
            _reject_source_package_path(target, "target_dir")
        if not backup.exists() or not backup.is_dir():
            raise BackupVerificationError(f"backup_dir is not a directory: {backup}")
        if target is None and not verify_only:
            raise BackupError("target_dir is required for restore")
        if target is not None and (target == backup or target.is_relative_to(backup)):
            raise BackupError("target_dir must be outside backup_dir")
        manifest = self._load_manifest(backup)
        verification = self._verify_backup_payload(backup, manifest)
        self._check_fence()
        base_result: dict[str, Any] = {
            "ok": True,
            "status": "verified" if verify_only else "restored",
            "verify_only": bool(verify_only),
            "backup_dir": str(backup),
            "target_dir": str(target) if target is not None else None,
            "manifest_version": manifest["manifest_version"],
            **verification,
        }
        if verify_only:
            if replay_decision_id:
                database_paths = [
                    backup / Path(*PurePosixPath(item["path"]).parts)
                    for item in verification["databases"]
                ]
                if not database_paths:
                    raise BackupVerificationError("cannot replay without a database payload")
                base_result["replay"] = _replay_report_from_database(
                    _find_replay_database(database_paths, replay_decision_id),
                    replay_decision_id,
                )
            return base_result

        assert target is not None
        if target.exists():
            if not target.is_dir():
                raise BackupError(f"target_dir is not a directory: {target}")
            if any(target.iterdir()):
                raise BackupError(f"target_dir must be absent or empty: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.restore-", dir=str(target.parent)))
        published = False
        restored_databases: list[dict[str, Any]] = []
        restored_artifacts: list[dict[str, Any]] = []
        replay_result: dict[str, Any] | None = None
        try:
            for index, database in enumerate(manifest["databases"]):
                backup_relative = _safe_relative_path(database["backup_path"], f"databases[{index}].backup_path")
                restore_relative = self._validate_restore_path(database["restore_path"], "databases", f"databases[{index}].restore_path")
                source = backup / Path(*backup_relative.parts)
                destination = staging / Path(*restore_relative.parts)
                _ensure_regular_file(source, f"databases[{index}] payload")
                digest, size = _copy_file_with_hash(source, destination)
                if digest != database["sha256"] or size != database["size"]:
                    raise BackupVerificationError(f"restored database hash or size mismatch: {destination}")
                _assert_sqlite_readable(destination)
                restored_databases.append(
                    {
                        "path": str(target / Path(*restore_relative.parts)),
                        "relative_path": restore_relative.as_posix(),
                        "sha256": digest,
                        "size": size,
                        "sqlite_readable": True,
                    }
                )

            for index, artifact in enumerate(manifest["artifacts"]):
                backup_root = _safe_relative_path(artifact["backup_root"], f"artifacts[{index}].backup_root")
                restore_root = self._validate_restore_path(artifact["restore_root"], "artifacts", f"artifacts[{index}].restore_root")
                (staging / Path(*restore_root.parts)).mkdir(parents=True, exist_ok=True)
                restored_count = 0
                restored_size = 0
                for nested_index, nested in enumerate(artifact["files"]):
                    relative = _safe_relative_path(nested["relative_path"], f"artifacts[{index}].files[{nested_index}]")
                    source = backup / Path(*(backup_root / relative).parts)
                    destination = staging / Path(*(restore_root / relative).parts)
                    _ensure_regular_file(source, f"artifacts[{index}].files[{nested_index}] payload")
                    digest, size = _copy_file_with_hash(source, destination)
                    if digest != nested["sha256"] or size != nested["size"]:
                        raise BackupVerificationError(f"restored artifact hash or size mismatch: {destination}")
                    restored_count += 1
                    restored_size += size
                restored_artifacts.append(
                    {
                        "path": str(target / Path(*restore_root.parts)),
                        "relative_path": restore_root.as_posix(),
                        "file_count": restored_count,
                        "size": restored_size,
                        "content_hash": artifact["content_hash"],
                    }
                )

            if replay_decision_id:
                replay_paths = [
                    staging / Path(*PurePosixPath(item["relative_path"]).parts)
                    for item in restored_databases
                ]
                replay_result = _replay_report_from_database(
                    _find_replay_database(replay_paths, replay_decision_id),
                    replay_decision_id,
                )
                self._check_fence()

            if target.exists():
                try:
                    target.rmdir()
                except OSError as exc:
                    raise BackupError(f"target_dir changed during restore: {target}") from exc
            self._check_fence()
            staging.replace(target)
            published = True
            self._check_fence()
            return {
                **base_result,
                "databases": restored_databases,
                "artifacts": restored_artifacts,
                **({"replay": replay_result} if replay_result is not None else {}),
            }
        finally:
            if not published and staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def run_recovery_drill(
        self,
        backup_root: str | os.PathLike[str],
        recovery_root: str | os.PathLike[str],
        *,
        replay_decision_id: str | None = None,
        scheduled_for: datetime | None = None,
    ) -> dict[str, Any]:
        """Verify, restore, and replay one local backup in an isolated directory.

        The drill intentionally takes only explicit local paths.  It does not
        construct a runtime, start a provider, enqueue delivery, call an LLM,
        or touch a live database.  When no decision id is configured, the
        lexicographically smallest id in the restored decision database is the
        deterministic replay sample.
        """

        self._check_fence()
        source_root = _guard_explicit_path(backup_root, "backup_root")
        destination_root = _guard_explicit_path(recovery_root, "recovery_root")
        _reject_source_package_path(destination_root, "recovery_root")
        if destination_root == source_root or destination_root.is_relative_to(source_root):
            raise BackupError("recovery_root must be outside backup_root")

        backup = _latest_backup_directory(source_root)
        manifest = self._load_manifest(backup)
        verification = self.restore(backup, verify_only=True)
        database_paths = [
            backup / Path(*PurePosixPath(item["path"]).parts)
            for item in verification["databases"]
        ]
        selected_decision_id = str(replay_decision_id).strip() if replay_decision_id else None
        if selected_decision_id is None:
            selected_decision_id = _first_replay_decision_id(database_paths)
        if selected_decision_id:
            verification = self.restore(
                backup,
                verify_only=True,
                replay_decision_id=selected_decision_id,
            )
        self._check_fence()

        effective_schedule = scheduled_for or datetime.now(timezone.utc)
        if effective_schedule.tzinfo is None:
            effective_schedule = effective_schedule.replace(tzinfo=timezone.utc)
        month_key = effective_schedule.astimezone(timezone.utc).strftime("%Y-%m")
        manifest_digest = str(manifest.get("file_list_sha256") or "")
        if not _HASH_RE.fullmatch(manifest_digest):
            raise BackupVerificationError("backup manifest file_list_sha256 is invalid")
        drill_dir = destination_root / f"{month_key}-{manifest_digest[:16]}"
        target = drill_dir / "restore"
        record_path = drill_dir / "drill.json"

        if record_path.exists() or target.exists():
            if not record_path.is_file() or not target.is_dir():
                raise BackupError(f"recovery drill directory is incomplete: {drill_dir}")
            try:
                existing = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BackupError(f"cannot read existing recovery drill: {record_path}: {exc}") from exc
            if (
                not isinstance(existing, Mapping)
                or existing.get("format") != RECOVERY_DRILL_FORMAT
                or existing.get("status") != "passed"
                or existing.get("source_manifest_sha256") != manifest_digest
                or existing.get("replay_decision_id") != selected_decision_id
            ):
                raise BackupError(f"existing recovery drill does not match the latest backup: {drill_dir}")
            self._check_fence()
            return {**dict(existing), "reused": True}

        restored = self.restore(
            backup,
            target,
            replay_decision_id=selected_decision_id,
        )
        self._check_fence()
        result: dict[str, Any] = {
            "format": RECOVERY_DRILL_FORMAT,
            "version": RECOVERY_DRILL_VERSION,
            "status": "passed",
            "scheduled_for": effective_schedule.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_backup": str(backup),
            "source_manifest_sha256": manifest_digest,
            "replay_decision_id": selected_decision_id,
            "verify": verification,
            "restore": restored,
            "restore_dir": str(target),
            "reused": False,
        }
        drill_dir.mkdir(parents=True, exist_ok=True)
        temporary_record = drill_dir / ".drill.json.tmp"
        with temporary_record.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_record.replace(record_path)
        self._check_fence()
        return result

    def monthly_recovery_drill(
        self,
        backup_root: str | os.PathLike[str],
        recovery_root: str | os.PathLike[str],
        *,
        replay_decision_id: str | None = None,
        scheduled_for: datetime | None = None,
    ) -> dict[str, Any]:
        """Compatibility-named entry point for the scheduled monthly job."""

        return self.run_recovery_drill(
            backup_root,
            recovery_root,
            replay_decision_id=replay_decision_id,
            scheduled_for=scheduled_for,
        )


__all__ = [
    "BACKUP_FORMAT",
    "MANIFEST_FILENAME",
    "MANIFEST_VERSION",
    "RECOVERY_DRILL_FORMAT",
    "RECOVERY_DRILL_VERSION",
    "TRANSIENT_WORKER_DATABASE_NAMES",
    "BackupError",
    "BackupManager",
    "BackupVerificationError",
    "NoopWriteBarrier",
    "WriteBarrier",
]
