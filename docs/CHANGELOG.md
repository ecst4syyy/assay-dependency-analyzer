# Changelog

Dated entries per slice: what was built, what was decided, what was deferred.

## 2026-10-07 — Slice 0: Orientation
- Reviewed SPEC.md and schema.sql.
- Raised 14 questions: unapproved but necessary libraries, test database,
  limiter storage, scoped npm names, scoring ambiguities, schema/spec
  mismatches. All resolved in docs/DECISIONS.md (D-01 to D-14).

## 2026-10-07 — Slice 1: Skeleton and database
- **Built:** the `create_app()` factory; Dev/Test/Prod configs (Prod refuses to
  start with missing, short or shared secrets); `ALLOWED_HOSTS`; extensions;
  six registered blueprints; SQLAlchemy models for all 11 tables; the initial
  Flask-Migrate migration (generated against MySQL 8.0, `flask db check`
  clean); `/health`; HTML/JSON error handlers; base layout and CSS with no
  inline script or style (CSP-ready).
- **Docker:** the app runs under gunicorn as a non-root user. MySQL 8.0 is not
  published to the host. An init script creates `assay_app` (DML only) and
  `assay_migrate` (DDL), and migrations connect through `MIGRATE_DATABASE_URL`.
  The app is published on `127.0.0.1:5000` only.
- **Decided:** D-01, D-02, D-04, D-06, D-07, D-08.
- **Verified:** `docker compose up` → migration applied, `/health` 200 with
  `db: ok`; `SHOW GRANTS` confirms the least-privilege app user; 11 tests pass.
- **Deferred:** the auth routes, scan, allow-list and admin pages are 404 stubs
  so the layout renders; they are filled in by later slices.

## 2026-10-07 — Slice 2: Authentication and security baseline
- **Built:** registration, login and logout with Flask-Login and Argon2id;
  a 12-character minimum, a 128-character maximum and a 95-entry common-password
  list (`data/common_passwords.txt`); account lockout after 5 failures in 15
  minutes, measured from `audit_log` so the window is exact without a schema
  change; session cleared on login; Secure/HttpOnly/SameSite=Lax cookies with
  a 60-minute idle timeout; Talisman with a strict CSP; Flask-Limiter at
  5/min on login and 10/hour on register; audit events LOGIN_OK, LOGIN_FAIL,
  LOGIN_LOCKED, LOGIN_INACTIVE, ACCOUNT_LOCKED, REGISTER, REGISTER_DUPLICATE,
  LOGOUT, RATE_LIMIT and AUTHZ_DENY; an `admin_required` decorator.
- **Extra hardening not in the spec:** a timing-equalising dummy hash for
  unknown emails; registration that does not reveal existing accounts; an
  open-redirect guard on `next`; `no-store` on authenticated pages; Argon2
  rehash on login when parameters change.
- **Tests:** `tests/security/test_auth.py` (22 tests) covers lockout, lock
  expiry, the window, session regeneration, cookie flags, CSRF rejection and
  acceptance, the rate limit and its audit, headers, enumeration and open
  redirects.
- **Decided:** D-03 (no email-validator), D-12 (Secure cookies on localhost).
- **Deferred:** R-01, server-side session invalidation on logout (see
  threat-model.md).
