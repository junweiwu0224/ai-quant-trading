from click.testing import CliRunner

import scripts.run_live as run_live


def test_no_risk_option_is_removed() -> None:
    result = CliRunner().invoke(run_live.main, ["--codes", "000001", "--no-risk"])

    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


def test_live_flag_fails_closed_before_engine_construction(monkeypatch) -> None:
    constructed = []

    def unexpected_engine(*args, **kwargs):
        constructed.append(True)
        raise AssertionError("LiveTradingEngine must not be constructed")

    monkeypatch.setattr(run_live, "LiveTradingEngine", unexpected_engine)
    result = CliRunner().invoke(run_live.main, ["--codes", "000001", "--live"])

    assert result.exit_code != 0
    assert "V2 Live disabled" in result.output
    assert constructed == []


def test_legacy_simulated_cli_always_enables_risk(monkeypatch) -> None:
    captured = {}

    class FakeEngine:
        def __init__(self, *, strategy, codes, broker, config):
            captured.update({"broker": broker, "config": config, "codes": codes})

        def run_loop(self):
            return None

    monkeypatch.setattr(run_live, "LiveTradingEngine", FakeEngine)
    result = CliRunner().invoke(run_live.main, ["--codes", "000001"])

    assert result.exit_code == 0
    assert captured["config"].enable_risk is True
    assert captured["config"].dry_run is True
    assert captured["broker"] is not None
