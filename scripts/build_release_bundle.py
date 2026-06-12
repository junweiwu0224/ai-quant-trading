#!/usr/bin/env python3
"""Build a local release delta archive from the delivery evidence document."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(ROOT_FOR_IMPORT))

from scripts.release_preflight import DEFAULT_EVIDENCE_PATH, _extract_text_block, verify_release_evidence


DEFAULT_RELEASE_ID = "local-delivery-2026-06-12"
DEFAULT_OUTPUT_DIR = "releases/local-delivery-2026-06-12"
ARCHIVE_CHECKSUM_LINE_RE = re.compile(
    r"(?i)\b(?:bundle|archive|release|tar\.gz)\b.*\bsha256\b.*\b[0-9a-f]{64}\b"
    r"|\bsha256\b.*\b(?:bundle|archive|release|tar\.gz)\b.*\b[0-9a-f]{64}\b"
)


@dataclass(frozen=True)
class BundlePaths:
    output_dir: Path
    manifest: Path
    archive: Path
    checksum: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_evidence_files(root: Path, evidence_path: str) -> list[str]:
    text = (root / evidence_path).read_text(encoding="utf-8")
    modified = _extract_text_block(text, "Modified files currently in the delivery delta")
    new = _extract_text_block(text, "New files that must be included in a staging/release bundle")
    return sorted(modified | new)


def _find_embedded_archive_checksums(root: Path, files: list[str]) -> list[str]:
    issues: list[str] = []
    for relative in files:
        path = root / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if ARCHIVE_CHECKSUM_LINE_RE.search(line):
                issues.append(f"{relative}:{line_number}")
    return issues


def _bundle_paths(root: Path, output_dir: str, release_id: str) -> BundlePaths:
    directory = root / output_dir
    return BundlePaths(
        output_dir=directory,
        manifest=directory / "manifest.json",
        archive=directory / f"{release_id}.tar.gz",
        checksum=directory / f"{release_id}.tar.gz.sha256",
    )


def build_release_bundle(
    *,
    root: Path,
    evidence_path: str = DEFAULT_EVIDENCE_PATH,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    release_id: str = DEFAULT_RELEASE_ID,
) -> BundlePaths:
    issues = verify_release_evidence(root=root, evidence_path=evidence_path)
    if issues:
        raise RuntimeError("Release evidence is not current:\n- " + "\n- ".join(issues))

    files = _load_evidence_files(root, evidence_path)
    paths = _bundle_paths(root, output_dir, release_id)
    paths.output_dir.mkdir(parents=True, exist_ok=True)

    missing = [relative for relative in files if not (root / relative).is_file()]
    if missing:
        raise FileNotFoundError("Release bundle files are missing: " + ", ".join(missing))
    embedded_checksums = _find_embedded_archive_checksums(root, files)
    if embedded_checksums:
        raise RuntimeError(
            "Release bundle/archive SHA256 must not be embedded in archived files; "
            "write it only to the .sha256 artifact. Offending lines: "
            + ", ".join(embedded_checksums)
        )

    manifest = {
        "release_id": release_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evidence": evidence_path,
        "archive": paths.archive.name,
        "file_count": len(files),
        "files": [
            {
                "path": relative,
                "size": (root / relative).stat().st_size,
                "sha256": _sha256(root / relative),
            }
            for relative in files
        ],
        "safety_boundary": [
            "local delta archive only",
            "not a production deployment approval",
            "does not run Docker or external providers",
        ],
    }
    paths.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    with tarfile.open(paths.archive, "w:gz") as archive:
        archive.add(paths.manifest, arcname=f"{release_id}/manifest.json")
        for relative in files:
            archive.add(root / relative, arcname=f"{release_id}/{relative}")

    checksum = _sha256(paths.archive)
    paths.checksum.write_text(f"{checksum}  {paths.archive.name}\n", encoding="utf-8")
    return paths


def verify_bundle(*, root: Path, output_dir: str = DEFAULT_OUTPUT_DIR, release_id: str = DEFAULT_RELEASE_ID) -> list[str]:
    paths = _bundle_paths(root, output_dir, release_id)
    issues: list[str] = []
    for path in (paths.manifest, paths.archive, paths.checksum):
        if not path.exists():
            issues.append(f"Missing bundle artifact: {path}")
    if issues:
        return issues

    checksum_line = paths.checksum.read_text(encoding="utf-8").strip().split()
    if not checksum_line or checksum_line[0] != _sha256(paths.archive):
        issues.append("Archive checksum does not match checksum file.")

    manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
    for entry in manifest.get("files", []):
        relative = entry.get("path", "")
        source = root / relative
        if not source.exists():
            issues.append(f"Manifest source file is missing from workspace: {relative}")
            continue
        if source.stat().st_size != entry.get("size"):
            issues.append(f"Manifest size is stale for workspace file: {relative}")
        if _sha256(source) != entry.get("sha256"):
            issues.append(f"Manifest checksum is stale for workspace file: {relative}")

    expected_names = {f"{release_id}/manifest.json"} | {
        f"{release_id}/{entry['path']}" for entry in manifest.get("files", [])
    }
    with tarfile.open(paths.archive, "r:gz") as archive:
        archived_names = set(archive.getnames())
        missing = sorted(expected_names - archived_names)
        extra = sorted(archived_names - expected_names)
        if missing:
            issues.append("Archive is missing manifest entries: " + ", ".join(missing))
        if extra:
            issues.append("Archive contains unexpected entries: " + ", ".join(extra))

    with tempfile.TemporaryDirectory(prefix="aiqt-release-bundle-") as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(paths.archive, "r:gz") as archive:
            archive.extractall(tmp_path, filter="data")
        extracted_manifest = tmp_path / release_id / "manifest.json"
        if not extracted_manifest.exists():
            issues.append("Unpack drill did not produce manifest.json.")

    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify a local release delta bundle.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE_PATH, help="Delivery evidence document.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for bundle artifacts.")
    parser.add_argument("--release-id", default=DEFAULT_RELEASE_ID, help="Release bundle id and archive prefix.")
    parser.add_argument("--verify-only", action="store_true", help="Verify an existing bundle without rebuilding it.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not args.verify_only:
        paths = build_release_bundle(
            root=root,
            evidence_path=args.evidence,
            output_dir=args.output_dir,
            release_id=args.release_id,
        )
        print(f"Wrote manifest: {paths.manifest}")
        print(f"Wrote archive: {paths.archive}")
        print(f"Wrote checksum: {paths.checksum}")

    issues = verify_bundle(root=root, output_dir=args.output_dir, release_id=args.release_id)
    if issues:
        print("Release bundle issues:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Release bundle OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
