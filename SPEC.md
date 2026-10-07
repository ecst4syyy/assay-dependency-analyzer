# Assay — Project Specification

> **Name note:** "Assay" is a placeholder. Before the first commit, confirm the name is free on GitHub, `pypi.org/project/<name>` and `npmjs.com/package/<name>`. If taken, pick another and find-and-replace it across this spec.

---

## 1. One-line description

Assay is a Flask web application that lets a developer paste AI-generated code or upload a dependency file, then checks whether each suggested package actually exists, how trustworthy it looks, and whether it has known or actively exploited vulnerabilities — showing a plain-language reason for every verdict.

## 2. Problem statement

Developers increasingly copy `pip install` and `npm install` lines straight out of AI chat assistants. Large language models sometimes invent package names that do not exist. Because the same fake names recur across runs, an attacker can register one on PyPI or npm and wait for people to install it. This is called **slopsquatting**.

Separately, a package can be perfectly real and still be unsafe: abandoned, brand new, or carrying a vulnerability that is already being exploited in the wild.

Assay checks both problems in one pass and explains itself, so the user learns *why* a dependency is risky rather than just seeing a red badge.

**Important framing for the report:** slopsquatting is a *measured and plausible* risk, not a confirmed widespread attack wave. Write it that way. Overclaiming is the easiest way to lose marks.

## 3. Target users

- Students and developers using AI coding assistants
- Small development teams without a commercial software-composition-analysis tool
- Instructors demonstrating supply-chain risk

## 4. Scope

### In scope
- PyPI (Python) and npm (JavaScript) ecosystems only
- Metadata analysis only — Assay **never downloads, installs, executes or unpacks a package**
- Web UI (Jinja2) plus a REST API
- Single-server deployment via Docker Compose

### Out of scope (state this in the report as a limitation)
- Other ecosystems (Go, Maven, crates.io, RubyGems)
- Transitive dependency resolution — only the packages the user supplies are checked
- Static analysis of package source code
- Any form of defensive package registration

## 5. Technology stack (fixed — do not substitute)

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Web framework | Flask 3.x (application-factory pattern, blueprints) |
| Templating | Jinja2 (server-rendered) |
| Database | MySQL 8.0 |
| ORM | SQLAlchemy 2.x + Flask-SQLAlchemy, PyMySQL driver |
| Migrations | Flask-Migrate (Alembic) |
| Web auth | Flask-Login (server-side sessions) |
| API auth | Flask-JWT-Extended (access + refresh tokens) |
| Forms / CSRF | Flask-WTF + WTForms |
| Rate limiting | Flask-Limiter |
| Security headers | Flask-Talisman |
| Password hashing | Argon2 (`argon2-cffi`) |
| HTTP client | `requests` + `requests-cache` |
| Fuzzy matching | `rapidfuzz` |
| Requirement parsing | `packaging` |
| Scheduled jobs | Flask CLI commands run by cron (simpler and more testable than APScheduler) |
| Testing | `pytest`, `pytest-flask`, `responses` |
| Linting | `ruff`, `black`, `bandit` |
| Deployment | Docker Compose (app + MySQL) |
| Version control | Git / GitHub |

**Dependency rule:** use only the libraries listed above. Any addition must be justified and recorded in `docs/DECISIONS.md`.

---

## 6. Data sources

All are free and require no API key. Every outbound host must be on a hard-coded allow-list.

| Source | Endpoint | Method | Notes |
|---|---|---|---|
| PyPI JSON API | `https://pypi.org/pypi/<name>/json` | GET | 404 means the package does not exist. The `downloads` field always returns `-1` and is deprecated — do not use it. The `releases` key is deprecated but still present; use it for the release count and earliest upload date, and note the deprecation in a code comment. Use `upload_time_iso_8601` from file entries for dates. |
| npm registry | `https://registry.npmjs.org/<name>` | GET | 404 means it does not exist. `time.created` gives first publish; `versions` gives the release count. |
| npm downloads | `https://api.npmjs.org/downloads/point/last-month/<name>` | GET | Monthly download count. May return 429. |
| pypistats | `https://pypistats.org/api/packages/<name>/recent` | GET | Monthly downloads for PyPI. IP rate-limited; cache for 24 h. |
| OSV | `https://api.osv.dev/v1/querybatch` | POST | Up to 1000 queries per request. Returns **only vulnerability IDs**, not full records. |
| OSV detail | `https://api.osv.dev/v1/vulns/<id>` | GET | Fetch full record (summary, aliases, severity) for each ID found. |
| EPSS | `https://api.first.org/data/v1/epss?cve=CVE-1,CVE-2` | GET | Comma-separated CVE list, **max 2000 characters** including commas — batch accordingly. Scores are returned as strings; cast to float. |
| CISA KEV | `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json` | GET | One JSON file. Sync daily into the local DB; never query per-request. |

