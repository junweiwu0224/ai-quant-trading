from __future__ import annotations

from scripts import deployment_static_preflight


ROOT = deployment_static_preflight.Path(__file__).resolve().parents[1]
PREFLIGHT_FILES = [
    "Dockerfile",
    ".dockerignore",
    ".env.example",
    "docker-compose.yml",
    "docs/decisions/0004-production-release-risk-gates.md",
    "docs/release-evidence/production-release-decision-template.md",
]


def _copy_preflight_files(tmp_path):
    for relative in PREFLIGHT_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")


def test_current_deployment_static_preflight_has_no_hard_findings():
    findings = deployment_static_preflight.run_checks(ROOT)

    assert findings == []


def test_secret_literal_in_compose_is_hard_finding(tmp_path):
    _copy_preflight_files(tmp_path)
    compose = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        compose.replace("OPENAI_API_KEY=${OPENAI_API_KEY:-}", "OPENAI_API_KEY=sk-live-secret"),
        encoding="utf-8",
    )

    findings = deployment_static_preflight.run_checks(tmp_path)

    assert any(item.severity == "hard" and item.check == "secret-values" for item in findings)


def test_trading_services_must_stay_behind_profile(tmp_path):
    _copy_preflight_files(tmp_path)
    compose = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        compose.replace("  live:\n    build: .", "  live:\n    build: .", 1).replace(
            "    profiles:\n      - trading\n\n  backtest:",
            "\n  backtest:",
            1,
        ),
        encoding="utf-8",
    )

    findings = deployment_static_preflight.run_checks(tmp_path)

    assert any(item.severity == "hard" and item.check == "trading-profile" for item in findings)


def test_missing_release_risk_decision_docs_are_hard_findings(tmp_path):
    for relative in ["Dockerfile", ".dockerignore", ".env.example", "docker-compose.yml"]:
        (tmp_path / relative).write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")

    findings = deployment_static_preflight.run_checks(tmp_path)

    assert any(item.severity == "hard" and item.check == "release-risk-decision" for item in findings)


def test_env_example_openclaw_managed_defaults_must_be_deployment_safe(tmp_path):
    _copy_preflight_files(tmp_path)
    env_example = (tmp_path / ".env.example").read_text(encoding="utf-8")
    (tmp_path / ".env.example").write_text(
        env_example.replace("OPENCLAW_MANAGED=false", "OPENCLAW_MANAGED=true").replace(
            "OPENCLAW_AUTO_START=false",
            "OPENCLAW_AUTO_START=true",
        ),
        encoding="utf-8",
    )

    findings = deployment_static_preflight.run_checks(tmp_path)

    assert any(
        item.severity == "hard" and item.check == "env-example" and "OPENCLAW_MANAGED" in item.message
        for item in findings
    )
    assert any(
        item.severity == "hard" and item.check == "env-example" and "OPENCLAW_AUTO_START" in item.message
        for item in findings
    )


def test_env_example_does_not_override_compose_openclaw_urls(tmp_path):
    _copy_preflight_files(tmp_path)
    env_example = (tmp_path / ".env.example").read_text(encoding="utf-8")
    (tmp_path / ".env.example").write_text(
        env_example.replace("OPENCLAW_GATEWAY_URL=", "OPENCLAW_GATEWAY_URL=http://127.0.0.1:18789").replace(
            "OPENCLAW_WEB_URL=",
            "OPENCLAW_WEB_URL=http://127.0.0.1:18789",
        ),
        encoding="utf-8",
    )

    findings = deployment_static_preflight.run_checks(tmp_path)

    assert any(
        item.severity == "hard" and item.check == "env-example" and "OPENCLAW_GATEWAY_URL" in item.message
        for item in findings
    )
    assert any(
        item.severity == "hard" and item.check == "env-example" and "OPENCLAW_WEB_URL" in item.message
        for item in findings
    )


def test_openclaw_auth_none_is_hard_finding(tmp_path):
    _copy_preflight_files(tmp_path)
    compose = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        compose.replace('--auth token --token "$${OPENCLAW_API_KEY}"', "--auth none"),
        encoding="utf-8",
    )

    findings = deployment_static_preflight.run_checks(tmp_path)

    assert any(item.severity == "hard" and item.check == "openclaw-auth" for item in findings)


def test_openclaw_host_port_publish_is_hard_finding(tmp_path):
    _copy_preflight_files(tmp_path)
    compose = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        compose.replace('    expose:\n      - "18789"', '    ports:\n      - "18789:18789"'),
        encoding="utf-8",
    )

    findings = deployment_static_preflight.run_checks(tmp_path)

    assert any(item.severity == "hard" and item.check == "openclaw-port" for item in findings)


def test_fail_on_soft_exits_zero_when_no_soft_findings(capsys):
    exit_code = deployment_static_preflight.main(["--root", str(ROOT), "--fail-on-soft"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Deployment static preflight OK" in output


def test_production_mode_exits_zero_when_no_soft_findings(capsys):
    exit_code = deployment_static_preflight.main(["--root", str(ROOT), "--production"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Deployment static preflight OK" in output


def test_default_cli_reports_ok_without_findings(capsys):
    exit_code = deployment_static_preflight.main(["--root", str(ROOT)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Deployment static preflight OK" in output
