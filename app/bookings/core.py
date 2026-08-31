"""
bookings/core.py — Booking lifecycle: create, confirm, check-in, check-out, cancel,
                   list, availability check, and today's view.
"""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.booking import Booking, BookingStatus
from app.models.bookable_resource import BookableResource, ResourceType
from app.models.audit_log import AuditLog
from app.services.booking import (
    compute_base_total, check_resource_availability, check_capacity,
    transition_booking, get_or_create_guest_record, get_deposit_total,
    open_villa_tab,
)
from app.services.tab import get_tab_balance, is_tab_closable, check_band_credit
from app.models.tab import TabStatus

bookings_bp = Blueprint("bookings_core", __name__, url_prefix="/bookings")

MANAGER_LEVEL   = 5
FRONT_DESK_LEVEL = 3   # staff or above can create bookings


def _parse_dt(val: str) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _booking_dict(b: Booking, include_balance: bool = False) -> dict:
    d = {
        "id":                    b.id,
        "resource_id":           b.resource_id,
        "resource_name":         b.resource.name if b.resource else None,
        "guest_name":            b.guest_name,
        "guest_phone":           b.guest_phone,
        "guest_id_number":       b.guest_id_number,
        "number_of_guests":      b.number_of_guests,
        "check_in_planned":      b.check_in_planned_utc.isoformat() if b.check_in_planned_utc else None,
        "check_out_planned":     b.check_out_planned_utc.isoformat() if b.check_out_planned_utc else None,
        "check_in_actual":       b.check_in_actual_utc.isoformat() if b.check_in_actual_utc else None,
        "check_out_actual":      b.check_out_actual_utc.isoformat() if b.check_out_actual_utc else None,
        "base_total":            str(b.base_total),
        "deposit_required":      str(b.deposit_required),
        "deposit_paid":          str(get_deposit_total(b.id)),
        "status":                b.status,
        "tab_id":                b.tab_id,
        "notes":                 b.notes,
        "guest_record_id":       b.guest_record_id,
    }
    if include_balance and b.tab_id:
        d["tab_balance"] = str(get_tab_balance(b.tab_id))
    return d


# ── Create ────────────────────────────────────────────────────────────────────

@bookings_bp.post("")
@require_active_user
def create_booking():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required to create bookings."}), 403

    data        = request.get_json(silent=True) or {}
    resource_id = data.get("resource_id")
    guest_name  = (data.get("guest_name") or "").strip()
    guest_phone = (data.get("guest_phone") or "").strip()
    ci_str      = data.get("check_in_planned_utc")
    co_str      = data.get("check_out_planned_utc")
    idem_key    = data.get("idempotency_key") or str(uuid.uuid4())
    num_guests  = data.get("number_of_guests", 1)

    if not resource_id or not guest_name or not guest_phone:
        return jsonify({"error": "resource_id, guest_name, and guest_phone are required."}), 400
    if not ci_str or not co_str:
        return jsonify({"error": "check_in_planned_utc and check_out_planned_utc are required."}), 400

    check_in  = _parse_dt(ci_str)
    check_out = _parse_dt(co_str)
    if not check_in or not check_out:
        return jsonify({"error": "Dates must be ISO 8601 (e.g. 2026-06-01T14:00:00)."}), 400
    if check_out <= check_in:
        return jsonify({"error": "check_out_planned_utc must be after check_in_planned_utc."}), 400

    try:
        num_guests = int(num_guests)
    except (ValueError, TypeError):
        return jsonify({"error": "number_of_guests must be an integer."}), 400

    # Idempotency
    existing = db.session.query(Booking).filter_by(idempotency_key=idem_key).first()
    if existing:
        return jsonify({"id": existing.id, "duplicate": True}), 200

    # Lock the resource row for the duration of this transaction.
    # check_resource_availability() + Booking insert are now atomic: no concurrent
    # request can pass the overlap check for this resource until we commit.
    # (SELECT FOR UPDATE serialises in Postgres; SQLite serialises at the writer level.)
    resource = (
        db.session.query(BookableResource)
        .filter_by(id=resource_id)
        .with_for_update()
        .first()
    )
    if not resource or not resource.is_active:
        return jsonify({"error": "Resource not found or disabled."}), 404

    # Capacity check
    ok, reason = check_capacity(resource, num_guests)
    if not ok:
        return jsonify({"error": reason}), 400

    # Double-booking check — runs while the lock is held
    ok, reason = check_resource_availability(resource_id, check_in, check_out)
    if not ok:
        return jsonify({"error": reason}), 409

    base_total = compute_base_total(resource, check_in, check_out, num_guests)

    # Default deposit policy: VILLA requires 30% deposit
    deposit_pct = Decimal("0.30") if resource.resource_type == ResourceType.VILLA.value else Decimal("0")
    deposit_required = (base_total * deposit_pct).quantize(Decimal("0.01"))

    # Guest record auto-match
    guest = get_or_create_guest_record(
        guest_name, guest_phone, data.get("guest_id_number")
    )

    booking = Booking(
        resource_id=resource_id,
        guest_record_id=guest.id,
        guest_name=guest_name,
        guest_phone=guest_phone,
        guest_id_number=data.get("guest_id_number"),
        number_of_guests=num_guests,
        check_in_planned_utc=check_in,
        check_out_planned_utc=check_out,
        base_total=base_total,
        deposit_required=deposit_required,
        notes=data.get("notes"),
        idempotency_key=idem_key,
        created_by_id=actor.id,
    )
    db.session.add(booking)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.create",
                 details=f"{resource.name} {guest_name}")
    db.session.commit()
    return jsonify(_booking_dict(booking)), 201


