# Security

V1 contains no real broker integration and no bank integration.

Repository protections:

- `.env` and sensitive local config are ignored.
- keys, credentials, tokens, and logs are ignored.
- `.env.example` contains safe placeholders only.

The code intentionally exposes no withdrawal, bank-transfer, UPI, NEFT, RTGS, IMPS, beneficiary-management, or external-transfer methods.

Authenticated authorization contexts are issued only by the trusted context issuer. Manually constructing an `Actor(role=ADMIN)` or `AuthorizationContext(authenticated=True)` does not create authority, and there is no public convenience `admin_context()` helper for strategy code to call. The external reconciler is limited to funding confirmation and does not receive `CAPITAL_ADMIN`.

Execution and context authorization are hardened but not a true same-process Python security sandbox. Future live integration must add isolation, least-privilege service boundaries, official broker OAuth/API permissions, and independent broker reconciliation.
