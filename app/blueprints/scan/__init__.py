from flask import Blueprint

bp = Blueprint("scan", __name__)

from app.blueprints.scan import routes  # noqa: E402,F401
