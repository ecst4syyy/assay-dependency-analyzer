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

## 2026-10-12 — Slice 3: Input parser
- **Built:** `app/services/parser.py`. It handles pasted text, uploads and
  single-package lookups.
  - Install commands: pip, pip3, `python -m pip`, uv, poetry, pdm, pipenv,
    npm, yarn, pnpm and bun.
  - Code: Python `import`/`from`; JS `require`, `import ... from`, bare and
    dynamic `import()`.
  - Files: requirements.txt (continuations, comments, markers, `--hash`,
    options) and package.json (`dependencies` and `devDependencies`).
  - Names are PEP 503-normalised. Standard-library and Node built-in modules
    are dropped, and relative imports are skipped.
  - Exact versions are kept (`==` for PyPI, plain semver for npm) so later
    slices can query OSV for a specific release. Ranges become "no version".
  - Results are capped at 200 packages. The parser also reports how many
    entries it rejected and whether it truncated, so the UI can say so.
- **Uploads:** only `.txt` and `.json`, at most 256 KB. Binary content (NUL
  bytes) and non-UTF-8 files are refused, and the content decides the format:
  a `.txt` containing JSON is read as package.json.
  JSON nesting is checked before `json.loads`, so deep nesting can't crash it.
- **Name safety:** the SPEC regex, plus a leading letter or digit (so `..`,
  `.env` and `-rf` are rejected) and scoped npm names (D-09). Paths, URLs,
  `git+`, `file:` and archives are rejected and counted.
- **Bugs found while testing:**
  - prose produced fake packages (D-15);
  - `google.cloud` imports mapped to the wrong package (D-16);
  - `"lodash": "~4.17.21"` in package.json was rejected because `~` looked
    like a home directory;
  - one huge command line took a second to parse (D-18).
- **Alias table:** `data/aliases.json` has the 13 SPEC import aliases plus 22
  more and the dotted namespace table.
- **Tests:** `tests/unit/test_parser.py` has 132 cases, including:
  - 48 paste fixtures, plus a realistic chat answer, a requirements.txt and a
    package.json in `tests/fixtures/`;
  - upload rejections and 22 hostile names (path traversal, `@evil.com`,
    CRLF injection, a Unicode homoglyph, 215-character names);
  - timing tests on pathological input.

  The full suite is at 165 passing, offline.
- **Deferred:** local-module false positives (D-17). Nothing calls the parser
  yet; the scan form wires it up in Slice 7.
