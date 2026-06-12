from __future__ import annotations

from scripts import deployment_static_preflight


ROOT = deployment_static_preflight.Path(__file__).resolve().parents[1]


def test_current_deployment_static_preflight_has_no_hard_findings():
    findings = deployment_static_preflight.run_checks(ROOT)

    hard = [item for item in findings if item.severity == "hard"]

    assert hard == []
    assert any(item.check == "openclaw-auth" and item.severity == "soft" for item in findings)


def test_secret_literal_in_compose_is_hard_finding(tmp_path):
    for relative in ["Dockerfile", ".dockerignore", ".env.example", "docker-compose.yml"]:
        (tmp_path / relative).write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")
    compose = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        compose.replace("OPENAI_API_KEY=${OPENAI_API_KEY:-}", "OPENAI_API_KEY=sk-live-secret"),
        encoding="utf-8",
    )

    findings = deployment_static_preflight.run_checks(tmp_path)

    assert any(item.severity == "hard" and item.check == "secret-values" for item in findings)


def test_trading_services_must_stay_behind_profile(tmp_path):
    for relative in ["Dockerfile", ".dockerignore", ".env.example", "docker-compose.yml"]:
        (tmp_path / relative).write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")
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


def test_fail_on_soft_exits_nonzero(capsys):
    exit_code = deployment_static_preflight.main(["--root", str(ROOT), "--fail-on-soft"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "openclaw-auth" in output


def test_default_cli_allows_soft_findings(capsys):
    exit_code = deployment_static_preflight.main(["--root", str(ROOT)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "openclaw-auth" in output
