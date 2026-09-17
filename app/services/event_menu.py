"""
services/event_menu.py — an event as a special customer: its menu, its stock
check, its buy list, its bill.

The rules live here; app/events/bill.py is only HTTP. Decided 17 Sep 2026:

  plan    A manager plans dish × plates ahead. Nothing moves in the store.
  check   Every planned dish is checked against the store, AFTER what earlier
          events have already planned — each event alone can look covered
          while together they are not.
  buy     Whatever is short becomes a PENDING purchase request tagged with the
          event, so it lands in the manager's queue and is never asked twice.
  confirm Opens the event's bill, charges the venue once, writes the buy list,
          and tells the head chef (food), the bar lead (drinks) and managers.
  send    On the day, planned lines become real orders on the event's bill at
          the discounted price — through the same checks and charge-writing as
          a till order, so the kitchen board, stock deduction on READY, and the
          theft checks all see it.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models.event import Event, EventStatus
from app.models.event_menu_line import EventMenuLine
from app.models.inventory_item import InventoryItem
from app.models.menu_item import MenuItem, PrepStation, StockTracking
from app.models.recipe_line import RecipeLine
from app.models.tab import Tab, TabType
from app.models.charge import Charge
from app.models.payment import Payment
from app.models.user import User
from app.models.role import Role
from app.models.system_setting import SystemSetting
from app.models.purchase_request import PurchaseRequest, RequestStatus
from app.models.notification import Notification, NotificationStatus, NotificationChannel
from app.services.stock import get_current_stock

MANAGER_LEVEL = 5
OWNER_LEVEL = 10
OPEN_STATUSES = (EventStatus.PLANNED.value, EventStatus.CONFIRMED.value,
                 EventStatus.IN_PROGRESS.value)

money = lambda d: f"{Decimal(str(d)):.2f}"
qty4 = lambda d: f"{Decimal(str(d)):.4f}"


def plates(d) -> str:
    """40.00 → "40", 12.50 → "12.5" — how a person writes a plate count."""
    d = Decimal(str(d)).normalize()
    return f"{d:f}"


# ── Money on a line ───────────────────────────────────────────────────────────

def parse_discount(raw) -> Decimal | None:
    """A per-plate discount in shillings, or None if it is not a number ≥ 0."""
    try:
        d = Decimal(str(raw if raw not in (None, "") else "0"))
    except InvalidOperation:
        return None
    return d if d.is_finite() and d >= 0 else None


def discount_refusal(actor: User, price: Decimal, discount: Decimal, reason: str | None):
    """(message, status) if this discount may not be given by this person, else None.

    Recorded, bounded, explained: a discount cannot exceed the plate, must say
    why, and a manager may only go as far as the owner has delegated. With no
    ceiling set nothing is delegated — the same rule as an unset budget.
    """
    if discount > price:
        return "A discount cannot be more than the plate's price.", 400
    if discount == 0:
        return None
    if not (reason or "").strip():
        return "Give a reason for the discount.", 400
    if actor.role.level >= OWNER_LEVEL:
        return None
    row = db.session.get(SystemSetting, "event_discount_max_percent")
    ceiling = int(row.value) if row else 0
    if ceiling == 0:
        return ("Discounts on events are the owner's to give until the owner sets "
                "how far a manager may go."), 403
    percent = discount / price * 100 if price else Decimal("100")
    if percent > ceiling:
        return (f"A manager may discount up to {ceiling}% on their own. "
                f"This is {percent:.0f}% — ask the owner."), 403
    return None


def line_dict(line: EventMenuLine) -> dict:
    mi = line.menu_item
    return {
        "id":                line.id,
        "menu_item_id":      line.menu_item_id,
        "name":              mi.name if mi else None,
        "prep_station":      mi.prep_station if mi else None,
        "quantity":          plates(line.quantity),
        "menu_price":        money(line.menu_price),
        "discount_per_unit": money(line.discount_per_unit),
        "charged_per_unit":  money(line.charged_per_unit),
        "line_total":        money(line.charged_per_unit * Decimal(str(line.quantity))),
        "discount_reason":   line.discount_reason,
        "discount_by":       line.discount_by.username if line.discount_by else None,
        "sent":              line.is_sent,
    }


def active_lines(event_id: str, unsent_only: bool = False) -> list[EventMenuLine]:
    q = db.session.query(EventMenuLine).filter_by(event_id=event_id, is_active=True)
    if unsent_only:
        q = q.filter(EventMenuLine.order_item_id.is_(None))
    return q.order_by(EventMenuLine.created_at_utc).all()


def totals(lines: list[EventMenuLine]) -> dict:
    value = sum((Decimal(str(l.menu_price)) * Decimal(str(l.quantity)) for l in lines), Decimal("0"))
    disc = sum((Decimal(str(l.discount_per_unit)) * Decimal(str(l.quantity)) for l in lines), Decimal("0"))
    return {"menu_value": money(value), "discount": money(disc), "to_charge": money(value - disc)}


# ── Stock ─────────────────────────────────────────────────────────────────────

def _needs(pairs) -> dict[str, Decimal]:
    """Stock units each inventory item must supply for these (menu item, qty) pairs.

    Mirrors how a sale consumes: RECIPE draws every ingredient × qty in stock
    units; DIRECT draws its one linked item per unit; SERVICE draws nothing.
    """
    need: dict[str, Decimal] = {}
    for mi, n in pairs:
        n = Decimal(str(n))
        if mi.stock_tracking == StockTracking.DIRECT.value and mi.inventory_item_id:
            need[mi.inventory_item_id] = need.get(mi.inventory_item_id, Decimal("0")) + n
        elif mi.stock_tracking == StockTracking.RECIPE.value:
            for rl in db.session.query(RecipeLine).filter_by(menu_item_id=mi.id, is_active=True):
                inv = db.session.get(InventoryItem, rl.inventory_item_id)
                if inv:
                    need[inv.id] = need.get(inv.id, Decimal("0")) + \
                        inv.recipe_to_stock(Decimal(str(rl.quantity))) * n
    return need


def _lines(lines):
    return [(l.menu_item, l.quantity) for l in lines]


def _waiting_on_boards() -> dict[str, Decimal]:
    """Stock already promised to dishes sent to a kitchen or bar and not yet made.

    Stock only moves when a dish is marked READY, so a sent order sitting on the
    board still looks like it is on the shelf. Counting it is what stops "30
    more plates" reading covered when 90 are already waiting to be cooked.
    """
    from app.models.order import Order, OrderStatus
    from app.models.order_item import OrderItem, OrderItemStatus
    items = db.session.query(OrderItem).join(Order, Order.id == OrderItem.order_id).filter(
        Order.status != OrderStatus.DRAFT.value,
        OrderItem.status.in_([OrderItemStatus.PENDING.value, OrderItemStatus.RECEIVED.value]),
    ).all()
    return _needs((oi.menu_item, oi.quantity) for oi in items)


def stock_check(event: Event) -> dict:
    """Can the store cover this event's unsent plan, after everything ahead of it?

    Ahead of it: dishes already on a kitchen/bar board, and the plans of events
    that start earlier. Each event alone can look covered while together they
    are not.
    """
    mine = _needs(_lines(active_lines(event.id, unsent_only=True)))
    earlier_lines = db.session.query(EventMenuLine).join(Event).filter(
        EventMenuLine.is_active.is_(True),
        EventMenuLine.order_item_id.is_(None),
        Event.id != event.id,
        Event.status.in_(OPEN_STATUSES),
        Event.starts_at_utc < event.starts_at_utc,
    ).all()
    earlier = _needs(_lines(earlier_lines))
    boards = _waiting_on_boards()

    items = []
    for item_id, needed in mine.items():
        inv = db.session.get(InventoryItem, item_id)
        in_store = get_current_stock(item_id)
        ahead = earlier.get(item_id, Decimal("0"))
        cooking = boards.get(item_id, Decimal("0"))
        # This event's share of the gap: never more than it needs itself, so
        # an earlier shortfall is written on the list of whoever caused it.
        short = min(needed, max(Decimal("0"), needed + ahead + cooking - in_store))
        items.append({
            "inventory_item_id":         item_id,
            "name":                      inv.name,
            "unit":                      inv.unit,
            "needed":                    qty4(needed),
            "planned_by_earlier_events": qty4(ahead),
            "waiting_on_boards":         qty4(cooking),
            "in_store":                  qty4(in_store),
            "short":                     qty4(short),
        })
    items.sort(key=lambda i: i["name"])
    return {"ready": all(Decimal(i["short"]) == 0 for i in items), "items": items}


def write_buy_list(event: Event, actor: User) -> list[PurchaseRequest]:
    """A PENDING purchase request per short item, once per event and item."""
    from app.models.audit_log import AuditLog
    live = (RequestStatus.DRAFT.value, RequestStatus.PENDING.value,
            RequestStatus.PROPOSED.value, RequestStatus.APPROVED.value)
    written = []
    for item in stock_check(event)["items"]:
        short = Decimal(item["short"])
        if short <= 0:
            continue
        already = db.session.query(PurchaseRequest).filter(
            PurchaseRequest.event_id == event.id,
            PurchaseRequest.item_id == item["inventory_item_id"],
            PurchaseRequest.status.in_(live),
        ).first()
        if already:
            continue
        # The SYSTEM is the requester, like the nightly reorder drafts. Naming the
        # manager here meant the rule "nobody approves their own request" sent
        # every event's shopping to the owner, and budget delegation never
        # applied. The audit line below still records which manager wrote it.
        pr = PurchaseRequest(item_id=item["inventory_item_id"], quantity=short,
                             status=RequestStatus.PENDING.value, system_generated=True,
                             requested_by_id=None, event_id=event.id)
        db.session.add(pr)
        db.session.flush()
        AuditLog.log(actor=actor.username, action="event.buy_list", target=pr.id,
                     details=f"{event.title}: {item['name']} {item['short']}")
        written.append(pr)
    return written


# ── Bill ──────────────────────────────────────────────────────────────────────

def open_bill(event: Event, actor: User) -> Tab:
    """The event's one bill, with the venue charged once."""
    if event.tab_id:
        return event.tab
    from app.services.tax import get_vat_rate
    tab = Tab(tab_type=TabType.EVENT.value, reference=event.title[:100], opened_by_id=actor.id)
    db.session.add(tab)
    db.session.flush()
    event.tab_id = tab.id
    venue = event.venue
    if venue and Decimal(str(venue.base_price)) > 0:
        db.session.add(Charge(tab_id=tab.id, amount=venue.base_price,
                              description=f"Venue hire — {venue.name}",
                              created_by_id=actor.id, tax_rate_snapshot=get_vat_rate(),
                              idempotency_key=f"event-venue-{event.id}"))
    return tab


