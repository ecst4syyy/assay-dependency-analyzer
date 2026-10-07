"""Routes for the allowlist blueprint. Implemented in Slice 8."""

from flask import abort

from app.blueprints.allowlist import bp


@bp.get("/")
def index():
    abort(404)
