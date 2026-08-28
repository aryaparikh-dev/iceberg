# Iceberg Trading Foundation

Version 1 is a safety-first Indian-equity paper-trading and backtesting foundation.

**LIVE TRADING DISABLED BY DEFAULT.**

**NO BANK ACCESS.**

**NO WITHDRAWALS.**

**NO LEVERAGE.**

**NO INTRADAY CAPITAL TOPUPS.**

**STATE IS PERSISTED.**

**FAIL CLOSED ON UNCERTAINTY.**

The system is intentionally built around a hard money boundary:

```text
AI / Strategy
  -> TradeProposal
  -> ExecutionEngine
  -> RiskEngine
  -> trusted ExecutionAuthorization
  -> CapitalGuard
  -> BrokerInterface
  -> PaperBroker
```

Strategies and advisory models only create `TradeProposal` objects. They cannot place broker orders, submit arbitrary approval booleans, modify permissions, confirm funding, access banks, transfer money, withdraw funds, or increase their own capital.

## What Exists

- Authoritative `CapitalGuard` for cash, equity, deployed capital, settlement cash, user distribution, and daily capital snapshots.
- `FundingLedger` for pending, confirmed, rejected, cancelled, and applied external funding events.
- Authenticated actors and authorization contexts for funding/risk administration.
- Trusted single-use `ExecutionAuthorization` objects issued only by the risk/execution path.
- SQLite persistence for capital, snapshots, funding, positions, cost basis, execution records, decision IDs, idempotency keys, emergency stop, audit records, and reconciliation status.
- Strict daily profit sharing with the requested `> 10%` threshold.
- Risk engine enforcing 10% per-stock cap using remaining gross cost basis, no leverage, cash availability, transaction costs, liquidity checks, stale-data rejection, market hours, last-entry cutoff, daily loss limit, consecutive closed-trade loss limit, emergency stop, permissions, and fail-closed behavior.
- Functional `PaperBroker` with fills, rejections, duplicate-decision protection, idempotency keys, settlement lag, positions, and cash effects.
- `LiveBrokerStub` that raises `LiveTradingDisabledError` for order submission and reconciliation.
- Market clock and calendar abstractions for Asia/Kolkata NSE-style normal equity hours.
- Backtest engine that passes strategies only timestamp-available candle history and uses a next-bar-open execution convention.
- Explicit backtest transaction-cost, slippage, and liquidity-assumption inputs.
- Data validation for OHLCV integrity, stale data, duplicates, future timestamps, and symbol mismatches.
- Transparent baseline strategies and advisory regime detection.
- Model-evaluation scaffolding with strategy lifecycle gates.

## Running Checks

```bash
python3 -m compileall iceberg tests
python3 -m pytest -q
```

Install test tooling only in a local development environment:

```bash
python3 -m pip install -e ".[dev]"
```

Do not add real secrets, bank details, broker credentials, OAuth tokens, or 2FA material to this repository.
