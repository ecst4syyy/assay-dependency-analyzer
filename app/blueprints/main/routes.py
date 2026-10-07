"""Landing page, learn page and health check."""

import logging

from flask import current_app, jsonify, render_template
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.blueprints.main import bp
from app.extensions import db

log = logging.getLogger(__name__)


@bp.get("/")
def index():
    return render_template("main/index.html")


@bp.get("/health")
def health():
    db_status = "ok"
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.exception("Health check: database unreachable")
        db_status = "unavailable"
    status_code = 200 if db_status == "ok" else 503
    body = {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "version": current_app.config["APP_VERSION"],
    }
    return jsonify(body), status_code


@bp.get("/learn")
def learn():
    return render_template("main/learn.html")
