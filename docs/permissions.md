# Permissions

Default AI permissions:

- `MARKET_DATA_READ`
- `PORTFOLIO_READ`
- `PAPER_TRADE`

Explicitly denied by default:

- `LIVE_TRADE`
- `WITHDRAW_FUNDS`
- `BANK_ACCESS`
- `EXTERNAL_TRANSFER`
- `CAPITAL_ADMIN`
- `FUNDING_REQUEST`
- `FUNDING_CONFIRM`

Strategies and AI cannot modify their own permissions.

Funding requests, funding confirmation, emergency-stop deactivation, and risk-counter resets require authenticated authorization contexts with the relevant capability. Manually constructed contexts are unauthenticated by default, and `PermissionManager.from_context()` does not copy permissions from unauthenticated contexts. AI contexts lack `FUNDING_REQUEST`, `FUNDING_CONFIRM`, `CAPITAL_ADMIN`, `BANK_ACCESS`, `WITHDRAW_FUNDS`, and `EXTERNAL_TRANSFER`.
