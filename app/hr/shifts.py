"""
hr/shifts.py — Shift scheduling.
Manager+ creates/edits shifts. CANCELLED status is permanent (no delete).
Schedule conflicts (same employee overlapping) → rejected.
"""
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile
from app.models.department import Department
from app.models.shift import Shift, ShiftStatus
from app.models.audit_log import AuditLog

shifts_bp = Blueprint("hr_shifts", __name__, url_prefix="/hr")

MANAGER_LEVEL = 5


def _parse_dt(val: str) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _has_conflict(employee_id: str, start: datetime, end: datetime,
                  exclude_id: str | None = None) -> bool:
    """True if the employee already has a SCHEDULED shift overlapping [start, end)."""
    query = db.session.query(Shift).filter(
        Shift.employee_id == employee_id,
        Shift.status == ShiftStatus.SCHEDULED.value,
        Shift.scheduled_start_utc < end,
        Shift.scheduled_end_utc   > start,
    )
    if exclude_id:
        query = query.filter(Shift.id != exclude_id)
    return query.first() is not None


@shifts_bp.post("/shifts")
@require_active_user
def create_shift():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to create shifts."}), 403

    data        = request.get_json(silent=True) or {}
    employee_id = data.get("employee_id")
    start_str   = data.get("scheduled_start_utc")
    end_str     = data.get("scheduled_end_utc")
    idem_key    = data.get("idempotency_key") or str(uuid.uuid4())

    if not employee_id or not start_str or not end_str:
        return jsonify({"error": "employee_id, scheduled_start_utc, and scheduled_end_utc are required."}), 400

    start = _parse_dt(start_str)
    end   = _parse_dt(end_str)
    if not start or not end:
        return jsonify({"error": "Dates must be ISO 8601 (e.g. 2026-06-01T08:00:00)."}), 400
    if end <= start:
        return jsonify({"error": "scheduled_end_utc must be after scheduled_start_utc."}), 400

    profile = db.session.get(EmployeeProfile, employee_id)
    if not profile or not profile.is_active:
        return jsonify({"error": "Employee profile not found or disabled."}), 404

    # A department is OPTIONAL on a shift, but if one is named it has to be a
    # real, active one. Copying the raw string onto the row meant a typo either
    # blew up as a bare FOREIGN KEY error (a 500 with no readable reason) or —
    # where the FK is not enforced — landed a shift pointing at nothing, which
    # then vanishes from GET /hr/attendance/today?department_id=... Same rule
    # POST /hr/roster already applies; checked here so the two agree.
    department_id = data.get("department_id")
    if department_id:
        dept = db.session.get(Department, department_id)
        if not dept or not dept.is_active:
            return jsonify({"error": "Department not found or disabled."}), 404

    # Idempotency
    existing = db.session.query(Shift).filter_by(idempotency_key=idem_key).first()
    if existing:
        return jsonify({"id": existing.id, "duplicate": True}), 200

    if _has_conflict(employee_id, start, end):
        return jsonify({
            "error": f"{profile.full_name} already has a scheduled shift during this time. "
                      "Cancel the existing shift first."
        }), 409

    shift = Shift(
        employee_id=employee_id,
        scheduled_start_utc=start,
        scheduled_end_utc=end,
        role_on_shift=data.get("role_on_shift"),
        department_id=department_id,
        created_by_id=actor.id,
        idempotency_key=idem_key,
    )
    db.session.add(shift)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.shift.create", target=employee_id,
                 details=f"{start.isoformat()}–{end.isoformat()}")
    db.session.commit()
    return jsonify({"id": shift.id, "employee_id": employee_id,
                    "scheduled_start_utc": start.isoformat(),
                    "scheduled_end_utc":   end.isoformat()}), 201


