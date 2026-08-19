from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.execution_protocol import (
    Environment,
    ExecutionPermit,
    OrderIntent,
    OrderIntentBatch,
    RiskDecision,
    RiskDecisionStatus,
    Side,
)


@pytest.fixture
def intent() -> OrderIntent:
    return OrderIntent(
        execution_run_id="run-1",
        account_id="paper-account",
        environment=Environment.PAPER,
        instrument="600519",
        side=Side.BUY,
        quantity="100",
        idempotency_key="intent-1",
    )


def test_order_intent_is_immutable_and_normalizes_quantity(intent: OrderIntent) -> None:
    assert intent.quantity == Decimal("100")
    assert intent.environment is Environment.PAPER
    assert intent.side is Side.BUY

    with pytest.raises((AttributeError, TypeError)):
        intent.quantity = Decimal("200")  # type: ignore[misc]


def test_order_intent_rejects_empty_fields_and_non_positive_quantity() -> None:
    common = {
        "execution_run_id": "run-1",
        "account_id": "paper-account",
        "environment": Environment.PAPER,
        "instrument": "600519",
        "side": Side.BUY,
        "idempotency_key": "intent-invalid",
    }
    for field, value in (("account_id", " "), ("instrument", ""), ("idempotency_key", " ")):
        with pytest.raises(ValueError):
            OrderIntent(**{**common, field: value}, quantity=1)

    for quantity in (0, -1, "NaN", "Infinity"):
        with pytest.raises(ValueError, match="positive"):
            OrderIntent(**common, quantity=quantity)


def test_batch_rejects_empty_values_and_keeps_intents_immutable(intent: OrderIntent) -> None:
    with pytest.raises(ValueError, match="at least one"):
        OrderIntentBatch(batch_id="batch-empty", intents=[])

    batch = OrderIntentBatch(batch_id="batch-1", intents=[intent])
    assert isinstance(batch.intents, tuple)
    assert batch.idempotency_keys == ("intent-1",)

    with pytest.raises((AttributeError, TypeError)):
        batch.intents += (intent,)  # type: ignore[misc]


def test_batch_rejects_duplicate_idempotency_keys(intent: OrderIntent) -> None:
    duplicate = OrderIntent(
        execution_run_id="run-1",
        account_id="paper-account",
        environment="paper",
        instrument="000001",
        side="sell",
        quantity=Decimal("1"),
        idempotency_key="intent-1",
    )

    with pytest.raises(ValueError, match="unique"):
        OrderIntentBatch(batch_id="batch-duplicate", intents=(intent, duplicate))


def test_batch_rejects_mixed_execution_contexts(intent: OrderIntent) -> None:
    mismatched = OrderIntent(
        execution_run_id="run-2",
        account_id="paper-account",
        environment=Environment.PAPER,
        instrument="000001",
        side=Side.SELL,
        quantity=1,
        idempotency_key="intent-2",
    )
    with pytest.raises(ValueError, match="execution_run_id"):
        OrderIntentBatch(batch_id="batch-mixed", intents=(intent, mismatched))


def test_risk_decision_requires_closed_batch_coverage(intent: OrderIntent) -> None:
    second = OrderIntent(
        execution_run_id="run-1",
        account_id="paper-account",
        environment=Environment.PAPER,
        instrument="000001",
        side=Side.SELL,
        quantity=1,
        idempotency_key="intent-2",
    )
    batch = OrderIntentBatch(batch_id="batch-closed", intents=(intent, second))
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="cover"):
        RiskDecision.from_batch(
            batch,
            decision_id="decision-incomplete",
            policy_version="risk-v1",
            evaluated_at=now,
            status=RiskDecisionStatus.PARTIAL,
            approved_intent_keys=("intent-1",),
        )
    with pytest.raises(ValueError, match="belong"):
        RiskDecision.from_batch(
            batch,
            decision_id="decision-foreign",
            policy_version="risk-v1",
            evaluated_at=now,
            status=RiskDecisionStatus.REJECTED,
            rejected_intent_keys=("foreign",),
        )


def test_live_intent_is_fail_closed_even_when_allow_live_is_requested() -> None:
    with pytest.raises(ValueError, match="disabled"):
        OrderIntent(
            execution_run_id="run-live",
            account_id="live-account",
            environment=Environment.LIVE,
            instrument="600519",
            side=Side.BUY,
            quantity=1,
            idempotency_key="live-intent-1",
            allow_live=True,
        )


