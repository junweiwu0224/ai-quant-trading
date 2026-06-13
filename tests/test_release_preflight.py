from __future__ import annotations

import subprocess

from scripts import release_preflight


ROOT = release_preflight.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/release-evidence/2026-06-12-local-delivery-readiness.md"


def test_default_preflight_plan_is_local_and_non_deploying():
    plan = release_preflight.build_preflight_plan()
    labels = [step.label for step in plan]
    commands = [" ".join(step.command) for step in plan]
    rendered = "\n".join(commands)

    assert labels == [
        "context-pack",
        "release-evidence",
        "pytest",
        "compileall",
        "diff-check",
    ]
    assert ".venv/bin/python scripts/verify_context_pack.py" in rendered
    assert ".venv/bin/python scripts/release_preflight.py --verify-evidence" in rendered
    assert ".venv/bin/python -m pytest -q -p no:cacheprovider" in rendered
    assert ".venv/bin/python -m compileall -q ." in rendered
    assert "git diff --check" in rendered
    assert "docker compose" not in rendered
    assert "scripts/run_dashboard.py" not in rendered
    assert "scripts/run_live.py" not in rendered
    assert "scripts/run_paper.py" not in rendered
    assert "scripts/sync_data.py" not in rendered
    assert "openclaw" not in rendered.lower()
    assert "production_env_preflight.py" not in rendered
    assert "production_auth_preflight.py" not in rendered
    assert "production_release_decision_verify.py" not in rendered


def test_preflight_plan_can_include_report_audits_explicitly():
    plan = release_preflight.build_preflight_plan(with_audits=True)
    labels = [step.label for step in plan]

    assert labels[-2:] == ["dashboard-data-health", "frontend-render-audit"]
    assert any(step.writes_reports for step in plan if step.label == "dashboard-data-health")
    assert any(step.writes_reports for step in plan if step.label == "frontend-render-audit")


def test_preflight_plan_can_include_static_deployment_gate_explicitly():
    plan = release_preflight.build_preflight_plan(with_deployment_static=True)
    labels = [step.label for step in plan]
    commands = [" ".join(step.command) for step in plan]
    rendered = "\n".join(commands)

    assert labels[-1] == "deployment-static"
    assert ".venv/bin/python scripts/deployment_static_preflight.py" in rendered
    assert "docker compose" not in rendered


def test_preflight_plan_can_include_production_static_gate_explicitly():
    plan = release_preflight.build_preflight_plan(with_production_static=True)
    labels = [step.label for step in plan]
    commands = [" ".join(step.command) for step in plan]
    rendered = "\n".join(commands)

    assert labels[-1] == "deployment-production-static"
    assert ".venv/bin/python scripts/deployment_static_preflight.py --production" in rendered
    assert "docker compose" not in rendered


def test_preflight_plan_can_include_production_env_gate_explicitly():
    plan = release_preflight.build_preflight_plan(with_production_env=True)
    labels = [step.label for step in plan]
    commands = [" ".join(step.command) for step in plan]
    rendered = "\n".join(commands)

    assert labels[-1] == "production-env"
    assert ".venv/bin/python scripts/production_env_preflight.py --profile all" in rendered
    assert "docker compose" not in rendered


def test_preflight_plan_can_include_production_auth_gate_explicitly():
    plan = release_preflight.build_preflight_plan(with_production_auth=True)
    labels = [step.label for step in plan]
    commands = [" ".join(step.command) for step in plan]
    rendered = "\n".join(commands)

    assert labels[-1] == "production-auth"
    assert ".venv/bin/python scripts/production_auth_preflight.py" in rendered
    assert "docker compose" not in rendered


def test_preflight_plan_can_include_release_decision_gate_explicitly():
    plan = release_preflight.build_preflight_plan(with_release_decision=True)
    labels = [step.label for step in plan]
    commands = [" ".join(step.command) for step in plan]
    rendered = "\n".join(commands)

    assert labels[-1] == "production-release-decision"
    assert ".venv/bin/python scripts/production_release_decision_verify.py" in rendered
    assert "docker compose" not in rendered