# ── Confirm (HELD → CONFIRMED) ────────────────────────────────────────────────

@bookings_bp.post("/<booking_id>/confirm")
@require_active_user
def confirm_booking(booking_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    ok, err = transition_booking(booking, BookingStatus.CONFIRMED.value)
    if not ok:
        return jsonify({"error": err}), 400

    # Require deposit if configured
    deposit_paid = get_deposit_total(booking_id)
    if booking.deposit_required > Decimal("0") and deposit_paid < booking.deposit_required:
        return jsonify({
            "error": f"A deposit of {booking.deposit_required} is required to confirm. "
                     f"Recorded so far: {deposit_paid}. Record the deposit first."
        }), 400

    booking.status = BookingStatus.CONFIRMED.value
    booking.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.confirm", target=booking_id)

    # Guest notification — WhatsApp > SMS > logged-only (never blocks the commit)
    try:
        from app.services.notifications.guest_notify import notify_guest, MessageType
        notify_guest(booking.guest_phone, MessageType.BOOKING_CONFIRMED, {
            "resource":   booking.resource.name if booking.resource else "your room",
            "checkin":    booking.check_in_planned_utc.strftime("%Y-%m-%d") if booking.check_in_planned_utc else "TBD",
            "checkout":   booking.check_out_planned_utc.strftime("%Y-%m-%d") if booking.check_out_planned_utc else "TBD",
            "booking_id": booking_id[:8],
        })
    except Exception:
        pass  # notification failure must never block a booking confirmation

    db.session.commit()
    return jsonify(_booking_dict(booking)), 200


# ── Check-in (CONFIRMED → CHECKED_IN, opens Villa tab) ───────────────────────

@bookings_bp.post("/<booking_id>/check-in")
@require_active_user
def check_in(booking_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required to check guests in."}), 403

    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    # Idempotent: already checked in → return current state
    if booking.status == BookingStatus.CHECKED_IN.value:
        return jsonify(_booking_dict(booking, include_balance=True)), 200

    ok, err = transition_booking(booking, BookingStatus.CHECKED_IN.value)
    if not ok:
        return jsonify({"error": err}), 400

    tab = open_villa_tab(booking, actor.id)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.check_in",
                 target=booking_id, details=f"tab={tab.id}")
    db.session.commit()
    return jsonify({**_booking_dict(booking, include_balance=True), "tab_id": tab.id}), 200


# ── Check-out (CHECKED_IN → CHECKED_OUT, closes tab) ─────────────────────────

@bookings_bp.post("/<booking_id>/check-out")
@require_active_user
def check_out(booking_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required to check guests out."}), 403

    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    ok, err = transition_booking(booking, BookingStatus.CHECKED_OUT.value)
    if not ok:
        return jsonify({"error": err}), 400

    if not booking.tab_id:
        return jsonify({"error": "No tab found for this booking."}), 400

    ok, reason = is_tab_closable(booking.tab_id)
    if not ok:
        balance = get_tab_balance(booking.tab_id)
        return jsonify({
            "error": reason,
            "outstanding_balance": str(balance),
        }), 400

    from app.models.tab import Tab, TabStatus
    tab = db.session.get(Tab, booking.tab_id)
    tab.status        = TabStatus.CLOSED.value
    tab.closed_at_utc = datetime.now(timezone.utc)
    tab.closed_by_id  = actor.id

    booking.status              = BookingStatus.CHECKED_OUT.value
    booking.check_out_actual_utc = datetime.now(timezone.utc)
    booking.updated_at_utc      = datetime.now(timezone.utc)

    # Update guest record last visit timestamp
    if booking.guest_record_id:
        from app.models.guest_record import GuestRecord
        gr = db.session.get(GuestRecord, booking.guest_record_id)
        if gr:
            gr.last_visit_utc = datetime.now(timezone.utc)

    # Auto-create a DIRTY cleaning record so housekeeping sees it immediately
    from app.housekeeping import create_dirty_record
    dirty = create_dirty_record(booking.resource_id)

    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.check_out", target=booking_id)
    AuditLog.log(actor="system", action="housekeeping.auto_dirty",
                 target=dirty.id, details=f"checkout of {booking.guest_name}")
    db.session.commit()
    return jsonify(_booking_dict(booking)), 200


# ── Cancel ────────────────────────────────────────────────────────────────────

@bookings_bp.post("/<booking_id>/cancel")
@require_active_user
def cancel_booking(booking_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    ok, err = transition_booking(booking, BookingStatus.CANCELLED.value)
    if not ok:
        return jsonify({"error": err}), 400

    booking.status = BookingStatus.CANCELLED.value
    booking.updated_at_utc = datetime.now(timezone.utc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.cancel", target=booking_id)
    db.session.commit()
    return jsonify(_booking_dict(booking)), 200


# ── List & availability ────────────────────────────────────────────────────────

@bookings_bp.get("")
@require_active_user
def list_bookings():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    resource_id = request.args.get("resource_id")
    status      = (request.args.get("status") or "").upper() or None
    date_str    = request.args.get("date")

    q = (request.args.get("q") or "").strip()

    query = db.session.query(Booking)
    if not include_disabled:
        query = query.filter(Booking.status != BookingStatus.CANCELLED.value)
    if q:
        query = query.filter(Booking.guest_name.ilike(f"%{q}%"))
    if resource_id:
        query = query.filter_by(resource_id=resource_id)
    if status:
        query = query.filter_by(status=status)
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "date must be YYYY-MM-DD."}), 400
        day_end = d + timedelta(days=1)
        query = query.filter(
            Booking.check_in_planned_utc >= d,
            Booking.check_in_planned_utc < day_end,
        )

    bookings = query.order_by(Booking.check_in_planned_utc).all()
    return jsonify([_booking_dict(b) for b in bookings]), 200


@bookings_bp.get("/availability")
@require_active_user
def check_availability():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    rtype  = (request.args.get("resource_type") or "").upper() or None
    from_s = request.args.get("from")
    to_s   = request.args.get("to")

    if not from_s or not to_s:
        return jsonify({"error": "from and to query params are required (ISO 8601)."}), 400

    from_dt = _parse_dt(from_s)
    to_dt   = _parse_dt(to_s)
    if not from_dt or not to_dt:
        return jsonify({"error": "from and to must be ISO 8601."}), 400

    query = db.session.query(BookableResource).filter_by(is_active=True)
    if rtype:
        query = query.filter_by(resource_type=rtype)

    result = []
    for r in query.all():
        available, _ = check_resource_availability(r.id, from_dt, to_dt)
        result.append({
            "id":            r.id,
            "name":          r.name,
            "resource_type": r.resource_type,
            "base_price":    str(r.base_price),
            "capacity":      r.capacity,
            "available":     available,
        })
    return jsonify(result), 200


@bookings_bp.get("/today")
@require_active_user
def today_bookings():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    today     = datetime.now(timezone.utc).date()
    day_start = datetime(today.year, today.month, today.day)
    day_end   = day_start + timedelta(days=1)

    arrivals = db.session.query(Booking).filter(
        Booking.check_in_planned_utc  >= day_start,
        Booking.check_in_planned_utc  < day_end,
        Booking.status.in_([BookingStatus.CONFIRMED.value, BookingStatus.HELD.value]),
    ).all()

    departures = db.session.query(Booking).filter(
        Booking.check_out_planned_utc >= day_start,
        Booking.check_out_planned_utc < day_end,
        Booking.status == BookingStatus.CHECKED_IN.value,
    ).all()

    occupancy = db.session.query(Booking).filter(
        Booking.status == BookingStatus.CHECKED_IN.value,
    ).all()

    return jsonify({
        "arrivals":   [_booking_dict(b) for b in arrivals],
        "departures": [_booking_dict(b, include_balance=True) for b in departures],
        "occupancy":  [_booking_dict(b, include_balance=True) for b in occupancy],
    }), 200


# ── Water-activity session (waiver gate) ──────────────────────────────────────

@bookings_bp.post("/<booking_id>/water-sessions")
@require_active_user
def book_water_session(booking_id):
    """
    Post a water-activity charge to the booking's tab.
    Blocked if no active WATER_ACTIVITY waiver exists for this booking.
    """
    from app.models.charge import Charge
    from app.services.tax import get_vat_rate
    from app.services.booking import has_active_waiver
    from decimal import Decimal

    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404
    if booking.status != BookingStatus.CHECKED_IN.value:
        return jsonify({"error": "Booking must be CHECKED_IN to add water sessions."}), 400
    if not booking.tab_id:
        return jsonify({"error": "No tab found for this booking."}), 400

    # Waiver gate
    if not has_active_waiver(booking_id, "WATER_ACTIVITY"):
        return jsonify({
            "error": "This guest has not signed the water-activity waiver. "
                     "Please collect a signed waiver before the session."
        }), 403

    data        = request.get_json(silent=True) or {}
    resource_id = data.get("resource_id")
    description = (data.get("description") or "Water activity session").strip()

    resource = db.session.get(BookableResource, resource_id) if resource_id else None
    if resource_id and (not resource or not resource.is_active):
        return jsonify({"error": "Water-activity resource not found or disabled."}), 404

    amount = resource.base_price if resource else data.get("amount")
    if amount is None:
        return jsonify({"error": "resource_id or amount is required."}), 400
    try:
        amount = Decimal(str(amount))
    except Exception:
        return jsonify({"error": "amount must be a number."}), 400

    # A charge may not be negative. models/charge.py states the invariant
    # outright: "No API accepts an arbitrary negative amount — that would be the
    # skim vector the judge watches." This endpoint took the amount straight
    # from the request body and only checked that it parsed, so a single call
    # with {"amount": "-14000"} wiped a guest's outstanding balance to zero —
    # with NO Payment row written, so cash reconciliation saw nothing missing
    # and check-out then succeeded. Reachable at front-desk level: an insider
    # vector, which is exactly the kind this system exists to close.
    #
    # Corrections go through the reversal path, which mirrors an EXISTING charge
    # and keeps its tax_rate_snapshot. They are never free-typed.
    #
    # is_finite() comes FIRST because Decimal('NaN') <= 0 does not return False,
    # it raises InvalidOperation — an unhandled 500 instead of a plain-English
    # 400. Same order as app/pos/payments.py:43, which had it right already.
    if not amount.is_finite() or amount <= 0:
        return jsonify({
            "error": "A session charge must be a positive amount. "
                     "To correct or refund a charge, reverse the original."
        }), 400

    # Band-tab credit ceiling: block if this charge would exceed 2× the entry fee
    ok, credit_err = check_band_credit(booking.tab_id, amount)
    if not ok:
        return jsonify({"error": credit_err}), 400

    charge = Charge(
        tab_id=booking.tab_id,
        amount=amount,
        description=description,
        created_by_id=actor.id,
        tax_rate_snapshot=get_vat_rate(),
    )
    db.session.add(charge)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.water_session",
                 target=booking_id, details=f"amount={amount}")
    db.session.commit()
    return jsonify({"charge_id": charge.id, "amount": str(amount)}), 201


# ── Occupants: who else is actually in the villa ─────────────────────────────
#
# Booking stores one name and number_of_guests as an integer, so five of the six
# people in Villa 6 existed only as part of that number. These endpoints give
# them names, and give front desk a way to answer "may this person charge here?"

from app.models.booking_occupant import BookingOccupant


def _occupant_dict(o: BookingOccupant) -> dict:
    return {
        "id":         o.id,
        "full_name":  o.full_name,
        "id_number":  o.id_number,
        "phone":      o.phone,
        "is_adult":   o.is_adult,
        "may_charge": o.may_charge,
        "checked_out_utc": o.checked_out_utc.isoformat() if o.checked_out_utc else None,
    }


@bookings_bp.get("/<booking_id>/occupants")
@require_active_user
def list_occupants(booking_id):
    """Everyone on file for this booking. Any staff member serving the guest may
    read this — it is how a waiter checks whether the person at the bar is
    entitled to charge the villa."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404
    rows = db.session.query(BookingOccupant).filter_by(booking_id=booking_id).all()
    return jsonify({
        "booking_id":       booking.id,
        "lead_guest":       booking.guest_name,
        "lead_id_number":   booking.guest_id_number,
        "number_of_guests": booking.number_of_guests,
        "occupants":        [_occupant_dict(o) for o in rows],
        # The number on the booking vs the names actually recorded. Front desk
        # can see at a glance that four people are unaccounted for.
        "unnamed_count":    max(0, (booking.number_of_guests or 1) - 1 - len(rows)),
    }), 200


@bookings_bp.post("/<booking_id>/occupants")
@require_active_user
def add_occupant(booking_id):
    """Record a companion. Front desk and above — this is check-in work."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Front desk or above required to register a guest."}), 403

    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Booking not found."}), 404

    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        return jsonify({"error": "A name is required — that is the point of the register."}), 400

    # Guard against listing more people than the villa was booked for. The
    # capacity check on the booking already happened; this keeps the register
    # honest against it rather than silently exceeding it.
    already = db.session.query(BookingOccupant).filter_by(booking_id=booking_id).count()
    if already + 1 >= (booking.number_of_guests or 1) + 1:
        return jsonify({
            "error": f"This booking is for {booking.number_of_guests} guest(s), "
                     f"including {booking.guest_name}. Raise the guest count on the "
                     f"booking before adding more people."
        }), 400

    occupant = BookingOccupant(
        booking_id=booking_id,
        full_name=full_name,
        id_number=(data.get("id_number") or "").strip() or None,
        phone=(data.get("phone") or "").strip() or None,
        is_adult=bool(data.get("is_adult", True)),
        may_charge=bool(data.get("may_charge", False)),
    )
    db.session.add(occupant)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="booking.occupant.add",
                 target=booking_id, details=f"{full_name}"
                 + (" (may charge)" if occupant.may_charge else ""))
    db.session.commit()
    return jsonify(_occupant_dict(occupant)), 201


