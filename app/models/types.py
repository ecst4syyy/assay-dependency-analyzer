"""Column types that render as the exact MySQL types in schema.sql while still
working on SQLite for the offline test suite (SQLite only auto-increments a
plain INTEGER primary key)."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Integer, SmallInteger, func
from sqlalchemy.dialects import mysql

from app.extensions import db

BigIntPK = (
    BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql").with_variant(Integer, "sqlite")
)
UBigInt = BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql")
UInt = Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql")
USmallInt = SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql")

ECOSYSTEMS = ("pypi", "npm")
VERDICTS = ("safe", "caution", "danger", "unknown")

TABLE_ARGS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


def utcnow():
    """Naive UTC timestamp, matching MySQL DATETIME semantics."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def created_at_column():
    return db.Column(db.DateTime, nullable=False, default=utcnow, server_default=func.now())


def updated_at_column():
    return db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )
