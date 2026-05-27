"""
admin/baselines.py — Full CRUD for JudgeBaselines. Owner only.
GET    /admin/baselines
POST   /admin/baselines
PATCH  /admin/baselines/:id
POST   /admin/baselines/:id/disable
POST   /admin/baselines/:id/enable
"""
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.judge_baseline import JudgeBaseline
from app.models.inventory_item import InventoryItem
from app.models.user import User
from app.models.audit_log import AuditLog

baselines_bp = Blueprint("admin_baselines", __name__, url_prefix="/admin/baselines")

OWNER_LEVEL = 10


def _require_owner(actor):
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can manage judge baselines."}), 403
    return None


@baselines_bp.get("")
@jwt_required()
def list_baselines():
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    query = db.session.query(JudgeBaseline)
    if not include_disabled:
        query = query.filter_by(is_active=True)
    return jsonify([
        {
            "id":               b.id,
            "item_id":          b.item_id,
            "item_name":        b.item.name if b.item else None,
            "business_driver":  b.business_driver,
            "expected_ratio":   str(b.expected_ratio),
            "driver_unit":      b.driver_unit,
            "tolerance_percent": str(b.tolerance_percent),
            "is_active":        b.is_active,
        }
        for b in query.all()
    ]), 200


@baselines_bp.post("")
@jwt_required()
def create_baseline():
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id")
    driver  = (data.get("business_driver") or "").strip()
    if not item_id or not driver:
        return jsonify({"error": "item_id and business_driver are required."}), 400
    item = db.session.get(InventoryItem, item_id)
    if not item:
        return jsonify({"error": "Item not found."}), 404
    try:
        ratio = Decimal(str(data.get("expected_ratio", "0")))
        tol   = Decimal(str(data.get("tolerance_percent", "20")))
    except InvalidOperation:
        return jsonify({"error": "expected_ratio and tolerance_percent must be numbers."}), 400
    if ratio <= 0:
        return jsonify({"error": "expected_ratio must be greater than zero."}), 400
    existing = db.session.query(JudgeBaseline).filter_by(
        item_id=item_id, business_driver=driver
    ).first()
    if existing:
        return jsonify({"error": "A baseline for this item and driver already exists. Edit it instead."}), 409
    with db.session.begin_nested():
        b = JudgeBaseline(
            item_id=item_id, business_driver=driver,
            expected_ratio=ratio, driver_unit=data.get("driver_unit", ""),
            tolerance_percent=tol,
        )
        db.session.add(b)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="admin.baseline.create", target=item.name)
    db.session.commit()
    return jsonify({"id": b.id}), 201


@baselines_bp.patch("/<baseline_id>")
@jwt_required()
def edit_baseline(baseline_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    b = db.session.get(JudgeBaseline, baseline_id)
    if not b:
        return jsonify({"error": "Baseline not found."}), 404
    data = request.get_json(silent=True) or {}
    with db.session.begin_nested():
        if "expected_ratio" in data:
            b.expected_ratio = Decimal(str(data["expected_ratio"]))
        if "tolerance_percent" in data:
            b.tolerance_percent = Decimal(str(data["tolerance_percent"]))
        if "driver_unit" in data:
            b.driver_unit = data["driver_unit"]
    db.session.commit()
    AuditLog.log(actor=actor.username, action="admin.baseline.edit", target=baseline_id)
    db.session.commit()
    return jsonify({"id": b.id, "expected_ratio": str(b.expected_ratio)}), 200


@baselines_bp.post("/<baseline_id>/disable")
@jwt_required()
def disable_baseline(baseline_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    b = db.session.get(JudgeBaseline, baseline_id)
    if not b:
        return jsonify({"error": "Baseline not found."}), 404
    with db.session.begin_nested():
        b.is_active = False
    db.session.commit()
    return jsonify({"id": b.id, "is_active": False}), 200


@baselines_bp.post("/<baseline_id>/enable")
@jwt_required()
def enable_baseline(baseline_id):
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err
    b = db.session.get(JudgeBaseline, baseline_id)
    if not b:
        return jsonify({"error": "Baseline not found."}), 404
    with db.session.begin_nested():
        b.is_active = True
    db.session.commit()
    return jsonify({"id": b.id, "is_active": True}), 200
