from unittest.mock import patch

from sqlalchemy.exc import OperationalError


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "db": "ok", "version": "1.0.0"}


def test_health_reports_db_failure(client, db):
    with patch.object(db.session, "execute", side_effect=OperationalError("x", {}, None)):
        resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.get_json()["db"] == "unavailable"


def test_landing_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"slopsquatting" in resp.data


def test_unknown_page_returns_html_404(client):
    resp = client.get("/no-such-page")
    assert resp.status_code == 404
    assert b"Error 404" in resp.data


def test_unknown_api_route_returns_json_404(client):
    resp = client.get("/api/v1/no-such-route")
    assert resp.status_code == 404
    assert resp.get_json() == {
        "error": {"code": "not_found", "message": "The page or object you asked for was not found."}
    }
