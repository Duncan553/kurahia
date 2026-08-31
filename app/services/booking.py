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
from app.models.payment import Payment
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

    # ── Anyone still physically in the room blocks it, whatever the calendar says.
    #
    # The overlap test above compares PLANNED dates. A guest who was due out on
    # the 28th but has not checked out is CHECKED_IN with a planned check-out in
    # the past, so they fall outside every future window and the villa reads as
    # free. Front desk could then sell an occupied room — found live: Villa 4
    # held two open accounts at once, PW Guest 96604 (due out 28 Aug, never
    # checked out) and a new arrival.
    #
    # A room is free when the person has LEFT, not when the diary says they
    # should have. Overstays are ordinary — late flights, extended stays — so
    # this is not an edge case.
    if not conflict:
        conflict = (
            db.session.query(Booking)
            .filter(Booking.resource_id == resource_id,
                    Booking.status == BookingStatus.CHECKED_IN.value,
                    Booking.check_out_actual_utc.is_(None),
                    Booking.check_out_planned_utc <= check_out)
            .filter(Booking.id != exclude_booking_id if exclude_booking_id else True)
            .first()
        )
        if conflict:
            from app.models.bookable_resource import BookableResource
            resource = db.session.get(BookableResource, resource_id)
            name = resource.name if resource else resource_id
            return False, (
                f"{name} is still occupied — {conflict.guest_name} was due out on "
                f"{conflict.check_out_planned_utc.strftime('%d %b %Y')} and has not "
                f"checked out. Check them out first, or extend their booking."
            )
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


def transfer_deposit_to_tab(booking: Booking, tab: Tab, _actor_id: str) -> None:
    """
    Attach the deposit the guest ALREADY paid to the villa tab, so it counts
    against the room charge.

    This does NOT create a new Payment. It re-points the existing deposit
    Payment rows at the tab.

    WHY (this used to be a real double-count). The deposit is collected at
    booking time, before any tab exists, so its Payment lands with tab_id=NULL.
    The old code then wrote a SECOND Payment for the same money to get it onto
    the tab. Tab balance was right, but every revenue reader sums Payment rows
    with no filter (app/services/finance.py:get_period_revenue_by_method, the
    daily-summary PDF, app/finance/reports.py) — so one KSh 6,000 deposit was
    reported as KSh 12,000 taken that day.

    One movement of money, one row. No amount, method, or timestamp is ever
    rewritten — only a foreign key that was NULL because the tab did not exist
    yet. Balances stay derived; the ledger stays append-only where it counts.

    Bonus: the real payment method (M-PESA, card) now survives onto the tab.
    The old credit row hard-coded CASH, which quietly skewed revenue-by-method.
    """
    # The DEPOSIT BookingPayment rows for this booking, and the Payments behind them.
    bps = db.session.query(BookingPayment).filter_by(
        booking_id=booking.id,
        purpose=BookingPaymentPurpose.DEPOSIT.value,
    ).all()

    for bp in bps:
        payment = db.session.get(Payment, bp.payment_id)
        if payment is None:
            continue
        # Already on this tab: a re-run must not move anything. Naturally
        # idempotent — no key needed, unlike the old insert.
        if payment.tab_id == tab.id:
            continue
        # Attached to some OTHER tab: never silently steal it. Should be
        # unreachable (a deposit belongs to one booking, which owns one tab).
        if payment.tab_id is not None:
            continue
        payment.tab_id = tab.id

    db.session.flush()


# ── Check-in / check-out ──────────────────────────────────────────────────────

def charge_accommodation_to_tab(booking: Booking, tab: Tab, actor_id: str) -> None:
    """Put the ROOM on the villa tab.

    THE HOLE THIS CLOSES. base_total is computed at booking time and stored on
    the BOOKING. Nothing ever wrote it to the tab, so a villa tab was only ever
    an incidentals account: it received the deposit as a credit and the guest's
    drinks as charges, and the accommodation itself — the entire reason they are
    here — was invisible to it.

    Measured on a real booking before this existed:

        room               KSh 200,000
        deposit collected  KSh  60,000
        bar                KSh   2,500
        tab balance        KSh -57,500   -> read as CREDIT
        is_tab_closable    True          -> CHECK-OUT ALLOWED

    So a guest paid 30% and could walk out owing 142,500 with the door held
    open, while reports/routes.py counted the full 200,000 as villa revenue.
    Two wrong numbers pointing opposite ways, neither visibly contradicting the
    other.

    Charged at CHECK-IN, not at booking: a HELD booking that never arrives must
    not leave a charge behind. Append-only and idempotent on the booking id, so
    a repeated check-in cannot double-charge the room.
    """
    from app.models.charge import Charge
    from app.services.tax import rate_for_menu_item

    total = Decimal(str(booking.base_total or 0))
    if total <= Decimal("0"):
        return

    # Charge has no idempotency_key column, so the guard is a lookup for an
    # accommodation line already on this tab. One villa tab belongs to exactly
    # one booking, so that is sufficient — and the booking state machine already
    # refuses a second CHECKED_IN transition. Belt and braces, cheaply.
    already = (
        db.session.query(Charge)
        .filter(Charge.tab_id == tab.id,
                Charge.description.like("Accommodation —%"))
        .first()
    )
    if already:
        return

    nights = 0
    if booking.check_in_planned_utc and booking.check_out_planned_utc:
        nights = max(1, (booking.check_out_planned_utc.date()
                         - booking.check_in_planned_utc.date()).days)
    resource_name = booking.resource.name if booking.resource else "Villa"

    db.session.add(Charge(
        tab_id=tab.id,
        amount=total,
        description=(f"Accommodation — {resource_name}"
                     + (f", {nights} night{'s' if nights != 1 else ''}" if nights else "")),
        created_by_id=actor_id,
        # Same treatment as every other line: the rate is frozen at the moment
        # the charge is made, so a later statutory change cannot rewrite history.
        tax_rate_snapshot=rate_for_menu_item(None),
    ))
    db.session.flush()


def open_villa_tab(booking: Booking, actor_id: str) -> Tab:
    """Open a VILLA tab for this booking, charge the room, credit the deposit."""
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

    # Order matters for readability of the folio: the room first, then what
    # has already been paid against it.
    charge_accommodation_to_tab(booking, tab, actor_id)
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