### HTTP client rules
- Timeout: 5 s connect, 10 s read.
- Retries: 2, with exponential backoff, only on 429/5xx.
- Custom `User-Agent`: `Assay/1.0 (student security project; +<repo-url>)`.
- Cache responses with `requests-cache` (24 h for metadata, 24 h for downloads).
- Treat *any* non-200, non-404 response as "unknown", never as "safe".

---

## 7. Core logic

### 7.1 Input parsing

Accept three input types:
1. **Paste** — free text: AI chat output, code, or a list of names.
2. **Upload** — `requirements.txt` or `package.json` (max 256 KB).
3. **Single package** — name + optional version + ecosystem.

Extract candidate names using these patterns:
- `pip install X Y Z` and `pip3 install ...`
- `npm install X` / `npm i X` / `yarn add X`
- Python `import X` and `from X import ...` (top-level module only)
- JS `require('X')` and `from 'X'`
- Lines of a `requirements.txt` (parse with `packaging.requirements.Requirement`)
- `dependencies` and `devDependencies` keys of a `package.json`

Then normalise:
- Lowercase; for PyPI, replace `_` and `.` with `-` (PEP 503 normalisation).
- Drop Python standard-library modules using `sys.stdlib_module_names`.
- Apply an **alias table** mapping import names to distribution names. Seed it with at least: `cv2→opencv-python`, `PIL→pillow`, `jwt→PyJWT`, `yaml→PyYAML`, `sklearn→scikit-learn`, `bs4→beautifulsoup4`, `dateutil→python-dateutil`, `dotenv→python-dotenv`, `serial→pyserial`, `Crypto→pycryptodome`, `psycopg2→psycopg2-binary`, `attr→attrs`, `OpenSSL→pyOpenSSL`.
- Deduplicate.
- Cap at 200 packages per scan.

### 7.2 Signals

For each package, gather signals. Every signal carries a code, a weight, and a human-readable sentence that is shown to the user.

| Code | Condition | Weight | Explanation shown |
|---|---|---|---|
| `NOT_FOUND` | Registry returns 404 | +100 | "This package does not exist on \<registry\>. It may have been invented by an AI model." |
| `MALICIOUS` | OSV record ID starts with `MAL-` | +100 | "This package has been reported as malicious." |
| `KEV_LISTED` | Any CVE appears in CISA KEV | +60 | "A vulnerability in this package is on CISA's known-exploited list." |
| `VULN_SEVERE` | OSV record with CVSS ≥ 7.0 | +30 | "Has a high-severity known vulnerability." |
| `VULN_MINOR` | OSV record with CVSS < 7.0 or unscored | +10 | "Has a known vulnerability of lower severity." |
| `EPSS_HIGH` | Max EPSS ≥ 0.10 | +25 | "Its vulnerability has an above-average predicted chance of exploitation." |
| `AGE_VERY_NEW` | First publish < 30 days ago | +40 | "Published very recently, which is a common pattern for malicious packages." |
| `AGE_NEW` | First publish < 180 days ago | +15 | "Published fairly recently." |
| `SINGLE_RELEASE` | Exactly 1 release | +15 | "Has only ever had one release." |
| `NO_REPO` | No source repository URL in metadata | +10 | "No public source repository is linked." |
| `LOW_DOWNLOADS` | < 1000 downloads last month | +20 | "Very few people download this package." |
| `TYPOSQUAT` | Levenshtein distance 1–2 from a top-1000 package, and not that package | +45 | "The name is one or two characters away from the popular package '\<X\>'." |
| `LLM_PATTERN` | Name matches a suspicious-pattern regex | +20 | "The name follows a pattern that AI models often invent." |
| `ALLOWLISTED` | Name on the user's private allow-list | −1000 | "You marked this as an internal package." |
| `UNKNOWN` | Registry unreachable | +0 | "Could not be checked — try again later." (sets verdict `UNKNOWN`) |

