"""Write security-relevant events to audit_log. Never log passwords, tokens or
raw scan input."""

import logging

from flask import has_request_context, request
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

log = logging.getLogger(__name__)


def record_event(event, user_id=None, detail=None):
    from app.models import AuditLog

    ip_address = user_agent = None
    if has_request_context():
        ip_address = (request.remote_addr or "")[:45] or None
        user_agent = (request.user_agent.string or "")[:255] or None
    entry = AuditLog(
        user_id=user_id,
        event=event[:64],
        ip_address=ip_address,
        user_agent=user_agent,
        detail=detail[:500] if detail else None,
    )
    try:
        db.session.add(entry)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        log.exception("Could not write audit event %s", event)
