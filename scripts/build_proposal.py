"""
scripts/build_proposal.py — assemble the client proposal from the captured set.

The document is GENERATED, not hand-written, for one reason: there are 59
plates and a hand-written page is where a plate quietly goes missing or keeps a
caption describing what a screen used to show. This reads docs/proposal/
evidence.json — the capture log — and refuses to build if a plate it wants was
never captured, or if a plate was captured and nobody wrote a caption for it.

Run:  .venv/bin/python scripts/build_proposal.py
Then: .venv/bin/python scripts/proposal_pdf.py
"""
import json
import pathlib
import sys
from html import escape

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs/proposal/evidence.json"
OUT = ROOT / "docs/proposal/index.html"

# ── Every plate, with the words that go under it ───────────────────────────
# (id, caption). Order here is the order they appear.
PLATES = {
 # The owner
 "01_owner_dashboard": "The owner's dashboard at the close of a traded day: <b>KSh 444,750</b> taken, up on the trend, nine guests still inside on wristbands, two incidents not yet actioned, eleven of twelve staff on duty, one item running low. Occupancy reads zero because both villas had already checked out.",
 "02_owner_alerts": "Alerts. What the system noticed on its own — portions drifting on one cook's shift, tickets opened and voided, one account used from two places. Reading <b>all clear</b> here is a finding, not a blank screen.",
 "03_owner_finance": "Finance. Revenue, expenses, profit for the month, budgets per department, open shortfalls and purchases with no receipt attached. Requested as a manager, this is <b>refused</b> — revenue and profit are yours.",
 "04_owner_purchase_approvals": "Approvals. What a manager could not approve inside their delegated budget, waiting with the item, the quantity, who asked and their cost estimate.",
 "05_owner_reconciliation": "Recon, for the same day: KSh 23,000 cash, KSh 140,450 card, KSh 281,300 M&#8209;Pesa — <b>KSh 444,750</b>, which is the dashboard figure on PL&nbsp;01 arrived at from the other direction.",
 "06_owner_payroll": "Payroll, built from clock records rather than from anyone's memory. It refuses to invent a figure for anyone without a wage rate and prints that instead.",
 "07_owner_staff": "Staff. Every account with its role, department, whether it is active and whether a PIN is set. Disabling one stops that person on their very next tap, not at their next login.",
 "08_owner_bookings": "Bookings. Who is in, who is coming, who owes a deposit, and who has not signed a waiver for tomorrow.",
 "09_owner_menu_profit": "Profit. The menu sorted by what it actually earns you, not by what sells. A dish with no recipe cannot have a margin, so it is named rather than guessed at.",
 "10_owner_feedback": "Feedback. What guests said, attached to the department and the person it was about — and feeding that person's performance score rather than sitting in a list nobody reads.",
 "11_owner_suggestions": "From staff. Notes sent up to management, and notes marked for the owner alone. A manager listing suggestions is refused entirely — their screen is never given the private ones.",
 "12_owner_disputes": "Disputes that reached the owner, with what was decided and the notes that went back to whoever filed it.",
 "13_owner_audit": "The audit trail. Every write, hash-chained: each row carries a fingerprint of the row before it, so removing or altering one breaks every row after it, and the check says so.",
 "14_owner_settings": "Settings. Roles and their levels, the thresholds the alert engine judges against, and the resort's own network. Changing how the resort works does not mean calling me.",
 # Management
 "20_manager_hub": "The manager's first screen. Stock behaviour and stock by department across the top — 32 items, none low, every department green — then budget burn: Bar 68% of its month gone, Kitchen 32%, Water Activities untouched.",
 "21_manager_front_house": "Front House. One arrival today — Mwangi Family, Villa 1, deposit KSh 0 of 60,000. <b>Confirm is refused until the deposit is recorded</b>, which is why both controls sit on the same card.",
 "22_manager_cash": "Cash. A person's cash in against what the system says they took, with the payments behind the figure and an immediate verdict. The expected amount is frozen at the moment of reconciliation so it cannot drift afterwards.",
 "23_manager_reconcile": "Close of day. What the system says was taken, matched against the statement, method by method.",
 "24_manager_staff": "Staff accounts, roles and departments — and who may reach what.",
 "25_manager_roster": "Today's roster: who is on which post. This is the roster people are held to, and the one the wages are read from.",
 "26_manager_shifts": "Shifts, scheduled ahead. Staff do not clock <em>out</em> — the roster closes the shift at its scheduled end, because a manager already set whether that person is on days or nights.",
 "27_manager_attendance": "Attendance. Everyone rostered and everyone who clocked in, unioned — so somebody who turned up unrostered is visible rather than absent from the list.",
 "28_manager_leave": "Leave, with the request in front of you rather than in a message thread: the person, the type, the dates and their reason. Unanswered requests are chased daily and escalate to the owner after a week.",
 "29_manager_purchases": "Purchase requests. A station says what it needs, the manager costs it. Beyond the delegated budget the refusal carries the arithmetic.",
 "30_manager_receive": "Receiving a delivery against a purchase and a supplier, with the receipt photographed at the moment it is recorded. Purchases with no receipt are counted on the owner's dashboard.",
 "31_manager_suppliers": "Suppliers, so every delivery recorded is recorded against somebody.",
 "32_manager_menu": "The menu, opened by the <b>head chef</b> — who owns the food, the prices and the recipes. Each item declares how it draws on stock; an item that declares nothing cannot be sold at all.",
 "33_inventory_count": "Stock. A count is a count, not a delivery: counting higher than the books is refused, because more on the shelf than in the books means a delivery nobody recorded.",
 "34_manager_resources": "The villas: what each sleeps, its nightly rate, and whether it is in service. Taking one out for repairs is a switch, not a phone call.",
 "35_manager_suggestions": "What staff sent up to management. A note marked for the owner never appears here — not hidden by the screen, never given to it.",
 "36_manager_disputes": "A grievance, and the answer that goes back to the person who raised it. Resolving one now notifies them; it used to write the outcome into the row and stop.",
 "37_lost_found": "Lost &amp; Found. Front desk may look in the box — that is who a guest asks. Releasing the property still takes a manager.",
 "38_events": "Events. A wedding or conference with who is working it and the stock set aside for it, and the four lifecycle steps that run it from planned to closed.",
 "39_calendar": "The calendar. A peak weekend or a public holiday marked once and seen by the whole property, with a reminder ahead of it.",
 # The floor
 "50_gate_hub": "The gate. The entry fee is not taken away — it goes onto the band as credit the guest spends anywhere on the property, and the bands issued today are listed so a second one is not handed to somebody who already has one.",
 "51_gate_band_lookup": "Band lookup, used: <b>Band #1, active, KSh 1,800 credit remaining</b>, issued by a named member of staff at 13:51 — and one control to close it when the guest leaves.",
 "52_gate_waiver": "A waiver recorded against the guest's band or their booking. Selling a jet ski to a band without one is refused, naming exactly what is missing.",
 "53_front_desk_checkin": "Check-in. The room charge lands on the villa's account here, so a villa never leaves without its own room on the bill.",
 "54_front_desk_new_booking": "A new booking, priced from the villa rate card — which was checked against your own website.",
 "55_villa_folio": "The villa folio: the room's whole bill, wherever on the property it was run up. A room is settled <b>here and nowhere else</b> — a till shows the bill and points at the desk.",
 "56_receipts": "Every bill raised today, whatever till raised it, reading one of three states — owing, settled, or credit left. A wristband with money still on it is not the same as a bill that has been paid.",
 "57_pos_tabs": "The waiter's tables. Every bill belongs to a wristband or a room; a free-text table is refused, because that is an account with nobody attached and nothing paid in advance.",
 "58_kitchen_board": "The kitchen queue, with a live timer on each ticket. Stock is consumed when an item is marked <b>ready</b> — not when it is ordered, and not when it is served.",
 "59_bar_board": "The bar board, on the same rule — the pour is what moves the stock.",
 "60_chef_dashboard": "The head chef's own board: the queue, the recipes and the kitchen's stock in one place.",
 "61_pos_spa": "The spa till sells the spa's list and nothing else. Opening a wristband here used to show the whole restaurant menu.",
 "62_pos_water": "The water post: jet ski, boat, kayak, fishing, pool pass — and a restock request that reaches the manager without leaving the till.",
 "63_safety_check": "Safety checks against the boat or jet ski, item by item from that equipment's own checklist. What is due for service is derived from when it was last serviced, not from a date somebody typed.",
 "64_incidents": "An incident filed from any post reaches the manager and the owner in the same request. Before this review, filing one notified nobody.",
 # The person's own phone
 "70_employee_clock": "Clock in — and only from the resort's own network, which is what stops somebody clocking in a colleague from home.",
 "71_employee_profile": "Their own record, and nobody else's.",
 "72_employee_leave": "Leave asked for here, decided by the manager, and the answer comes back.",
 "73_employee_absence": "The absence notice — the screen whose entire purpose is “I am not coming in today”. It could once only be opened by somebody already at work.",
 "74_employee_calendar": "The shifts they are on, and the days the property has marked.",
 "75_employee_notifications": "Their inbox — where an answered grievance now lands, and where the event they are working reminds them.",
 "76_employee_conduct": "Conduct rules by version, with their signature against each. Signing version three does not silently become consent to version four.",
 "77_employee_disputes": "A formal route to raise something, and the status of what they raised.",
 "78_employee_incidents": "Any member of staff can file an incident from their own phone.",
 # The guest
 "90_kiosk_menu": "The kiosk a guest touches: no login screen, no staff tools, the back button disabled. Priced from the same list the till sells from, so a price change is never in two places. A sold-out dish strikes itself through.",
}

