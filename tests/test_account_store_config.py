import pytest

from config.settings import ACCOUNT_DB_PATH, DB_PATH, parse_bool
from dashboard.account_store import AccountStore


def test_account_store_default_db_is_separate_from_market_data_db():
    assert ACCOUNT_DB_PATH.name == "accounts.db"
    assert ACCOUNT_DB_PATH != DB_PATH
    assert AccountStore.__init__.__defaults__[0] == ACCOUNT_DB_PATH


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        (" TRUE ", True),
        ("false", False),
        ("0", False),
        ("unexpected", False),
        ("enabled", False),
        (2, False),
        (None, False),
    ],
)
def test_parse_bool_is_strict_and_fail_closed(value, expected):
    assert parse_bool(value) is expected


def test_workspace_settings_strip_retired_provider_and_entry_flags(tmp_path):
    store = AccountStore(tmp_path / "accounts.db")

    normalized = store._normalize_workspace_settings({"native_panel_mode": "native"})
    assert "retired_setup_completed" not in normalized
    assert "vue_app_default" not in normalized

    bundle = store.create_user("settings-user", "Password123!", "LOCAL1")
    workspace_id = bundle["workspace"]["id"]
    updated = store.update_workspace_settings(
        workspace_id,
        {
            "native_panel_mode": "native",
            "daily_research_enabled": "false",
            "tool_confirmations": {"write_paper_trade": "false"},
        },
    )
    assert "retired_setup_completed" not in updated["settings"]
    assert updated["settings"]["daily_research_enabled"] is False
    assert updated["settings"]["tool_confirmations"]["write_paper_trade"] is False

    ordinary_update = store.update_workspace_settings(workspace_id, {"native_panel_mode": "iframe"})
    assert "retired_setup_completed" not in ordinary_update["settings"]


def test_workspace_boolean_settings_reject_truthy_strings(tmp_path):
    store = AccountStore(tmp_path / "accounts.db")

    normalized = store._normalize_workspace_settings(
        {
            "retired_setup_completed": "enabled",
            "decision_worker_enabled": "yes please",
            "tool_confirmations": {"manage_skills": "1maybe"},
        }
    )

    assert "retired_setup_completed" not in normalized
    assert normalized["decision_worker_enabled"] is False
    assert normalized["tool_confirmations"]["manage_skills"] is False
