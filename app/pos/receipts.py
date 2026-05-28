"""
pos/receipts.py — Compiled receipt data for a tab.
GET /receipts/:tab_id — returns structured data the frontend renders visually.
"""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.tab import Tab
from app.models.charge import Charge
from app.models.payment import Payment
from app.models.user import User
from app.services.tab import get_tab_balance

receipts_bp = Blueprint("receipts", __name__, url_prefix="/receipts")


@receipts_bp.get("/<tab_id>")
@jwt_required()
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
