import re

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import User
from app.services.passwords import hash_password

PASSWORD = "correct horse battery"


def _build(overrides=None):
    app = create_app("testing", overrides)
    ctx = app.app_context()
    ctx.push()
    _db.create_all()
    return app, ctx


def _teardown(ctx):
    _db.session.remove()
    _db.drop_all()
    ctx.pop()


@pytest.fixture
def app():
    app, ctx = _build()
    yield app
    _teardown(ctx)


@pytest.fixture
def make_app():
    """Build an app with config overrides, e.g. CSRF or rate limiting switched on."""
    contexts = []

    def factory(**overrides):
        app, ctx = _build(overrides)
        contexts.append(ctx)
        return app

    yield factory
    for ctx in reversed(contexts):
        _teardown(ctx)


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def make_user():
    def factory(email="alice@example.com", password=PASSWORD, role="user", is_active=True):
        user = User(
            email=email, password_hash=hash_password(password), role=role, is_active=is_active
        )
        _db.session.add(user)
        _db.session.commit()
        return user

    return factory


def login(client, email="alice@example.com", password=PASSWORD):
    return client.post("/auth/login", data={"email": email, "password": password})


def csrf_token_from(html):
    match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', html) or re.search(
        r'name="csrf_token" value="([^"]+)"', html
    )
    assert match, "no CSRF token in page"
    return match.group(1)
