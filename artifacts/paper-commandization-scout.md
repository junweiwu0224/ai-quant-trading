# Code Context

## Files Retrieved
1. `docs/architecture-v2-plan.md:1-260` - explicit target baseline; it says it is not current implementation, defines PaperWorker ownership, command flow, ExecutionRun and durable facts.
2. `engine/operations_store.py:1-459` - current SQLite command/task/attempt inbox with idempotency, claim, lease renewal, fencing and terminal transitions.
3. `dashboard/routers/paper_control.py:1-369` - current API-local `PaperManager`; start constructs `PaperEngine` in a Dashboard thread, stop/reset mutate process/JSON state, status/trades read in-memory engine.
4. `scripts/run_paper.py:1-78` - current CLI directly acquires `PaperOwnership`, constructs `PaperEngine`, and runs it.
5. `engine/paper_engine.py:1-320` - current engine loop, JSON state manager, DB order loading, matching, DB synchronization and risk behavior.
6. `dashboard/routers/portfolio.py:200-220,408-510,666-760,822-870,1080-1110` - status/portfolio/history/risk APIs read `portfolio_state.json` and JSONL, including an API write for stop-loss fields.
7. `dashboard/routers/paper_trading.py:20-180,230-310` - order API directly calls `OrderManager.create_order/cancel_order`; positions query `paper_positions` directly.
8. `docker-compose.yml:1-105` - dashboard, generic decision worker, and separate `paper` trading profile; no PaperWorker service.
9. `tests/test_paper.py:1-220`, `tests/test_paper_ownership.py:1-120` - current tests cover engine/state/ownership, not command-to-worker integration.

## Key Code

Current API path is direct execution: `PaperManager.start()` acquires `PaperOwnership`, imports/constructs `PaperEngine`, initializes strategy/config, then starts a daemon thread (`dashboard/routers/paper_control.py:96-190`). `stop()` calls the in-memory engine and joins the thread (`:192-219`); `reset()` stops and writes a hard-coded `logs/paper/portfolio_state.json` (`:221-250`). `/status`, `/trades`, and `/equity-curve` depend on the local manager/engine (`:292-369`). This cannot work as a cross-process source of truth.

CLI repeats the bypass: it imports `PaperEngine`, acquires `PaperOwnership`, starts renewal, and calls `engine.run_loop()` (`scripts/run_paper.py:10-70`). Compose starts it as an independent `paper` service (`docker-compose.yml:82-94`), so Dashboard and CLI can compete outside the durable task inbox.

`OperationsStore` already provides the minimum durable command substrate: `commands` stores `idempotency_key`, `kind`, and JSON payload; `tasks` stores queued/running/terminal state; `task_attempts` stores owner, lease token, fence, expiry and status (`engine/operations_store.py:45-96`). `accept_command()` is idempotent (`:130-191`), `claim_task()` reclaims expired attempts and increments fence (`:193-270`), `renew_attempt()` and finish methods enforce owner/token/fence/expiry (`:276-374`). It does not yet provide Paper-specific validation, worker loop, command result, or execution-run tables.

Engine behavior is mixed: `run_once()` obtains quotes, performs stop-loss and strategy callbacks, filters orders, then loads DB manual orders via `_load_db_orders()`, matches, syncs DB, and writes JSON state (`engine/paper_engine.py:205-305`). `PaperStateManager.save/load()` makes `portfolio_state.json` a second state store (`:61-104`). This is exactly the order bypass and JSON dual-write called out by the architecture plan, not solved by commandizing start/stop/reset alone.

`paper_trading.py` still writes orders directly (`:68-99`) and cancellation directly calls `OrderManager.cancel_order()` (`:140-155`); this is an explicit out-of-scope order bypass for this slice. Portfolio reads JSON state/history (`portfolio.py:408-510`, `:666-760`, `:822-870`) and therefore must be adapted to DB projections or remain explicitly legacy/read-only during migration.

## Architecture

Minimum seam:

