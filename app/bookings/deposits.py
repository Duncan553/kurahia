"""
bookings/deposits.py — Deposit and balance payment recording.
Deposits: recorded before check-in; Payment.tab_id is NULL.
Balance: can also be recorded here; links to booking post-check-in.
"""
import uuid
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models.user import User
from app.models.booking import Booking, BookingStatus
from app.models.booking_payment import BookingPayment, BookingPaymentPurpose
from app.models.payment import Payment, PaymentMethod
from app.models.audit_log import AuditLog

deposits_bp = Blueprint("booking_deposits", __name__, url_prefix="/booking-payments")

FRONT_DESK_LEVEL = 3


@deposits_bp.post("")
@jwt_required()
def record_booking_payment():
    """Record a DEPOSIT or BALANCE payment against a booking."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    data       = request.get_json(silent=True) or {}
    booking_id = data.get("booking_id")
    purpose    = (data.get("purpose") or "DEPOSIT").upper()
    method     = (data.get("method") or "").upper()
    idem_key   = data.get("idempotency_key") or str(uuid.uuid4())

    if not booking_id:
        return jsonify({"error": "booking_id is required."}), 400
    if purpose not in BookingPaymentPurpose.__members__:
        return jsonify({"error": f"purpose must be one of {list(BookingPaymentPurpose.__members__)}."}), 400
    if method not in PaymentMethod.__members__:
        return jsonify({"error": f"method must be one of {list(PaymentMethod.__members__)}."}), 400

    try:
        amount = Decimal(str(data.get("amount", 0)))
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return jsonify({"error": "amount must be a positive number."}), 400

    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    # Deposit only allowed before check-in
    if purpose == BookingPaymentPurpose.DEPOSIT.value and \
            booking.status not in (BookingStatus.HELD.value, BookingStatus.CONFIRMED.value):
        return jsonify({"error": "Deposits can only be recorded for HELD or CONFIRMED bookings."}), 400

    # Idempotency check on the Payment record
    existing_payment = db.session.query(Payment).filter_by(idempotency_key=idem_key).first()
    if existing_payment:
        bp = db.session.query(BookingPayment).filter_by(payment_id=existing_payment.id).first()
        return jsonify({"id": bp.id if bp else None, "duplicate": True}), 200

    # Deposit: no tab yet; Balance: use booking's tab if available
    tab_id = booking.tab_id if purpose == BookingPaymentPurpose.BALANCE.value else None

    payment = Payment(
        tab_id=tab_id,
        amount=amount,
        method=method,
        mpesa_code=data.get("mpesa_code"),
        card_ref=data.get("card_ref"),
        description=f"{purpose.lower()} for booking {booking_id[:8]}",
        received_by_id=actor.id,
        idempotency_key=idem_key,
    )
    db.session.add(payment)
    db.session.flush()

    bp = BookingPayment(
        booking_id=booking_id,
        payment_id=payment.id,
        purpose=purpose,
    )
    db.session.add(bp)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="booking.payment",
                 target=booking_id, details=f"{purpose} {method} {amount}")
    db.session.commit()
    return jsonify({
        "id":         bp.id,
        "booking_id": booking_id,
        "payment_id": payment.id,
        "purpose":    purpose,
        "amount":     str(amount),
        "method":     method,
    }), 201


@deposits_bp.get("")
@jwt_required()
def list_booking_payments():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    booking_id = request.args.get("booking_id")
    if not booking_id:
        return jsonify({"error": "booking_id query parameter required."}), 400

    bps = db.session.query(BookingPayment).filter_by(booking_id=booking_id).all()
    result = []
    for bp in bps:
        p = db.session.get(Payment, bp.payment_id)
        result.append({
            "id":         bp.id,
            "purpose":    bp.purpose,
            "amount":     str(p.amount) if p else None,
            "method":     p.method if p else None,
            "created_at": bp.created_at_utc.isoformat(),
        })
    return jsonify(result), 200