@bookings_bp.patch("/<booking_id>/occupants/<occupant_id>")
@require_active_user
def edit_occupant(booking_id, occupant_id):
    """Correct a name, add an ID that was fetched from the car, or grant/revoke
    charging rights. Charging rights are the sensitive part, so they are logged
    explicitly rather than as a generic edit."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Front desk or above required."}), 403

    o = db.session.get(BookingOccupant, occupant_id)
    if not o or o.booking_id != booking_id:
        return jsonify({"error": "Occupant not found on this booking."}), 404

    data = request.get_json(silent=True) or {}
    changes = []
    if "full_name" in data and data["full_name"].strip():
        changes.append(f"name {o.full_name!r} -> {data['full_name'].strip()!r}")
        o.full_name = data["full_name"].strip()
    if "id_number" in data:
        o.id_number = (data["id_number"] or "").strip() or None
        changes.append("id_number recorded" if o.id_number else "id_number cleared")
    if "phone" in data:
        o.phone = (data["phone"] or "").strip() or None
    if "may_charge" in data:
        new_val = bool(data["may_charge"])
        if new_val != o.may_charge:
            changes.append(f"may_charge {o.may_charge} -> {new_val}")
        o.may_charge = new_val

    AuditLog.log(actor=actor.username, action="booking.occupant.edit",
                 target=occupant_id, details="; ".join(changes) or "no effective change")
    db.session.commit()
    return jsonify(_occupant_dict(o)), 200
