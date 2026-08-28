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