def test_risk_decision_can_express_full_partial_and_rejected_batches() -> None:
    now = datetime.now(timezone.utc)
    approved = RiskDecision(
        decision_id="decision-full",
        batch_id="batch-1",
        policy_version="risk-v1",
        evaluated_at=now,
        status=RiskDecisionStatus.APPROVED,
        evaluated_intent_keys=("intent-1", "intent-2"),
        approved_intent_keys=("intent-1", "intent-2"),
    )
    partial = RiskDecision(
        decision_id="decision-partial",
        batch_id="batch-1",
        policy_version="risk-v1",
        evaluated_at=now,
        status=RiskDecisionStatus.PARTIAL,
        evaluated_intent_keys=("intent-1", "intent-2"),
        reasons=("cash limit",),
        approved_intent_keys=("intent-1",),
        rejected_intent_keys=("intent-2",),
    )
    rejected = RiskDecision(
        decision_id="decision-rejected",
        batch_id="batch-1",
        policy_version="risk-v1",
        evaluated_at=now,
        status="rejected",
        evaluated_intent_keys=("intent-1", "intent-2"),
        reasons=("kill switch",),
        rejected_intent_keys=("intent-1", "intent-2"),
    )

    assert approved.status is RiskDecisionStatus.APPROVED
    assert partial.status is RiskDecisionStatus.PARTIALLY_APPROVED
    assert partial.rejected_intent_keys == ("intent-2",)
    assert rejected.reasons == ("kill switch",)


def test_rejected_risk_decision_cannot_create_permit() -> None:
    decision = RiskDecision(
        decision_id="decision-rejected",
        batch_id="batch-1",
        policy_version="risk-v1",
        evaluated_at=datetime.now(timezone.utc),
        status=RiskDecisionStatus.REJECTED,
        evaluated_intent_keys=("intent-1",),
        reasons=("risk limit",),
        rejected_intent_keys=("intent-1",),
    )

    with pytest.raises(ValueError, match="rejected"):
        ExecutionPermit.from_risk_decision(
            decision,
            permit_id="permit-1",
            expires_at=datetime.now(timezone.utc),
            fence_token="fence-1",
        )
    with pytest.raises(TypeError):
        ExecutionPermit(  # type: ignore[call-arg]
            permit_id="permit-direct",
            decision_id="decision-rejected",
            batch_id="batch-1",
            expires_at=datetime.now(timezone.utc),
            fence_token="fence-1",
            idempotency_keys=("intent-1",),
        )


def test_permit_preserves_decision_fence_and_idempotency_fields() -> None:
    decision = RiskDecision(
        decision_id="decision-1",
        batch_id="batch-1",
        policy_version="risk-v1",
        evaluated_at=datetime.now(timezone.utc),
        status=RiskDecisionStatus.APPROVED,
        evaluated_intent_keys=("intent-1", "intent-2"),
        approved_intent_keys=("intent-1", "intent-2"),
    )
    expires_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

    permit = ExecutionPermit.from_risk_decision(
        decision,
        permit_id="permit-1",
        expires_at=expires_at,
        fence_token="worker-fence-7",
    )

    assert permit.decision_id == decision.decision_id
    assert permit.batch_id == decision.batch_id
    assert permit.expires_at == expires_at
    assert permit.fence_token == "worker-fence-7"
    assert permit.idempotency_keys == ("intent-1", "intent-2")

    with pytest.raises((AttributeError, TypeError)):
        permit.fence_token = "stale-fence"  # type: ignore[misc]


def test_partial_permit_contains_only_approved_idempotency_keys() -> None:
    decision = RiskDecision(
        decision_id="decision-partial-permit",
        batch_id="batch-1",
        policy_version="risk-v1",
        evaluated_at=datetime.now(timezone.utc),
        status=RiskDecisionStatus.PARTIAL,
        evaluated_intent_keys=("intent-1", "intent-2"),
        approved_intent_keys=("intent-1",),
        rejected_intent_keys=("intent-2",),
    )

    permit = ExecutionPermit.from_decision(
        decision,
        permit_id="permit-partial",
        expires_at=datetime.now(timezone.utc),
        fence_token="worker-fence-partial",
    )

    assert permit.idempotency_keys == ("intent-1",)
