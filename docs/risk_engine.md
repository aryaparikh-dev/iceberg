# Risk Engine

`RiskEngine` approves or rejects each `TradeProposal`.

Hard checks include:

- paper-trading mode only
- required `PAPER_TRADE` permission
- emergency stop
- known portfolio and broker state
- market open
- last new entry cutoff
- fresh market data
- liquidity controls
- whole-share sizing
- 10% per-stock allocation from frozen `daily_starting_capital`
- 100% portfolio allocation
- transaction costs before approval
- available and broker cash
- no leverage and no negative cash
- daily loss and consecutive loss limits

Rejections return structured reason codes and are logged by the audit layer.
