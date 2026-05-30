"""
hr/performance.py — Per-staff performance scoring and payroll draft.
Owner/manager+ access. All values derived from immutable records.
"""
from datetime import datetime, timezone, timedelta, date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile
from app.services.hr import compute_performance, compute_hours_worked

performance_bp = Blueprint("hr_performance", __name__, url_prefix="/hr")

MANAGER_LEVEL = 5


def _parse_period(start_str: str | None, end_str: str | None) -> tuple:
    """Return (period_start datetime, period_end datetime) defaulting to current month."""
    today = datetime.now(timezone.utc).date()
    start_s = start_str or today.replace(day=1).isoformat()
    end_s   = end_str   or today.isoformat()
    try:
        period_start = datetime.strptime(start_s, "%Y-%m-%d")
        period_end   = datetime.strptime(end_s,   "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return None, None
    return period_start, period_end


@performance_bp.get("/performance/<profile_id>")
@require_active_user
def staff_performance(profile_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    profile = db.session.get(EmployeeProfile, profile_id)
    if not profile:
        return jsonify({"error": "Employee profile not found."}), 404

    period_start, period_end = _parse_period(
        request.args.get("start_date"),
        request.args.get("end_date"),
    )
    if period_start is None:
        return jsonify({"error": "start_date and end_date must be YYYY-MM-DD."}), 400

    scores = compute_performance(profile_id, period_start, period_end)
    return jsonify({
        "employee_id":   profile_id,
        "employee_name": profile.full_name,
        "period_start":  period_start.strftime("%Y-%m-%d"),
        "period_end":    (period_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        **scores,
    }), 200


@performance_bp.get("/payroll-draft")
@require_active_user
def payroll_draft():
    """
    Payroll-ready summary for all active employees for the period.
    Returns hours worked + wage info; management only.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    period_start, period_end = _parse_period(
        request.args.get("start_date"),
        request.args.get("end_date"),
    )
    if period_start is None:
        return jsonify({"error": "start_date and end_date must be YYYY-MM-DD."}), 400

    profiles = db.session.query(EmployeeProfile).filter_by(is_active=True).all()
    rows = []
    for p in profiles:
        hours = compute_hours_worked(p.id, period_start, period_end)
        rows.append({
            "employee_id":   p.id,
            "employee_name": p.full_name,
            "wage_rate":     str(p.wage_rate) if p.wage_rate else None,
            "wage_period":   p.wage_period,
            "hours_worked":  str(hours),
        })

    return jsonify({
        "period_start": period_start.strftime("%Y-%m-%d"),
        "period_end":   (period_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        "employees":    rows,
    }), 200
