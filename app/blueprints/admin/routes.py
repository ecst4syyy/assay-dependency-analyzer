"""Routes for the admin blueprint. Implemented in Slice 8."""

from flask import abort

from app.blueprints.admin import bp


@bp.get("/users")
def users():
    abort(404)
