import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from engine.events.models import DomainEvent
from engine.events.outbox import SQLiteOutbox
from engine.notifications.adapters import InMemoryNotificationAdapter
from engine.notifications.adapters import DailyBriefNotificationAdapter
from engine.notifications.dispatcher import NotificationDispatcher


def test_outbox_is_idempotent_and_dispatches_once():
    outbox = SQLiteOutbox(sqlite3.connect(":memory:"))
    event = DomainEvent.create("test.ready", "aggregate-1", {"ok": True}, idempotency_key="same-key")
    first_id = outbox.publish(event)
    assert outbox.publish(event) == first_id
    adapter = InMemoryNotificationAdapter()
    results = NotificationDispatcher(outbox, adapter, consumer="test").dispatch()
    assert len(results) == 1
    assert results[0].delivered
    assert len(adapter.events) == 1
    assert outbox.get(first_id).status == "delivered"
    assert NotificationDispatcher(outbox, adapter, consumer="test").dispatch() == []


def test_outbox_can_read_the_immutable_event_by_idempotency_key():
    outbox = SQLiteOutbox(sqlite3.connect(":memory:"))
    event = DomainEvent.create("test.lookup", "aggregate-lookup", {"report_url": "/report/token"}, idempotency_key="lookup-key")

    assert outbox.get_by_idempotency_key("missing") is None
    event_id = outbox.publish(event)

    stored = outbox.get_by_idempotency_key("lookup-key")
    assert stored is not None
    assert stored.event.event_id == event_id
    assert stored.event.payload["report_url"] == "/report/token"


def test_injected_connection_lifecycle_and_caller_transaction_are_preserved():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE caller_state(value TEXT)")
    connection.execute("INSERT INTO caller_state(value) VALUES ('uncommitted')")
    assert connection.in_transaction

    outbox = SQLiteOutbox(connection)

    assert connection.in_transaction
    connection.rollback()
    assert connection.execute("SELECT * FROM caller_state").fetchall() == []

    outbox.close()
    assert connection.execute("SELECT 1").fetchone()[0] == 1


def test_publish_joins_an_existing_external_transaction_without_committing_it():
    connection = sqlite3.connect(":memory:")
    outbox = SQLiteOutbox(connection)
    connection.execute("BEGIN")

    event = DomainEvent.create("test.transaction", "aggregate", {}, idempotency_key="transaction")
    event_id = outbox.publish(event)

    assert connection.in_transaction
    connection.rollback()
    assert outbox.get(event_id) is None


def test_claim_rejects_an_existing_external_transaction_without_committing_it():
    connection = sqlite3.connect(":memory:")
    outbox = SQLiteOutbox(connection)
    outbox.publish(DomainEvent.create("test.claim-transaction", "aggregate", {}, idempotency_key="claim-transaction"))
    connection.execute("BEGIN")

    with pytest.raises(sqlite3.OperationalError, match="active transaction"):
        outbox.claim(consumer="transaction-worker")

    assert connection.in_transaction
    connection.rollback()


def test_readonly_outbox_does_not_create_or_modify_a_database(tmp_path):
    database = tmp_path / "readonly-outbox.db"
    readonly = SQLiteOutbox(database, readonly=True)

    assert not database.exists()
    assert readonly.get("missing") is None
    with pytest.raises(sqlite3.OperationalError, match="read-only"):
        readonly.publish(DomainEvent.create("test.readonly", "aggregate", {}, idempotency_key="readonly"))
    readonly.close()
    assert not database.exists()


def test_injected_connection_can_be_used_from_multiple_threads_when_configured_for_it():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    outbox = SQLiteOutbox(connection)
    errors = []

    def worker(index):
        try:
            outbox.publish(
                DomainEvent.create(
                    "test.threaded",
                    str(index),
                    {},
                    idempotency_key=f"threaded-{index}",
                )
            )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert connection.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0] == 10


def test_permanent_failure_enters_dead_letter():
    outbox = SQLiteOutbox(sqlite3.connect(":memory:"))
    event = DomainEvent.create("test.failed", "aggregate-2", {}, idempotency_key="dead-key")
    event_id = outbox.publish(event)
    adapter = InMemoryNotificationAdapter(fail=True, retryable=False)
    result = NotificationDispatcher(outbox, adapter, consumer="test").dispatch()[0]
    assert not result.delivered
    assert outbox.get(event_id).status == "dead"


