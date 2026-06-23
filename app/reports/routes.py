"""
reports/routes.py — Three PDF export endpoints.

GET /reports/receipt/<tab_id>                         — receipt for a closed tab
GET /reports/daily-summary?date=YYYY-MM-DD            — daily operations summary
GET /reports/occupancy?from=YYYY-MM-DD&to=YYYY-MM-DD  — villa occupancy report

All require JWT auth. Receipt is available to front-desk+ (level 3).
Daily summary and occupancy are owner-only (level 10).
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import func
from reportlab.lib.units import mm

from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.tab import Tab, TabStatus
from app.models.charge import Charge
from app.models.payment import Payment, PaymentMethod
from app.models.shift import Shift, ShiftStatus
from app.models.wristband import Wristband
from app.models.gate_entry import GateEntry
from app.models.inventory_item import InventoryItem
from app.models.stock_movement import StockMovement
from app.models.booking import Booking, BookingStatus
from app.models.bookable_resource import BookableResource, ResourceType
from app.services.tab import get_tab_balance
from app.services.finance import parse_date_bounds
from app.services.stock import get_current_stock

from .pdf_helpers import (
    new_pdf_buffer, finalize_pdf, draw_header, draw_table_header,
    draw_row, draw_right_aligned, draw_divider, draw_section_title,
    draw_kv, check_page_break,
    MARGIN, PAGE_W, PAGE_H, CONTENT_W, LINE_H,
)

pdf_reports_bp = Blueprint("pdf_reports", __name__, url_prefix="/reports")

FRONT_DESK_LEVEL = 3
OWNER_LEVEL = 10


def _pdf_response(pdf_bytes: bytes, filename: str):
    """Wrap raw PDF bytes in a Flask response with correct headers."""
    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


# ── Receipt PDF ──────────────────────────────────────────────────────────────

@pdf_reports_bp.get("/receipt/<tab_id>")
@require_active_user
def receipt_pdf(tab_id: str):
    """Generate a PDF receipt for a closed tab."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Front desk or above required."}), 403

    tab = db.session.get(Tab, tab_id)
    if not tab:
        return jsonify({"error": "Tab not found."}), 404
    if tab.status != TabStatus.CLOSED.value:
        return jsonify({"error": "Receipt is only available for closed tabs."}), 400

    # Fetch charges and payments for this tab
    charges = db.session.query(Charge).filter_by(tab_id=tab_id).order_by(Charge.created_at).all()
    payments = db.session.query(Payment).filter_by(tab_id=tab_id).order_by(Payment.created_at_utc).all()
    total_charges = sum(Decimal(str(c.amount)) for c in charges)
    total_payments = sum(Decimal(str(p.amount)) for p in payments)
    balance = get_tab_balance(tab_id)

    # Build PDF
    buf, c = new_pdf_buffer()

    # Reference line for subtitle
    ref = tab.reference or f"Tab #{tab_id[:8]}"
    opened = tab.opened_at_utc.strftime("%Y-%m-%d %H:%M") if tab.opened_at_utc else "—"
    closed = tab.closed_at_utc.strftime("%Y-%m-%d %H:%M") if tab.closed_at_utc else "—"

    y = PAGE_H - MARGIN
    y = draw_header(c, y, "Receipt", f"{ref}  |  Opened: {opened}  |  Closed: {closed}")

    # Tab info
    y = draw_kv(c, y, "Server", tab.opened_by.username if tab.opened_by else "—")
    y = draw_kv(c, y, "Type", tab.tab_type)
    y -= 3 * mm

    # Charges table
    y = draw_section_title(c, y, "Items")
    col_desc = MARGIN
    col_amt = PAGE_W - MARGIN - 30 * mm
    y = draw_table_header(c, y, [("Description", col_desc), ("Amount (KSh)", col_amt)])

    for ch in charges:
        y = check_page_break(c, y)
        amt_str = f"{Decimal(str(ch.amount)):,.2f}"
        y = draw_row(c, y, [(ch.description, col_desc), (amt_str, col_amt)])

    y -= 2 * mm
    y = draw_divider(c, y)

    # Subtotal
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col_desc, y, "Subtotal")
    c.drawString(col_amt, y, f"KSh {total_charges:,.2f}")
    y -= LINE_H * 1.5

    # Payments table
    y = check_page_break(c, y, 40 * mm)
    y = draw_section_title(c, y, "Payments")
    col_method = MARGIN
    col_ref_mid = MARGIN + 40 * mm
    y = draw_table_header(c, y, [
        ("Method", col_method), ("Reference", col_ref_mid), ("Amount (KSh)", col_amt),
    ])

    for p in payments:
        y = check_page_break(c, y)
        ref_text = p.mpesa_code or p.card_ref or p.bank_ref or "—"
        amt_str = f"{Decimal(str(p.amount)):,.2f}"
        y = draw_row(c, y, [
            (p.method, col_method), (ref_text, col_ref_mid), (amt_str, col_amt),
        ])

    y -= 2 * mm
    y = draw_divider(c, y)

    # Total paid + balance
    c.setFont("Helvetica-Bold", 9)
    c.drawString(col_desc, y, "Total Paid")
    c.drawString(col_amt, y, f"KSh {total_payments:,.2f}")
    y -= LINE_H

    c.drawString(col_desc, y, "Balance")
    bal_str = f"KSh {balance:,.2f}"
    c.drawString(col_amt, y, bal_str)
    y -= LINE_H * 2

    # Footer
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN, y, "Thank you for visiting Waterfront Kurahia Resort. Karibu tena!")

    # Finalize
    pdf_bytes = finalize_pdf(c, buf)
    filename = f"receipt_{ref.replace(' ', '_')}_{closed[:10]}.pdf"
    return _pdf_response(pdf_bytes, filename)


