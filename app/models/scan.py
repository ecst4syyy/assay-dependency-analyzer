"""Scans and everything hanging off them."""

from app.extensions import db
from app.models.types import (
    ECOSYSTEMS,
    TABLE_ARGS,
    VERDICTS,
    BigIntPK,
    UBigInt,
    UInt,
    USmallInt,
    created_at_column,
    updated_at_column,
)


class Scan(db.Model):
    __tablename__ = "scans"
    __table_args__ = (db.Index("ix_scans_user_created", "user_id", "created_at"), TABLE_ARGS)

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    user_id = db.Column(
        BigIntPK,
        db.ForeignKey("users.id", ondelete="CASCADE", name="fk_scans_user"),
        nullable=False,
    )
    input_type = db.Column(
        db.Enum("paste", "upload", "single", name="scan_input_type"), nullable=False
    )
    # SHA-256 of the raw input. The raw text itself is never stored (SPEC §8).
    input_hash = db.Column(db.CHAR(64), nullable=False)
    source_label = db.Column(db.String(255), nullable=True)
    package_count = db.Column(USmallInt, nullable=False, default=0, server_default="0")
    status = db.Column(
        db.Enum("pending", "complete", "failed", name="scan_status"),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    worst_verdict = db.Column(db.Enum(*VERDICTS, name="scan_worst_verdict"), nullable=True)
    created_at = created_at_column()
    updated_at = updated_at_column()
    completed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", lazy="joined")
    findings = db.relationship(
        "Finding",
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Finding.id",
    )


class Finding(db.Model):
    __tablename__ = "findings"
    __table_args__ = (
        db.Index("ix_findings_scan", "scan_id"),
        db.Index("ix_findings_name", "ecosystem", "name"),
        TABLE_ARGS,
    )

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    scan_id = db.Column(
        BigIntPK,
        db.ForeignKey("scans.id", ondelete="CASCADE", name="fk_findings_scan"),
        nullable=False,
    )
    ecosystem = db.Column(db.Enum(*ECOSYSTEMS, name="finding_ecosystem"), nullable=False)
    name = db.Column(db.String(214), nullable=False)
    requested_version = db.Column(db.String(64), nullable=True)
    exists_flag = db.Column(db.Boolean, nullable=True)  # NULL = could not determine
    first_published = db.Column(db.DateTime, nullable=True)
    latest_published = db.Column(db.DateTime, nullable=True)
    release_count = db.Column(UInt, nullable=True)
    monthly_downloads = db.Column(UBigInt, nullable=True)
    repo_url = db.Column(db.String(512), nullable=True)
    summary = db.Column(db.String(500), nullable=True)
    score = db.Column(db.SmallInteger, nullable=False, default=0, server_default="0")
    verdict = db.Column(
        db.Enum(*VERDICTS, name="finding_verdict"),
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    created_at = created_at_column()

    scan = db.relationship("Scan", back_populates="findings")
    signals = db.relationship(
        "Signal", cascade="all, delete-orphan", passive_deletes=True, order_by="Signal.id"
    )
    advisories = db.relationship(
        "Advisory", cascade="all, delete-orphan", passive_deletes=True, order_by="Advisory.id"
    )


class Signal(db.Model):
    __tablename__ = "signals"
    __table_args__ = (db.Index("ix_signals_finding", "finding_id"), TABLE_ARGS)

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    finding_id = db.Column(
        BigIntPK,
        db.ForeignKey("findings.id", ondelete="CASCADE", name="fk_signals_finding"),
        nullable=False,
    )
    code = db.Column(db.String(32), nullable=False)
    weight = db.Column(db.SmallInteger, nullable=False)
    explanation = db.Column(db.String(500), nullable=False)
    created_at = created_at_column()


class Advisory(db.Model):
    __tablename__ = "advisories"
    __table_args__ = (
        db.Index("ix_advisories_finding", "finding_id"),
        db.Index("ix_advisories_cve", "cve_id"),
        TABLE_ARGS,
    )

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    finding_id = db.Column(
        BigIntPK,
        db.ForeignKey("findings.id", ondelete="CASCADE", name="fk_advisories_finding"),
        nullable=False,
    )
    osv_id = db.Column(db.String(64), nullable=False)
    cve_id = db.Column(db.String(32), nullable=True)
    is_malicious = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    severity = db.Column(db.String(16), nullable=True)
    cvss_score = db.Column(db.Numeric(3, 1), nullable=True)
    epss_score = db.Column(db.Numeric(9, 8), nullable=True)
    epss_percentile = db.Column(db.Numeric(9, 8), nullable=True)
    kev_listed = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    summary = db.Column(db.String(500), nullable=True)
    created_at = created_at_column()
