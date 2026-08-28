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
- remaining gross cost basis
- accounting cash
- settled and unsettled cash
- durable execution records
- reconciliation failure handling

It never calls any live endpoint.

Execution is transaction-protected. Capital state, portfolio state, cost basis, execution records, idempotency, decision history, audit, and reconciliation status are persisted through SQLite. If a fill cannot update all required state, the broker rolls back and fails closed.
