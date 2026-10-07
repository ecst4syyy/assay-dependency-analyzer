"""Registration and authentication, including account lockout.

Lockout rule (SPEC §11): 5 failed logins within 15 minutes locks the account
for 15 minutes. The users table has only a counter and a lock time, so the
15-minute window is measured from LOGIN_FAIL rows in audit_log, counting only
failures since the user's last successful login or last lockout.
"""

from dataclasses import dataclass

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.audit import record_event
from app.extensions import db
from app.models import AuditLog, User
from app.models.types import utcnow
from app.services.passwords import (
    burn_verify_time,
    hash_password,
    needs_rehash,
    verify_password,
)

RESET_EVENTS = ("LOGIN_OK", "ACCOUNT_LOCKED")


@dataclass
class AuthResult:
    user: User | None
    ok: bool


def normalise_email(email):
    return (email or "").strip().lower()


def register_user(email, password, display_name=None):
    """Create a user. Returns the user, or None if the email is taken."""
    user = User(
        email=normalise_email(email),
        display_name=(display_name or "").strip() or None,
        password_hash=hash_password(password),
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        record_event("REGISTER_DUPLICATE")
        return None
    record_event("REGISTER", user_id=user.id)
    return user


def authenticate(email, password):
    """Check credentials and apply the lockout policy.

    Every failure looks identical to the caller: unknown email, wrong
    password, locked account and deactivated account all return ok=False.
    """
    now = utcnow()
    user = db.session.execute(
        select(User).filter_by(email=normalise_email(email))
    ).scalar_one_or_none()

    if user is None:
        burn_verify_time(password)
        record_event("LOGIN_FAIL", detail="unknown account")
        return AuthResult(None, False)

    if user.is_locked(now):
        burn_verify_time(password)
        record_event("LOGIN_LOCKED", user_id=user.id)
        return AuthResult(user, False)

    if not verify_password(user.password_hash, password):
        _register_failure(user, now)
        return AuthResult(user, False)

    if not user.is_active:
        record_event("LOGIN_INACTIVE", user_id=user.id)
        return AuthResult(user, False)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.failed_logins = 0
    user.locked_until = None
    db.session.commit()
    record_event("LOGIN_OK", user_id=user.id)
    return AuthResult(user, True)


def _register_failure(user, now):
    cfg = current_app.config
    record_event("LOGIN_FAIL", user_id=user.id, detail="bad password")

    window_start = now - cfg["LOCKOUT_WINDOW"]
    last_reset = db.session.execute(
        select(func.max(AuditLog.created_at)).where(
            AuditLog.user_id == user.id, AuditLog.event.in_(RESET_EVENTS)
        )
    ).scalar_one_or_none()
    since = max(window_start, last_reset) if last_reset else window_start

    recent_failures = db.session.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.user_id == user.id,
            AuditLog.event == "LOGIN_FAIL",
            AuditLog.created_at > since,
        )
    ).scalar_one()

    user.failed_logins = min(recent_failures, 65535)
    if recent_failures >= cfg["LOCKOUT_THRESHOLD"]:
        user.locked_until = now + cfg["LOCKOUT_DURATION"]
        user.failed_logins = 0
        db.session.commit()
        record_event("ACCOUNT_LOCKED", user_id=user.id, detail=f"{recent_failures} failures")
        return
    db.session.commit()