def bill_dict(event: Event) -> dict:
    if not event.tab_id:
        return {"tab_id": None, "tab_type": None, "charged": "0.00", "paid": "0.00", "owing": "0.00"}
    charged = db.session.query(db.func.sum(Charge.amount)).filter_by(tab_id=event.tab_id).scalar() or 0
    paid = db.session.query(db.func.sum(Payment.amount)).filter_by(tab_id=event.tab_id).scalar() or 0
    # Every line on the bill, so "what is the 60,000?" has an answer: the venue
    # hire, each dish sent, and every payment taken.
    charges = db.session.query(Charge).filter_by(tab_id=event.tab_id).order_by(Charge.created_at).all()
    payments = db.session.query(Payment).filter_by(tab_id=event.tab_id).all()
    return {"tab_id": event.tab_id, "tab_type": TabType.EVENT.value, "status": event.tab.status,
            "charged": money(charged), "paid": money(paid),
            "owing": money(Decimal(str(charged)) - Decimal(str(paid))),
            "lines": [{"description": c.description, "amount": money(c.amount)} for c in charges],
            "payments": [{"method": p.method, "amount": money(p.amount)} for p in payments]}


# ── The kitchen board ─────────────────────────────────────────────────────────

def event_for_tab(tab_id: str | None) -> Event | None:
    """The event whose bill this is, or None for an ordinary tab."""
    if not tab_id:
        return None
    return db.session.query(Event).filter_by(tab_id=tab_id).first()


