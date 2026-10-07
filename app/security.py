"""Login manager, security headers (Talisman) and shared auth decorators."""

from functools import wraps

from flask import abort, request
from flask_login import current_user

from app.extensions import db, login_manager, talisman

# Strict CSP (SPEC §11): same-origin only, no inline scripts, no CDN.
CSP = {
    "default-src": "'self'",
    "script-src": "'self'",
    "style-src": "'self'",
    "img-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'none'",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
}


def init_security(app):
    from app.models import User

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "error"
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user = db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None
        if user is None or not user.is_active:
            return None
        return user

    talisman.init_app(
        app,
        force_https=app.config["FORCE_HTTPS"],
        strict_transport_security=app.config["FORCE_HTTPS"],
        session_cookie_secure=app.config["SESSION_COOKIE_SECURE"],
        session_cookie_http_only=True,
        content_security_policy=CSP,
        frame_options="DENY",
        referrer_policy="strict-origin-when-cross-origin",
        permissions_policy={"geolocation": "()", "camera": "()", "microphone": "()"},
    )

    @app.after_request
    def no_store_for_authenticated_pages(response):
        # Results pages reveal a user's dependencies; keep them out of shared caches.
        if current_user.is_authenticated and not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response


def admin_required(view):
    """Route decorator: 403 for authenticated non-admins."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            from app.audit import record_event

            record_event("AUTHZ_DENY", user_id=current_user.id, detail=request.path[:500])
            abort(403)
        return view(*args, **kwargs)

    return wrapped
