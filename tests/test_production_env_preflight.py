from __future__ import annotations

from scripts import production_env_preflight


VALID_ENV = {
    "APP_ENV": "production",
    "QUANT_SYSTEM_API_KEY": "quant-system-key-123456",
    "OPENCLAW_API_KEY": "openclaw-token-123456",
    "OPENAI_API_KEY": "opaque-openai-key-for-test-1234567890",
    "OPENAI_BASE_URL": "https://api.openai.example/v1",
    "IWENCAI_COOKIE": "iwencai-cookie-value-123456",
}


def test_base_profile_requires_production_env_and_api_key():
    findings = production_env_preflight.run_checks({}, profiles=["base"])

    assert {item.variable for item in findings} == {"APP_ENV", "QUANT_SYSTEM_API_KEY"}
    assert all(item.severity == "hard" for item in findings)


def test_docker_profile_includes_base_and_openclaw_key():
    env = {
        "APP_ENV": "production",
        "QUANT_SYSTEM_API_KEY": "quant-system-key-123456",
    }

    findings = production_env_preflight.run_checks(env, profiles=["docker"])

    assert [item.variable for item in findings] == ["OPENCLAW_API_KEY"]
    assert findings[0].status == "missing"


def test_all_profiles_pass_with_operator_values():
    findings = production_env_preflight.run_checks(VALID_ENV, profiles=["all"])

    assert findings == []


def test_placeholders_short_values_and_invalid_urls_are_findings():
    env = {
        "APP_ENV": "development",
        "QUANT_SYSTEM_API_KEY": "your-api-key",
        "OPENAI_API_KEY": "short",
        "OPENAI_BASE_URL": "api.openai.example/v1",
    }

    findings = production_env_preflight.run_checks(env, profiles=["llm"])
    status_by_variable = {item.variable: item.status for item in findings}

    assert status_by_variable["APP_ENV"] == "invalid_value"
    assert status_by_variable["QUANT_SYSTEM_API_KEY"] == "placeholder"
    assert status_by_variable["OPENAI_API_KEY"] == "too_short"
    assert status_by_variable["OPENAI_BASE_URL"] == "invalid_url"


def test_cli_output_is_sanitized_and_never_prints_secret_values(monkeypatch, capsys):
    secret_env = {
        "APP_ENV": "production",
        "QUANT_SYSTEM_API_KEY": "opaque-quant-key-for-test-abcdef",
        "OPENCLAW_API_KEY": "opaque-openclaw-key-for-test-abcdef",
        "OPENAI_API_KEY": "opaque-openai-key-for-test-abcdef",
        "OPENAI_BASE_URL": "https://api.openai.example/v1",
        "IWENCAI_COOKIE": "opaque-cookie-value-for-test-abcdef",
    }
    for key in list(production_env_preflight.os.environ):
        monkeypatch.delenv(key, raising=False)
    for key, value in secret_env.items():
        monkeypatch.setenv(key, value)

    exit_code = production_env_preflight.main(["--profile", "all"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Production env preflight OK" in output
    assert "Secret values were not printed." in output
    for secret in secret_env.values():
        if secret == "production" or secret.startswith("https://"):
            continue
        assert secret not in output


def test_json_output_is_sanitized(monkeypatch, capsys):
    for key in list(production_env_preflight.os.environ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("QUANT_SYSTEM_API_KEY", "opaque-quant-key-for-test-abcdef")

    exit_code = production_env_preflight.main(["--json"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"variable": "QUANT_SYSTEM_API_KEY"' in output
    assert '"status": "present"' in output
    assert "opaque-quant-key-for-test-abcdef" not in output
