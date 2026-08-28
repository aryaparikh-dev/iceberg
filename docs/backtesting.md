# Backtesting

`BacktestEngine` uses the same `CapitalGuard`, `RiskEngine`, `TransactionCostModel`, and `PaperBroker` path as paper trading.

It accounts for:

- whole shares
- 10% per-stock cap
- cash availability
- transaction costs
- market hours
- liquidity checks
- stale-data rejection
- rejected-trade reporting
- no future candle access at decision time

Strategies receive only the candle history available at the current timestamp.
