from datetime import timedelta

import pytest

from app.models import AuditLog, User
from app.models.types import utcnow
from tests.conftest import PASSWORD, csrf_token_from, login


def events(db, user_id=None):
    query = db.session.query(AuditLog.event).order_by(AuditLog.id)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    return [row.event for row in query]


# --- password storage and policy -------------------------------------------


def test_password_is_stored_as_argon2id(client, db):
    client.post(
        "/auth/register",
        data={"email": "new@example.com", "password": PASSWORD, "confirm": PASSWORD},
    )
    user = db.session.query(User).filter_by(email="new@example.com").one()
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


@pytest.mark.parametrize(
    "password,reason",
    [
        ("short-pass1", b"at least 12 characters"),
        ("password1234", b"too common"),
        ("PASSWORD1234", b"too common"),
        ("x" * 129, b"at most 128"),
    ],
)
def test_weak_passwords_are_rejected(client, db, password, reason):
    resp = client.post(
        "/auth/register",
        data={"email": "weak@example.com", "password": password, "confirm": password},
    )
    assert reason in resp.data
    assert db.session.query(User).filter_by(email="weak@example.com").count() == 0


def test_duplicate_registration_does_not_reveal_existing_account(client, make_user):
    make_user(email="taken@example.com")
    resp = client.post(
        "/auth/register",
        data={"email": "taken@example.com", "password": PASSWORD, "confirm": PASSWORD},
        follow_redirects=True,
    )
    assert b"If that email address was not already registered" in resp.data


# --- login, logout, audit ---------------------------------------------------


def test_login_success_is_audited(client, db, make_user):
    user = make_user()
    resp = login(client)
    assert resp.status_code == 302
    assert "LOGIN_OK" in events(db, user.id)


def test_unknown_email_and_wrong_password_give_identical_responses(client, make_user):
    make_user()
    a = login(client, email="nobody@example.com")
    b = login(client, password="wrong password here")
    assert a.status_code == b.status_code == 200
    assert b"Invalid email or password" in a.data
    # The pages differ only by the email address echoed back into the form.
    assert a.data.replace(b"nobody@example.com", b"alice@example.com") == b.data


def test_inactive_user_cannot_log_in(client, make_user):
    make_user(is_active=False)
    resp = login(client)
    assert b"Invalid email or password" in resp.data


def test_logout_requires_post(client, make_user):
    make_user()
    login(client)
    assert client.get("/auth/logout").status_code == 405
    assert client.post("/auth/logout").status_code == 302
    # Now logged out, so a second logout bounces to the login page.
    resp = client.post("/auth/logout")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_open_redirect_via_next_is_blocked(client, make_user):
    make_user()
    for target in ("https://evil.example", "//evil.example", "/\\evil.example"):
        resp = client.post(
            f"/auth/login?next={target}", data={"email": "alice@example.com", "password": PASSWORD}
        )
        assert resp.headers["Location"] == "/scan/new"
        client.post("/auth/logout")


# --- lockout ----------------------------------------------------------------


def test_five_failures_lock_the_account_even_for_the_right_password(client, db, make_user):
    user = make_user()
    for _ in range(5):
        login(client, password="wrong password here")
    db.session.refresh(user)
    assert user.locked_until is not None
    assert "ACCOUNT_LOCKED" in events(db, user.id)

    resp = login(client)  # correct password, but locked
    assert b"Invalid email or password" in resp.data
    assert "LOGIN_LOCKED" in events(db, user.id)


def test_four_failures_then_success_resets_the_counter(client, db, make_user):
    user = make_user()
    for _ in range(4):
        login(client, password="wrong password here")
    assert login(client).status_code == 302
    client.post("/auth/logout")
    for _ in range(4):
        login(client, password="wrong password here")
    db.session.refresh(user)
    assert user.locked_until is None


def test_lock_expires_after_fifteen_minutes(client, db, make_user, monkeypatch):
    user = make_user()
    for _ in range(5):
        login(client, password="wrong password here")
    later = utcnow() + timedelta(minutes=16)
    monkeypatch.setattr("app.services.accounts.utcnow", lambda: later)
    assert login(client).status_code == 302
    db.session.refresh(user)
    assert user.locked_until is None


def test_failures_older_than_the_window_do_not_count(client, db, make_user):
    user = make_user()
    old = utcnow() - timedelta(minutes=20)
    for _ in range(4):
        db.session.add(AuditLog(user_id=user.id, event="LOGIN_FAIL", created_at=old))
    db.session.commit()
    login(client, password="wrong password here")
    db.session.refresh(user)
    assert user.locked_until is None


# --- session handling --------------------------------------------------------


def test_session_is_regenerated_on_login(client, make_user):
    make_user()
    with client.session_transaction() as sess:
        sess["planted"] = "attacker-value"
    login(client)
    with client.session_transaction() as sess:
        assert "planted" not in sess
        assert sess.permanent is True
        assert sess["_user_id"]


def test_session_cookie_flags(make_app, make_user):
    app = make_app(SESSION_COOKIE_SECURE=True)
    make_user()
    resp = login(app.test_client())
    cookie = resp.headers["Set-Cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_session_idle_timeout_is_sixty_minutes(app):
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(minutes=60)
    assert app.config["SESSION_REFRESH_EACH_REQUEST"] is True


# --- CSRF, rate limiting, headers --------------------------------------------


def test_form_post_without_csrf_token_is_rejected(make_app, make_user):
    app = make_app(WTF_CSRF_ENABLED=True)
    make_user()
    client = app.test_client()
    resp = client.post("/auth/login", data={"email": "alice@example.com", "password": PASSWORD})
    assert resp.status_code == 400


def test_form_post_with_csrf_token_is_accepted(make_app, make_user):
    app = make_app(WTF_CSRF_ENABLED=True)
    make_user()
    client = app.test_client()
    token = csrf_token_from(client.get("/auth/login").get_data(as_text=True))
    resp = client.post(
        "/auth/login",
        data={"email": "alice@example.com", "password": PASSWORD, "csrf_token": token},
    )
    assert resp.status_code == 302


def test_login_is_rate_limited_to_five_per_minute(make_app, make_user):
    app = make_app(RATELIMIT_ENABLED=True)
    make_user()
    client = app.test_client()
    statuses = [login(client, password="wrong password here").status_code for _ in range(6)]
    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429
    from app.extensions import db

    db_events = [row.event for row in db.session.query(AuditLog.event)]
    assert "RATE_LIMIT" in db_events


def test_security_headers_present(client):
    resp = client.get("/")
    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
