from __future__ import annotations

from datetime import datetime, timezone
import uuid

from agentic.repository import AgenticRepository, TradingSignal


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SignalService:
    def __init__(self, repo: AgenticRepository):
        self.repo = repo

    def publish(
        self,
        *,
        agent_id: str,
        source: str,
        code: str,
        direction: str,
        confidence: float,
        time_horizon: str,
        entry_reasons: list[str],
        risk_notes: list[str],
        suggested_position: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        expires_at: str | None = None,
        metadata: dict | None = None,
    ) -> TradingSignal:
        signal = TradingSignal(
            f"sig_{uuid.uuid4().hex[:12]}",
            agent_id,
            source,
            code,
            direction,
            confidence,
            time_horizon,
            entry_reasons,
            risk_notes,
            suggested_position,
            stop_loss,
            take_profit,
            "new",
            iso_now(),
            expires_at,
            metadata or {},
        )
        self.repo.save_signal(signal)
        return signal

    def list(self, limit: int = 100) -> list[TradingSignal]:
        return self.repo.list_signals(limit=limit)
