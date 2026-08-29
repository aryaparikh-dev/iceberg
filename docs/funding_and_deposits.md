# Funding And Deposits

`FundingLedger` records external funding events with these statuses:

- `PENDING`
- `CONFIRMED`
- `REJECTED`
- `CANCELLED`
- `APPLIED`

A pending deposit is never spendable. Creating one requires an authenticated `AuthorizationContext` with `FUNDING_REQUEST`, and `created_by` is derived from the authenticated actor rather than caller-supplied text. A confirmed deposit is not spendable for the current day after the daily snapshot has already been created when `intraday_capital_topups_allowed = false`, which is the V1 default.

The AI cannot create, confirm, apply, or date-shift funding. Confirmation requires an authenticated `AuthorizationContext` with `FUNDING_CONFIRM`; a plain string such as `confirmed_by="ADMIN"` is not accepted as proof of authority.

Confirmed events move to `APPLIED` only when `CapitalManager` includes them in an eligible daily snapshot. Applied events are not applied again after restart or repeated snapshot attempts.

There is no UPI, NEFT, RTGS, IMPS, bank-transfer, broker-balance sweep, withdrawal, or external-transfer capability.
