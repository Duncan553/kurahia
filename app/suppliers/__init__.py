"""
suppliers/ — Supplier CRUD endpoints.

GET    /suppliers             — list all active suppliers
POST   /suppliers             — create (manager+)
PATCH  /suppliers/<id>        — edit   (manager+)
POST   /suppliers/<id>/disable — soft-delete (manager+)
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.supplier import Supplier
from app.models.audit_log import AuditLog

suppliers_bp = Blueprint("suppliers", __name__, url_prefix="/suppliers")

MANAGER_LEVEL = 5


def _supplier_dict(s: Supplier) -> dict:
    """Serialize a Supplier row for JSON response."""
    return {
        "id":              s.id,
        "name":            s.name,
        "contact_person":  s.contact_person,
        "phone":           s.phone,
        "email":           s.email,
        "items_supplied":  s.items_supplied,
        "payment_terms":   s.payment_terms,
        "is_active":       s.is_active,
        "notes":           s.notes,
        "created_at_utc":  s.created_at_utc.isoformat() if s.created_at_utc else None,
    }


@suppliers_bp.get("")
@require_active_user
def list_suppliers():
    """Return all active suppliers. Pass ?include_disabled=true for inactive ones too."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    q = db.session.query(Supplier)
    if not include_disabled:
        q = q.filter_by(is_active=True)
    return jsonify([_supplier_dict(s) for s in q.order_by(Supplier.name).all()]), 200


@suppliers_bp.post("")
@require_active_user
def create_supplier():
    """Create a new supplier. Manager+ only."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required."}), 400
    # Check uniqueness (case-insensitive)
    exists = db.session.query(Supplier).filter(
        db.func.lower(Supplier.name) == name.lower()
    ).first()
    if exists:
        return jsonify({"error": f"A supplier named '{exists.name}' already exists."}), 409
    s = Supplier(
        name=name,
        contact_person=(data.get("contact_person") or "").strip() or None,
        phone=(data.get("phone") or "").strip() or None,
        email=(data.get("email") or "").strip() or None,
        items_supplied=(data.get("items_supplied") or "").strip() or None,
        payment_terms=(data.get("payment_terms") or "").strip() or None,
        notes=(data.get("notes") or "").strip() or None,
    )
    db.session.add(s)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="supplier.create", target=s.id, details=name)
    db.session.commit()
    return jsonify(_supplier_dict(s)), 201


@suppliers_bp.patch("/<supplier_id>")
@require_active_user
def edit_supplier(supplier_id):
    """Edit an existing supplier. Manager+ only."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    s = db.session.get(Supplier, supplier_id)
    if not s or not s.is_active:
        return jsonify({"error": "Supplier not found or disabled."}), 404
    data = request.get_json(silent=True) or {}
    if "name" in data:
        new_name = (data["name"] or "").strip()
        if not new_name:
            return jsonify({"error": "name cannot be empty."}), 400
        # Check uniqueness against other suppliers
        dup = db.session.query(Supplier).filter(
            db.func.lower(Supplier.name) == new_name.lower(),
            Supplier.id != supplier_id,
        ).first()
        if dup:
            return jsonify({"error": f"A supplier named '{dup.name}' already exists."}), 409
        s.name = new_name
    if "contact_person" in data:
        s.contact_person = (data["contact_person"] or "").strip() or None
    if "phone" in data:
        s.phone = (data["phone"] or "").strip() or None
    if "email" in data:
        s.email = (data["email"] or "").strip() or None
    if "items_supplied" in data:
        s.items_supplied = (data["items_supplied"] or "").strip() or None
    if "payment_terms" in data:
        s.payment_terms = (data["payment_terms"] or "").strip() or None
    if "notes" in data:
        s.notes = (data["notes"] or "").strip() or None
    s.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="supplier.edit", target=supplier_id)
    db.session.commit()
    return jsonify(_supplier_dict(s)), 200


@suppliers_bp.post("/<supplier_id>/disable")
@require_active_user
def disable_supplier(supplier_id):
    """Soft-delete a supplier. Manager+ only."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    s = db.session.get(Supplier, supplier_id)
    if not s:
        return jsonify({"error": "Supplier not found."}), 404
    s.is_active = False
    s.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="supplier.disable", target=supplier_id)
    db.session.commit()
    return jsonify({"id": s.id, "is_active": False}), 200