ACTS = [
    ("02", "The owner", "What you see, and why you can trust the numbers",
     "Your app is separate from everyone else's. It is not a manager screen with "
     "extra buttons — it is a different application, and it refuses to open at all "
     "for anyone below owner level, at the door, before any screen loads.",
     [k for k in PLATES if k[:2] in ("01","02","03","04","05","06","07","08","09","10","11","12","13","14")]),
    ("03", "Management", "The manager runs the day; you are not in it",
     "The manager's app opens on what is waiting rather than a list of what exists. "
     "Counts sit on the tiles, and only the ones with a person waiting take the "
     "accent colour — so the colour keeps its meaning.",
     [k for k in PLATES if k[:2] in ("20","21","22","23","24","25","26","27","28","29","30","31","32","33","34","35","36","37","38","39")]),
    ("04", "The floor", "The tills, the gate, and the people carrying plates",
     "Each post gets the tools for that post and nothing else. A person signs in "
     "with a four-digit PIN on a shared tablet, and what appears is decided by their "
     "department and today's roster. Every screen below was opened as the person who "
     "works that post, not as an administrator.",
     [k for k in PLATES if k[:2] in ("50","51","52","53","54","55","56","57","58","59","60","61","62","63","64")]),
    ("05", "The staff app", "What each employee carries on their own phone",
     "Separate from the till. This app is a person's own record — their proof of "
     "work — and holds none of the tools for their post.",
     [k for k in PLATES if k[:2] in ("70","71","72","73","74","75","76","77","78")]),
    ("06", "The guest", "What a visitor touches",
     "A guest screen is reached by a member of staff handing the tablet over, never "
     "by typing an address. Try to open the guest menu directly and the app returns "
     "you to the clock — which is the behaviour, not a fault.",
     [k for k in PLATES if k[:2] == "90"]),
]


