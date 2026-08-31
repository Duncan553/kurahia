"""
pos/tabs.py — Tab lifecycle: open, view, close.
POST /tabs            — open a tab
GET  /tabs/:id        — full tab state (charges, payments, derived balance)
POST /tabs/:id/close  — close when balance ≤ 0 and all items resolved
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user, require_clocked_in
from app.extensions import db
from app.models.tab import Tab, TabType, TabStatus
from app.models.charge import Charge
from app.models.payment import Payment
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.user import User
from app.models.audit_log import AuditLog
from app.services.tab import get_tab_balance, is_tab_closable

tabs_bp = Blueprint("tabs", __name__, url_prefix="/tabs")

MANAGER_LEVEL = 5
# Front desk settles other people's accounts, so they may open any tab. Below
# that you get the tables you are actually working. Same threshold and same
# rule as pos/receipts.py — one idea of "a tab that is mine", not two that can
# drift apart.
FRONT_DESK_LEVEL = 3


@tabs_bp.get("")
@require_active_user
def list_tabs():
    """List tabs. Optional filters: status=OPEN|CLOSED, mine=true, tab_type=WALK_IN|VILLA|BAND.

    mine=true means "assigned to me, OR nobody's" (assigned_to_id is me or NULL)
    for anyone below manager level — a waiter's own Tables screen. Including
    unassigned tables is deliberate: a table a manager hasn't gotten to yet
    (e.g. one with money still owed, opened before any waiter claimed it)
    must stay visible to *some* waiter, or it's invisible to everyone until a
    manager notices and assigns it. Manager+ passing mine=true still get
    "opened by me" (assigned_to_id doesn't apply the same way to a manager
    covering the whole floor).

    That broadening excludes BAND tabs specifically — those are gate-issued
    wristband credit accounts (Gate screens own that workflow, no waiter is
    ever meant to stumble into one this way) — but keeps VILLA in, since
    waiters also deliver food/drinks to villas, not just restaurant tables.
    """
    actor     = db.session.get(User, get_jwt_identity())
    status    = (request.args.get("status") or "").upper() or None
    mine      = request.args.get("mine", "false").lower() == "true"
    tab_type  = (request.args.get("tab_type") or "").upper() or None

    query = db.session.query(Tab)
    if status:
        if status not in TabStatus.__members__:
            return jsonify({"error": f"status must be one of {list(TabStatus.__members__)}."}), 400
        query = query.filter_by(status=status)
    if mine:
        if actor.role.level < MANAGER_LEVEL:
            query = query.filter(
                (Tab.assigned_to_id == actor.id) |
                ((Tab.assigned_to_id.is_(None)) & (Tab.tab_type != TabType.BAND.value))
            )
        else:
            query = query.filter_by(opened_by_id=actor.id)
    if tab_type:
        if tab_type not in TabType.__members__:
            return jsonify({"error": f"tab_type must be one of {list(TabType.__members__)}."}), 400
        query = query.filter_by(tab_type=tab_type)

    tabs = query.order_by(Tab.opened_at_utc.desc()).all()
    return jsonify([
        {
            "id":           t.id,
            "reference":    t.reference,
            "tab_type":     t.tab_type,
            "status":       t.status,
            "opened_at":    t.opened_at_utc.isoformat(),
            "opened_by":    t.opened_by.username if t.opened_by else None,
            "assigned_to":  t.assigned_to.username if t.assigned_to else None,
            "assigned_to_id": t.assigned_to_id,
            "balance":      str(get_tab_balance(t.id)),
        }
        for t in tabs
    ]), 200


def _normalise_reference(raw: str | None) -> str | None:
    """Tidy a tab reference so the same table cannot become two.

    The reference is deliberately POLYMORPHIC — on the live database it holds
    "Band #12" (auto-generated at the gate), "Villa 6 / Wanjiru Kamau",
    "Table 2 — breakfast" and "Spa — Full Body Massage". A Table model would be
    the wrong shape for that; only a minority of tabs are dining tables at all.

    What free text does cost is consistency, so this collapses internal runs of
    whitespace and trims the ends. "Table  5" and "Table 5" are the same table
    and must not become separate rows in every report that groups by reference.

    Case is left alone on purpose: "Villa 6 / Wanjiru Kamau" contains a guest's
    name, and title-casing or lower-casing someone's name to tidy a key is not
    a trade worth making.
    """
    if not raw:
        return None
    return " ".join(str(raw).split())[:200] or None


@tabs_bp.post("")
@require_active_user
@require_clocked_in
def open_tab():
    actor = db.session.get(User, get_jwt_identity())
    data      = request.get_json(silent=True) or {}
    tab_type  = (data.get("tab_type") or TabType.WALK_IN.value).upper()
    reference = _normalise_reference(data.get("reference"))

    if tab_type not in TabType.__members__:
        return jsonify({"error": f"tab_type must be one of {list(TabType.__members__)}."}), 400

    with db.session.begin_nested():
        tab = Tab(tab_type=tab_type, reference=reference, opened_by_id=actor.id)
        db.session.add(tab)

    AuditLog.log(actor=actor.username, action="tab.open", target=tab.id,
                 details=f"ref={reference}")
    db.session.commit()
    # Match GET /tabs/:id's shape (WaiterTabsScreen's Tab interface declares
    # tab_type/opened_at/balance too) — a fresh tab has zero balance by
    # definition, no need to query it.
    return jsonify({
        "id": tab.id, "reference": tab.reference, "tab_type": tab.tab_type,
        "status": tab.status, "opened_at": tab.opened_at_utc.isoformat(), "balance": "0",
    }), 201


@tabs_bp.get("/<tab_id>")
@require_active_user
def get_tab(tab_id):
    """One tab in full: charges, payments, orders, balance.

    Scoped the SAME way as GET /receipts/:tab_id, and it has to be. That
    endpoint restricts a folio because "a villa folio is a guest's whole stay" —
    but this one returned the same charges and payments (plus the order lines,
    the payment method and who took it) with no check at all, and GET /tabs
    hands out the ids. The restriction over there was decorative while this door
    stood open beside it.

    Front desk and above may open any tab, because settling other people's
    accounts is their job. Below that, only a tab you are working: assigned to
    you, or opened by you. Waiters legitimately need their own tables, which is
    why this is an is-mine rule rather than a level gate.
    """
    actor = db.session.get(User, get_jwt_identity())
    tab = db.session.get(Tab, tab_id)
    if not tab:
        return jsonify({"error": "Tab not found."}), 404

    if actor.role.level < FRONT_DESK_LEVEL:
        is_mine = (tab.assigned_to_id == actor.id) or (tab.opened_by_id == actor.id)
        if not is_mine:
            return jsonify({
                "error": "You can only open a table you are serving. "
                         "Ask front desk or a manager for anything else."
            }), 403

    balance = get_tab_balance(tab_id)

    charges  = db.session.query(Charge).filter_by(tab_id=tab_id).all()
    payments = db.session.query(Payment).filter_by(tab_id=tab_id).all()
    orders   = db.session.query(Order).filter_by(tab_id=tab_id).all()

    return jsonify({
        "id":          tab.id,
        "reference":   tab.reference,
        "tab_type":    tab.tab_type,
        "status":      tab.status,
        "opened_at":   tab.opened_at_utc.isoformat(),
        "opened_by":   tab.opened_by.username if tab.opened_by else None,
        "assigned_to": tab.assigned_to.username if tab.assigned_to else None,
        "assigned_to_id": tab.assigned_to_id,
        "balance":     str(balance),
        "charges":  [{"id": c.id, "description": c.description, "amount": str(c.amount),
                      "created_at": c.created_at.isoformat()} for c in charges],
        "payments": [{"id": p.id, "method": p.method, "amount": str(p.amount),
                      "received_by": p.received_by.username if p.received_by else None,
                      "created_at": p.created_at_utc.isoformat()} for p in payments],
        "orders": [
            {
                "id": o.id,
                "status": o.status,
                "items": [
                    {"id": oi.id, "name": oi.menu_item.name if oi.menu_item else None,
                     "quantity": str(oi.quantity), "status": oi.status,
                     "notes": oi.notes}
                    for oi in o.items
                ],
            }
            for o in orders
        ],
    }), 200


@tabs_bp.post("/<tab_id>/assign")
@require_active_user
def assign_tab(tab_id):
    """Manager assigns (or reassigns) this table to a waiter. Same shape as
    POST /housekeeping/assign — one active assignment at a time, reassignable,
    history lives in AuditLog rather than a separate table."""
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager access required to assign waiters."}), 403

    tab = db.session.get(Tab, tab_id)
    if not tab:
        return jsonify({"error": "Tab not found."}), 404
    if tab.status == TabStatus.CLOSED.value:
        return jsonify({"error": "Cannot assign a closed tab."}), 400

    data        = request.get_json(silent=True) or {}
    employee_id = data.get("employee_id")
    if not employee_id:
        return jsonify({"error": "employee_id is required."}), 400

    employee = db.session.get(User, employee_id)
    if not employee or not employee.is_active:
        return jsonify({"error": "Employee not found or disabled."}), 404

    with db.session.begin_nested():
        tab.assigned_to_id = employee.id
        tab.assigned_at_utc = datetime.now(timezone.utc)

    AuditLog.log(actor=actor.username, action="tab.assign", target=tab.id,
                 details=f"assigned {employee.username} to {tab.reference or tab.id[:8]}")
    db.session.commit()
    return jsonify({
        "id": tab.id, "assigned_to": employee.username, "assigned_to_id": employee.id,
        "assigned_at": tab.assigned_at_utc.isoformat(),
    }), 200


@tabs_bp.post("/<tab_id>/close")
@require_active_user
@require_clocked_in
def close_tab(tab_id):
    actor = db.session.get(User, get_jwt_identity())
    tab   = db.session.get(Tab, tab_id)
    if not tab:
        return jsonify({"error": "Tab not found."}), 404
    if tab.status == TabStatus.CLOSED.value:
        return jsonify({"error": "This tab is already closed."}), 400

    ok, reason = is_tab_closable(tab_id)
    if not ok:
        return jsonify({"error": reason}), 400

    with db.session.begin_nested():
        tab.status        = TabStatus.CLOSED.value
        tab.closed_at_utc = datetime.now(timezone.utc)
        tab.closed_by_id  = actor.id

        # A settled band is a guest who has left. Nothing linked the two, so a
        # wristband stayed ACTIVE after its account was closed and paid — it
        # still appeared in /gate/active-bands, still counted toward headcount,
        # and the EOD forfeit sweep would process an account that owed nothing.
        # Closing the account is the moment the band stops being live.
        if tab.tab_type == TabType.BAND.value:
            from app.models.wristband import Wristband, WristbandStatus
            band = db.session.query(Wristband).filter_by(
                tab_id=tab.id, status=WristbandStatus.ACTIVE.value
            ).first()
            if band:
                band.status = WristbandStatus.DEACTIVATED.value
                AuditLog.log(actor=actor.username, action="gate.band.deactivate",
                             target=str(band.band_number),
                             details="account settled and closed")

    AuditLog.log(actor=actor.username, action="tab.close", target=tab_id)
    db.session.commit()
    return jsonify({"id": tab.id, "status": tab.status}), 200


@tabs_bp.get("/references")
@require_active_user
def recent_references():
    """References already in use, newest first — for a pick-list.

    This is the actual fix for typed references. On the live data two tabs were
    opened as bare "6" and "9" where someone meant "Table 6" — nothing was
    misspelled, the waiter just did not have the real name in front of them.
    Offering what has genuinely been used before turns a free-text box into a
    pick-list without inventing a Table model that villas, bands and spa tabs
    would not fit.

    Band references are excluded: the gate generates those automatically and a
    waiter never types one, so listing 26 of them would bury the handful of
    names that matter.
    """
    rows = (db.session.query(Tab.reference)
            .filter(Tab.reference.isnot(None))
            .filter(~Tab.reference.ilike("Band #%"))
            .order_by(Tab.opened_at_utc.desc())
            .limit(300).all())

    seen, out = set(), []
    for (ref,) in rows:
        key = ref.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
        if len(out) >= 40:
            break
    return jsonify(out), 200


@tabs_bp.get("/by-room/<path:room>")
@require_active_user
def tab_by_room(room):
    """Find the open villa account for a room, and say who may charge to it.

    A wristband has had a lookup since Chunk 7 — GET /gate/bands/<number>, scan
    and go. A villa had nothing, so a guest saying "put it on Villa 6" left the
    waiter scrolling every open villa tab on the property, matching on a text
    reference. That is slow at a busy bar and it is guesswork.

    It returns the register with the tab on purpose. The tab alone answers
    "where does this go"; only the register answers "should it", and those two
    questions are asked in the same breath by the same person.
    """
    from app.models.booking import Booking
    from app.models.booking_occupant import BookingOccupant

    # Matching must never be "close enough". A substring search for "Villa 1"
    # also matches Villa 14 and Villa 15, and .first() would silently pick one —
    # so a waiter typing a real room number could charge a different guest's
    # account. References are stored as "<resource> / <guest>", so an exact
    # match on the part before the slash is the only unambiguous answer.
    needle = room.strip().lower()
    candidates = (
        db.session.query(Tab)
        .filter(Tab.tab_type == TabType.VILLA.value,
                Tab.status == TabStatus.OPEN.value,
                Tab.reference.ilike(f"%{needle}%"))
        .all()
    )

    def room_part(ref: str) -> str:
        return (ref or "").split("/")[0].strip().lower()

    exact = [t for t in candidates if room_part(t.reference) == needle]

    if len(exact) == 1:
        tab = exact[0]
    elif len(exact) > 1:
        # Two open accounts for one room should not happen, but if it does, the
        # POS must not guess which one the drink belongs to.
        return jsonify({
            "error": f"More than one open account for '{room}'. Ask front desk.",
            "candidates": [{"tab_id": t.id, "reference": t.reference} for t in exact],
        }), 409
    elif len(candidates) == 1:
        tab = candidates[0]
    elif len(candidates) > 1:
        # "Villa 1" typed, "Villa 1" / "Villa 14" / "Villa 15" all open. Hand
        # back the list and let the person choose rather than pick for them.
        return jsonify({
            "error": f"'{room}' matches more than one room. Pick the exact one.",
            "candidates": [{"tab_id": t.id, "reference": t.reference} for t in candidates],
        }), 409
    else:
        return jsonify({
            "error": f"No open villa account matches '{room}'. "
                     f"Check the room number, or the guest may not be checked in yet."
        }), 404

    booking = db.session.query(Booking).filter_by(tab_id=tab.id).first()
    occupants = []
    if booking:
        occupants = db.session.query(BookingOccupant).filter_by(
            booking_id=booking.id, checked_out_utc=None
        ).all()

    return jsonify({
        "tab_id":    tab.id,
        "reference": tab.reference,
        "balance":   str(get_tab_balance(tab.id)),
        "booking_id": booking.id if booking else None,
        # The lead guest is liable for the bill, so they may always charge.
        "lead_guest": booking.guest_name if booking else None,
        # Everyone else must have been granted it deliberately at check-in.
        "may_charge": (
            ([booking.guest_name] if booking else [])
            + [o.full_name for o in occupants if o.may_charge]
        ),
        "also_staying": [o.full_name for o in occupants if not o.may_charge],
        "unnamed_count": max(
            0, (booking.number_of_guests or 1) - 1 - len(occupants)
        ) if booking else 0,
    }), 200
