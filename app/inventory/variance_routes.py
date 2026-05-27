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
from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.user import User
from app.services.variance import compute_variance

variance_bp = Blueprint("inv_variance", __name__, url_prefix="/inventory")

MANAGER_LEVEL = 5


@variance_bp.get("/variance")
@jwt_required()
def variance_report():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    dept_id  = request.args.get("dept") or (actor.department_id if actor.role.level < 10 else None)
    from_str = request.args.get("from")
    to_str   = request.args.get("to")

    if not from_str or not to_str:
        return jsonify({"error": "'from' and 'to' query params required (ISO 8601 UTC)"}), 400

    try:
        period_start = datetime.fromisoformat(from_str).replace(tzinfo=timezone.utc)
        period_end   = datetime.fromisoformat(to_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use ISO 8601, e.g. 2026-05-01T00:00:00"}), 400

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