def cooking_opens(event: Event):
    """The resort-clock day the kitchen may start this event's dishes."""
    from app.services.business_day import _get_tz
    starts = event.starts_at_utc
    starts = starts if starts.tzinfo else starts.replace(tzinfo=timezone.utc)
    return starts.astimezone(_get_tz()).date()


def too_early_to_cook(event: Event) -> str | None:
    """Refusal if today (resort clock) is before the event's day.

    Starting a dish is what leads to READY, and READY is what takes the stock.
    A wedding's 120 plates started a week early empty the store for a meal
    nobody is eating yet — so the kitchen may not, whoever taps it.
    """
    from app.services.business_day import _get_tz
    opens = cooking_opens(event)
    if datetime.now(_get_tz()).date() < opens:
        return (f"This is for {event.title} on {opens:%a %d %b}. "
                f"The kitchen can start it on that day, not before.")
    return None


def board_event(event: Event | None) -> dict | None:
    """What a cook needs to know about the event a ticket belongs to."""
    if not event:
        return None
    return {
        "id": event.id, "title": event.title,
        "starts_at": event.starts_at_utc.isoformat(), "ends_at": event.ends_at_utc.isoformat(),
        "venue": event.venue.name if event.venue else event.location,
        "expected_guests": event.expected_guests,
        "opens_on": cooking_opens(event).isoformat(),
        "can_start": too_early_to_cook(event) is None,
    }


