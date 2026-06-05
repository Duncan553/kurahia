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

    from app.pos import menu_bp, tabs_bp, orders_bp, payments_bp, queues_bp, receipts_bp
    app.register_blueprint(menu_bp)
    app.register_blueprint(tabs_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(queues_bp)
    app.register_blueprint(receipts_bp)

    from app.cli import (pos_cli_bp, finance_cli_bp, hr_cli_bp, bookings_cli_bp,
                         gate_cli_bp, events_cli_bp,
                         conduct_cli_bp, calendar_cli_bp, feedback_cli_bp,
                         system_cli_bp, audit_cli_bp, judge_cli_bp)
    app.register_blueprint(pos_cli_bp)
    app.register_blueprint(finance_cli_bp)
    app.register_blueprint(hr_cli_bp)
    app.register_blueprint(bookings_cli_bp)
    app.register_blueprint(gate_cli_bp)
    app.register_blueprint(events_cli_bp)
    app.register_blueprint(conduct_cli_bp)
    app.register_blueprint(calendar_cli_bp)
    app.register_blueprint(feedback_cli_bp)
    app.register_blueprint(system_cli_bp)
    app.register_blueprint(audit_cli_bp)
    app.register_blueprint(judge_cli_bp)

    from app.gate import gate_bp
    app.register_blueprint(gate_bp)

    from app.finance import cash_bp, mpesa_bp, budgets_bp, analytics_bp, reports_bp
    app.register_blueprint(cash_bp)
    app.register_blueprint(mpesa_bp)
    app.register_blueprint(budgets_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(reports_bp)

    from app.finance.mpesa_daraja import mpesa_daraja_bp
    app.register_blueprint(mpesa_daraja_bp)

    from app.finance.bank import bank_bp
    app.register_blueprint(bank_bp)

    from app.finance.bank_transfer import bank_transfer_bp
    app.register_blueprint(bank_transfer_bp)

    from app.finance.card_gateway import card_gateway_bp
    app.register_blueprint(card_gateway_bp)

    from app.hr import (profiles_bp, wifi_bp, shifts_bp, clock_bp,
                        leave_bp, absence_bp, attendance_bp, performance_bp)
    app.register_blueprint(profiles_bp)
    app.register_blueprint(wifi_bp)
    app.register_blueprint(shifts_bp)
    app.register_blueprint(clock_bp)
    app.register_blueprint(leave_bp)
    app.register_blueprint(absence_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(performance_bp)

    from app.bookings import (resources_bp, bookings_bp, deposits_bp,
                               waivers_bp, guests_bp, dashboard_bp)
    app.register_blueprint(resources_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(deposits_bp)
    app.register_blueprint(waivers_bp)
    app.register_blueprint(guests_bp)
    app.register_blueprint(dashboard_bp)

    from app.events import events_bp, event_types_bp
    app.register_blueprint(events_bp)
    app.register_blueprint(event_types_bp)

    from app.notifications import notifications_bp
    app.register_blueprint(notifications_bp)

    from app.suggestions import suggestions_bp
    app.register_blueprint(suggestions_bp)

    from app.conduct import conduct_bp
    app.register_blueprint(conduct_bp)

    from app.disputes import disputes_bp
    app.register_blueprint(disputes_bp)

    from app.feedback import feedback_bp
    app.register_blueprint(feedback_bp)

    from app.calendar_view import calendar_bp
    app.register_blueprint(calendar_bp)

    from app.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)

    from app.equipment import equipment_bp
    app.register_blueprint(equipment_bp)

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

    # Catch-all: unhandled exceptions return JSON, never Flask HTML.
    # Mirrors Flask's own propagation check so TESTING=True still propagates
    # exceptions to the test suite (handle_user_exception calls this before
    # handle_exception's propagation guard, so we must guard here too).
    @app.errorhandler(Exception)
    def handle_unexpected(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e   # 4xx errors pass through to their own handlers
        propagate = app.config.get("PROPAGATE_EXCEPTIONS")
        if propagate is None:
            propagate = app.testing or app.debug
        # Re-raise in test/debug mode so pytest and Werkzeug debugger see real exceptions. Standard Flask pattern.
        if propagate:
            raise
        app.logger.exception("Unhandled exception")
        return jsonify({
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again or contact your manager.",
        }), 500

    return app
