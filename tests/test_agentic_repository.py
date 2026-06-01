from dataclasses import dataclass, field

from agentic.repository import AgenticRepository


@dataclass(frozen=True)
class SignalLike:
    id: str
    agent_id: str
    source: str
    code: str
    direction: str
    confidence: float
    time_horizon: str
    entry_reasons: list[str]
    risk_notes: list[str]
    suggested_position: float
    stop_loss: float | None
    take_profit: float | None
    status: str
    created_at: str
    expires_at: str | None = None
    metadata: dict = field(default_factory=dict)


def test_repository_saves_and_lists_signals(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    signal = SignalLike(
        "sig_1",
        "qlib_agent",
        "qlib",
        "605066.SH",
        "buy",
        0.72,
        "3-10d",
        ["Qlib score top 5"],
        ["break MA20 invalidates"],
        0.1,
        0.05,
        0.12,
        "new",
        "2026-06-01T15:00:00+08:00",
    )

    repo.save_signal(signal)
    rows = repo.list_signals()

    assert len(rows) == 1
    assert rows[0].id == "sig_1"
    assert rows[0].code == "605066"
    assert rows[0].entry_reasons == ("Qlib score top 5",)


def test_repository_get_signal_raises_for_missing_id(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")

    try:
        repo.get_signal("missing")
    except KeyError as exc:
        assert "signal not found" in str(exc)
    else:
        raise AssertionError("missing signal should raise")
