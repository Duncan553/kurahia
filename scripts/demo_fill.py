"""
scripts/demo_fill.py — give every screen something true to show.

live_day.py trades a day and proves the books balance. That fills the money
screens and nothing else, so a capture run for the client proposal produced 22
plates of empty states: Leave Requests with no requests, Approvals with nothing
to approve, Feedback with no feedback, an Alerts page reading "All clear".

Every one of those is a TRUE picture of a screen with no data in it, and
useless in a document whose whole job is showing someone who has never seen
the system what it does.

So this puts the day's ordinary paperwork through the same real endpoints the
staff use: leave asked for, restock requested, guests booked in, a guest rating
a waiter, a note to the manager and one to the owner alone, a peak weekend
marked, a boat inspected. Nothing is written to the database directly — if an
endpoint would refuse a person, it refuses here too, and the line says so.

Run:  FLASK_ENV=development .venv/bin/python scripts/demo_fill.py
"""
import sys, os, uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.user import User
from flask_jwt_extended import create_access_token

app = create_app("development")
LAN = {"REMOTE_ADDR": "127.0.0.1"}

DONE, SKIPPED = [], []


def person(username):
    u = db.session.query(User).filter_by(username=username).first()
    if u is None:
        return None
    c = app.test_client()
    h = {"Authorization": f"Bearer {create_access_token(identity=u.id)}"}
    return c, h


def post(who, path, body, label):
    """One write, through the front door, reported honestly."""
    p = person(who)
    if p is None:
        SKIPPED.append(f"{label} — no account for {who}")
        return None
    c, h = p
    body = {"idempotency_key": str(uuid.uuid4()), **body}
    r = c.post(path, json=body, headers=h, environ_base=LAN)
    if r.status_code in (200, 201):
        DONE.append(label)
        return r.get_json()
    SKIPPED.append(f"{label} — {r.status_code} {str(r.get_json())[:90]}")
    return None


def get(who, path):
    p = person(who)
    if p is None:
        return None
    c, h = p
    r = c.get(path, headers=h, environ_base=LAN)
    return r.get_json() if r.status_code == 200 else None


