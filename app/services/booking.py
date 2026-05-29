"""
services/booking.py — Booking domain logic.

All derived calculations live here; routes stay thin.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.models.booking import Booking, BookingStatus, VALID_BOOKING_TRANSITIONS
from app.models.bookable_resource import ResourceType
from app.models.booking_payment import BookingPayment, BookingPaymentPurpose
from app.models.payment import Payment, PaymentMethod
from app.models.tab import Tab, TabType, TabStatus
from app.models.waiver import Waiver, WaiverActivityType
from app.models.guest_record import GuestRecord


# ── Resource / date helpers ───────────────────────────────────────────────────

def compute_base_total(resource, check_in: datetime, check_out: datetime,
                       num_guests: int) -> Decimal:
    """Snapshot price at booking time. Villas: per night; others: per session."""
    price = Decimal(str(resource.base_price))
    if resource.resource_type == ResourceType.VILLA.value:
        nights = max((check_out.date() - check_in.date()).days, 1)
        return price * nights
    return price   # flat session rate for activities / event venue


def check_resource_availability(resource_id: str, check_in: datetime, check_out: datetime,
                                 exclude_booking_id: str | None = None) -> tuple[bool, str]:
    """
    Returns (True, "") if the resource is free, or (False, plain-English reason).
    Overlap condition: existing.check_in < new.check_out AND existing.check_out > new.check_in
    """
    blocking_statuses = {
        BookingStatus.HELD.value,
        BookingStatus.CONFIRMED.value,
        BookingStatus.CHECKED_IN.value,
    }
    query = db.session.query(Booking).filter(
        Booking.resource_id == resource_id,
        Booking.status.in_(blocking_statuses),
        Booking.check_in_planned_utc  < check_out,
        Booking.check_out_planned_utc > check_in,
    )
    if exclude_booking_id:
        query = query.filter(Booking.id != exclude_booking_id)

    conflict = query.first()
    if conflict:
        fmt = "%d %b %Y"
        from app.models.bookable_resource import BookableResource
        resource = db.session.get(BookableResource, resource_id)
        name = resource.name if resource else resource_id
        ci = conflict.check_in_planned_utc
        co = conflict.check_out_planned_utc
        if ci.tzinfo is None:
            ci = ci.replace(tzinfo=timezone.utc)
        if co.tzinfo is None:
            co = co.replace(tzinfo=timezone.utc)
        return False, (
            f"{name} is already booked from {ci.strftime(fmt)} to {co.strftime(fmt)}. "
            "Please pick another resource or different dates."
        )
    return True, ""


def check_capacity(resource, num_guests: int) -> tuple[bool, str]:
    """For resources with a capacity limit, enforce it."""
    if resource.capacity and num_guests > resource.capacity:
        return False, (
            f"{resource.name} holds up to {resource.capacity} guests, "
            f"but {num_guests} were requested."
        )
    return True, ""


# ── Booking state machine ─────────────────────────────────────────────────────

def transition_booking(booking: Booking, new_status: str) -> tuple[bool, str]:
    """Enforce state machine. Returns (ok, error_message)."""
    allowed = VALID_BOOKING_TRANSITIONS.get(booking.status, set())
    if new_status not in allowed:
        return False, (
            f"Cannot move booking from {booking.status} to {new_status}. "
            f"Allowed next states: {sorted(allowed) or 'none (terminal state)'}."
        )
    return True, ""


# ── Guest records ─────────────────────────────────────────────────────────────

def get_or_create_guest_record(name: str, phone: str,
                                id_number: str | None = None) -> GuestRecord:
    """Auto-match by phone; create new record if phone not seen before."""
    existing = db.session.query(GuestRecord).filter_by(phone=phone).first()
    if existing:
        return existing
    guest = GuestRecord(name=name, phone=phone, id_number=id_number)
    db.session.add(guest)
    db.session.flush()   # get id without committing
    return guest


# ── Deposit transfer ──────────────────────────────────────────────────────────

def get_deposit_total(booking_id: str) -> Decimal:
    """Sum of all DEPOSIT BookingPayments for this booking."""
    bps = db.session.query(BookingPayment).filter_by(
        booking_id=booking_id,
        purpose=BookingPaymentPurpose.DEPOSIT.value,
    ).all()
    total = Decimal("0")
    for bp in bps:
        p = db.session.get(Payment, bp.payment_id)
        if p:
            total += Decimal(str(p.amount))
    return total


def transfer_deposit_to_tab(booking: Booking, tab: Tab, actor_id: str) -> None:
    """
    Creates a credit Payment on the villa tab for the total deposits collected.
    Append-only: original BookingPayment records are unchanged.
    """
    total = get_deposit_total(booking.id)
    if total <= Decimal("0"):
        return

    # A credit payment: the guest already paid this; it reduces the tab balance.
    credit = Payment(
        tab_id=tab.id,
        amount=total,
        method=PaymentMethod.CASH.value,   # generic — actual method is on the original Payment
        description=f"Deposit transferred from booking {booking.id[:8]}",
        received_by_id=actor_id,
        idempotency_key=f"deposit-transfer-{booking.id}",
    )
    db.session.add(credit)
    db.session.flush()


# ── Check-in / check-out ──────────────────────────────────────────────────────

def open_villa_tab(booking: Booking, actor_id: str) -> Tab:
    """Open a VILLA tab for this booking and transfer deposit as a credit."""
    resource_name = booking.resource.name if booking.resource else "Villa"
    tab = Tab(
        tab_type=TabType.VILLA.value,
        reference=f"{resource_name} / {booking.guest_name}",
        opened_by_id=actor_id,
        status=TabStatus.OPEN.value,
    )
    db.session.add(tab)
    db.session.flush()

    booking.tab_id = tab.id
    booking.status = BookingStatus.CHECKED_IN.value
    booking.check_in_actual_utc = datetime.now(timezone.utc)

    transfer_deposit_to_tab(booking, tab, actor_id)
    return tab


# ── No-show / hold expiry sweeps ──────────────────────────────────────────────

def flag_no_shows(now: datetime | None = None) -> int:
    """
    Flip HELD/CONFIRMED bookings to NO_SHOW if planned check-in has passed.
    Returns count of records updated.
    """
    now = now or datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)
    candidates = db.session.query(Booking).filter(
        Booking.status.in_([BookingStatus.HELD.value, BookingStatus.CONFIRMED.value]),
    ).all()
    count = 0
    for b in candidates:
        ci = b.check_in_planned_utc
        if ci and ci.tzinfo is not None:
            ci = ci.replace(tzinfo=None)
        if ci and ci < now_naive:
            b.status = BookingStatus.NO_SHOW.value
            b.updated_at_utc = now
            count += 1
    return count


def release_expired_holds(window_hours: int = 24, now: datetime | None = None) -> int:
    """
    Auto-cancel HELD bookings whose created_at is older than window_hours.
    No deposit exists for HELD bookings so no refund logic needed.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    cutoff_naive = cutoff.replace(tzinfo=None)
    candidates = db.session.query(Booking).filter(
        Booking.status == BookingStatus.HELD.value,
    ).all()
    count = 0
    for b in candidates:
        created = b.created_at_utc
        if created and created.tzinfo is not None:
            created = created.replace(tzinfo=None)
        if created and created < cutoff_naive:
            b.status = BookingStatus.CANCELLED.value
            b.updated_at_utc = now
            count += 1
    return count


# ── Waiver check ──────────────────────────────────────────────────────────────

def has_active_waiver(booking_id: str, activity_type: str) -> bool:
    """True if an active waiver exists for this booking and activity type."""
    return db.session.query(Waiver).filter_by(
        booking_id=booking_id,
        activity_type=activity_type,
        is_active=True,
    ).first() is not None
