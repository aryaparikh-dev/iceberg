# Future Live Trading

Live trading is intentionally unavailable in V1.

`LiveBrokerStub` raises `LiveTradingDisabledError` for order submission and reconciliation. Any future broker integration must be audited, use official broker APIs or OAuth, and retain this order:

```text
TradeProposal -> RiskEngine -> CapitalGuard -> ExecutionEngine -> BrokerInterface
```

Future live integrations must constrain spendable cash by the minimum of permitted AI accounting cash and confirmed broker-available cash. If broker state is unknown or reconciliation fails, no new order may be placed.
