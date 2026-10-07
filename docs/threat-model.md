# Threat model

Kept current as routes are added.

## Assets
- User accounts and password hashes
- Users' scan history (reveals which dependencies a user or team is evaluating)
- Users' private allow-lists (reveals internal package names)
- JWT signing key, session secret, refresh tokens
- Availability of upstream APIs (abuse of them through Assay harms the project's standing)

## Trust boundaries
1. Browser ↔ Flask app (sessions, CSRF, CSP)
2. API client ↔ `/api/v1` (JWT bearer)
3. Flask app ↔ MySQL (least-privilege user, internal network only)
4. Flask app ↔ registries and vulnerability APIs (**all responses untrusted**)

## Routes and threats

| Route | Access | Main threats | Controls |
|---|---|---|---|
| `GET /health` | public | Information disclosure | Returns only status, db flag and version; no stack trace |
| `GET /`, `GET /learn` | public | — | Static content |
| `GET,POST /auth/register` | public | Account enumeration, weak passwords, mass sign-up | Same message whether or not the email exists; 12-char minimum + common-password list; 10/hour per IP; CSRF |
| `GET,POST /auth/login` | public | Credential stuffing, brute force, session fixation, user enumeration via timing, open redirect via `next` | 5/min per IP; lockout after 5 failures in 15 min; dummy Argon2 verify for unknown emails; identical error for every failure; session cleared on login; `next` must be a same-site relative path |
| `POST /auth/logout` | user | Logout CSRF | POST-only with CSRF token |

## Cross-cutting controls
- **Headers (Talisman):** CSP `default-src 'self'` with no `unsafe-inline`,
  `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, a strict
  Referrer-Policy and a Permissions-Policy. Authenticated pages are sent
  `Cache-Control: no-store`.
- **Cookies:** Secure, HttpOnly, SameSite=Lax. The 60-minute idle timeout is
  enforced server-side: Flask rejects a signed session cookie older than
  `PERMANENT_SESSION_LIFETIME`, and every request refreshes it.

## Known residual risks
- **R-01: client-side sessions survive logout.** Flask's default session is
  a signed cookie. Logout clears it in the browser, but a copy captured
  earlier (with Burp, say) stays valid until the 60-minute idle timeout.
  Fix if required: store a per-user session version and check it in
  `user_loader`. That needs a schema change, so it is deferred. It is a good
  candidate finding for the Slice 9 Burp exercise.
- **R-02: shared source IP behind Docker port publishing.** All clients
  can appear to come from the Docker gateway, so per-IP rate limits are
  effectively global on the local demo. Acceptable for a single-user demo.
  Behind a real reverse proxy, use `ProxyFix` with an explicit hop count.
