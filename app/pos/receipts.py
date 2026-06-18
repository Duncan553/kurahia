"""
pos/receipts.py — Compiled receipt data for a tab.
GET /receipts           — central search (date, staff, status filters)
GET /receipts/:tab_id   — full receipt for one tab
"""
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.tab import Tab
from app.models.charge import Charge
from app.models.payment import Payment
from app.models.user import User
from app.services.tab import get_tab_balance

receipts_bp = Blueprint("receipts", __name__, url_prefix="/receipts")


FRONT_DESK_LEVEL = 3


@receipts_bp.get("")
@require_active_user
def list_receipts():
    """Central receipts search — front desk+ can search by date, staff, q."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Front desk or above required."}), 403

    from app.services.business_day import business_day_bounds
    date_str = request.args.get("date")
    q = (request.args.get("q") or "").strip()

    if date_str:
        try:
            day_start, day_end = business_day_bounds(date_str)
        except ValueError:
            return jsonify({"error": "date must be YYYY-MM-DD."}), 400
    else:
        day_start = datetime.now(timezone.utc) - timedelta(days=1)
        day_end = datetime.now(timezone.utc) + timedelta(hours=1)

    query = db.session.query(Tab).filter(
        Tab.opened_at_utc >= day_start,
        Tab.opened_at_utc < day_end,
    )
    if q:
        query = query.filter(Tab.reference.ilike(f"%{q}%"))

    tabs = query.order_by(Tab.opened_at_utc.desc()).limit(100).all()

    return jsonify([{
        "tab_id":    t.id,
        "reference": t.reference,
        "tab_type":  t.tab_type,
        "status":    t.status,
        "opened_at": t.opened_at_utc.isoformat(),
        "opened_by": t.opened_by.username if t.opened_by else None,
        "balance":   str(get_tab_balance(t.id)),
    } for t in tabs]), 200


@receipts_bp.get("/<tab_id>")
@require_active_user
def get_receipt(tab_id):
    tab = db.session.get(Tab, tab_id)
    if not tab:
        return jsonify({"error": "Tab not found."}), 404

    charges  = db.session.query(Charge).filter_by(tab_id=tab_id).order_by(Charge.created_at).all()
    payments = db.session.query(Payment).filter_by(tab_id=tab_id).order_by(Payment.created_at_utc).all()

    total_charges  = sum(c.amount for c in charges)
    total_payments = sum(p.amount for p in payments)
    balance        = get_tab_balance(tab_id)

    return jsonify({
        "tab_id":         tab.id,
        "reference":      tab.reference,
        "tab_type":       tab.tab_type,
        "opened_at":      tab.opened_at_utc.isoformat(),
        "closed_at":      tab.closed_at_utc.isoformat() if tab.closed_at_utc else None,
        "opened_by":      tab.opened_by.username if tab.opened_by else None,
        "charges": [
            {
                "description": c.description,
                "amount":      str(c.amount),
                "created_at":  c.created_at.isoformat(),
            }
            for c in charges
        ],
        "payments": [
            {
                "method":      p.method,
                "amount":      str(p.amount),
                "received_by": p.received_by.username if p.received_by else None,
                "mpesa_code":  p.mpesa_code,
                "card_ref":    p.card_ref,
                "created_at":  p.created_at_utc.isoformat(),
            }
            for p in payments
        ],
        "total_charges":  str(total_charges),
        "total_payments": str(total_payments),
        "balance":        str(balance),
        "status":         tab.status,
    }), 200