# ── Daily Summary PDF ────────────────────────────────────────────────────────

@pdf_reports_bp.get("/daily-summary")
@require_active_user
def daily_summary_pdf():
    """Generate a daily operations summary PDF. Owner only."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can generate the daily summary."}), 403

    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "date query parameter required (YYYY-MM-DD)."}), 400
    try:
        day_start, day_end = parse_date_bounds(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # ── Revenue by method ─────────────────────────────────────────────────
    from app.services.finance import get_period_revenue_by_method
    revenue = get_period_revenue_by_method(day_start, day_end)

    # ── Wristbands issued + entry fee revenue ─────────────────────────────
    bands_issued = db.session.query(func.count(Wristband.id)).filter(
        Wristband.issue_date == date_str,
    ).scalar() or 0

    entry_fee_total = db.session.query(func.sum(Payment.amount)).join(
        Wristband, Wristband.entry_payment_id == Payment.id
    ).filter(
        Wristband.issue_date == date_str,
    ).scalar()
    entry_fee_total = Decimal(str(entry_fee_total)) if entry_fee_total else Decimal("0")

    # ── Tabs opened / closed ──────────────────────────────────────────────
    tabs_opened = db.session.query(func.count(Tab.id)).filter(
        Tab.opened_at_utc >= day_start, Tab.opened_at_utc < day_end,
    ).scalar() or 0

    tabs_closed = db.session.query(func.count(Tab.id)).filter(
        Tab.closed_at_utc >= day_start, Tab.closed_at_utc < day_end,
        Tab.status == TabStatus.CLOSED.value,
    ).scalar() or 0

    # ── Staff on duty (shifts scheduled for this day) ─────────────────────
    shifts = db.session.query(Shift).filter(
        Shift.scheduled_start_utc < day_end,
        Shift.scheduled_end_utc > day_start,
        Shift.status == ShiftStatus.SCHEDULED.value,
    ).all()

    staff_on_duty = []
    for s in shifts:
        emp = s.employee
        # employee profile has a user_id FK — get the user name
        user = db.session.get(User, emp.user_id) if emp else None
        staff_on_duty.append({
            "name": user.username if user else "—",
            "role": s.role_on_shift or "—",
            "start": s.scheduled_start_utc.strftime("%H:%M"),
            "end": s.scheduled_end_utc.strftime("%H:%M"),
        })

    # ── Low stock items (below reorder level) ─────────────────────────────
    active_items = db.session.query(InventoryItem).filter_by(is_active=True).all()
    low_stock = []
    for item in active_items:
        stock = get_current_stock(item.id)
        reorder = Decimal(str(item.reorder_level))
        if reorder > 0 and stock <= reorder:
            low_stock.append({
                "name": item.name,
                "current": str(stock),
                "reorder": str(reorder),
                "unit": item.unit,
            })

    # ── Build PDF ─────────────────────────────────────────────────────────
    buf, c = new_pdf_buffer()
    y = PAGE_H - MARGIN
    y = draw_header(c, y, "Daily Operations Summary", f"Date: {date_str}")

    # Revenue section
    y = draw_section_title(c, y, "Revenue")
    for method in ["CASH", "MPESA", "CARD", "BANK_TRANSFER"]:
        amt = revenue.get(method, Decimal("0"))
        y = draw_kv(c, y, method.replace("_", " ").title(), f"KSh {amt:,.2f}")
    y -= 2 * mm
    y = draw_divider(c, y)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, y, "Total Revenue")
    c.drawString(MARGIN + 80 * mm, y, f"KSh {revenue.get('total', Decimal('0')):,.2f}")
    y -= LINE_H * 2

    # Gate section
    y = check_page_break(c, y)
    y = draw_section_title(c, y, "Gate")
    y = draw_kv(c, y, "Wristbands issued", str(bands_issued))
    y = draw_kv(c, y, "Entry fee revenue", f"KSh {entry_fee_total:,.2f}")
    y -= 3 * mm

    # Tabs section
    y = check_page_break(c, y)
    y = draw_section_title(c, y, "Tables / Tabs")
    y = draw_kv(c, y, "Opened", str(tabs_opened))
    y = draw_kv(c, y, "Closed", str(tabs_closed))
    y -= 3 * mm

    # Staff on duty
    y = check_page_break(c, y, 40 * mm)
    y = draw_section_title(c, y, f"Staff on Duty ({len(staff_on_duty)})")
    if staff_on_duty:
        col_name = MARGIN
        col_role = MARGIN + 50 * mm
        col_time = MARGIN + 100 * mm
        y = draw_table_header(c, y, [
            ("Name", col_name), ("Role", col_role), ("Shift", col_time),
        ])
        for s in staff_on_duty:
            y = check_page_break(c, y)
            y = draw_row(c, y, [
                (s["name"], col_name), (s["role"], col_role),
                (f"{s['start']}–{s['end']}", col_time),
            ])
    else:
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN, y, "No shifts scheduled for this day.")
        y -= LINE_H
    y -= 3 * mm

    # Low stock items
    y = check_page_break(c, y, 40 * mm)
    y = draw_section_title(c, y, f"Low Stock Items ({len(low_stock)})")
    if low_stock:
        col_item = MARGIN
        col_stock = MARGIN + 70 * mm
        col_reorder = MARGIN + 100 * mm
        col_unit = MARGIN + 130 * mm
        y = draw_table_header(c, y, [
            ("Item", col_item), ("Current", col_stock),
            ("Reorder Level", col_reorder), ("Unit", col_unit),
        ])
        for ls in low_stock:
            y = check_page_break(c, y)
            y = draw_row(c, y, [
                (ls["name"], col_item), (ls["current"], col_stock),
                (ls["reorder"], col_reorder), (ls["unit"], col_unit),
            ])
    else:
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN, y, "All items above reorder level.")
        y -= LINE_H

    # Footer
    y -= 6 * mm
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN, max(y, 15 * mm),
                 f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    pdf_bytes = finalize_pdf(c, buf)
    return _pdf_response(pdf_bytes, f"daily_summary_{date_str}.pdf")


# ── Occupancy Report PDF ─────────────────────────────────────────────────────

@pdf_reports_bp.get("/occupancy")
@require_active_user
def occupancy_pdf():
    """Generate a villa occupancy report for a date range. Owner only."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can generate the occupancy report."}), 403

    from_str = request.args.get("from")
    to_str = request.args.get("to")
    if not from_str or not to_str:
        return jsonify({"error": "'from' and 'to' query params required (YYYY-MM-DD)."}), 400

    try:
        from_date = datetime.strptime(from_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        to_date = datetime.strptime(to_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if to_date <= from_date:
        return jsonify({"error": "'to' must be after 'from'."}), 400

    # Limit range to 90 days
    if (to_date - from_date).days > 90:
        return jsonify({"error": "Maximum range is 90 days."}), 400

    # Get all villa resources
    villas = db.session.query(BookableResource).filter_by(
        resource_type=ResourceType.VILLA.value, is_active=True,
    ).order_by(BookableResource.name).all()

    if not villas:
        return jsonify({"error": "No active villa resources found."}), 404

    # Get all bookings that overlap with the range (not cancelled/no-show)
    active_statuses = [
        BookingStatus.CONFIRMED.value, BookingStatus.CHECKED_IN.value,
        BookingStatus.CHECKED_OUT.value, BookingStatus.HELD.value,
    ]
    bookings = db.session.query(Booking).filter(
        Booking.resource_id.in_([v.id for v in villas]),
        Booking.status.in_(active_statuses),
        Booking.check_in_planned_utc < to_date,
        Booking.check_out_planned_utc > from_date,
    ).all()

    # Build a per-villa, per-day occupancy grid
    num_days = (to_date - from_date).days
    dates = [from_date + timedelta(days=i) for i in range(num_days)]

    # villa_id → {date_str → True}
    occupancy_grid: dict[str, dict[str, bool]] = {v.id: {} for v in villas}
    # villa_id → total revenue from bookings in range
    villa_revenue: dict[str, Decimal] = {v.id: Decimal("0") for v in villas}

    for b in bookings:
        checkin = b.check_in_planned_utc
        checkout = b.check_out_planned_utc
        for d in dates:
            day_end = d + timedelta(days=1)
            # Booking overlaps this day if check_in < day_end AND check_out > day_start
            if checkin < day_end and checkout > d:
                occupancy_grid[b.resource_id][d.strftime("%Y-%m-%d")] = True

        # Revenue: attribute full base_total to the villa if the booking overlaps our range
        villa_revenue[b.resource_id] += Decimal(str(b.base_total))

    # ── Build PDF ─────────────────────────────────────────────────────────
    buf, c = new_pdf_buffer()
    y = PAGE_H - MARGIN
    y = draw_header(c, y, "Villa Occupancy Report", f"{from_str} to {to_str}")

    # Summary stats
    total_villa_nights = len(villas) * num_days
    occupied_nights = sum(len(days_map) for days_map in occupancy_grid.values())
    occ_pct = (occupied_nights / total_villa_nights * 100) if total_villa_nights > 0 else 0
    total_rev = sum(villa_revenue.values())

    y = draw_kv(c, y, "Total villas", str(len(villas)))
    y = draw_kv(c, y, "Days in range", str(num_days))
    y = draw_kv(c, y, "Occupied nights", f"{occupied_nights} / {total_villa_nights}")
    y = draw_kv(c, y, "Occupancy rate", f"{occ_pct:.1f}%")
    y = draw_kv(c, y, "Total revenue", f"KSh {total_rev:,.2f}")
    y -= 4 * mm

    # Per-villa breakdown
    y = draw_section_title(c, y, "Per-Villa Breakdown")
    col_villa = MARGIN
    col_nights = MARGIN + 60 * mm
    col_occ = MARGIN + 90 * mm
    col_rev = MARGIN + 120 * mm

    y = draw_table_header(c, y, [
        ("Villa", col_villa), ("Nights Occupied", col_nights),
        ("Occupancy %", col_occ), ("Revenue (KSh)", col_rev),
    ])

    for v in villas:
        y = check_page_break(c, y)
        nights = len(occupancy_grid.get(v.id, {}))
        pct = (nights / num_days * 100) if num_days > 0 else 0
        rev = villa_revenue.get(v.id, Decimal("0"))
        y = draw_row(c, y, [
            (v.name, col_villa),
            (f"{nights} / {num_days}", col_nights),
            (f"{pct:.1f}%", col_occ),
            (f"{rev:,.2f}", col_rev),
        ])

    # Daily occupancy grid (if range is <= 31 days, show a per-day table)
    if num_days <= 31:
        y -= 6 * mm
        y = check_page_break(c, y, 60 * mm)
        y = draw_section_title(c, y, "Daily Occupancy Grid")

        # Column positions: date + one column per villa
        villa_col_width = max(15 * mm, CONTENT_W / (len(villas) + 1))
        col_date_x = MARGIN

        # Header row with villa names
        c.setFillColorRGB(0.9, 0.9, 0.9)
        c.rect(MARGIN, y - 1 * mm, CONTENT_W, 5 * mm, fill=True, stroke=False)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(col_date_x, y, "Date")
        for idx, v in enumerate(villas):
            # Truncate long villa names
            name = v.name[:10] if len(v.name) > 10 else v.name
            x = MARGIN + 25 * mm + idx * villa_col_width
            c.drawString(x, y, name)
        y -= 5 * mm

        # Data rows
        c.setFont("Helvetica", 7)
        for d in dates:
            y = check_page_break(c, y)
            ds = d.strftime("%m-%d")
            c.drawString(col_date_x, y, ds)
            for idx, v in enumerate(villas):
                x = MARGIN + 25 * mm + idx * villa_col_width
                occupied = occupancy_grid.get(v.id, {}).get(d.strftime("%Y-%m-%d"), False)
                c.drawString(x, y, "X" if occupied else "-")
            y -= 4 * mm

    # Footer
    y -= 6 * mm
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN, max(y, 15 * mm),
                 f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    pdf_bytes = finalize_pdf(c, buf)
    return _pdf_response(pdf_bytes, f"occupancy_{from_str}_to_{to_str}.pdf")
