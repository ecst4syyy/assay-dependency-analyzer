import pytest

from app.config import ALLOWED_HOSTS, ProdConfig


def test_allowed_hosts_is_an_immutable_tuple():
    assert isinstance(ALLOWED_HOSTS, tuple)
    assert "pypi.org" in ALLOWED_HOSTS


@pytest.mark.parametrize(
    "secret,jwt_secret",
    [(None, "x" * 40), ("x" * 40, None), ("short", "y" * 40), ("z" * 40, "z" * 40)],
)
def test_prod_config_rejects_weak_or_shared_secrets(monkeypatch, secret, jwt_secret):
    monkeypatch.setattr(ProdConfig, "SECRET_KEY", secret)
    monkeypatch.setattr(ProdConfig, "JWT_SECRET_KEY", jwt_secret)
    monkeypatch.setattr(ProdConfig, "SQLALCHEMY_DATABASE_URI", "sqlite://")
    with pytest.raises(RuntimeError):
        ProdConfig.validate()


def test_prod_config_accepts_strong_distinct_secrets(monkeypatch):
    monkeypatch.setattr(ProdConfig, "SECRET_KEY", "a" * 48)
    monkeypatch.setattr(ProdConfig, "JWT_SECRET_KEY", "b" * 48)
    monkeypatch.setattr(ProdConfig, "SQLALCHEMY_DATABASE_URI", "sqlite://")
    ProdConfig.validate()