# ── Confirm ───────────────────────────────────────────────────────────────────

def _people(role_names=None, min_level=None) -> list[User]:
    q = db.session.query(User).join(Role, Role.id == User.role_id).filter(User.is_active.is_(True))
    if role_names:
        q = q.filter(Role.name.in_(role_names))
    if min_level is not None:
        q = q.filter(Role.level >= min_level)
    return q.all()


def _tell(users: list[User], event: Event, subject: str, body: str) -> None:
    """One notice per person per distinct message.

    The key carries a fingerprint of the text: the same plan saved twice says
    nothing new, while a plan that CHANGED after confirming (120 plates → 90)
    reaches the kitchen again instead of leaving the old number standing.
    """
    import hashlib
    now = datetime.now(timezone.utc)
    fingerprint = hashlib.sha1(body.encode()).hexdigest()[:12]
    for u in users:
        key = f"event-menu-{event.id}-{u.id}-{fingerprint}"
        if db.session.query(Notification).filter_by(idempotency_key=key).first():
            continue
        db.session.add(Notification(
            recipient_user_id=u.id, reference_type="event_menu", reference_id=event.id,
            subject=subject[:200], body=body, status=NotificationStatus.DELIVERED.value,
            channel=NotificationChannel.IN_APP.value, scheduled_for_utc=now, sent_at_utc=now,
            idempotency_key=key,
        ))


def announce_menu(event: Event) -> None:
    """Tell the head chef (food), the bar lead (drinks) and managers what is planned."""
    lines = active_lines(event.id, unsent_only=True)
    if not lines:
        return
    when = f"{event.starts_at_utc:%d %b}"
    listing = lambda ls: ", ".join(f"{plates(l.quantity)} × {l.menu_item.name}" for l in ls)
    food = [l for l in lines if l.menu_item.prep_station == PrepStation.KITCHEN.value]
    drink = [l for l in lines if l.menu_item.prep_station == PrepStation.BAR.value]
    if food:
        _tell(_people(role_names=["head_chef"]), event,
              f"Plates for {event.title}", f"{event.title} on {when}: {listing(food)}.")
    if drink:
        _tell(_people(role_names=["bar_lead"]), event,
              f"Drinks for {event.title}", f"{event.title} on {when}: {listing(drink)}.")
    # What is short NOW, whether or not a request for it already exists — a
    # notice built from newly written requests said "covers it" when the list
    # had simply been written earlier.
    short = ", ".join(f"{plates(i['short'])} {i['unit']} {i['name']}"
                      for i in stock_check(event)["items"] if Decimal(i["short"]) > 0)
    _tell(_people(min_level=MANAGER_LEVEL), event, f"Menu for {event.title}",
          f"{event.title} on {when}: {listing(lines)}."
          + (f" To buy: {short}." if short else " The store covers it."))


def on_confirm(event: Event, actor: User) -> None:
    """Everything confirming an event sets in motion."""
    open_bill(event, actor)
    write_buy_list(event, actor)
    announce_menu(event)
