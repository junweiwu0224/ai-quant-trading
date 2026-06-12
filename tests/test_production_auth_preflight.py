from __future__ import annotations

from scripts import production_auth_preflight


ROOT = production_auth_preflight.Path(__file__).resolve().parents[1]
PREFLIGHT_FILES = [
    "dashboard/app.py",
    "dashboard/auth.py",
    "dashboard/session.py",
    "dashboard/account_store.py",
    "tests/test_session_gate.py",
    "tests/test_openclaw_account.py",
]


def _copy_preflight_files(tmp_path):
    for relative in PREFLIGHT_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")


def test_current_production_auth_preflight_has_no_findings():
    assert production_auth_preflight.run_checks(ROOT) == []


def test_production_cors_must_not_allow_localhost(tmp_path):
    _copy_preflight_files(tmp_path)
    app_path = tmp_path / "dashboard/app.py"
    app_text = app_path.read_text(encoding="utf-8")
    app_path.write_text(
        app_text.replace('["https://biga.junwei.fun"]', '["https://biga.junwei.fun", "http://localhost:8001"]'),
        encoding="utf-8",
    )

    findings = production_auth_preflight.run_checks(tmp_path)

    assert any(item.check == "production-cors" for item in findings)


def test_session_cookie_must_be_secure_in_production(tmp_path):
    _copy_preflight_files(tmp_path)
    session_path = tmp_path / "dashboard/session.py"
    session_text = session_path.read_text(encoding="utf-8")
    session_path.write_text(
        session_text.replace('os.getenv("APP_ENV", "development").lower() == "production"', "False"),
        encoding="utf-8",
    )

    findings = production_auth_preflight.run_checks(tmp_path)

    assert any(item.check == "secure-session-cookie" for item in findings)


def test_api_key_compare_must_stay_constant_time(tmp_path):
    _copy_preflight_files(tmp_path)
    auth_path = tmp_path / "dashboard/auth.py"
    auth_text = auth_path.read_text(encoding="utf-8")
    auth_path.write_text(
        auth_text.replace("secrets.compare_digest(candidate, expected)", "candidate == expected"),
        encoding="utf-8",
    )

    findings = production_auth_preflight.run_checks(tmp_path)

    assert any(item.check == "constant-time-api-key" for item in findings)


def test_production_must_not_bootstrap_local_invite(tmp_path):
    _copy_preflight_files(tmp_path)
    store_path = tmp_path / "dashboard/account_store.py"
    store_text = store_path.read_text(encoding="utf-8")
    store_path.write_text(
        store_text.replace('elif os.getenv("APP_ENV", "development").lower() == "production":', "elif False:"),
        encoding="utf-8",
    )

    findings = production_auth_preflight.run_checks(tmp_path)

    assert any(item.check == "production-invite-bootstrap" for item in findings)


def test_registration_audit_must_not_store_plaintext_invite_code(tmp_path):
    _copy_preflight_files(tmp_path)
    store_path = tmp_path / "dashboard/account_store.py"
    store_text = store_path.read_text(encoding="utf-8")
    store_path.write_text(
        store_text.replace('"invite_code_hash": code_hash', '"invite_code": code'),
        encoding="utf-8",
    )

    findings = production_auth_preflight.run_checks(tmp_path)

    assert any(item.check == "invite-audit-redaction" for item in findings)


def test_cli_reports_ok_without_importing_app(capsys):
    exit_code = production_auth_preflight.main(["--root", str(ROOT)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Production auth preflight OK" in output
