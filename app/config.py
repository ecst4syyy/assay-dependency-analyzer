"""Configuration classes. All secrets come from environment variables."""

import os
from datetime import timedelta

APP_NAME = "Assay"
APP_VERSION = "1.0.0"

# Every outbound HTTP request must target one of these hosts (SPEC §6, §11).
# The guard in app/services/http.py rejects anything else.
ALLOWED_HOSTS = (
    "pypi.org",
    "registry.npmjs.org",
    "api.npmjs.org",
    "pypistats.org",
    "api.osv.dev",
    "api.first.org",
    "www.cisa.gov",
)


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BaseConfig:
    APP_NAME = APP_NAME
    APP_VERSION = APP_VERSION
    ALLOWED_HOSTS = ALLOWED_HOSTS

    SECRET_KEY = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # Uploads and request bodies (SPEC §11).
    MAX_CONTENT_LENGTH = 256 * 1024
    MAX_PACKAGES_PER_SCAN = 200

    # Session cookies (SPEC §11). The lifetime is an idle timeout because
    # SESSION_REFRESH_EACH_REQUEST pushes the expiry forward on every request.
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_REFRESH_EACH_REQUEST = True
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)
    REMEMBER_COOKIE_DURATION = timedelta(seconds=0)

    # Account lockout policy.
    LOCKOUT_THRESHOLD = 5
    LOCKOUT_WINDOW = timedelta(minutes=15)
    LOCKOUT_DURATION = timedelta(minutes=15)
    PASSWORD_MIN_LENGTH = 12

    # JWT (SPEC §10). Only HS256 is accepted on decode.
    JWT_ALGORITHM = "HS256"
    JWT_DECODE_ALGORITHMS = ["HS256"]
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)

    # Rate limiting. In-memory storage is correct because gunicorn runs a
    # single worker process (see docs/DECISIONS.md D-06).
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_ENABLED = True

    # Talisman. HTTPS redirection is off by default because the local demo and
    # the Nmap/ZAP exercises run over plain HTTP on 127.0.0.1.
    FORCE_HTTPS = _env_bool("FORCE_HTTPS", False)

    # Outbound HTTP.
    REPO_URL = os.environ.get("REPO_URL", "https://github.com/your-account/assay")
    HTTP_USER_AGENT = f"Assay/1.0 (student security project; +{REPO_URL})"
    HTTP_CONNECT_TIMEOUT = 5
    HTTP_READ_TIMEOUT = 10
    HTTP_CACHE_BACKEND = os.environ.get("HTTP_CACHE_BACKEND", "sqlite")
    HTTP_CACHE_NAME = os.environ.get("HTTP_CACHE_NAME", "instance/http_cache")
    HTTP_CACHE_TTL = timedelta(hours=24)

    KEV_FEED_URL = (
        "https://www.cisa.gov/sites/default/files/feeds/" "known_exploited_vulnerabilities.json"
    )


class DevConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///assay-dev.sqlite")


class TestConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-secret-key-not-for-production-0123456789"  # noqa: S105 test-only
    JWT_SECRET_KEY = "test-jwt-secret-key-not-for-production-0123456789"  # noqa: S105
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    # Individual security tests switch these back on.
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_SECURE = False
    HTTP_CACHE_BACKEND = "memory"
    SERVER_NAME = "localhost"


class ProdConfig(BaseConfig):
    DEBUG = False

    @classmethod
    def validate(cls):
        """Refuse to start with missing or weak secrets."""
        problems = []
        for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
            value = getattr(cls, key)
            if not value or len(value) < 32:
                problems.append(f"{key} must be set and at least 32 characters")
        if cls.SECRET_KEY and cls.SECRET_KEY == cls.JWT_SECRET_KEY:
            problems.append("SECRET_KEY and JWT_SECRET_KEY must differ")
        if not cls.SQLALCHEMY_DATABASE_URI:
            problems.append("DATABASE_URL must be set")
        if problems:
            raise RuntimeError("Invalid production config: " + "; ".join(problems))


CONFIGS = {"development": DevConfig, "testing": TestConfig, "production": ProdConfig}
