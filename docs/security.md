# Security

V1 contains no real broker integration and no bank integration.

Repository protections:

- `.env` and sensitive local config are ignored.
- keys, credentials, tokens, and logs are ignored.
- `.env.example` contains safe placeholders only.

The code intentionally exposes no withdrawal, bank-transfer, UPI, NEFT, RTGS, IMPS, beneficiary-management, or external-transfer methods.

Execution authorization is hardened but not a true same-process Python security sandbox. Future live integration must add isolation, least-privilege service boundaries, official broker OAuth/API permissions, and independent broker reconciliation.