def main():
    if not EVIDENCE.exists():
        sys.exit(f"No capture log at {EVIDENCE}. Run the capture spec first.")
    ev = {e["id"]: e for e in json.loads(EVIDENCE.read_text(encoding="utf-8"))}

    captured = {k for k, e in ev.items() if e.get("captured")}
    wanted = set(PLATES)
    missing = wanted - captured
    uncaptioned = captured - wanted
    if missing:
        sys.exit("These plates are in the document but were never captured:\n  "
                 + "\n  ".join(sorted(missing)))
    if uncaptioned:
        sys.exit("These plates were captured but nobody wrote a caption:\n  "
                 + "\n  ".join(sorted(uncaptioned)))

    # ── Captions must agree with the plate above them ─────────────────────
    #
    # A caption quoting "KSh 429,750" beside a dashboard reading 444,750 is the
    # exact slop this document claims not to contain, and it happens the moment
    # the system is used again between writing and capturing. So any currency
    # figure written into a caption has to appear in the text that plate
    # actually rendered, or the build stops and says which.
    import re as _re
    drift = []
    for pid, cap in PLATES.items():
        # "KSh&nbsp;?" required a literal &nbsp — so it matched nothing at all
        # and the check passed on a caption that was already wrong. A checker
        # that cannot fail is worse than no checker.
        for fig in _re.findall(r"KSh(?:&nbsp;|&#8209;|\s)\s*([\d,]{3,})", cap):
            seen = " ".join(ev[pid].get("visible_numbers") or [])
            if fig not in seen:
                drift.append(f"{pid}: caption says KSh {fig}; the plate shows "
                             f"{seen or '(no figures at all)'}")
    if drift:
        sys.exit("Captions disagree with their own plates:\n  " + "\n  ".join(drift))

    n = 0
    body = []
    for num, eyebrow, heading, lede, ids in ACTS:
        body.append(f'''
  <section>
    <div class="sec-head">
      <div class="num">{num} &mdash; {escape(eyebrow)}</div>
      <h2>{escape(heading)}</h2>
      <p>{lede}</p>
    </div>
    <div class="plates">''')
        for i, pid in enumerate(ids):
            n += 1
            e = ev[pid]
            wide = ' wide' if i == 0 else ''
            body.append(f'''
      <figure class="plate{wide}">
        <img src="shots/{pid}.jpg" loading="lazy" alt="{escape(e['route'])} as {escape(e['role'])}">
        <figcaption>
          <span class="pnum">PL&nbsp;{n:02d}</span>
          <span class="cap">{PLATES[pid]}
            <span class="prov">Opened at <code>{escape(e['route'])}</code> as <b>{escape(e['role'])}</b>.</span>
          </span>
        </figcaption>
      </figure>''')
        body.append("\n    </div>\n  </section>")

    html = TEMPLATE.replace("<!--ACTS-->", "".join(body)).replace("{{N}}", str(n))
    OUT.write_text(html, encoding="utf-8")
    print(f"built {OUT} — {n} plates across {len(ACTS)} acts")


TEMPLATE = (ROOT / "scripts/proposal_template.html").read_text(encoding="utf-8")

if __name__ == "__main__":
    main()