`LLM_PATTERN` regex seeds (document each in code):
```
^(.+)-(ai|gpt|llm|helper|utils|utilities|tools|toolkit|wrapper|sdk|client|api)$
^(easy|simple|quick|fast|super|smart|auto)-(.+)$
^(.+)-(py|js|python|node)$   # only when the base name is itself a popular package
```

### 7.3 Verdict

```
score = sum(weights)
score <= 24           -> SAFE
25 <= score <= 59     -> CAUTION
score >= 60           -> DANGER
registry unreachable  -> UNKNOWN
```

The UI must list every contributing signal with its weight. **No hidden scoring.** This explainability is the project's main selling point.

### 7.4 Top-packages list

Store a local table of the ~1000 most-downloaded PyPI and npm packages for typosquat comparison. Seed it from a committed JSON file in `data/top_packages.json` so the app works offline and tests are deterministic. Refresh it with a CLI command, not on every request.

---

## 8. Database schema (MySQL 8)

Use `utf8mb4` / `utf8mb4_unicode_ci` and InnoDB throughout. Full DDL is in `schema.sql`; SQLAlchemy models must match it.

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Accounts | `id`, `email` (unique), `password_hash`, `role` (`user`/`admin`), `is_active`, `created_at` |
| `scans` | One submission | `id`, `user_id` FK, `input_type`, `input_hash` (SHA-256 of raw input), `package_count`, `status`, `created_at` |
| `findings` | One package in a scan | `id`, `scan_id` FK, `ecosystem`, `name`, `version`, `exists_flag`, `first_published`, `release_count`, `monthly_downloads`, `repo_url`, `score`, `verdict` |
| `signals` | One reason for a score | `id`, `finding_id` FK, `code`, `weight`, `explanation` |
| `advisories` | A vulnerability on a finding | `id`, `finding_id` FK, `osv_id`, `cve_id`, `severity`, `cvss_score`, `epss_score`, `kev_listed`, `summary` |
| `kev_entries` | Local copy of CISA KEV | `cve_id` (PK), `vendor`, `product`, `date_added`, `due_date`, `ransomware_use` |
| `top_packages` | Typosquat reference | `id`, `ecosystem`, `name`, `rank` — unique on (`ecosystem`,`name`) |
| `allowlist_entries` | User's private packages | `id`, `user_id` FK, `ecosystem`, `name` — unique on (`user_id`,`ecosystem`,`name`) |
| `refresh_tokens` | JWT refresh revocation | `id`, `user_id` FK, `jti` (unique), `token_hash`, `expires_at`, `revoked_at` |
| `audit_log` | Security-relevant events | `id`, `user_id` (nullable), `event`, `ip_address`, `user_agent`, `detail`, `created_at` |
| `api_cache` | Upstream response cache | `cache_key` (PK), `payload` JSON, `fetched_at` |

Notes:
- Store **only a hash** of raw pasted input, never the text itself.
- Store refresh tokens hashed, never in plaintext.
- `ON DELETE CASCADE` from `scans` → `findings` → `signals`/`advisories`.
- Index `scans(user_id, created_at)` and `findings(scan_id)`.

---

## 9. Pages (Jinja2)

| Route | Page | Access |
|---|---|---|
| `GET /` | Landing page: what the tool does, call to action | public |
| `GET,POST /auth/register` | Registration | public |
| `GET,POST /auth/login` | Login | public |
| `POST /auth/logout` | Logout | user |
| `GET,POST /scan/new` | Scan form with three tabs (paste / upload / single) | user |
| `GET /scan/<id>` | Results: one trust card per package, each expandable to show signals | owner or admin |
| `GET /scan/history` | Paginated list of the user's scans | user |
| `GET /allowlist` | Manage private package allow-list | user |
| `GET /learn` | Explains slopsquatting, EPSS, KEV, with references | public |
| `GET /admin/users` | List, deactivate and promote users | admin |
| `GET /admin/scans` | All scans, for moderation | admin |

**Trust card** shows: package name, ecosystem, verdict badge (colour + text label — never colour alone, for accessibility), score, first-published date, release count, downloads, repo link, and the signal list with weights.

---

## 10. REST API

Base path `/api/v1`. JSON only. JWT bearer auth. CSRF is exempt here because there is no cookie auth on these routes.

