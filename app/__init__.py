"""Application factory."""

import logging
import os

from flask import Flask

from app.config import CONFIGS, ProdConfig
from app.extensions import csrf, db, jwt, limiter, login_manager, migrate


def create_app(config_name=None, overrides=None):
    config_name = config_name or os.environ.get("APP_ENV", "production")
    config_class = CONFIGS[config_name]
    if config_class is ProdConfig:
        config_class.validate()

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    if overrides:
        app.config.update(overrides)
    os.makedirs(app.instance_path, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    _init_extensions(app)
    _register_blueprints(app)

    from app.errors import register_error_handlers

    register_error_handlers(app)

    from app.cli import register_cli

    register_cli(app)
    return app


def _init_extensions(app):
    from app import models  # noqa: F401  (registers models with the metadata)

    db.init_app(app)
    migrate.init_app(app, db, compare_type=True)
    login_manager.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)

    from app.security import init_security

    init_security(app)


def _register_blueprints(app):
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.allowlist import bp as allowlist_bp
    from app.blueprints.api import bp as api_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.scan import bp as scan_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(scan_bp, url_prefix="/scan")
    app.register_blueprint(allowlist_bp, url_prefix="/allowlist")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api/v1")
