from flask import Blueprint

bp = Blueprint("allowlist", __name__)

from app.blueprints.allowlist import routes  # noqa: E402,F401
