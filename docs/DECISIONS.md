# Design decisions

Non-obvious choices, with the alternatives considered. Raised during the
planning review and resolved on 2026-10-07.

## D-01 — gunicorn as the production WSGI server
**Decision:** add `gunicorn` (not in SPEC §5).
**Why:** the Flask development server must not run in a container that is
scanned with Nmap/ZAP. SPEC §5 lists no server at all, so one was required.
**Alternatives:** `waitress` (equally fine, less common in Docker examples);
Flask's built-in server (explicitly unsafe for production).

## D-02 — `cryptography` for PyMySQL
**Decision:** add `cryptography`.
**Why:** MySQL 8 defaults to `caching_sha2_password`; PyMySQL needs
`cryptography` to complete that handshake over a non-TLS connection.
**Alternatives:** switch MySQL to `mysql_native_password` (deprecated, weaker).

## D-03 — No `email-validator`; email checked with a regex
**Decision:** WTForms' `Email()` validator needs the `email-validator`
package, which is not approved. Registration uses a conservative `Regexp`
plus a length limit instead.
**Trade-off:** no DNS/deliverability checks, which the project does not need.

## D-04 — Tests run on SQLite in memory; Docker runs MySQL 8
**Decision:** the offline test suite uses `sqlite://`. Column types use
`with_variant()` so the same models emit exact MySQL types (`BIGINT UNSIGNED`,
`ENUM`, `utf8mb4`). The migration was generated against a real MySQL 8.0 and
`flask db check` reports no drift.
**Alternatives:** a MySQL service container for tests (more faithful, but
tests would no longer run offline in a second, and need Docker in CI).
**Risk accepted:** MySQL-only behaviour (strict-mode truncation, ENUM
rejection) is not exercised by pytest. Mitigated by validating lengths and
enum values in application code before insert.

## D-05 — `requests-cache` with a SQLite file; `api_cache` table unused
**Decision:** `requests-cache` has no MySQL backend, so it caches to
`instance/http_cache.sqlite` (memory backend in tests). The `api_cache` model
is kept so the schema still matches `schema.sql`, but nothing writes to it.
**Alternatives:** a custom cache on the `api_cache` table (duplicates
requests-cache's TTL and header handling); Redis (not approved).

## D-06 — Flask-Limiter in-memory storage, one gunicorn worker
**Decision:** `memory://` storage with `--workers 1 --threads 8`.
**Why:** memory storage is per-process. With several worker processes, each
would keep its own counters, and the 5/min login limit would become 5×N/min.
One worker with threads keeps a single counter and is plenty for a
single-server coursework deployment.
**Alternatives:** Redis (not approved; would be the right call for scale-out).

## D-07 — Timestamps added to schema.sql
**Decision:** the coding standards require `created_at` on every model and
`updated_at` on mutable ones, which `schema.sql` did not have. Added
`created_at` to `signals` and `advisories` and `updated_at` to `scans` (its
`status` changes). Tables whose rows are only inserted and deleted
(`findings`, `allowlist_entries`, `audit_log`) or that already carry their own
timestamp (`refresh_tokens.revoked_at`, `kev_entries.synced_at`,
`top_packages.synced_at`, `api_cache.fetched_at`) were left alone.
`schema.sql` was updated so the models still match it exactly.

## D-08 — Spec-table vs schema.sql column names
**Decision:** `schema.sql` wins (SPEC §8 says the models must match it). So
it is `vendor_project`, `rank_pos` and `requested_version`, not the shorter
names in the SPEC §8 summary table.

## D-09 — Scoped npm package names are supported
**Decision:** the SPEC regex `^[A-Za-z0-9._-]{1,214}$` rejects every scoped
npm name (`@types/node`, `@angular/core`), which is a large share of real
npm usage. For npm only, a second strict pattern accepts `@scope/name`, where
both parts match `[a-z0-9][a-z0-9._~-]*`. In URLs the whole name is
percent-encoded with `quote(name, safe="")`, so `@` and `/` become `%40` and
`%2F` and can never change the host or path. The SSRF test covers
`@evil.com`, `@evil.com/x` and similar.
**Alternative:** list scoped packages as a limitation.

## D-10 — Scoring-rule interpretations (SPEC §7.2–7.3 left these open)
- `AGE_VERY_NEW` and `AGE_NEW` are mutually exclusive; the stronger applies.
- `VULN_SEVERE` fires once per package if any advisory has CVSS ≥ 7.0.
  `VULN_MINOR` fires once, only if there is no severe advisory. Stacking one
  signal per advisory would let one old, well-maintained package with ten
  minor CVEs outscore a non-existent one.
- `KEV_LISTED`, `EPSS_HIGH` and `MALICIOUS` each fire at most once per package.
- `NOT_FOUND` skips the metadata signals (`AGE_*`, `SINGLE_RELEASE`,
  `NO_REPO`, `LOW_DOWNLOADS`), which are meaningless for a package with no
  metadata. Name-based signals (`TYPOSQUAT`, `LLM_PATTERN`) still apply.
- If the downloads API fails, `LOW_DOWNLOADS` is not applied. Missing data is
  never treated as evidence either way.
- **Precedence:** if the registry is unreachable the verdict is `UNKNOWN`,
  *unless* the package is allow-listed (`SAFE`) or OSV has a `MAL-` record
  (`DANGER`). A positive malicious report is decisive even without registry
  metadata.
- `ALLOWLISTED` (−1000) is a plain sum, so the result is always `SAFE`.

## D-11 — Admin access to `/scan/<id>`
**Decision:** the owner filter is still applied *in the query*. Admins get
a query without the filter; everyone else gets
`filter_by(id=..., user_id=current_user.id)`. Both paths go through one
helper, `get_scan_for_viewer()`, which has its own tests. Admin views are
recorded in `audit_log`.

## D-12 — Secure cookies over plain HTTP on 127.0.0.1
**Decision:** keep `SESSION_COOKIE_SECURE=True` by default. Current
Chrome, Firefox and Safari treat `http://localhost` and `http://127.0.0.1`
as secure contexts and accept Secure cookies there, so the local demo and the
Burp/ZAP exercises still work. Talisman's `force_https` defaults to off
(env `FORCE_HTTPS`) because the stack has no TLS terminator. Turn it on when
deploying behind TLS.

## D-13 — Project name left as "Assay"
"assay" is already taken on PyPI, npm and GitHub (checked 2026-10-07).
Assay is never published as a package, so there is no collision risk, but
SPEC §0 asks for a free name. Renaming is the owner's branding call. The name
lives in `app/config.py` (`APP_NAME`), the templates and the docs, so it is a
find-and-replace.

## D-14 — `pip-audit` in requirements-dev.txt
`pip-audit` is used for dependency auditing but is not in SPEC §5. It is a
development tool only and is not installed in the image.