- Add a Paper command client/helper (likely `engine/paper_commands.py`) used by Dashboard and CLI. It opens the same DB-backed `OperationsStore` database and accepts only typed commands: `paper.start`, `paper.stop`, `paper.reset`.
- Payloads: `paper.start`: `{account_id, strategy, codes, interval_seconds, initial_cash, params, custom_code}` (exclude `enable_risk=false`; API validator already requires true at `paper_control.py:62-76`); `paper.stop`: `{account_id, reason}`; `paper.reset`: `{account_id, initial_cash, reason}`. Require caller-supplied idempotency key and include account in key scope. Do not put mutable portfolio snapshots in payload.
- Add `engine/paper_worker.py`; it is the only component allowed to construct/run/stop/reset `PaperEngine`. Worker claims Paper commands using `OperationsStore` owner ID, renews attempt lease in a heartbeat, and gates every state/fact write on current attempt fence. A worker account lease should remain `execution:paper:<account_id>` (architecture plan section 5); reuse `PaperOwnership` only as a compatibility lock during migration, or replace it with a durable account lease table. Stop must be a command observed by the worker, not API thread signaling.
- Start must create/activate a durable run/config record before engine loop; stop records requested/stopped state; reset should create a new run or reset marker and never overwrite historical ledger/order/fill facts. This slice may use existing paper DB tables for projection but must identify the new run/account key.
- Status across processes: query SQLite authoritative execution/task/run tables and current paper projections in a fresh connection; report task status, run status, lease/worker health, and DB-derived cash/positions/trades. In-memory `PaperManager` status is removed/reduced to compatibility wrapper. JSON may be retained as export/cache during migration but must not be read for authoritative status or used by reset.
- Modify `paper_control.py` endpoints to enqueue and return command/task IDs (preserve endpoint paths and response compatibility fields where practical). `paper_trading.py` order create/cancel remains legacy direct path for now, but response/API should clearly not imply it is consumed by PaperWorker; do not silently claim full commandization.
- Modify `scripts/run_paper.py` into a command producer or deprecate it in favor of `scripts/run_worker.py --paper`; it must not instantiate `PaperEngine`. Add PaperWorker startup to `scripts/run_worker.py` behind explicit `PAPER_WORKER_ENABLED`, with separate owner identity and graceful shutdown.
- Compose: remove/disable the `paper` service as an engine runner; add PaperWorker to `worker` or a dedicated `paper-worker` service sharing `./data` and `./logs`, with explicit enable flag. Avoid two workers consuming same Paper partition. Keep `paper` profile only as command-client compatibility if needed.

Do not treat `commands.payload_json` as a fact source: it is request metadata and immutable intent only. Payload references account/run/config IDs; authoritative run state, orders, fills, ledger and projections live in SQLite tables. The current JSON files (`portfolio_state.json`, `equity_history.jsonl`, trade JSONL) are exports/projections to deprecate, never inputs for status/reset.

## Start Here

Open `engine/operations_store.py:130-374` first, then `dashboard/routers/paper_control.py:96-369`. The former is the reusable durable command/lease primitive; the latter is the exact direct-execution boundary to replace.

## Minimal implementation file list

- Add `engine/paper_worker.py` (consumer, heartbeat, account lease, lifecycle dispatch).
- Add `engine/paper_commands.py` (typed command kinds/payload validation and enqueue helper), unless this belongs in an existing operations client module.
- Modify `dashboard/routers/paper_control.py` (enqueue start/stop/reset; DB-backed status compatibility).
- Modify `scripts/run_paper.py` (enqueue-only compatibility CLI) and `scripts/run_worker.py` (PaperWorker lifecycle/flag).
- Modify `docker-compose.yml` (single PaperWorker owner/service and explicit flag).
- Add/modify Paper command, worker, API contract tests; defer broad Portfolio migration unless needed for status endpoint.
- Likely add schema/migration for paper run/account/status projection and lease ownership; do not overload JSON.

## Required tests (at least 8)

