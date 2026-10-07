-- Assay — MySQL 8.0 schema
-- Reference DDL. SQLAlchemy models must match this; migrations are generated
-- with Flask-Migrate. This file exists so the schema can be reviewed and
-- included in the coursework report.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 1;

CREATE DATABASE IF NOT EXISTS assay
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE assay;

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email           VARCHAR(255)    NOT NULL,
    display_name    VARCHAR(100)        NULL,
    password_hash   VARCHAR(255)    NOT NULL,   -- argon2id
    role            ENUM('user','admin') NOT NULL DEFAULT 'user',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    failed_logins   SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    locked_until    DATETIME            NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- scans  (one user submission)
-- ---------------------------------------------------------------------------
CREATE TABLE scans (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id         BIGINT UNSIGNED NOT NULL,
    input_type      ENUM('paste','upload','single') NOT NULL,
    input_hash      CHAR(64)        NOT NULL,   -- SHA-256 of raw input; raw text is never stored
    source_label    VARCHAR(255)        NULL,   -- e.g. original filename
    package_count   SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    status          ENUM('pending','complete','failed') NOT NULL DEFAULT 'pending',
    worst_verdict   ENUM('safe','caution','danger','unknown') NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
    completed_at    DATETIME            NULL,
    PRIMARY KEY (id),
    KEY ix_scans_user_created (user_id, created_at),
    CONSTRAINT fk_scans_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- findings  (one package within a scan)
-- ---------------------------------------------------------------------------
CREATE TABLE findings (
    id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    scan_id            BIGINT UNSIGNED NOT NULL,
    ecosystem          ENUM('pypi','npm') NOT NULL,
    name               VARCHAR(214)    NOT NULL,   -- npm max name length
    requested_version  VARCHAR(64)         NULL,
    exists_flag        TINYINT(1)          NULL,   -- NULL = could not determine
    first_published    DATETIME            NULL,
    latest_published   DATETIME            NULL,
    release_count      INT UNSIGNED        NULL,
    monthly_downloads  BIGINT UNSIGNED     NULL,
    repo_url           VARCHAR(512)        NULL,
    summary            VARCHAR(500)        NULL,   -- truncated registry description
    score              SMALLINT        NOT NULL DEFAULT 0,
    verdict            ENUM('safe','caution','danger','unknown') NOT NULL DEFAULT 'unknown',
    created_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_findings_scan (scan_id),
    KEY ix_findings_name (ecosystem, name),
    CONSTRAINT fk_findings_scan FOREIGN KEY (scan_id)
        REFERENCES scans (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- signals  (why a finding scored what it scored)
-- ---------------------------------------------------------------------------
CREATE TABLE signals (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    finding_id   BIGINT UNSIGNED NOT NULL,
    code         VARCHAR(32)     NOT NULL,   -- NOT_FOUND, TYPOSQUAT, KEV_LISTED, ...
    weight       SMALLINT        NOT NULL,
    explanation  VARCHAR(500)    NOT NULL,   -- shown verbatim in the UI
    created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_signals_finding (finding_id),
    CONSTRAINT fk_signals_finding FOREIGN KEY (finding_id)
        REFERENCES findings (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- advisories  (vulnerabilities attached to a finding)
-- ---------------------------------------------------------------------------
CREATE TABLE advisories (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    finding_id    BIGINT UNSIGNED NOT NULL,
    osv_id        VARCHAR(64)     NOT NULL,   -- GHSA-..., PYSEC-..., MAL-...
    cve_id        VARCHAR(32)         NULL,
    is_malicious  TINYINT(1)      NOT NULL DEFAULT 0,  -- true when osv_id starts with MAL-
    severity      VARCHAR(16)         NULL,   -- LOW / MODERATE / HIGH / CRITICAL
    cvss_score    DECIMAL(3,1)        NULL,
    epss_score    DECIMAL(9,8)        NULL,   -- 0.00000000 - 1.00000000
    epss_percentile DECIMAL(9,8)      NULL,
    kev_listed    TINYINT(1)      NOT NULL DEFAULT 0,
    summary       VARCHAR(500)        NULL,
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_advisories_finding (finding_id),
    KEY ix_advisories_cve (cve_id),
    CONSTRAINT fk_advisories_finding FOREIGN KEY (finding_id)
        REFERENCES findings (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- kev_entries  (local daily copy of the CISA Known Exploited Vulnerabilities feed)
-- ---------------------------------------------------------------------------
CREATE TABLE kev_entries (
    cve_id          VARCHAR(32)  NOT NULL,
    vendor_project  VARCHAR(255)     NULL,
    product         VARCHAR(255)     NULL,
    vulnerability_name VARCHAR(500)  NULL,
    date_added      DATE             NULL,
    due_date        DATE             NULL,
    ransomware_use  TINYINT(1)   NOT NULL DEFAULT 0,
    synced_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (cve_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- top_packages  (reference list for typosquat distance checks)
-- ---------------------------------------------------------------------------
CREATE TABLE top_packages (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ecosystem  ENUM('pypi','npm') NOT NULL,
    name       VARCHAR(214)    NOT NULL,
    rank_pos   INT UNSIGNED        NULL,
    synced_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_top_packages (ecosystem, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- allowlist_entries  (a user's own internal/private packages)
-- ---------------------------------------------------------------------------
CREATE TABLE allowlist_entries (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id    BIGINT UNSIGNED NOT NULL,
    ecosystem  ENUM('pypi','npm') NOT NULL,
    name       VARCHAR(214)    NOT NULL,
    note       VARCHAR(255)        NULL,
    created_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_allowlist (user_id, ecosystem, name),
    CONSTRAINT fk_allowlist_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- refresh_tokens  (so JWT refresh tokens can be revoked)
-- ---------------------------------------------------------------------------
CREATE TABLE refresh_tokens (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     BIGINT UNSIGNED NOT NULL,
    jti         CHAR(36)        NOT NULL,
    token_hash  CHAR(64)        NOT NULL,   -- SHA-256; plaintext is never stored
    issued_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at  DATETIME        NOT NULL,
    revoked_at  DATETIME            NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_refresh_jti (jti),
    KEY ix_refresh_user (user_id),
    CONSTRAINT fk_refresh_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- audit_log  (security-relevant events; evidence for the report)
-- ---------------------------------------------------------------------------
CREATE TABLE audit_log (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     BIGINT UNSIGNED     NULL,   -- NULL for pre-auth events
    event       VARCHAR(64)     NOT NULL,   -- LOGIN_OK, LOGIN_FAIL, AUTHZ_DENY, RATE_LIMIT, ADMIN_ACTION
    ip_address  VARCHAR(45)         NULL,   -- IPv6-capable
    user_agent  VARCHAR(255)        NULL,
    detail      VARCHAR(500)        NULL,   -- never passwords, tokens or raw scan input
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY ix_audit_user_created (user_id, created_at),
    KEY ix_audit_event (event),
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- api_cache  (cached upstream responses, so demos work and APIs are respected)
-- ---------------------------------------------------------------------------
CREATE TABLE api_cache (
    cache_key   VARCHAR(255) NOT NULL,      -- e.g. 'pypi:requests'
    payload     JSON         NOT NULL,
    fetched_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (cache_key),
    KEY ix_cache_fetched (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- Least-privilege application user.
-- Run as root once; the app NEVER connects as root.
-- Replace the password with a value from the environment.
-- ---------------------------------------------------------------------------
-- CREATE USER 'assay_app'@'%' IDENTIFIED BY '<from-env>';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON assay.* TO 'assay_app'@'%';
-- -- Migrations need more; grant temporarily to a separate migration user instead:
-- -- GRANT CREATE, ALTER, DROP, INDEX, REFERENCES ON assay.* TO 'assay_migrate'@'%';
-- FLUSH PRIVILEGES;
