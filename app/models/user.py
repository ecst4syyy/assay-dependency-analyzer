"""Accounts, refresh tokens and the audit log."""

from flask_login import UserMixin

from app.extensions import db
from app.models.types import (
    TABLE_ARGS,
    BigIntPK,
    USmallInt,
    created_at_column,
    updated_at_column,
    utcnow,
)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (db.UniqueConstraint("email", name="uq_users_email"), TABLE_ARGS)

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum("user", "admin", name="user_role"),
        nullable=False,
        default="user",
        server_default="user",
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    failed_logins = db.Column(USmallInt, nullable=False, default=0, server_default="0")
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = created_at_column()
    updated_at = updated_at_column()

    @property
    def is_admin(self):
        return self.role == "admin"

    def is_locked(self, now=None):
        now = now or utcnow()
        return self.locked_until is not None and self.locked_until > now

    def __repr__(self):
        return f"<User {self.id}>"


class RefreshToken(db.Model):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        db.UniqueConstraint("jti", name="uq_refresh_jti"),
        db.Index("ix_refresh_user", "user_id"),
        TABLE_ARGS,
    )

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    user_id = db.Column(
        BigIntPK,
        db.ForeignKey("users.id", ondelete="CASCADE", name="fk_refresh_user"),
        nullable=False,
    )
    jti = db.Column(db.CHAR(36), nullable=False)
    token_hash = db.Column(db.CHAR(64), nullable=False)
    issued_at = db.Column(db.DateTime, nullable=False, default=utcnow, server_default=db.func.now())
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    __table_args__ = (
        db.Index("ix_audit_user_created", "user_id", "created_at"),
        db.Index("ix_audit_event", "event"),
        TABLE_ARGS,
    )

    id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    user_id = db.Column(
        BigIntPK,
        db.ForeignKey("users.id", ondelete="SET NULL", name="fk_audit_user"),
        nullable=True,
    )
    event = db.Column(db.String(64), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    detail = db.Column(db.String(500), nullable=True)
    created_at = created_at_column()
