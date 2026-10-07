"""Routes for the scan blueprint. Implemented in Slice 7."""

from flask import abort

from app.blueprints.scan import bp


@bp.route("/new", methods=["GET", "POST"])
def new():
    abort(404)


@bp.get("/history")
def history():
    abort(404)