def run():
    today = date.today()
    fmt = "%Y-%m-%d"

    # ── People asking for things ──────────────────────────────────────────
    for who, ltype, days_out, span, why in [
        ("ivan.kipchoge", "ANNUAL", 9, 3, "Brother's wedding in Nyeri."),
        ("joyce.wambua", "SICK", 1, 1, "Fever since last night, seeing a doctor."),
        ("kevin.mutua", "ANNUAL", 21, 5, "Taking my leave days before the year ends."),
        ("esther.kamau", "EMERGENCY", 2, 1, "Family matter at home, back Thursday."),
    ]:
        start = today + timedelta(days=days_out)
        post(who, "/hr/leave-requests", {
            "leave_type": ltype,
            "start_date": start.strftime(fmt),
            "end_date": (start + timedelta(days=span - 1)).strftime(fmt),
            "reason": why,
        }, f"leave asked for by {who}")

    # ── Stations asking to be restocked ───────────────────────────────────
    items = get("brian.mwangi", "/inventory/items") or []
    named = {i["name"]: i["id"] for i in items if isinstance(i, dict) and i.get("name")}
    picks = [(n, q) for n, q in [("Tusker Lager", 120), ("Cooking Oil", 20),
                                 ("Tomatoes", 15), ("Onions", 25)] if n in named]
    if not picks:                                  # fall back to whatever exists
        picks = [(n, 12) for n in list(named)[:3]]
    for name, qty in picks:
        post("brian.mwangi", "/inventory/purchase-requests", {
            "item_id": named[name], "quantity": qty,
            "notes": f"Running low on {name.lower()} — weekend is coming.",
        }, f"restock requested: {name}")

    # ── What the spa and the water post actually sell ─────────────────────
    #
    # There were NO spa or water items on the menu at all, so both tills opened
    # on an empty list — "0 service(s)". prep_station only knows KITCHEN, BAR
    # and NONE; a service belongs to a DEPARTMENT, and the till filters on that.
    # SERVICE means a human confirmed it consumes no stock, which is the whole
    # reason an unclassified item cannot be sold.
    depts = get("brian.mwangi", "/admin/departments") or get("brian.mwangi", "/hr/departments") or []
    by_name = {d["name"]: d["id"] for d in depts if isinstance(d, dict) and d.get("name")}

    SERVICES = [
        ("Spa & Gym", [("Full Body Massage", 3500, "Sixty minutes, by appointment."),
                       ("Back & Shoulders", 2000, "Thirty minutes."),
                       ("Manicure", 1200, None),
                       ("Pedicure", 1500, None),
                       ("Gym Day Pass", 800, "Access to the gym for the day.")]),
        ("Water Activities", [("Jet Ski Ride", 3500, "Fifteen minutes. Waiver required."),
                              ("Boat Ride 30 min", 2500, "Waiver required."),
                              ("Kayak Hire", 1500, "Per hour. Waiver required."),
                              ("Fishing Trip", 4000, "Half day, rods provided."),
                              ("Pool Pass", 500, "No waiver needed.")]),
    ]
    for dept_name, rows in SERVICES:
        dept_id = by_name.get(dept_name)
        if not dept_id:
            SKIPPED.append(f"{dept_name} services — no department by that name")
            continue
        for name, price, desc in rows:
            post("brian.mwangi", "/menu/items", {
                "name": name, "price": price, "category": "Service",
                "prep_station": "NONE", "department_id": dept_id,
                "stock_tracking": "SERVICE",
                "description": desc,
            }, f"service on the list: {name}")

    # ── Guests arriving ───────────────────────────────────────────────────
    # The villa LIST is manager-and-above, though front desk takes the booking.
    # Asking as grace returned 403 and the loop then booked nobody, silently.
    resources = get("brian.mwangi", "/bookable-resources") or []
    villas = [r for r in resources if isinstance(r, dict) and r.get("is_active")]
    if not villas:
        SKIPPED.append("bookings — no bookable resources exist to book")
    for idx, (guest, phone, nights, adults) in enumerate([
        ("Mwangi Family", "+254711100201", 2, 8),
        ("Achieng Party", "+254711100202", 1, 6),
        ("Otieno Reunion", "+254711100203", 3, 8),
    ]):
        if idx >= len(villas):
            break
        start = datetime.combine(today + timedelta(days=idx),
                                 datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=14)
        post("grace.muthoni", "/bookings", {
            "resource_id": villas[idx]["id"],
            "guest_name": guest,
            "guest_phone": phone,
            "check_in_planned_utc": start.isoformat(),
            "check_out_planned_utc": (start + timedelta(days=nights, hours=-3)).isoformat(),
            "number_of_guests": adults,
        }, f"booking taken: {guest}")

    # ── Guests saying how it went ─────────────────────────────────────────
    for name, score, words in [
        ("Wanjiru M.", 5, "The tilapia was excellent and Ivan looked after us all afternoon."),
        ("Kimani O.", 4, "Lovely grounds. The bar took a while at lunch."),
        ("Achieng P.", 5, "Booked Villa 4 for a birthday. Check-in took two minutes."),
        ("David K.", 3, "Jet ski was great, but nobody told us about the waiver until we got there."),
    ]:
        post("grace.muthoni", "/feedback", {
            "guest_name": name, "score": score, "comments": words,
        }, f"guest feedback: {name}")

    # ── Staff speaking up ─────────────────────────────────────────────────
    post("ivan.kipchoge", "/suggestions", {
        "category": "MANAGEMENT",
        "subject": "A second card machine at the bar",
        "body": "On Saturdays the queue at the bar is card payments waiting for "
                "the one machine. A second one would clear it.",
    }, "suggestion to management")
    post("cynthia.achieng", "/suggestions", {
        "category": "OWNER_PRIVATE",
        "subject": "Deliveries arriving short",
        "body": "Twice this month the vegetable delivery was short of what the "
                "invoice said, and it was signed for anyway. Worth a quiet word.",
    }, "private note to the owner")

    # ── The property's own diary ──────────────────────────────────────────
    for title, kind, days_out, span in [
        ("Peak weekend — school holidays", "PEAK", 9, 3),
        ("Mashujaa Day", "HOLIDAY", 36, 1),
        ("Monthly planning meeting", "PLANNING_MEETING", 14, 1),
    ]:
        start = datetime.combine(today + timedelta(days=days_out),
                                 datetime.min.time(), tzinfo=timezone.utc)
        post("brian.mwangi", "/calendar", {
            "title": title, "entry_type": kind,
            "date_start_utc": start.isoformat(),
            "date_end_utc": (start + timedelta(days=span - 1)).isoformat(),
        }, f"calendar: {title}")

    # ── Boats and jet skis, and somebody checking them ────────────────────
    # The type must be one the checklist knows (safety_templates.py), or the
    # post-use check has no template to hold it to. "BOAT" and "JET_SKI" matched
    # nothing, so four boats went on the books with no checklist behind them.
    from app.equipment.safety_templates import get_template
    for name, kind, interval in [
        ("Speedboat 1", "motorboat", 30), ("Jet Ski A", "jetski", 21),
        ("Jet Ski B", "jetski", 21), ("Paddle Boat 3", "paddle_boat", 90),
    ]:
        made = post("brian.mwangi", "/equipment", {
            "name": name, "equipment_type": kind, "service_interval_days": interval,
        }, f"equipment on the books: {name}")
        if not (made and made.get("id")):
            continue
        template = get_template(kind) or []
        post("francis.njoroge", f"/equipment/{made['id']}/safety-check", {
            "check_items": {k: {"checked": True, "note": ""} for k in template},
            "passed": True,
            "notes": "Checked before service. Lifejackets counted, fuel topped up.",
        }, f"safety check: {name}")

    print("\n══ what the day now has on it ══════════════════════════════")
    for d in DONE:
        print(f"  ok    {d}")
    if SKIPPED:
        print("\n  not done (reported, not hidden):")
        for s in SKIPPED:
            print(f"  --    {s}")
    print(f"\n{len(DONE)} written · {len(SKIPPED)} refused or absent")


if __name__ == "__main__":
    with app.app_context():
        run()
