# Architecture

V1 is built as a fail-closed paper-trading and backtesting foundation.

The mandatory execution path is:

```text
Strategy or AI
  -> TradeProposal
  -> RiskEngine
  -> CapitalGuard
  -> ExecutionEngine
  -> BrokerInterface
  -> PaperBroker
```

The strategy layer has no broker reference. The broker has no bank or withdrawal methods. The live broker is only a disabled stub.

Key modules:

- `iceberg/domain`: proposals, market data, candles, decisions, positions, executions, enums.
- `iceberg/capital`: authoritative capital state, funding ledger, daily snapshots, settlement.
- `iceberg/risk`: cost model, permissions, emergency stop, risk approvals.
- `iceberg/execution`: execution gate, paper broker, live disabled stub, forced exits.
- `iceberg/market`: market calendar and IST market clock.
- `iceberg/data`: OHLCV validation.
- `iceberg/backtesting`: realistic backtest loop using the same risk and capital controls.
- `iceberg/strategies`, `iceberg/ai`, `iceberg/features`, `iceberg/learning`: advisory infrastructure only.
