# StatAudit AI Security Architecture & Threat Model

StatAudit AI uses a state-of-the-art **Double-Token Capability Session model** to enforce ironclad application security while maintaining a completely **loginless and registrationless user experience**. There are no user sign-ups, passwords, logins, or JWTs. Instead, session authority is bound directly to transient client capabilities.

---

## 1. Double-Token Capability Model

Authentication and session ownership are verified via two independent cryptographically secure tokens.

```
                    ┌──────────────────────────────────────────────┐
                    │               Client Browser                 │
                    └──────┬────────────────────────────────┬──────┘
                           │                                │
                           │ 1. stautaudit_session_id       │ 2. Authorization: Bearer
                           │    (Secure httpOnly Cookie)    │    (session_secret)
                           ▼                                ▼
                    ┌──────────────────────────────────────────────┐
                    │               FastAPI Backend                │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │                 MongoDB                      │
                    │   Checks:                                    │
                    │   - Session Exists & Not Revoked             │
                    │   - Secret Hash SHA-256 matches              │
                    │   - IP /24 Subnet Matches                    │
                    │   - User-Agent + Lang Fingerprint matches    │
                    └──────────────────────────────────────────────┘
```

1. **`stataudit_session_id` (httpOnly Cookie)**: A cryptographically secure random token generated using `secrets.token_urlsafe(32)` on backend session creation.
   - Flagged with `httponly=True` to completely block access by malicious JavaScript (preventing XSS session extraction).
   - Flagged with `samesite="strict"` to defend against Cross-Site Request Forgery (CSRF).
   - Flagged with `secure=True` in production to ensure transmission only over encrypted TLS/HTTPS channels.
2. **`session_secret` (Bearer Credential)**: A secondary capability token returned only once in the JSON payload of `POST /api/session/create`.
   - Stored in the client's browser `localStorage` and sent with every API request via the `Authorization: Bearer <secret>` header.
   - Rotated dynamically every 15 minutes by the backend to prevent reuse of stale/intercepted bearer secrets.

Both credentials must be present, valid, and cryptographically linked in MongoDB. If either is missing or mismatched, access is instantly denied.

---

## 2. Threat Model & Defensive Controls

| Threat Vector | Severity | Impacted Area | Mitigation Control |
| :--- | :--- | :--- | :--- |
| **Session Hijacking / XSS** | **High** | Session State | The `stataudit_session_id` cookie is marked `httpOnly`, preventing extraction by malicious frontend scripts. The `session_secret` is verified against its SHA-256 hash in MongoDB, meaning even if a database read leak occurs, session credentials cannot be reversed. |
| **Session Fixation / Replay** | **Medium** | Session Reuse | Dynamic Token Rotation. The `session_secret` rotates every 15 minutes. The backend attaches the new token via the `X-Session-Secret` response header, which is captured and updated in `localStorage` by the frontend fetch interceptor. |
| **CSRF Attacks** | **High** | Protected Endpoints | Enforced `SameSite=Strict` cookie policies. Since no request is processed without the `Authorization: Bearer <secret>` header (which cannot be automatically attached by cross-site forms), CSRF attacks are rendered physically impossible. |
| **BOLA / Multi-Tenant Leakage** | **Critical** | Data Access | Strict workspace isolation. All uploaded ledger files and generated reconciliation spreadsheets are saved in isolated directories on disk resolved via `/data/<session_id>/`. Path traversal exploits (`../`) are strictly blocked via normalization checks. |
| **NoSQL / Parameter Injection** | **High** | Database / Analytics | Strict parameter validation and dynamic schema enforcement. The `safe_filter()` utility rejects query dict models. JSON inputs inside transaction fields (`deep-audit`) containing dictionary-based MongoDB operators (like `{"$gt": 0}`) are immediately rejected with `422 Unprocessable Entity`. |
| **Malicious File Uploads** | **High** | Remote Code Execution | Upload sizing limits are strictly capped at 25MB. Files are verified not only by their extension but by magic byte validation (verifying `.xlsx`/`.xls` file signatures via header headers and `.csv` parsing). |
| **Rate Limit Flooding & DDoS** | **Medium** | Service Availability | PyMongo-backed sliding-window rate limiters capped by IP and session. Multiple rate-limit breaches (e.g., >3 in 5 minutes) trigger an automatic 1-hour IP ban via a global circuit breaker, protecting GenAI resources from resource abuse. |
| **Timing Attacks** | **Low** | Credential Enumeration | Constant-time comparison using `hmac.compare_digest` for secret verification. Failed authentication attempts are hit with an artificial timing delay (up to 250ms), preventing side-channel brute-forcing. |

---

## 3. Secure Session State Lifecycle

- **Session Expiry**: Sessions are configured with an absolute expiration time of **24 hours** from creation, and a sliding inactive timeout of **2 hours** of no activity.
- **Revocation & Wiping**: Calling `POST /api/session/revoke` or clicking "Reset Session" instantly marks the session document as `is_revoked: True` in MongoDB and permanently deletes the local `/data/<session_id>/` disk workspace and GridFS file objects.
- **Database Housekeeping**: MongoDB TTL (Time-To-Live) indexes automatically remove expired session records, rate-limit logs, and temporary IP bans from the database immediately upon expiration.

---

## 4. Double-Token Model Limitations

- **Browser Fingerprint Volatility**: Since the session is cryptographically bound to the client's browser user agent and active subnet, toggling developer mode user-agent emulation, changing browsers, or shifting network connections (e.g. switching from Wi-Fi to a cellular data connection) will invalidate the session. This is an intended security feature.
- **No Static Persistence**: Because session credentials are loginless, clearing browser `localStorage` or site data will completely remove the transient `session_secret`, revoking access to that specific workspace. Important reconciliation reports should be downloaded locally before session termination.
