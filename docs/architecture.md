# Architecture

V1 is built as a fail-closed paper-trading and backtesting foundation.

The mandatory execution path is:

```text
Strategy or AI
  -> TradeProposal
  -> ExecutionEngine
  -> RiskEngine
  -> ExecutionAuthorization
  -> CapitalGuard
  -> BrokerInterface
  -> PaperBroker
```

The strategy layer has no broker reference. Normal trading code submits a proposal, not a caller-supplied approval. `RiskEngine` returns an auditable decision and, only for approved executable orders, a single-use `ExecutionAuthorization` bound to decision ID, symbol, side, quantity, price, estimated costs, required capital, and approval timestamp.

`PaperBroker` rejects missing, fake, mismatched, or reused authorizations. This is architectural hardening, not a Python sandbox: same-process Python can inspect private internals, so any future live broker must add process isolation and broker-side permission controls.

The broker has no bank or withdrawal methods. The live broker is only a disabled stub.

Key modules:

- `iceberg/domain`: proposals, market data, candles, decisions, positions, executions, enums.
- `iceberg/capital`: authoritative capital state, funding ledger, daily snapshots, settlement.
- `iceberg/risk`: cost model, permissions, emergency stop, risk approvals.
- `iceberg/execution`: execution gate, paper broker, live disabled stub, forced exits.
- `iceberg/persistence`: SQLite schema, database transaction wrapper, state repositories.
- `iceberg/security`: authenticated actors and authorization contexts.
- `iceberg/market`: market calendar and IST market clock.
- `iceberg/data`: OHLCV validation.
- `iceberg/backtesting`: realistic backtest loop using the same risk and capital controls.
- `iceberg/strategies`, `iceberg/ai`, `iceberg/features`, `iceberg/learning`: advisory infrastructure only.
