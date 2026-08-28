# Persistence And Recovery

V2 safety hardening stores critical safety state in SQLite through `iceberg.persistence`.

Persisted state includes capital state, immutable daily capital snapshots, funding events, portfolio positions, remaining gross cost basis, execution records, decision IDs, idempotency keys, emergency-stop state, user distributions, audit records, and reconciliation status.

`PaperBroker` writes execution, capital, position, cost-basis, idempotency, and reconciliation updates inside a SQLite transaction. If any step fails, the database transaction rolls back and in-memory capital/portfolio state is restored.

On restart, code should restore `CapitalGuard`, `Portfolio`, `FundingLedger`, `EmergencyStop`, and `PaperBroker` from the same `SQLiteStateStore`. The broker reloads decision and idempotency history, so duplicate orders remain blocked after restart.

If persisted local state and broker state disagree, reconciliation marks the portfolio `UNCERTAIN`, broker cash becomes unknown, and new entries fail closed.

SQLite hardens local paper-trading state, but it is not a substitute for process isolation or broker-side controls in a future live system.
