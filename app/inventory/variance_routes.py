"""
variance_routes.py — Layer 1 variance report endpoint.

GET /inventory/variance?dept=<id>&from=<ISO>&to=<ISO>

Returns per-item variance for a department over a date range.
Flagged items are those where |variance %| > item tolerance.
Staff-food items are excluded — they have their own stock category.
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.user import User
from app.services.variance import compute_variance
from app.services.business_day import business_day_bounds

variance_bp = Blueprint("inv_variance", __name__, url_prefix="/inventory")

MANAGER_LEVEL = 5
STATION_LEAD_LEVEL = 3


@variance_bp.get("/variance")
@require_active_user
def variance_report():
    """Expected use against actual use.

    This was manager-only, while the chef's own board carries a Variance tile
    and the shared inventory screen shows a Variance tab to whoever opens it.
    Both offered it and the endpoint refused, and the screen said nothing —
    it just sat on "Select a date range and tap Run".

    A department lead now reads variance FOR THEIR OWN DEPARTMENT, the same
    rule the stock count already uses. That is not a loosening for its own
    sake: the chef is the person who can say why 4kg of beef went, and a
    variance nobody can see is a variance nobody explains — which is exactly
    how genuine waste reaches the judge as an unexplained loss.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < STATION_LEAD_LEVEL:
        return jsonify({"error": "A department lead or above can read variance. "
                                 "Ask your supervisor."}), 403

    # A manager's post is the whole property, and every other inventory read
    # already treats them that way: GET /inventory/items lists all 40 lines for
    # a manager, and counts.py lets a manager count any department. Variance
    # alone defaulted to actor.department_id, so Brian — whose department is
    # "Management", which holds one active line — opened the theft-detection
    # screen and saw 1 item out of 40, silently, with nothing to say so.
    #
    # Below MANAGER_LEVEL nobody reaches this endpoint at all (the check above),
    # so this default only ever narrowed the person it is written for. `dept`
    # still narrows deliberately when a screen asks for one department.
    dept_id  = request.args.get("dept")

    # A lead sees their own department and nothing else — asking for another
    # one is refused rather than quietly answered with their own, so the number
    # on screen always matches the question asked.
    if actor.role.level < MANAGER_LEVEL:
        if dept_id and dept_id != actor.department_id:
            return jsonify({"error": "You can only read variance for your own "
                                     "department."}), 403
        dept_id = actor.department_id
    from_str = request.args.get("from")
    to_str   = request.args.get("to")

    if not from_str or not to_str:
        return jsonify({"error": "'from' and 'to' query params required (ISO 8601 UTC)"}), 400

    # A bare date means the resort's BUSINESS day, not a UTC calendar day.
    # A day here runs 06:00 EAT to 06:00 EAT (app/services/business_day.py,
    # which attendance, finance, receipts and the dashboards all use). Reading
    # "2026-09-11" as UTC midnight put the first three hours of a Kenyan day
    # into the previous window: a stock count taken at 00:50 EAT was reported
    # as "not yet counted" for the day it was taken in.
    #
    # A full ISO timestamp is still honoured exactly as given, so a caller that
    # wants a precise window keeps one.
    try:
        if len(from_str) == 10 and len(to_str) == 10:
            period_start, _ = business_day_bounds(from_str)
            _, period_end   = business_day_bounds(to_str)
        else:
            period_start = datetime.fromisoformat(from_str).replace(tzinfo=timezone.utc)
            period_end   = datetime.fromisoformat(to_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD, or a full "
                                 "ISO 8601 timestamp like 2026-05-01T00:00:00"}), 400

    if period_start >= period_end:
        return jsonify({"error": "'from' must be before 'to'"}), 400

    query = db.session.query(InventoryItem).filter_by(is_active=True, is_staff_food=False)
    if dept_id:
        query = query.filter_by(department_id=dept_id)

    items   = query.all()
    results = []
    flagged = []

    for item in items:
        v = compute_variance(item.id, period_start, period_end)
        if v is None:
            results.append({"item_id": item.id, "item_name": item.name, "no_closing_count": True})
            continue
        if v["flagged"]:
            flagged.append(item.name)
        # Serialize Decimals to strings for JSON
        results.append({k: str(val) if hasattr(val, "quantize") else val for k, val in v.items()})

    return jsonify({
        "period_start": period_start.isoformat(),
        "period_end":   period_end.isoformat(),
        "items":        results,
        "flagged_count": len(flagged),
        "flagged_items": flagged,
    }), 200
