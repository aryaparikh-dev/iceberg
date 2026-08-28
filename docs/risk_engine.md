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
- 10% per-stock allocation from frozen `daily_starting_capital` using remaining gross cost basis
- 100% portfolio allocation
- transaction costs before approval
- available and broker cash
- no leverage and no negative cash
- daily loss and consecutive closed-trade loss limits

Approved executable decisions include a trusted `ExecutionAuthorization`. Rejections return structured reason codes and are logged by the audit layer.

Consecutive losses count closed losing trades. Losing closes increment the counter, winning closes reset it, and break-even closes leave it unchanged. The counter persists across trading days until a winning closed trade or an authorized administrative risk reset.