@shifts_bp.post("/shifts/generate")
@require_active_user
def generate_roster():
    """Create a week of shifts from each employee's stored working pattern.

    Body: {"week_start": "2026-09-01", "dry_run": false}
    week_start defaults to the coming Monday.

    This is the answer to "who rosters 14 people every Sunday" — nobody does,
    which is why the board was empty. The pattern is set once per person; this
    turns it into shifts. Anyone without a pattern is untouched and still
    rostered by hand.
    """
    from datetime import date, timedelta
    from app.services.roster_generator import generate_week

    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to generate a roster."}), 403

    data = request.get_json(silent=True) or {}
    raw = data.get("week_start")
    if raw:
        try:
            week_start = date.fromisoformat(raw)
        except (ValueError, TypeError):
            return jsonify({"error": "week_start must be YYYY-MM-DD."}), 400
    else:
        today = date.today()
        week_start = today + timedelta(days=(7 - today.weekday()) % 7 or 7)

    result = generate_week(week_start, actor.id, dry_run=bool(data.get("dry_run")))
    if not data.get("dry_run"):
        AuditLog.log(actor=actor.username, action="hr.roster.generate",
                     target=result["week_start"],
                     details=f"created={result['created']} "
                             f"already={result['already_rostered']} "
                             f"on_leave={result['skipped_on_leave']}")
        db.session.commit()
    return jsonify(result), 200


@shifts_bp.get("/shifts")
@require_active_user
def list_shifts():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    employee_id = request.args.get("employee_id")
    date_str    = request.args.get("date")

    query = db.session.query(Shift)
    if employee_id:
        query = query.filter_by(employee_id=employee_id)
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            query = query.filter(
                Shift.scheduled_start_utc >= d,
                Shift.scheduled_start_utc <  d.replace(hour=23, minute=59, second=59),
            )
        except ValueError:
            return jsonify({"error": "date must be YYYY-MM-DD."}), 400

    shifts = query.order_by(Shift.scheduled_start_utc).all()
    return jsonify([{
        "id":          s.id,
        "employee_id": s.employee_id,
        "employee_name": s.employee.full_name if s.employee else None,
        "start":       s.scheduled_start_utc.isoformat(),
        "end":         s.scheduled_end_utc.isoformat(),
        "role":        s.role_on_shift,
        "status":      s.status,
    } for s in shifts]), 200


@shifts_bp.patch("/shifts/<shift_id>")
@require_active_user
def edit_shift(shift_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    shift = db.session.get(Shift, shift_id)
    if not shift:
        return jsonify({"error": "Shift not found."}), 404
    if shift.status == ShiftStatus.CANCELLED.value:
        return jsonify({"error": "Cannot edit a cancelled shift."}), 400

    data = request.get_json(silent=True) or {}
    new_start = _parse_dt(data.get("scheduled_start_utc")) or shift.scheduled_start_utc
    new_end   = _parse_dt(data.get("scheduled_end_utc"))   or shift.scheduled_end_utc

    if new_end <= new_start:
        return jsonify({"error": "End must be after start."}), 400
    if _has_conflict(shift.employee_id, new_start, new_end, exclude_id=shift_id):
        return jsonify({"error": "This change would create a schedule conflict."}), 409

    shift.scheduled_start_utc = new_start
    shift.scheduled_end_utc   = new_end
    if "role_on_shift" in data:
        shift.role_on_shift = data["role_on_shift"]
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.shift.edit", target=shift_id)
    db.session.commit()
    return jsonify({"id": shift.id, "status": shift.status}), 200


@shifts_bp.post("/shifts/<shift_id>/cancel")
@require_active_user
def cancel_shift(shift_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    shift = db.session.get(Shift, shift_id)
    if not shift:
        return jsonify({"error": "Shift not found."}), 404
    if shift.status == ShiftStatus.CANCELLED.value:
        return jsonify({"error": "Shift is already cancelled."}), 400
    shift.status = ShiftStatus.CANCELLED.value
    db.session.flush()
    AuditLog.log(actor=actor.username, action="hr.shift.cancel", target=shift_id)
    db.session.commit()
    return jsonify({"id": shift.id, "status": shift.status}), 200
