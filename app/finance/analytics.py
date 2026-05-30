"""
finance/analytics.py — Void & discount anomaly analytics.

GET /finance/anomalies/voids?from=...&to=...     → per-staff void rate + flagging
GET /finance/anomalies/discounts?from=...&to=... → placeholder (no discount model yet)

Abnormal void rates → JudgeAlert.
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.judge_alert import JudgeAlert, AlertSeverity, AlertStatus
from app.models.audit_log import AuditLog
from app.services.finance import get_void_rates

analytics_bp = Blueprint("finance_analytics", __name__, url_prefix="/finance")

MANAGER_LEVEL = 5


def _parse_from_to(args) -> tuple | None:
    """Parse 'from' and 'to' ISO datetime strings into UTC datetimes."""
    from_str = args.get("from")
    to_str   = args.get("to")
    if not from_str or not to_str:
        return None
    try:
        period_start = datetime.fromisoformat(from_str).replace(tzinfo=timezone.utc)
        period_end   = datetime.fromisoformat(to_str).replace(tzinfo=timezone.utc)
        return period_start, period_end
    except ValueError:
        return None


@analytics_bp.get("/anomalies/voids")
@require_active_user
def void_analytics():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    bounds = _parse_from_to(request.args)
    if not bounds:
        return jsonify({"error": "'from' and 'to' query params required (ISO 8601 datetime)."}), 400
    period_start, period_end = bounds

    rates = get_void_rates(period_start, period_end)

    # Fire alerts for newly flagged high-void staff (avoid duplicate storms — simple check)
    for row in rates:
        if row["flagged"]:
            existing = db.session.query(JudgeAlert).filter(
                JudgeAlert.alert_type == "VOID_ABUSE",
                JudgeAlert.description.contains(row["staff_id"]),
                JudgeAlert.status == AlertStatus.OPEN.value,
            ).first()
            if not existing:
                alert = JudgeAlert(
                    item_id=None,
                    alert_type="VOID_ABUSE",
                    severity=AlertSeverity.MEDIUM.value,
                    description=(
                        f"{row['staff_name']} has a void rate of {row['void_rate_pct']}% "
                        f"vs average {row['avg_rate_pct']}% "
                        f"({row['void_count']} voids out of {row['total_items']} items)."
                    ),
                    period_start=period_start,
                    period_end=period_end,
                    status=AlertStatus.OPEN.value,
                )
                db.session.add(alert)

    if any(r["flagged"] for r in rates):
        db.session.commit()

    return jsonify({
        "period_from": period_start.isoformat(),
        "period_to":   period_end.isoformat(),
        "staff_rates": rates,
        "flagged_count": sum(1 for r in rates if r["flagged"]),
    }), 200


@analytics_bp.get("/anomalies/discounts")
@require_active_user
def discount_analytics():
    """
    Placeholder — no discount/comp model exists yet.
    Returns empty data with a note so the frontend can show the screen without error.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    return jsonify({
        "note": "Discount/comp tracking is not yet configured. "
                "Add a discount field to Charge in a future chunk.",
        "staff_rates": [],
        "flagged_count": 0,
    }), 200
