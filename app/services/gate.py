"""
services/gate.py — Gate & wristband domain logic.

Key design decisions baked in:
- 1 band = 1 customer, 1 entry payment, 1 BAND tab.
- Entry Payment IS the tab credit (tab_id set immediately) → one record, not two.
- Forfeit = close tab, no refund. No exceptions.
- allocate_band_number() uses a row-level lock + DB unique constraint as belt-and-braces.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.wristband import Wristband, WristbandStatus
from app.models.wristband_counter import WristbandCounter
from app.models.gate_entry import GateEntry
from app.models.gate_headcount import GateHeadcount
from app.models.tab import Tab, TabType, TabStatus
from app.models.payment import Payment, PaymentMethod
from app.models.judge_alert import JudgeAlert, AlertSeverity, AlertStatus
from app.services.judge_alerts import fire_alert_if_absent

ENTRY_FEE = Decimal("3000")


# ── Band number allocation ────────────────────────────────────────────────────

def allocate_band_number(issue_date_str: str) -> int:
    """
    Atomically allocate the next band number for this day.
    with_for_update() serialises concurrent requests; the UniqueConstraint
    on (band_number, issue_date) is the DB-level safety net.
    """
    counter = (
        db.session.query(WristbandCounter)
        .with_for_update()
        .filter_by(issue_date=issue_date_str)
        .first()
    )
    if counter is None:
        counter = WristbandCounter(issue_date=issue_date_str, next_number=2)
        db.session.add(counter)
        db.session.flush()
        return 1
    number = counter.next_number
    counter.next_number = number + 1
    db.session.flush()
    return number


# ── Tab creation ──────────────────────────────────────────────────────────────

def open_band_tab(band_number: int, actor_id: str,
                  method: str, mpesa_code: str | None, card_ref: str | None,
                  tab_idem_key: str) -> tuple["Tab", "Payment"]:
    """
    Create the BAND tab and write the 3,000 entry fee as a credit Payment on it.
    The single Payment record both settles the physical cash and starts the tab
    with a -3,000 balance (credit the guest can spend). One record, no duplication.
    """
    tab = Tab(
        tab_type=TabType.BAND.value,
        reference=f"Band #{band_number}",
        opened_by_id=actor_id,
        status=TabStatus.OPEN.value,
    )
    db.session.add(tab)
    db.session.flush()

    credit = Payment(
        tab_id=tab.id,
        amount=ENTRY_FEE,
        method=method,
        mpesa_code=mpesa_code,
        card_ref=card_ref,
        description=f"Entry fee — band #{band_number}",
        received_by_id=actor_id,
        idempotency_key=tab_idem_key,
    )
    db.session.add(credit)
    db.session.flush()
    return tab, credit


# ── Band issuance ─────────────────────────────────────────────────────────────

def issue_band(actor_id: str, method: str, mpesa_code: str | None,
               card_ref: str | None, idem_key: str,
               notes: str | None = None) -> Wristband:
    """
    Full atomic issuance: allocate number → open tab → record payment → create Wristband.
    Idempotent on idem_key.
    """
    # Idempotency check
    existing = db.session.query(Wristband).filter_by(idempotency_key=idem_key).first()
    if existing:
        return existing

    today = datetime.now(timezone.utc).date().isoformat()
    band_number = allocate_band_number(today)

    tab, credit = open_band_tab(
        band_number=band_number,
        actor_id=actor_id,
        method=method,
        mpesa_code=mpesa_code,
        card_ref=card_ref,
        tab_idem_key=f"gate-credit-{idem_key}",
    )

    band = Wristband(
        band_number=band_number,
        issue_date=today,
        issued_by_id=actor_id,
        entry_payment_id=credit.id,
        tab_id=tab.id,
        notes=notes,
        idempotency_key=idem_key,
    )
    db.session.add(band)
    db.session.flush()

    entry = GateEntry(
        wristband_id=band.id,
        head_count=1,
        created_by_id=actor_id,
    )
    db.session.add(entry)
    db.session.flush()
    return band


# ── Deactivation / forfeit ────────────────────────────────────────────────────

def close_band(band: Wristband, actor_id: str,
               new_status: str, reason: str | None = None) -> None:
    """
    Close a band: set status, close its tab. Used for both DEACTIVATED and FORFEITED.
    Unused credit is forfeit — no refund logic exists or will be added.
    """
    from app.services.tab import get_tab_balance
    band.status = new_status
    band.deactivated_at_utc = datetime.now(timezone.utc)
    band.deactivated_by_id = actor_id
    if reason:
        band.notes = (band.notes or "") + f" | {reason}"

    tab = db.session.get(Tab, band.tab_id)
    if tab and tab.status == TabStatus.OPEN.value:
        tab.status        = TabStatus.CLOSED.value
        tab.closed_at_utc = datetime.now(timezone.utc)
        tab.closed_by_id  = actor_id

    db.session.flush()


def forfeit_day(date_str: str, actor_id: str) -> tuple[int, Decimal]:
    """
    EOD sweep: flip all ACTIVE bands for the given date to FORFEITED and close their tabs.
    Returns (count_forfeited, total_unused_credit).
    """
    from app.services.tab import get_tab_balance
    bands = db.session.query(Wristband).filter_by(
        issue_date=date_str,
        status=WristbandStatus.ACTIVE.value,
    ).all()
    count = 0
    total_unused = Decimal("0")
    for band in bands:
        balance = get_tab_balance(band.tab_id)
        # balance < 0 means credit remaining (unused portion of entry fee)
        if balance < Decimal("0"):
            total_unused += abs(balance)
        close_band(band, actor_id, WristbandStatus.FORFEITED.value, "EOD forfeit")
        count += 1
    return count, total_unused


# ── Lookups ───────────────────────────────────────────────────────────────────

def get_band_by_number(band_number: int, date_str: str | None = None) -> Wristband | None:
    """Look up an ACTIVE band by number. date_str defaults to today."""
    today = date_str or datetime.now(timezone.utc).date().isoformat()
    return db.session.query(Wristband).filter_by(
        band_number=band_number,
        issue_date=today,
        status=WristbandStatus.ACTIVE.value,
    ).first()


def get_active_bands(date_str: str | None = None) -> list[Wristband]:
    today = date_str or datetime.now(timezone.utc).date().isoformat()
    return db.session.query(Wristband).filter_by(
        issue_date=today,
        status=WristbandStatus.ACTIVE.value,
    ).order_by(Wristband.band_number).all()


# ── Reconciliation ────────────────────────────────────────────────────────────

def get_reconciliation(date_str: str) -> dict:
    """
    Gate revenue truth-check for the day.
    bands_issued × ENTRY_FEE must equal sum(entry_payments).
    Mismatch → flag to owner.
    """
    bands = db.session.query(Wristband).filter_by(issue_date=date_str).all()
    bands_issued = len(bands)

    entry_payment_ids = [b.entry_payment_id for b in bands]
    if entry_payment_ids:
        total = db.session.query(func.sum(Payment.amount)).filter(
            Payment.id.in_(entry_payment_ids)
        ).scalar()
        gate_revenue = Decimal(str(total)) if total is not None else Decimal("0")
    else:
        gate_revenue = Decimal("0")

    expected = ENTRY_FEE * bands_issued
    mismatch = gate_revenue != expected

    # Independent headcount cross-check
    hc = db.session.query(GateHeadcount).filter_by(count_date=date_str).first()
    headcount_mismatch = hc and hc.counted > bands_issued

    return {
        "date":               date_str,
        "bands_issued":       bands_issued,
        "gate_revenue":       str(gate_revenue),
        "expected_revenue":   str(expected),
        "mismatch":           mismatch,
        "headcount_recorded": hc.counted if hc else None,
        "headcount_mismatch": headcount_mismatch,
    }


# ── Judge signals ─────────────────────────────────────────────────────────────

def check_gate_signals(date_str: str) -> int:
    """
    Fire JudgeAlerts for gate theft signals. Returns count of alerts raised.
    Signal 1: gate revenue ≠ bands_issued × 3,000
    Signal 2: a gate staff member's forfeit rate is ≥ 3× the day average
    """
    alerts_fired = 0
    now = datetime.now(timezone.utc)

    recon = get_reconciliation(date_str)

    # Signal 1 — revenue mismatch
    if recon["mismatch"]:
        _, created = fire_alert_if_absent(
            alert_type="GATE_REVENUE_MISMATCH",
            description_key=f"Gate revenue mismatch on {date_str}",
            item_id=None,
            severity=AlertSeverity.HIGH.value,
            description=(
                f"Gate revenue mismatch on {date_str}: "
                f"{recon['bands_issued']} bands issued (expected {recon['expected_revenue']} KSh) "
                f"but {recon['gate_revenue']} KSh collected."
            ),
            period_start=now,
            period_end=now,
        )
        if created:
            alerts_fired += 1

    # Signal 1b — headcount mismatch
    if recon["headcount_mismatch"]:
        _, created = fire_alert_if_absent(
            alert_type="GATE_HEADCOUNT_MISMATCH",
            description_key=f"Headcount mismatch on {date_str}",
            item_id=None,
            severity=AlertSeverity.HIGH.value,
            description=(
                f"Headcount mismatch on {date_str}: "
                f"physical counter saw {recon['headcount_recorded']} people "
                f"but only {recon['bands_issued']} bands were issued. "
                "Someone may have entered without paying."
            ),
            period_start=now,
            period_end=now,
        )
        if created:
            alerts_fired += 1

    # Signal 2 — per-staff forfeit rate anomaly
    bands = db.session.query(Wristband).filter_by(issue_date=date_str).all()
    if not bands:
        return alerts_fired

    total_bands = len(bands)
    total_forfeited = sum(1 for b in bands if b.status == WristbandStatus.FORFEITED.value)
    if total_bands == 0:
        return alerts_fired

    avg_rate = total_forfeited / total_bands

    # Group by issuer
    by_staff: dict[str, dict] = {}
    for b in bands:
        sid = b.issued_by_id
        if sid not in by_staff:
            by_staff[sid] = {"total": 0, "forfeited": 0}
        by_staff[sid]["total"] += 1
        if b.status == WristbandStatus.FORFEITED.value:
            by_staff[sid]["forfeited"] += 1

    for staff_id, counts in by_staff.items():
        if counts["total"] < 3:  # too small a sample to flag
            continue
        staff_rate = counts["forfeited"] / counts["total"]
        if avg_rate > 0 and staff_rate >= avg_rate * 3:
            from app.models.user import User
            staff_user = db.session.get(User, staff_id)
            name = staff_user.username if staff_user else staff_id
            _, created = fire_alert_if_absent(
                alert_type="GATE_FORFEIT_ANOMALY",
                description_key=f"Gate staff {name}",
                item_id=None,
                severity=AlertSeverity.MEDIUM.value,
                description=(
                    f"Gate staff {name} has an unusually high band forfeit rate on {date_str}: "
                    f"{counts['forfeited']}/{counts['total']} ({staff_rate:.0%}) vs "
                    f"day average of {avg_rate:.0%}."
                ),
                period_start=now,
                period_end=now,
            )
            if created:
                alerts_fired += 1

    db.session.flush()
    return alerts_fired