1. Start payload validation rejects empty codes/account and risk-disable attempts.
2. Same idempotency key + same kind/payload returns same command/task; differing payload raises `IdempotencyConflictError`.
3. Dashboard start/stop/reset endpoints enqueue and never construct `PaperEngine`.
4. CLI enqueue path never imports/executes the engine.
5. Worker claims only Paper command kinds and ignores/rejects unrelated tasks.
6. Lease renewal extends expiry; expired attempt is reclaimed with incremented fence.
7. Old fence cannot write terminal state or mutate Paper run after reclaim (`LeaseLostError`).
8. Start creates one durable run; duplicate/replayed start is idempotent; stop is observed by worker and durable.
9. Reset creates a new run/reset fact and preserves prior orders/fills/ledger; it does not write JSON as authority.
10. Cross-process status from a second SQLite connection reports worker/run/projection state without in-memory manager.
11. Worker crash/restart reclaims command and resumes/halts deterministically.
12. Compatibility API response shape and 409/400 behavior remain stable.
13. Explicit regression test documents `paper_trading` direct order create/cancel as out-of-scope and prevents accidental worker claim of those rows.
14. JSON corruption does not change authoritative status/projection.

## Explicitly out of scope for this slice

- `paper_trading.py` manual order create/cancel bypass and its unification into `OrderIntentBatch`.
- `ExecutionRun` complete aggregate, frozen StrategyVersion/ScopeSnapshot/Qualification/Approval references and lifecycle state machine.
- Final worker-side RiskGate with latest account snapshot plus atomic reservation; current engine has position filtering and separate RiskManager paths (`paper_engine.py:143-169,254-262`; `paper_trading.py:23-25`).
- Ledger-first order/fill/reconciliation model and broker/external adapter semantics.
- Portfolio’s full JSON-to-SQL projection migration, historical data backfill, and deletion of JSON writers.
- Multi-account partitioning beyond the minimal `account_id` key and one PaperWorker lease.

## Review Findings / Residual Risks

- P0: `paper_control.py:96-250` and `scripts/run_paper.py:10-70` directly execute `PaperEngine`; commandization must remove both paths or the singleton worker claim is false.
- P0: `paper_engine.py:205-305` loads direct DB manual orders and writes JSON; merely adding commands leaves order bypass and dual facts intact.
- P0: `paper_trading.py:68-155` directly mutates order state, outside durable commands and worker lease.
- P1: `portfolio.py:408-510` and related history/risk endpoints read JSON, so cross-process status will be inconsistent until migrated or explicitly marked legacy.
- P1: current `OperationsStore` task schema only has queued/running/succeeded/failed and no command result/run linkage; Paper lifecycle schema is required.
- P1: `PaperOwnership` is account lock but not equivalent to OperationsStore task attempt fencing; keep both only temporarily with clear ownership semantics.
- P1: existing tests validate engine/state/ownership, not durable command-to-worker lifecycle or stale-writer protection.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Concrete current-code findings, file paths/line ranges, severity-ranked risks, implementation seam, tests, and residual risks are documented above."
    }
  ],
  "changedFiles": [],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "read/grep/find only; no services, trading, or external calls",
      "result": "passed",
      "summary": "Read-only repository inspection completed"
    }
  ],
  "validationOutput": [
    "No files modified; no runtime or external integration invoked."
  ],
  "residualRisks": [
    "Manual order API remains a direct bypass until a later OrderIntentBatch command slice.",
    "ExecutionRun/RiskGate/ledger/reconciliation and JSON projection migration remain unresolved."
  ],
  "noStagedFiles": true,
  "diffSummary": "No code changes; scouting artifact only.",
  "reviewFindings": [
    "P0: Dashboard and CLI directly run PaperEngine.",
    "P0: manual order API bypasses worker and engine writes JSON as a second state source.",
    "P1: cross-process portfolio/status APIs read JSON and current OperationsStore lacks Paper run linkage."
  ],
  "manualNotes": "architecture-v2-plan.md is a target baseline and explicitly not proof of current implementation."
}
```