"""Import every model so Flask-Migrate sees the full metadata."""

from app.models.reference import AllowlistEntry, ApiCache, KevEntry, TopPackage
from app.models.scan import Advisory, Finding, Scan, Signal
from app.models.user import AuditLog, RefreshToken, User

__all__ = [
    "Advisory",
    "AllowlistEntry",
    "ApiCache",
    "AuditLog",
    "Finding",
    "KevEntry",
    "RefreshToken",
    "Scan",
    "Signal",
    "TopPackage",
    "User",
]
