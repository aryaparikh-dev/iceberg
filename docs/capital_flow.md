# Capital Flow

`CapitalGuard` is the single authoritative money boundary. It tracks:

- `starting_capital`
- `daily_starting_capital`
- `available_cash`
- `broker_available_cash`
- `settled_cash`
- `unsettled_cash`
- `deployed_capital`
- `realized_pnl`
- `unrealized_pnl`
- `market_value`
- `total_equity`
- `user_distribution`
- `next_day_capital`

Cash and equity are separate. `total_equity = available_cash + market_value`.

`user_distribution` is accounting-only and is permanently excluded from future AI capital. There is no withdrawal or transfer implementation.

Daily capital snapshots are logically immutable. The public workflow does not accept arbitrary caller-supplied capital. `CapitalManager` computes:

```text
previous next_day_capital + eligible externally confirmed funding
```

and then asks `CapitalGuard` to freeze the new `daily_starting_capital`.

Daily settlement no longer accepts fake caller-supplied ending equity. The production settlement path requires a flat portfolio, known broker/cash state, and reconciled cash components. A pure calculation helper remains for testing the profit-sharing formula.

After daily settlement or a new daily snapshot, prior realized and unrealized P&L have been incorporated into `next_day_capital` and reset to zero. During a trading day those fields describe only current-day P&L, which prevents prior-day realized P&L from being counted again inside capital conservation checks.

The 10% per-stock limit is based on remaining gross cost basis, not current market value. If a stock falls after purchase, the price decline does not create more allocation room. The broker repeats this check at the final slippage-adjusted execution price before committing a fill.
