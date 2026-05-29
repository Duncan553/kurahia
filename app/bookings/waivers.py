"""
bookings/waivers.py — Waiver collection and verification.
Required for water activities; checked at session-booking time.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.user import User
from app.models.booking import Booking
from app.models.waiver import Waiver, WaiverActivityType
from app.models.audit_log import AuditLog

waivers_bp = Blueprint("booking_waivers", __name__, url_prefix="/waivers")

FRONT_DESK_LEVEL = 3


@waivers_bp.post("")
@jwt_required()
def create_waiver():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    data          = request.get_json(silent=True) or {}
    booking_id    = data.get("booking_id")
    activity_type = (data.get("activity_type") or "").upper()
    signed_by     = (data.get("signed_by_name") or "").strip()

    if not booking_id or not signed_by:
        return jsonify({"error": "booking_id and signed_by_name are required."}), 400
    if activity_type not in WaiverActivityType.__members__:
        return jsonify({"error": f"activity_type must be one of {list(WaiverActivityType.__members__)}."}), 400

    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    waiver = Waiver(
        booking_id=booking_id,
        activity_type=activity_type,
        signed_by_name=signed_by,
        signature_proof=data.get("signature_proof"),
    )
    db.session.add(waiver)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="booking.waiver.create",
                 target=booking_id, details=f"type={activity_type}")
    db.session.commit()
    return jsonify({
        "id":            waiver.id,
        "booking_id":    waiver.booking_id,
        "activity_type": waiver.activity_type,
        "signed_by":     waiver.signed_by_name,
        "signed_at":     waiver.signed_at_utc.isoformat(),
    }), 201


@waivers_bp.get("")
@jwt_required()
def list_waivers():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    booking_id    = request.args.get("booking_id")
    activity_type = (request.args.get("activity_type") or "").upper() or None

    query = db.session.query(Waiver)
    if booking_id:
        query = query.filter_by(booking_id=booking_id)
    if activity_type:
        query = query.filter_by(activity_type=activity_type)

    waivers = query.order_by(Waiver.signed_at_utc.desc()).all()
    return jsonify([{
        "id":            w.id,
        "booking_id":    w.booking_id,
        "activity_type": w.activity_type,
        "signed_by":     w.signed_by_name,
        "signed_at":     w.signed_at_utc.isoformat(),
        "is_active":     w.is_active,
    } for w in waivers]), 200


@waivers_bp.post("/<waiver_id>/revoke")
@jwt_required()
def revoke_waiver(waiver_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403
    waiver = db.session.get(Waiver, waiver_id)
    if not waiver:
        return jsonify({"error": "Waiver not found."}), 404
    waiver.is_active = False
    db.session.commit()
    AuditLog.log(actor=actor.username, action="booking.waiver.revoke", target=waiver_id)
    db.session.commit()
    return jsonify({"id": waiver.id, "is_active": False}), 200
