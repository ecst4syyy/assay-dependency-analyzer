"""Reference data synced by CLI commands, plus the allow-list and API cache."""

from app.extensions import db
from app.models.types import ECOSYSTEMS, TABLE_ARGS, BigIntPK, UInt, created_at_column, utcnow


class KevEntry(db.Model):
    __tablename__ = "kev_entries"
    __table_args__ = (TABLE_ARGS,)

    cve_id = db.Column(db.String(32), primary_key=True)
    vendor_project = db.Column(db.String(255), nullable=True)
    product = db.Column(db.String(255), nullable=True)
    vulnerability_name = db.Column(db.String(500), nullable=True)
    date_added = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    ransomware_use = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    synced_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow, server_default=db.func.now()
    )


class TopPackage(db.Model):
    __tablename__ = "top_packages"
    __table_args__ = (
        db.UniqueConstraint("ecosystem", "name", name="uq_top_packages"),
        TABLE_ARGS,
    )

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    ecosystem = db.Column(db.Enum(*ECOSYSTEMS, name="top_ecosystem"), nullable=False)
    name = db.Column(db.String(214), nullable=False)
    rank_pos = db.Column(UInt, nullable=True)
    synced_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, onupdate=utcnow, server_default=db.func.now()
    )


class AllowlistEntry(db.Model):
    __tablename__ = "allowlist_entries"
    __table_args__ = (
        db.UniqueConstraint("user_id", "ecosystem", "name", name="uq_allowlist"),
        TABLE_ARGS,
    )

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    user_id = db.Column(
        BigIntPK,
        db.ForeignKey("users.id", ondelete="CASCADE", name="fk_allowlist_user"),
        nullable=False,
    )
    ecosystem = db.Column(db.Enum(*ECOSYSTEMS, name="allowlist_ecosystem"), nullable=False)
    name = db.Column(db.String(214), nullable=False)
    note = db.Column(db.String(255), nullable=True)
    created_at = created_at_column()


class ApiCache(db.Model):
    """Kept to match schema.sql. Response caching is done by requests-cache
    (see docs/DECISIONS.md D-05), so this table is currently unused."""

    __tablename__ = "api_cache"
    __table_args__ = (db.Index("ix_cache_fetched", "fetched_at"), TABLE_ARGS)

    cache_key = db.Column(db.String(255), primary_key=True)
    payload = db.Column(db.JSON, nullable=False)
    fetched_at = db.Column(
        db.DateTime, nullable=False, default=utcnow, server_default=db.func.now()
    )
