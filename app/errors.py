"""Error handlers: HTML for page routes, JSON for /api/v1. No stack traces leak."""

import logging

from flask import jsonify, render_template, request
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)

MESSAGES = {
    400: "The request could not be understood.",
    401: "Authentication is required.",
    403: "You do not have permission to do that.",
    404: "The page or object you asked for was not found.",
    405: "That method is not allowed here.",
    413: "The upload is too large. The limit is 256 KB.",
    429: "Too many requests. Please slow down and try again shortly.",
    500: "Something went wrong on our side.",
}

CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    429: "rate_limited",
    500: "internal_error",
}


def wants_json():
    return request.path.startswith("/api/")


def error_response(status, message=None):
    message = message or MESSAGES.get(status, "Error.")
    if wants_json():
        body = {"error": {"code": CODES.get(status, "error"), "message": message}}
        return jsonify(body), status
    return render_template("errors/error.html", status=status, message=message), status


def register_error_handlers(app):
    def handle_http(exc):
        status = exc.code or 500
        if status == 429:
            from app.audit import record_event

            record_event("RATE_LIMIT", detail=f"{request.method} {request.path}"[:500])
        return error_response(status)

    def handle_unexpected(exc):
        log.exception("Unhandled error on %s %s", request.method, request.path)
        return error_response(500)

    app.register_error_handler(HTTPException, handle_http)
    app.register_error_handler(Exception, handle_unexpected)
