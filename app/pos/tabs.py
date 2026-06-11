"""
pos/tabs.py — Tab lifecycle: open, view, close.
POST /tabs            — open a tab
GET  /tabs/:id        — full tab state (charges, payments, derived balance)
POST /tabs/:id/close  — close when balance ≤ 0 and all items resolved
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.tab import Tab, TabType, TabStatus
from app.models.charge import Charge
from app.models.payment import Payment
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.user import User
from app.models.audit_log import AuditLog
from app.services.tab import get_tab_balance, is_tab_closable

tabs_bp = Blueprint("tabs", __name__, url_prefix="/tabs")


@tabs_bp.get("")
@require_active_user
def list_tabs():
    """List tabs. Optional filters: status=OPEN|CLOSED, mine=true, tab_type=WALK_IN|VILLA|BAND."""
    actor     = db.session.get(User, get_jwt_identity())
    status    = (request.args.get("status") or "").upper() or None
    mine      = request.args.get("mine", "false").lower() == "true"
    tab_type  = (request.args.get("tab_type") or "").upper() or None

    query = db.session.query(Tab)
    if status:
        if status not in TabStatus.__members__:
            return jsonify({"error": f"status must be one of {list(TabStatus.__members__)}."}), 400
        query = query.filter_by(status=status)
    if mine:
        query = query.filter_by(opened_by_id=actor.id)
    if tab_type:
        if tab_type not in TabType.__members__:
            return jsonify({"error": f"tab_type must be one of {list(TabType.__members__)}."}), 400
        query = query.filter_by(tab_type=tab_type)

    tabs = query.order_by(Tab.opened_at_utc.desc()).all()
    return jsonify([
        {
            "id":        t.id,
            "reference": t.reference,
            "tab_type":  t.tab_type,
            "status":    t.status,
            "opened_at": t.opened_at_utc.isoformat(),
            "opened_by": t.opened_by.username if t.opened_by else None,
            "balance":   str(get_tab_balance(t.id)),
        }
        for t in tabs
    ]), 200


@tabs_bp.post("")
@require_active_user
def open_tab():
    actor = db.session.get(User, get_jwt_identity())
    data      = request.get_json(silent=True) or {}
    tab_type  = (data.get("tab_type") or TabType.WALK_IN.value).upper()
    reference = (data.get("reference") or "").strip() or None

    if tab_type not in TabType.__members__:
        return jsonify({"error": f"tab_type must be one of {list(TabType.__members__)}."}), 400

    with db.session.begin_nested():
        tab = Tab(tab_type=tab_type, reference=reference, opened_by_id=actor.id)
        db.session.add(tab)

    AuditLog.log(actor=actor.username, action="tab.open", target=tab.id,
                 details=f"ref={reference}")
    db.session.commit()
    return jsonify({"id": tab.id, "reference": tab.reference, "status": tab.status}), 201


@tabs_bp.get("/<tab_id>")
@require_active_user
def get_tab(tab_id):
    tab = db.session.get(Tab, tab_id)
    if not tab:
        return jsonify({"error": "Tab not found."}), 404

    balance = get_tab_balance(tab_id)

    charges  = db.session.query(Charge).filter_by(tab_id=tab_id).all()
    payments = db.session.query(Payment).filter_by(tab_id=tab_id).all()
    orders   = db.session.query(Order).filter_by(tab_id=tab_id).all()

    return jsonify({
        "id":          tab.id,
        "reference":   tab.reference,
        "tab_type":    tab.tab_type,
        "status":      tab.status,
        "opened_at":   tab.opened_at_utc.isoformat(),
        "opened_by":   tab.opened_by.username if tab.opened_by else None,
        "balance":     str(balance),
        "charges":  [{"id": c.id, "description": c.description, "amount": str(c.amount),
                      "created_at": c.created_at.isoformat()} for c in charges],
        "payments": [{"id": p.id, "method": p.method, "amount": str(p.amount),
                      "received_by": p.received_by.username if p.received_by else None,
                      "created_at": p.created_at_utc.isoformat()} for p in payments],
        "orders": [
            {
                "id": o.id,
                "status": o.status,
                "items": [
                    {"id": oi.id, "name": oi.menu_item.name if oi.menu_item else None,
                     "quantity": str(oi.quantity), "status": oi.status}
                    for oi in o.items
                ],
            }
            for o in orders
        ],
    }), 200


@tabs_bp.post("/<tab_id>/close")
@require_active_user
def close_tab(tab_id):
    actor = db.session.get(User, get_jwt_identity())
    tab   = db.session.get(Tab, tab_id)
    if not tab:
        return jsonify({"error": "Tab not found."}), 404
    if tab.status == TabStatus.CLOSED.value:
        return jsonify({"error": "This tab is already closed."}), 400

    ok, reason = is_tab_closable(tab_id)
    if not ok:
        return jsonify({"error": reason}), 400

    with db.session.begin_nested():
        tab.status        = TabStatus.CLOSED.value
        tab.closed_at_utc = datetime.now(timezone.utc)
        tab.closed_by_id  = actor.id

    AuditLog.log(actor=actor.username, action="tab.close", target=tab_id)
    db.session.commit()
    return jsonify({"id": tab.id, "status": tab.status}), 200
