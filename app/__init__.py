"""
app/__init__.py — Application factory.

Why a factory? It lets you create multiple app instances with different configs
(dev, test, prod) without global state collisions. Flask-Migrate and tests rely on this.

Call create_app() once in run.py (or via `flask run`). Extensions are bound here.
"""
import os
from flask import Flask, jsonify
from .extensions import db, jwt, migrate
from config import config


def create_app(config_name: str = None) -> Flask:
    # Use FLASK_ENV env var if no config_name passed in
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "default")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config[config_name])

    # Validate required prod config before going further
    if config_name == "production" and not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL must be set in production")

    # Bind extensions to this specific app instance
    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)

    # Import models here so Flask-Migrate sees them for `flask db migrate`
    with app.app_context():
        from app import models  # noqa: F401

    # Register blueprints (URL namespaces)
    from app.auth import auth_bp, users_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)

    from app.cli import seed_bp, inventory_cli_bp
    app.register_blueprint(seed_bp)
    app.register_blueprint(inventory_cli_bp)

    from app.inventory import items_bp, movements_bp, counts_bp, purchases_bp, variance_bp
    app.register_blueprint(items_bp)
    app.register_blueprint(movements_bp)
    app.register_blueprint(counts_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(variance_bp)

    from app.judge import judge_bp
    app.register_blueprint(judge_bp)

    from app.admin import dept_bp, roles_bp, baselines_bp
    app.register_blueprint(dept_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(baselines_bp)

    # Health check — useful for load balancers and deploy scripts
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    # JWT error handlers — return JSON instead of HTML error pages
    @jwt.expired_token_loader
    def expired_token(_jwt_header, _jwt_data):
        return jsonify({"error": "Token has expired."}), 401

    @jwt.invalid_token_loader
    def invalid_token(_reason):
        return jsonify({"error": "Invalid token."}), 401

    @jwt.unauthorized_loader
    def missing_token(_reason):
        return jsonify({"error": "Authorization token required."}), 401

    return app
