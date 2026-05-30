"""
bookings/guests.py — GuestRecord queries.
Auto-managed; created / matched on booking creation. Read-only API.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.guest_record import GuestRecord
from app.models.booking import Booking

guests_bp = Blueprint("booking_guests", __name__, url_prefix="/guest-records")

FRONT_DESK_LEVEL = 3


@guests_bp.get("")
@require_active_user
def list_guests():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    phone  = request.args.get("phone")
    query  = db.session.query(GuestRecord).filter_by(is_active=True)
    if phone:
        query = query.filter(GuestRecord.phone.contains(phone))

    guests = query.order_by(GuestRecord.last_visit_utc.desc().nullslast()).all()
    return jsonify([_guest_dict(g) for g in guests]), 200


@guests_bp.get("/<guest_id>")
@require_active_user
def get_guest(guest_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403
    guest = db.session.get(GuestRecord, guest_id)
    if not guest:
        return jsonify({"error": "Guest record not found."}), 404
    return jsonify(_guest_dict(guest)), 200


@guests_bp.get("/<guest_id>/history")
@require_active_user
def guest_history(guest_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403
    guest = db.session.get(GuestRecord, guest_id)
    if not guest:
        return jsonify({"error": "Guest record not found."}), 404

    bookings = db.session.query(Booking).filter_by(guest_record_id=guest_id)\
                         .order_by(Booking.check_in_planned_utc.desc()).all()
    return jsonify({
        "guest": _guest_dict(guest),
        "bookings": [{
            "id":              b.id,
            "resource_name":   b.resource.name if b.resource else None,
            "check_in":        b.check_in_planned_utc.isoformat(),
            "check_out":       b.check_out_planned_utc.isoformat(),
            "status":          b.status,
            "base_total":      str(b.base_total),
        } for b in bookings],
    }), 200


def _guest_dict(g: GuestRecord) -> dict:
    return {
        "id":             g.id,
        "name":           g.name,
        "phone":          g.phone,
        "id_number":      g.id_number,
        "notes":          g.notes,
        "last_visit":     g.last_visit_utc.isoformat() if g.last_visit_utc else None,
        "is_active":      g.is_active,
    }
