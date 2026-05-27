"""
judge/routes.py — Owner-only alert feed + CLI triggers.
HTTP:  GET /judge/alerts, POST /judge/alerts/<id>/acknowledge
CLI:   flask judge run-weekly, flask judge run-daily, flask judge seed-baselines
"""
import click
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.judge_alert import JudgeAlert, AlertStatus
from app.models.user import User

judge_bp = Blueprint("judge", __name__, url_prefix="/judge")

OWNER_LEVEL = 10


def _require_owner(actor: User):
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Owner only."}), 403
    return None


@judge_bp.get("/alerts")
@jwt_required()
def list_alerts():
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err

    status_filter = request.args.get("status", AlertStatus.OPEN.value).upper()
    query = db.session.query(JudgeAlert).order_by(JudgeAlert.created_at.desc())

    if status_filter != "ALL":
        query = query.filter_by(status=status_filter)

    alerts = query.all()
    return jsonify([
        {
            "id":          a.id,
            "item_id":     a.item_id,
            "item_name":   a.item.name if a.item else None,
            "alert_type":  a.alert_type,
            "severity":    a.severity,
            "description": a.description,
            "status":      a.status,
            "created_at":  a.created_at.isoformat(),
        }
        for a in alerts
    ]), 200


@judge_bp.post("/alerts/<alert_id>/acknowledge")
@jwt_required()
def acknowledge_alert(alert_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err

    alert = db.session.get(JudgeAlert, alert_id)
    if not alert:
        return jsonify({"error": "Alert not found."}), 404

    with db.session.begin_nested():
        alert.status             = AlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_at    = datetime.now(timezone.utc)
        alert.acknowledged_by_id = actor.id

    db.session.commit()
    return jsonify({"id": alert.id, "status": alert.status}), 200


# ── CLI commands (flask judge ...) ────────────────────────────────────────────

@judge_bp.cli.command("seed-baselines")
def cli_seed_baselines():
    """Seed conservative judge baselines. Run once after flask inventory seed-items."""
    from app.cli.judge import _seed_baselines
    _seed_baselines()


@judge_bp.cli.command("run-weekly")
@click.option("--days-ago", default=7, help="How many days back the period starts")
def cli_run_weekly(days_ago):
    """Run the weekly judge analysis. Dormant until POS data arrives."""
    from app.judge.engine import run_weekly as _run
    now    = datetime.now(timezone.utc)
    start  = now - timedelta(days=days_ago)
    alerts = _run(start, now)
    click.echo(f"Weekly judge ran. Alerts fired: {alerts}")


@judge_bp.cli.command("run-daily")
def cli_run_daily():
    """Run the daily judge for watch-list items and spoilage spikes."""
    from app.judge.engine import run_daily as _run
    alerts = _run(datetime.now(timezone.utc))
    click.echo(f"Daily judge ran. Alerts fired: {alerts}")
