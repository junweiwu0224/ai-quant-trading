"""T+N evaluation for Decision Signals, separate from strategy backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any, Mapping, Protocol, Sequence

from .models import TradingSignal
from .signal_ledger import SignalLedger, SignalOutcome


class PriceSeries(Protocol):
    def __call__(self, code: str, *, start: str, end: str) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class OutcomeEvaluation:
    signal_id: str
    status: str
    horizon_days: int
    observed_days: int
    realized_return: float | None
    max_drawdown: float | None
    sample_sufficient: bool
    reason: str
    outcome: SignalOutcome | None = None
    direction_hit: bool | None = None
    take_profit_hit: bool | None = None
    stop_loss_hit: bool | None = None
    executable: bool = False
    profile: str = "unknown"
    market_phase: str = "unknown"


class DecisionSignalOutcomeEvaluator:
    """Evaluate one signal using a supplied, already-authorized price Adapter."""

    def __init__(self, ledger: SignalLedger, price_series: PriceSeries, *, min_observations: int = 1) -> None:
        self.ledger = ledger
        self.price_series = price_series
        self.min_observations = max(1, int(min_observations))

    def evaluate(self, signal: TradingSignal, *, horizon_days: int, end: str) -> OutcomeEvaluation:
        if horizon_days <= 0:
            raise ValueError("horizon_days must be positive")
        rows = list(self.price_series(signal.code, start=signal.created_at, end=end))
        observations, data_issue = self._prepare_observations(rows)
        required = max(self.min_observations + 1, horizon_days + 1)
        profile, market_phase = self._dimensions(signal)
        if data_issue:
            return OutcomeEvaluation(
                signal_id=signal.id,
                status="invalid_sample",
                horizon_days=horizon_days,
                observed_days=len(observations),
                realized_return=None,
                max_drawdown=None,
                sample_sufficient=False,
                reason=data_issue,
                executable=self._is_executable(signal, observations),
                profile=profile,
                market_phase=market_phase,
            )
        if len(observations) < required:
            return OutcomeEvaluation(
                signal_id=signal.id,
                status="insufficient_sample",
                horizon_days=horizon_days,
                observed_days=len(observations),
                realized_return=None,
                max_drawdown=None,
                sample_sufficient=False,
                reason=f"需要至少 {required} 个收盘价，当前 {len(observations)} 个",
                executable=self._is_executable(signal, observations),
                profile=profile,
                market_phase=market_phase,
            )
        window = observations[: horizon_days + 1]
        closes = [item["close"] for item in window]
        entry = closes[0]
        final = closes[-1]
        direction = 1 if signal.direction == "buy" else -1 if signal.direction == "sell" else 0
        realized_return = (final / entry - 1) * direction if direction else 0.0
        drawdown = self._directional_drawdown(closes, signal.direction)
        status = "win" if realized_return > 0 else "loss" if realized_return < 0 else "flat"
        take_profit_hit, stop_loss_hit = self._target_hits(signal, entry, window)
        executable = self._is_executable(signal, observations)
        outcome = self.ledger.record_outcome(
            signal.id,
            status=status,
            realized_return=realized_return,
            max_drawdown=abs(drawdown),
            metadata={
                "kind": "decision_signal_t+n",
                "outcome_version": 2,
                "horizon_days": horizon_days,
                "observed_days": len(closes),
                "direction_hit": None if direction == 0 else realized_return > 0,
                "take_profit_hit": take_profit_hit,
                "stop_loss_hit": stop_loss_hit,
                "executable": executable,
                "profile": profile,
                "market_phase": market_phase,
            },
            observed_at=end,
        )
        return OutcomeEvaluation(
            signal_id=signal.id,
            status=status,
            horizon_days=horizon_days,
            observed_days=len(closes),
            realized_return=realized_return,
            max_drawdown=abs(drawdown),
            sample_sufficient=True,
            reason="decision signal outcome recorded",
            outcome=outcome,
            direction_hit=None if direction == 0 else realized_return > 0,
            take_profit_hit=take_profit_hit,
            stop_loss_hit=stop_loss_hit,
            executable=executable,
            profile=profile,
            market_phase=market_phase,
        )

    @staticmethod
    def _number(row: Mapping[str, Any], key: str) -> float | None:
        try:
            value = row.get(key)
            number = None if value is None else float(value)
            return number if number is not None and math.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _prepare_observations(
        cls, rows: Sequence[Mapping[str, Any]]
    ) -> tuple[list[dict[str, float | None]], str | None]:
        prepared: list[tuple[tuple[int, float | str] | None, int, dict[str, float | None]]] = []
        timestamped = False
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            timestamp = cls._row_timestamp(row)
            timestamped = timestamped or timestamp is not None
            observation = cls._observation(row)
            close = observation["close"]
            if close is None or close <= 0:
                continue
            prepared.append((timestamp, index, observation))

        if timestamped:
            # Rows without a usable timestamp cannot be placed in a T+N
            # window without inventing chronology, so leave them out.
            prepared = [item for item in prepared if item[0] is not None]
            prepared.sort(key=lambda item: (item[0], item[1]))

        observations: list[dict[str, float | None]] = []
        seen: dict[tuple[int, float | str], dict[str, float | None]] = {}
        for timestamp, _, observation in prepared:
            if timestamp is None:
                observations.append(observation)
                continue
            previous = seen.get(timestamp)
            if previous is None:
                seen[timestamp] = observation
                observations.append(observation)
                continue
            if previous != observation:
                return observations, "价格数据存在重复时间点且价格冲突，无法形成可复现的 T+N 样本"
            # Identical provider duplicates do not create an extra trading day.
        return observations, None

    @staticmethod
    def _row_timestamp(row: Mapping[str, Any]) -> tuple[int, float | str] | None:
        for key in ("date", "trade_date", "datetime", "timestamp", "time", "observed_at"):
            raw = row.get(key)
            if raw is None or str(raw).strip() == "":
                continue
            if isinstance(raw, datetime):
                value = raw
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                return (0, value.timestamp())
            try:
                numeric = float(raw)
                if math.isfinite(numeric):
                    return (0, numeric)
            except (TypeError, ValueError):
                pass
            text = str(raw).strip()
            try:
                value = datetime.fromisoformat(text.replace("Z", "+00:00"))
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                return (0, value.timestamp())
            except ValueError:
                return (1, text)
        return None

    @staticmethod
    def _directional_drawdown(closes: Sequence[float], direction: str) -> float:
        if direction not in {"buy", "sell"}:
            return 0.0
        entry = closes[0]
        equity = [close / entry if direction == "buy" else entry / close for close in closes]
        peak = equity[0]
        max_drawdown = 0.0
        for value in equity:
            peak = max(peak, value)
            max_drawdown = max(max_drawdown, 1 - value / peak)
        return max_drawdown

    @classmethod
    def _observation(cls, row: Mapping[str, Any]) -> dict[str, float | None]:
        close = cls._number(row, "close")
        high = cls._number(row, "high")
        low = cls._number(row, "low")
        # Some local fixtures only provide closes. A close is still a valid
        # conservative intraday bound for direction-only evaluation.
        return {"close": close, "high": high if high is not None else close, "low": low if low is not None else close}

    @staticmethod
    def _metadata(signal: TradingSignal) -> dict[str, Any]:
        metadata = dict(signal.metadata or {})
        decision = metadata.get("decision_signal")
        if isinstance(decision, Mapping):
            metadata = {**metadata, "decision_signal": dict(decision)}
        return metadata

    @classmethod
    def _dimensions(cls, signal: TradingSignal) -> tuple[str, str]:
        metadata = cls._metadata(signal)
        decision = metadata.get("decision_signal") if isinstance(metadata.get("decision_signal"), Mapping) else {}
        model = metadata.get("model_metadata") if isinstance(metadata.get("model_metadata"), Mapping) else {}
        signal_model = signal.model_metadata if isinstance(signal.model_metadata, Mapping) else {}
        decision_model = decision.get("model_metadata") if isinstance(decision.get("model_metadata"), Mapping) else {}
        profile = (
            metadata.get("profile")
            or metadata.get("strategy_profile")
            or decision.get("profile")
            or decision.get("strategy_profile")
            or model.get("profile")
            or model.get("strategy_profile")
            or signal_model.get("profile")
            or signal_model.get("strategy_profile")
            or decision_model.get("profile")
            or decision_model.get("strategy_profile")
            or "unknown"
        )
        research_context = metadata.get("research_context")
        context_phase = research_context.get("market_phase") if isinstance(research_context, Mapping) else None
        market_phase = (
            metadata.get("market_phase")
            or context_phase
            or decision.get("market_phase")
            or model.get("market_phase")
            or signal_model.get("market_phase")
            or "unknown"
        )
        return str(profile), str(market_phase)

    @classmethod
    def _is_executable(cls, signal: TradingSignal, observations: Sequence[Mapping[str, Any]]) -> bool:
        metadata = cls._metadata(signal)
        decision = metadata.get("decision_signal") if isinstance(metadata.get("decision_signal"), Mapping) else {}
        for container in (metadata, decision):
            for key in ("executable", "executability"):
                if key in container:
                    return bool(container[key])
            if str(container.get("execution_status") or "").lower() in {"executable", "ready", "filled"}:
                return True
            if str(container.get("execution_status") or "").lower() in {"not_executable", "unavailable", "blocked"}:
                return False
        signal_model = signal.model_metadata if isinstance(signal.model_metadata, Mapping) else {}
        if "executable" in signal_model:
            return bool(signal_model["executable"])
        if str(signal_model.get("execution_status") or "").lower() in {"executable", "ready", "filled"}:
            return True
        if str(signal_model.get("execution_status") or "").lower() in {"not_executable", "unavailable", "blocked"}:
            return False
        missing_fields = set(signal.missing_fields or ())
        return signal.direction in {"buy", "sell"} and bool(observations) and not missing_fields

    @classmethod
    def _target_hits(
        cls,
        signal: TradingSignal,
        entry: float,
        observations: Sequence[Mapping[str, Any]],
    ) -> tuple[bool | None, bool | None]:
        direction = signal.direction
        if direction not in {"buy", "sell"}:
            return None, None
        target_price = signal.target_price
        if target_price is None and signal.take_profit is not None:
            target_price = entry * (1 + signal.take_profit) if direction == "buy" else entry * (1 - signal.take_profit)
        stop_price = None
        if signal.stop_loss is not None:
            stop_price = entry * (1 - signal.stop_loss) if direction == "buy" else entry * (1 + signal.stop_loss)
        take_profit_hit = None if target_price is None else any(
            (item["high"] or item["close"]) >= target_price if direction == "buy"
            else (item["low"] or item["close"]) <= target_price
            for item in observations[1:]
        )
        stop_loss_hit = None if stop_price is None else any(
            (item["low"] or item["close"]) <= stop_price if direction == "buy"
            else (item["high"] or item["close"]) >= stop_price
            for item in observations[1:]
        )
        return take_profit_hit, stop_loss_hit