def test_preflight_dry_run_prints_commands_without_running(monkeypatch, capsys):
    calls = []

    def fake_run(*_args, **_kwargs):
        calls.append((_args, _kwargs))
        return subprocess.CompletedProcess(args=[], returncode=0)

    monkeypatch.setattr(release_preflight.subprocess, "run", fake_run)

    exit_code = release_preflight.main(["--dry-run"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == []
    assert "Release preflight plan" in output
    assert ".venv/bin/python scripts/release_preflight.py --verify-evidence" in output
    assert ".venv/bin/python -m pytest -q -p no:cacheprovider" in output
    assert "docker compose" not in output


def test_preflight_stops_on_first_failed_gate(monkeypatch, capsys):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(args=command, returncode=1)

    monkeypatch.setattr(release_preflight.subprocess, "run", fake_run)

    exit_code = release_preflight.main([])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert len(calls) == 1
    assert "FAILED context-pack" in output


def test_local_delivery_evidence_lists_new_release_files():
    text = EVIDENCE.read_text(encoding="utf-8")

    for required in [
        "docs/release-evidence/2026-06-12-local-delivery-readiness.md",
        "docs/decisions/0004-production-release-risk-gates.md",
        "docs/release-evidence/production-release-decision-template.md",
        "scripts/build_release_bundle.py",
        "scripts/release_preflight.py",
        "scripts/production_auth_preflight.py",
        "scripts/production_env_preflight.py",
        "scripts/production_release_decision_verify.py",
        "tests/test_build_release_bundle.py",
        "tests/test_e2e_local_script.py",
        "tests/test_iwencai_client_status.py",
        "tests/test_iwencai_task_router_api.py",
        "tests/test_production_auth_preflight.py",
        "tests/test_production_env_preflight.py",
        "tests/test_production_release_decision_verify.py",
        "tests/test_release_preflight.py",
    ]:
        assert required in text

    assert "not a production deployment approval" in text
    assert "Docker compose start/stop" in text


def test_release_evidence_matches_current_modified_and_new_files():
    assert release_preflight.verify_release_evidence(root=ROOT) == []


def test_release_evidence_accepts_empty_new_files_block(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence.md"
    evidence.write_text(
        """# Evidence

This is not a production deployment approval.

Modified files currently in the delivery delta:

```text
README.md
```

New files that must be included in a staging/release bundle:

```text
```
""",
        encoding="utf-8",
    )

    def fake_capture(command, *, cwd):
        if command == ("git", "diff", "--name-only", "HEAD", "--"):
            return ["README.md"]
        if command == ("git", "diff", "--name-only", "--diff-filter=A", "HEAD", "--"):
            return []
        if command == ("git", "ls-files", "--others", "--exclude-standard"):
            return []
        raise AssertionError(command)

    monkeypatch.setattr(release_preflight, "_run_capture", fake_capture)
    monkeypatch.setattr(
        release_preflight,
        "_candidate_delta_bases",
        lambda *, root, evidence_path, base_ref: ["HEAD"],
    )

    assert release_preflight.verify_release_evidence(root=tmp_path, evidence_path="evidence.md") == []


def test_release_evidence_reports_missing_current_files(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence.md"
    evidence.write_text(
        """# Evidence

This is not a production deployment approval.

Modified files currently in the delivery delta:

```text
README.md
```

New files that must be included in a staging/release bundle:

```text
scripts/release_preflight.py
```
""",
        encoding="utf-8",
    )

    def fake_capture(command, *, cwd):
        if command == ("git", "diff", "--name-only", "HEAD", "--"):
            return ["README.md", "dashboard/app.py"]
        if command == ("git", "diff", "--name-only", "--diff-filter=A", "HEAD", "--"):
            return []
        if command == ("git", "ls-files", "--others", "--exclude-standard"):
            return ["scripts/release_preflight.py", "tests/new_test.py"]
        raise AssertionError(command)

    monkeypatch.setattr(release_preflight, "_run_capture", fake_capture)
    monkeypatch.setattr(
        release_preflight,
        "_candidate_delta_bases",
        lambda *, root, evidence_path, base_ref: ["HEAD"],
    )

    issues = release_preflight.verify_release_evidence(root=tmp_path, evidence_path="evidence.md")

    assert any("dashboard/app.py" in issue for issue in issues)
    assert any("tests/new_test.py" in issue for issue in issues)


def test_release_evidence_accepts_staged_release_delta(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence.md"
    evidence.write_text(
        """# Evidence

This is not a production deployment approval.

Modified files currently in the delivery delta:

```text
README.md
dashboard/app.py
```

New files that must be included in a staging/release bundle:

```text
docs/release-evidence/evidence.md
scripts/release_preflight.py
```
""",
        encoding="utf-8",
    )

    def fake_capture(command, *, cwd):
        if command == ("git", "diff", "--name-only", "HEAD", "--"):
            return [
                "README.md",
                "dashboard/app.py",
                "docs/release-evidence/evidence.md",
                "scripts/release_preflight.py",
            ]
        if command == ("git", "diff", "--name-only", "--diff-filter=A", "HEAD", "--"):
            return ["docs/release-evidence/evidence.md"]
        if command == ("git", "ls-files", "--others", "--exclude-standard"):
            return ["scripts/release_preflight.py"]
        raise AssertionError(command)

    monkeypatch.setattr(release_preflight, "_run_capture", fake_capture)
    monkeypatch.setattr(
        release_preflight,
        "_candidate_delta_bases",
        lambda *, root, evidence_path, base_ref: ["HEAD"],
    )

    assert release_preflight.verify_release_evidence(root=tmp_path, evidence_path="evidence.md") == []


def test_candidate_delta_bases_searches_deeper_release_history(monkeypatch, tmp_path):
    def fake_ref_exists(ref, *, root):
        return ref == "HEAD" or (ref.startswith("HEAD^") and len(ref) <= len("HEAD" + "^" * 8))

    def fake_path_exists(ref, path, *, root):
        assert ref == "HEAD"
        assert path == "docs/release-evidence/evidence.md"
        return True

    monkeypatch.setattr(release_preflight, "_git_ref_exists", fake_ref_exists)
    monkeypatch.setattr(release_preflight, "_path_exists_in_ref", fake_path_exists)

    bases = release_preflight._candidate_delta_bases(
        root=tmp_path,
        evidence_path="docs/release-evidence/evidence.md",
        base_ref=None,
    )

    assert "HEAD" + "^" * 8 in bases


def test_release_evidence_accepts_committed_release_delta_with_base_ref(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence.md"
    evidence.write_text(
        """# Evidence

This is not a production deployment approval.

Modified files currently in the delivery delta:

```text
README.md
dashboard/app.py
```

New files that must be included in a staging/release bundle:

```text
evidence.md
scripts/release_preflight.py
```
""",
        encoding="utf-8",
    )


    def fake_capture(command, *, cwd):
        if command == ("git", "diff", "--name-only", "HEAD^", "--"):
            return ["README.md", "dashboard/app.py", "evidence.md", "scripts/release_preflight.py"]
        if command == ("git", "diff", "--name-only", "--diff-filter=A", "HEAD^", "--"):
            return ["evidence.md", "scripts/release_preflight.py"]
        if command == ("git", "ls-files", "--others", "--exclude-standard"):
            return []
        raise AssertionError(command)

    monkeypatch.setattr(release_preflight, "_run_capture", fake_capture)
    monkeypatch.setattr(
        release_preflight,
        "_candidate_delta_bases",
        lambda *, root, evidence_path, base_ref: [base_ref or "HEAD^"],
    )

    assert (
        release_preflight.verify_release_evidence(
            root=tmp_path,
            evidence_path="evidence.md",
            base_ref="HEAD^",
        )
        == []
    )


def test_release_evidence_accepts_multi_commit_release_delta(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence.md"
    evidence.write_text(
        """# Evidence

This is not a production deployment approval.

Modified files currently in the delivery delta:

```text
README.md
dashboard/app.py
```

New files that must be included in a staging/release bundle:

```text
evidence.md
scripts/release_preflight.py
tests/test_release_preflight.py
```
""",
        encoding="utf-8",
    )

    def fake_capture(command, *, cwd):
        if command == ("git", "diff", "--name-only", "HEAD", "--"):
            return []
        if command == ("git", "diff", "--name-only", "--diff-filter=A", "HEAD", "--"):
            return []
        if command == ("git", "diff", "--name-only", "HEAD^", "--"):
            return ["evidence.md", "scripts/release_preflight.py", "tests/test_release_preflight.py"]
        if command == ("git", "diff", "--name-only", "--diff-filter=A", "HEAD^", "--"):
            return ["tests/test_release_preflight.py"]
        if command == ("git", "diff", "--name-only", "HEAD^^", "--"):
            return [
                "README.md",
                "dashboard/app.py",
                "evidence.md",
                "scripts/release_preflight.py",
                "tests/test_release_preflight.py",
            ]
        if command == ("git", "diff", "--name-only", "--diff-filter=A", "HEAD^^", "--"):
            return ["evidence.md", "scripts/release_preflight.py", "tests/test_release_preflight.py"]
        if command == ("git", "ls-files", "--others", "--exclude-standard"):
            return []
        raise AssertionError(command)

    monkeypatch.setattr(release_preflight, "_run_capture", fake_capture)
    monkeypatch.setattr(
        release_preflight,
        "_candidate_delta_bases",
        lambda *, root, evidence_path, base_ref: ["HEAD", "HEAD^", "HEAD^^"],
    )

    assert release_preflight.verify_release_evidence(root=tmp_path, evidence_path="evidence.md") == []