| Method | Path | Body / params | Returns |
|---|---|---|---|
| `POST` | `/auth/token` | `{email, password}` | `{access_token, refresh_token}` — access 15 min, refresh 7 days |
| `POST` | `/auth/refresh` | refresh token in header | new access token |
| `POST` | `/auth/revoke` | refresh token | 204; marks `revoked_at` |
| `POST` | `/scans` | `{input_type, content, ecosystem?}` | 201 + scan object with findings |
| `GET` | `/scans` | `?page=&per_page=` | the caller's scans only |
| `GET` | `/scans/<id>` | — | 404 if not the caller's (not 403 — do not leak existence) |
| `GET` | `/packages/<ecosystem>/<name>` | — | single-package check |
| `GET` | `/health` | — | `{status, db, version}` |

Rules:
- Pin the JWT algorithm to HS256 and reject anything else.
- Validate `ecosystem` against `{"pypi","npm"}` — reject everything else.
- Rate limits: `/auth/token` 5/min per IP; `/scans` 10/min per user; global 100/hour per user.
- Errors return `{"error": {"code": "...", "message": "..."}}` with no stack traces.

---

## 11. Security requirements

These are graded deliverables, not optional polish.

### Authentication
- Argon2id password hashing with library defaults.
- Minimum 12-character passwords; check against a small common-password list.
- Regenerate the session ID on login (prevents session fixation).
- Session cookies: `Secure`, `HttpOnly`, `SameSite=Lax`.
- Session idle timeout of 60 minutes.
- Account lockout: 5 failed logins in 15 minutes → 15-minute lock, logged to `audit_log`.

### Authorization
- **Every** query for a scan, finding or allowlist entry filters by `user_id` in the SQL `WHERE` clause. Never fetch by ID and then compare in Python.
- Admin routes are protected by a decorator that checks `role == 'admin'`, applied to the blueprint.
- Write one test per protected endpoint proving user B receives 404 for user A's object.

### Input handling
- All forms use Flask-WTF with CSRF tokens.
- Validate package names against `^[A-Za-z0-9._-]{1,214}$` before any outbound request.
- `MAX_CONTENT_LENGTH = 256 * 1024`.
- Accept only `.txt` and `.json` uploads; verify content, do not trust the extension.
- Parse JSON with a depth and size limit; never `eval`.

### SSRF prevention
- Outbound requests go only to a hard-coded `ALLOWED_HOSTS` tuple.
- URLs are built from a template plus a validated package name — **never** from user-supplied URLs.
- A unit test must assert that a crafted package name cannot change the request host.

### Output handling
- Jinja2 autoescaping stays on. **Never** use `|safe` on any data from an external API.
- Package descriptions come from attacker-controlled registries; treat them as hostile. Truncate to 500 characters.
- Flask-Talisman CSP: `default-src 'self'`, no inline scripts, no CDN.

### Secrets and config
- All secrets come from environment variables. `.env` is in `.gitignore` from commit 1.
- `SECRET_KEY` and `JWT_SECRET_KEY` are distinct, ≥ 32 random bytes.
- `DEBUG=False` in anything but local development.
- The MySQL application user gets only `SELECT, INSERT, UPDATE, DELETE` — no `DROP`, no `FILE`, no `GRANT`.

### Logging
- Log authentication events, authorization failures, rate-limit hits and admin actions to `audit_log`.
- Never log passwords, tokens, or raw scan input.

---

## 12. Security testing plan (coursework deliverable)

Test **only your own local instance**. Never point these tools at PyPI, npm or any third party.

### Nmap
Run against your Docker host and record the output:
- `nmap -sV -p- 127.0.0.1` — confirm only the app port is open and MySQL 3306 is not exposed externally.
- `nmap --script http-methods,http-headers -p 5000 127.0.0.1` — check allowed methods and that security headers are present.

### Burp Suite (Community Edition)
- **Proxy + Repeater:** tamper with scan IDs, user IDs, the `role` field and JWT claims.
- **Intruder:** confirm login rate limiting and lockout work (Community throttles Intruder, which is fine for a demo).
- **JWT Editor extension:** attempt `alg: none`, a modified payload, an expired token, and a token signed with a guessed weak secret. All must be rejected.
- **Autorize extension:** replay user A's requests as user B to catch IDOR.
- Community Edition has no active scanner. Use **OWASP ZAP** for an automated baseline scan and keep Burp for manual testing.

