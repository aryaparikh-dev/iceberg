# Funding And Deposits

`FundingLedger` records external funding events with these statuses:

- `PENDING`
- `CONFIRMED`
- `REJECTED`
- `CANCELLED`
- `APPLIED`

A pending deposit is never spendable. A confirmed deposit is not spendable for the current day after the daily snapshot has already been created when `intraday_capital_topups_allowed = false`, which is the V1 default.

The AI cannot confirm funding. Confirmation must come from `USER`, `EXTERNAL_RECONCILER`, or `ADMIN`.

There is no UPI, NEFT, RTGS, IMPS, bank-transfer, broker-balance sweep, withdrawal, or external-transfer capability.
