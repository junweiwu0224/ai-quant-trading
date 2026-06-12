from __future__ import annotations

import json
import subprocess
import tarfile
from pathlib import Path

from scripts import build_release_bundle


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


def test_build_release_bundle_uses_evidence_delta_and_verifies_archive(tmp_path):
    _run(["git", "init"], tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], tmp_path)
    _run(["git", "config", "user.name", "Test User"], tmp_path)

    _write(tmp_path / "README.md", "before\n")
    _run(["git", "add", "README.md"], tmp_path)
    _run(["git", "commit", "-m", "baseline"], tmp_path)

    _write(tmp_path / "README.md", "after\n")
    _write(tmp_path / "scripts/new_gate.py", "print('ok')\n")
    _write(
        tmp_path / "docs/release-evidence/evidence.md",
        """# Evidence

This is not a production deployment approval.

Modified files currently in the delivery delta:

```text
README.md
```

New files that must be included in a staging/release bundle:

```text
scripts/new_gate.py
```
""",
    )
    _run(["git", "add", "docs/release-evidence/evidence.md"], tmp_path)
    _run(["git", "commit", "-m", "add evidence"], tmp_path)
    _write(
        tmp_path / "docs/release-evidence/evidence.md",
        """# Evidence

This is not a production deployment approval.

Modified files currently in the delivery delta:

```text
README.md
docs/release-evidence/evidence.md
```

New files that must be included in a staging/release bundle:

```text
scripts/new_gate.py
```
""",
    )

    paths = build_release_bundle.build_release_bundle(
        root=tmp_path,
        evidence_path="docs/release-evidence/evidence.md",
        output_dir="releases/test",
        release_id="test-release",
    )

    assert paths.manifest.exists()
    assert paths.archive.exists()
    assert paths.checksum.exists()
    assert build_release_bundle.verify_bundle(root=tmp_path, output_dir="releases/test", release_id="test-release") == []

    manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
    assert manifest["file_count"] == 3
    assert {entry["path"] for entry in manifest["files"]} == {
        "README.md",
        "docs/release-evidence/evidence.md",
        "scripts/new_gate.py",
    }
    assert "not a production deployment approval" in " ".join(manifest["safety_boundary"])

    with tarfile.open(paths.archive, "r:gz") as archive:
        names = set(archive.getnames())
    assert "test-release/manifest.json" in names
    assert "test-release/README.md" in names
    assert "test-release/scripts/new_gate.py" in names


def test_verify_bundle_reports_checksum_mismatch(tmp_path):
    _run(["git", "init"], tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], tmp_path)
    _run(["git", "config", "user.name", "Test User"], tmp_path)
    _write(tmp_path / "README.md", "before\n")
    _run(["git", "add", "README.md"], tmp_path)
    _run(["git", "commit", "-m", "baseline"], tmp_path)
    _write(tmp_path / "README.md", "after\n")
    _write(
        tmp_path / "docs/release-evidence/evidence.md",
        """# Evidence

This is not a production deployment approval.

Modified files currently in the delivery delta:

```text
README.md
```

New files that must be included in a staging/release bundle:

```text
docs/release-evidence/evidence.md
```
""",
    )

    paths = build_release_bundle.build_release_bundle(
        root=tmp_path,
        evidence_path="docs/release-evidence/evidence.md",
        output_dir="releases/test",
        release_id="test-release",
    )
    paths.checksum.write_text("bad  test-release.tar.gz\n", encoding="utf-8")

    issues = build_release_bundle.verify_bundle(root=tmp_path, output_dir="releases/test", release_id="test-release")

    assert "Archive checksum does not match checksum file." in issues


def test_verify_bundle_reports_stale_workspace_file_after_build(tmp_path):
    _run(["git", "init"], tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], tmp_path)
    _run(["git", "config", "user.name", "Test User"], tmp_path)
    _write(tmp_path / "README.md", "before\n")
    _run(["git", "add", "README.md"], tmp_path)
    _run(["git", "commit", "-m", "baseline"], tmp_path)
    _write(tmp_path / "README.md", "after\n")
    _write(
        tmp_path / "docs/release-evidence/evidence.md",
        """# Evidence

This is not a production deployment approval.

Modified files currently in the delivery delta:

```text
README.md
```

New files that must be included in a staging/release bundle:

```text
docs/release-evidence/evidence.md
```
""",
    )

    build_release_bundle.build_release_bundle(
        root=tmp_path,
        evidence_path="docs/release-evidence/evidence.md",
        output_dir="releases/test",
        release_id="test-release",
    )
    _write(tmp_path / "README.md", "after bundle changed\n")

    issues = build_release_bundle.verify_bundle(root=tmp_path, output_dir="releases/test", release_id="test-release")

    assert any("README.md" in issue and "stale" in issue for issue in issues)


def test_build_release_bundle_rejects_archive_checksum_in_bundled_docs(tmp_path):
    _run(["git", "init"], tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], tmp_path)
    _run(["git", "config", "user.name", "Test User"], tmp_path)
    _write(tmp_path / "README.md", "before\n")
    _run(["git", "add", "README.md"], tmp_path)
    _run(["git", "commit", "-m", "baseline"], tmp_path)
    _write(tmp_path / "README.md", "after\n")
    fake_archive_checksum = "a" * 64
    _write(
        tmp_path / "docs/release-evidence/evidence.md",
        f"""# Evidence

This is not a production deployment approval.

Modified files currently in the delivery delta:

```text
README.md
```

New files that must be included in a staging/release bundle:

```text
docs/release-evidence/evidence.md
```

- Bundle SHA256: `{fake_archive_checksum}`.
""",
    )

    try:
        build_release_bundle.build_release_bundle(
            root=tmp_path,
            evidence_path="docs/release-evidence/evidence.md",
            output_dir="releases/test",
            release_id="test-release",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected embedded archive checksum to be rejected")

    assert "must not be embedded" in message
    assert "docs/release-evidence/evidence.md" in message