### Deliberate-vulnerability exercise
Ship one early commit with a known flaw — for example, `Scan.query.get(id)` without an ownership filter. Find it with Burp, document it, fix it in a later commit, and retest. A demonstrated find-fix-verify cycle scores better than claiming the app was perfect from the start. Keep that branch private and clearly labelled; never deploy it.

### Findings table format
| ID | Finding | Severity | Evidence | Fix (commit) | Retest result |
|---|---|---|---|---|---|

---

## 13. Evaluation (what lifts this above a typical student project)

Build a labelled dataset of ~100 package names before finishing the scoring engine:
- ~50 real, well-known packages (expected: SAFE)
- ~25 real but risky or deprecated packages
- ~25 names that do not exist, invented by prompting an AI assistant yourself and recording what it suggested

Then report **precision, recall and F1** for the DANGER verdict, plus a confusion matrix, and discuss the errors honestly. Known weakness to state plainly: a private or internal company package is indistinguishable from a hallucinated one by metadata alone — that is what the allow-list exists for.

Record the prompts you used and the packages each one produced; that is original data and makes a strong appendix.

---

## 14. Ethical and legal constraints

Non-negotiable. Put these in the README too.

- **Never register** a hallucinated or typosquatted package name on any registry, not even as a placeholder.
- **Never download, install, unpack or execute** any package.
- **Never scan or attack** a system you do not own. All Nmap and Burp activity targets your own local instance.
- Respect upstream API terms: cache aggressively, back off on 429, send an identifying User-Agent.
- Do **not** publish your collected list of hallucinated names. Publishing it would hand attackers a pre-registration shortlist. Keep it in a private appendix for your submission only.
- The tool is advisory. The UI must say that a SAFE verdict is not a guarantee.

---

## 15. Repository layout

```
assay/
├─ app/
│  ├─ __init__.py          # create_app() factory
│  ├─ config.py            # Config classes, env loading, ALLOWED_HOSTS
│  ├─ extensions.py        # db, migrate, login_manager, jwt, limiter, csrf
│  ├─ models/              # one module per table group
│  ├─ blueprints/
│  │  ├─ main/             # landing, learn
│  │  ├─ auth/             # register, login, logout
│  │  ├─ scan/             # new scan, results, history
│  │  ├─ allowlist/
│  │  ├─ admin/
│  │  └─ api/              # /api/v1
│  ├─ services/
│  │  ├─ parser.py         # input → candidate package names
│  │  ├─ registries.py     # PyPI + npm clients
│  │  ├─ downloads.py      # pypistats + npm downloads
│  │  ├─ osv.py            # querybatch + vuln detail
│  │  ├─ epss.py
│  │  ├─ kev.py            # daily sync
│  │  ├─ typosquat.py
│  │  ├─ scoring.py        # signals → score → verdict
│  │  └─ scanner.py        # orchestrates the above
│  ├─ templates/
│  ├─ static/
│  └─ cli.py               # flask sync-kev, flask sync-top-packages, flask seed-demo
├─ tests/
│  ├─ conftest.py
│  ├─ unit/
│  ├─ integration/
│  └─ security/            # authz, IDOR, SSRF, CSRF tests
├─ data/
│  ├─ top_packages.json
│  ├─ aliases.json
│  └─ eval_dataset.csv
├─ migrations/
├─ docs/
│  ├─ threat-model.md
│  ├─ security-testing.md
│  └─ evaluation.md
├─ docker-compose.yml
├─ Dockerfile
├─ requirements.txt
├─ .env.example
├─ .gitignore
├─ schema.sql
├─ SPEC.md
└─ README.md
```

## 16. Definition of done

- [ ] `docker compose up` gives a working app with MySQL on a clean machine
- [ ] All three input types work end to end
- [ ] Every verdict shows its contributing signals
- [ ] Session auth and JWT auth both work and are both tested
- [ ] `pytest` passes, including the `tests/security/` suite
- [ ] `bandit` and `pip-audit` report no unresolved high findings
- [ ] Nmap and Burp/ZAP findings documented with fixes and retests
- [ ] Evaluation section has real numbers from the labelled dataset
- [ ] README explains setup, the ethical constraints, and the limitations
