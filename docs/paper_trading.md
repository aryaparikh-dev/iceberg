# Paper Trading

`PaperBroker` is the only functional broker in V1.

It supports:

- risk-approved order submission
- fills and rejections
- idempotency keys
- duplicate-decision protection
- configurable slippage
- transaction costs
- positions
- accounting cash
- settled and unsettled cash
- reconciliation failure handling

It never calls any live endpoint.
