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
    assert rows[0].entry_reasons == ["Qlib score top 5"]
    assert rows[0].risk_notes == ["break MA20 invalidates"]


def test_repository_lists_newest_signals_first_with_limit(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    repo.save_signal(
        SignalLike("sig_old", "qlib_agent", "qlib", "000001", "buy", 0.7, "3-10d", ["old"], ["risk"], 0.1, None, None, "new", "2026-06-01T10:00:00+08:00")
    )
    repo.save_signal(
        SignalLike("sig_new", "qlib_agent", "qlib", "000002", "buy", 0.8, "3-10d", ["new"], ["risk"], 0.1, None, None, "new", "2026-06-01T11:00:00+08:00")
    )

    rows = repo.list_signals(limit=1)

    assert [row.id for row in rows] == ["sig_new"]
