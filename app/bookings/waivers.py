"""
bookings/waivers.py — Waiver collection and verification.
Required for water activities; checked at session-booking time.
"""
import uuid
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.booking import Booking
from app.models.waiver import Waiver, WaiverActivityType
from app.models.audit_log import AuditLog

waivers_bp = Blueprint("booking_waivers", __name__, url_prefix="/waivers")

FRONT_DESK_LEVEL = 3


def _at_an_activity_post(actor) -> bool:
    """Water or spa staff, whatever their rank."""
    name = (actor.department.name or "").lower() if actor.department else ""
    return any(k in name for k in ("water", "activit", "aqua", "spa"))


@waivers_bp.post("")
@require_active_user
def create_waiver():
    """Record a signed waiver, for a booking or for a wristband.

    Gated at FRONT_DESK_LEVEL, and the water lead is level 2 — so the person
    standing at the jet ski, whose own nav carries the Waiver tile, was refused
    by the endpoint behind it. That became a dead end the moment selling a water
    activity started requiring a waiver: he could not sell the ride, and could
    not record the thing that would let him.

    The collector of a waiver is whoever is at the post. Front desk and above
    keep it for the villa-guest path.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL and not _at_an_activity_post(actor):
        return jsonify({
            "error": "Front desk, or staff at the activity post, can record a waiver."
        }), 403

    data          = request.get_json(silent=True) or {}
    booking_id    = data.get("booking_id")
    # A day guest holds a WRISTBAND, not a booking. Accepting a band number here
    # is what makes the waiver recordable for the people most likely to be on
    # the water — before this, the only way to sign was to have reserved a villa.
    band_number   = data.get("band_number")
    activity_type = (data.get("activity_type") or "").upper()
    signed_by     = (data.get("signed_by_name") or "").strip()
    idem          = data.get("idempotency_key") or str(uuid.uuid4())

    if not signed_by:
        return jsonify({"error": "signed_by_name is required."}), 400
    if bool(booking_id) == bool(band_number):
        return jsonify({
            "error": "Give either a booking or a wristband number — one, not both."
        }), 400
    if activity_type not in WaiverActivityType.__members__:
        return jsonify({"error": f"activity_type must be one of {list(WaiverActivityType.__members__)}."}), 400

    # A guest double-tapping "Sign" (or a kiosk retrying a flaky request) must not
    # create two waiver records for the same signature.
    existing = db.session.query(Waiver).filter_by(idempotency_key=idem).first()
    if existing:
        return jsonify({
            "id":            existing.id,
            "booking_id":    existing.booking_id,
            "activity_type": existing.activity_type,
            "signed_by":     existing.signed_by_name,
            "signed_at":     existing.signed_at_utc.isoformat(),
            "duplicate":     True,
        }), 200

    tab_id = None
    if booking_id:
        booking = db.session.get(Booking, booking_id)
        if not booking:
            return jsonify({"error": "Booking not found."}), 404
    else:
        from app.services.gate import get_band_by_number
        try:
            band = get_band_by_number(int(band_number))
        except (TypeError, ValueError):
            return jsonify({"error": "Wristband number must be a number."}), 400
        if not band:
            return jsonify({
                "error": f"No active wristband #{band_number} today. "
                         f"Check the number on the band."
            }), 404
        tab_id = band.tab_id

    waiver = Waiver(
        booking_id=booking_id,
        tab_id=tab_id,
        activity_type=activity_type,
        signed_by_name=signed_by,
        signature_proof=data.get("signature_proof"),
        idempotency_key=idem,
    )
    db.session.add(waiver)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.waiver.create",
                 target=booking_id or tab_id, details=f"type={activity_type}")
    db.session.commit()
    return jsonify({
        "id":            waiver.id,
        "booking_id":    waiver.booking_id,
        "tab_id":        waiver.tab_id,
        "activity_type": waiver.activity_type,
        "signed_by":     waiver.signed_by_name,
        "signed_at":     waiver.signed_at_utc.isoformat(),
    }), 201


@waivers_bp.get("")
@require_active_user
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
@require_active_user
def revoke_waiver(waiver_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403
    waiver = db.session.get(Waiver, waiver_id)
    if not waiver:
        return jsonify({"error": "Waiver not found."}), 404
    waiver.is_active = False
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.waiver.revoke", target=waiver_id)
    db.session.commit()
    return jsonify({"id": waiver.id, "is_active": False}), 200