def test_stale_in_flight_event_can_be_reclaimed_after_worker_crash():
    outbox = SQLiteOutbox(sqlite3.connect(":memory:"))
    event = DomainEvent.create("test.stale", "aggregate-3", {}, idempotency_key="stale-key")
    event_id = outbox.publish(event)
    claimed_at = datetime.now(timezone.utc)
    assert len(outbox.claim(consumer="crashed-worker", now=claimed_at)) == 1
    assert outbox.get(event_id).status == "in_flight"
    reclaimed = outbox.reclaim_stale(
        older_than_seconds=0,
        now=claimed_at + timedelta(seconds=2),
    )
    assert reclaimed == 1
    assert outbox.get(event_id).status == "pending"


def test_claim_token_fences_reclaimed_worker_ack():
    outbox = SQLiteOutbox(sqlite3.connect(":memory:"))
    event_id = outbox.publish(DomainEvent.create("test.fenced", "aggregate-4", {}, idempotency_key="fenced-key"))
    first = outbox.claim(consumer="worker", limit=1)[0]
    outbox.reclaim_stale(older_than_seconds=0)
    second = outbox.claim(consumer="worker", limit=1)[0]
    assert first.claim_token != second.claim_token
    with pytest.raises(RuntimeError):
        outbox.mark_delivered(event_id, consumer="worker", claim_token=first.claim_token or "")
    outbox.mark_delivered(event_id, consumer="worker", claim_token=second.claim_token or "")
    assert outbox.get(event_id).status == "delivered"


def test_claim_token_fences_reclaimed_worker_failure():
    outbox = SQLiteOutbox(sqlite3.connect(":memory:"))
    event_id = outbox.publish(
        DomainEvent.create("test.fenced-failure", "aggregate", {}, idempotency_key="fenced-failure")
    )
    first = outbox.claim(consumer="worker", limit=1)[0]
    outbox.reclaim_stale(older_than_seconds=0)
    second = outbox.claim(consumer="worker", limit=1)[0]

    with pytest.raises(RuntimeError):
        outbox.mark_failed(
            event_id,
            consumer="worker",
            claim_token=first.claim_token or "",
            error="stale worker",
            retryable=True,
        )

    outbox.mark_failed(
        event_id,
        consumer="worker",
        claim_token=second.claim_token or "",
        error="current worker",
        retryable=False,
    )
    assert outbox.get(event_id).status == "dead"


def test_concurrent_file_backed_claims_do_not_duplicate_events(tmp_path):
    db_path = tmp_path / "outbox.db"
    seed = SQLiteOutbox(db_path)
    for index in range(20):
        seed.publish(DomainEvent.create("test.concurrent", str(index), {}, idempotency_key=f"concurrent-{index}"))
    seed.close()
    claimed = []
    errors = []
    lock = threading.Lock()

    def worker(index):
        try:
            store = SQLiteOutbox(db_path)
            messages = store.claim(consumer=f"worker-{index}", limit=20)
            with lock:
                claimed.extend(message.event.event_id for message in messages)
            store.close()
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(claimed) == len(set(claimed)) == 20


def test_dispatcher_can_filter_event_types():
    outbox = SQLiteOutbox(sqlite3.connect(":memory:"))
    alert = DomainEvent.create("market.alert.triggered", "a", {}, idempotency_key="alert-filter")
    other = DomainEvent.create("daily.brief.ready", "b", {}, idempotency_key="brief-filter")
    outbox.publish(alert)
    outbox.publish(other)
    adapter = InMemoryNotificationAdapter()
    NotificationDispatcher(
        outbox,
        adapter,
        consumer="alerts",
        event_types=("market.alert.triggered",),
    ).dispatch()
    assert [event.event_type for event in adapter.events] == ["market.alert.triggered"]
    assert outbox.get(other.event_id).status == "pending"


def test_daily_brief_adapter_blocks_local_event_without_external_webhook():
    event = DomainEvent.create("daily.brief.ready", "brief-1", {"markdown": "# brief"})
    result = DailyBriefNotificationAdapter().send(event)
    assert not result.delivered
    assert result.details["blocked"] == "daily_brief_webhook_not_configured"


def test_retry_after_from_adapter_controls_next_attempt_time():
    class RetryAfterAdapter:
        def send(self, event):
            from engine.notifications.models import DeliveryResult

            return DeliveryResult.retryable_failure(
                "busy",
                event_id=event.event_id,
                retry_after=17,
            )

    outbox = SQLiteOutbox(sqlite3.connect(":memory:"))
    event = DomainEvent.create("test.retry-after", "aggregate-5", {}, idempotency_key="retry-after")
    event_id = outbox.publish(event)
    now = datetime.now(timezone.utc) + timedelta(seconds=2)
    NotificationDispatcher(outbox, RetryAfterAdapter(), consumer="retry-after").dispatch(now=now)
    record = outbox.get(event_id)
    assert record.status == "pending"
    expected = (now + timedelta(seconds=17)).isoformat(timespec="seconds").replace("+00:00", "Z")
    assert record.available_at == expected
