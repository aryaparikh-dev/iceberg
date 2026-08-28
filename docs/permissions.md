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
- `FUNDING_CONFIRM`

Strategies and AI cannot modify their own permissions.

Funding confirmation, emergency-stop deactivation, and risk-counter resets require authenticated authorization contexts with the relevant capability. AI contexts lack `FUNDING_CONFIRM`, `CAPITAL_ADMIN`, `BANK_ACCESS`, `WITHDRAW_FUNDS`, and `EXTERNAL_TRANSFER`.
