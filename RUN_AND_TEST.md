# Run Kurahia locally and test it

Start everything, open every app, sign in as every role.
Dev machine only — these are practice accounts, never production.

---

## 1. Start the servers (4 terminals)

All from the project folder: `cd ~/kurahia`

| # | What | Command | Open in browser |
|---|------|---------|-----------------|
| 1 | **Backend API** | `.venv/bin/flask run --port 5000` | (no page — the apps talk to it) |
| 2 | **Station app** — tills, kitchen, bar, front house, manager | `cd station_pwa && npx vite --port 5176` | http://localhost:5176 |
| 3 | **Owner app** — owner dashboard | `cd owner_pwa && npx vite --port 5174` | http://localhost:5174 |
| 4 | **Staff app** — each person's own phone app | `cd employee_pwa && npx vite --port 5177 --strictPort` | http://localhost:5177 |

**Why 5177 for the staff app:** port 5173 is taken by your other project
(Kamili). If you open 5173 you get the luxury store, not Kurahia.

**Check the backend is up:**
```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:5000/auth/login -H 'Content-Type: application/json' -d '{}'
```
`400` = running. `000` = not running.

**Restart the backend after changing Python code.** It is not in debug mode,
so it does not reload on its own. Stop it with Ctrl+C and run the command again.
(The apps reload by themselves.)

**Database changes** (after pulling new code with migrations):
```bash
FLASK_ENV=development .venv/bin/flask db upgrade
```

---

## 2. Accounts

**Password for every account: `Kurahia1!`**

| Username | Role | Level | Department | Use which app |
|----------|------|-------|------------|---------------|
| amara.wanjiku | owner | 10 | General | Owner app (5174) |
| brian.mwangi | manager | 5 | Management | Station app (5176) → Manage, Events |
| cynthia.achieng | head chef | 3 | Kitchen | Station app → Kitchen board, Chef |
| david.otieno | bar lead | 3 | Bar | Station app → Bar board, Drinks |
| grace.muthoni | front desk | 3 | Front House | Station app → Check-In, Receipts |
| hassan.omondi | gate lead | 3 | Gate | Station app → Gate |
| esther.kamau | spa attendant | 2 | Spa & Gym | Station app → Services |
| francis.njoroge | water lead | 2 | Water Activities | Station app → Waiver, Safety, Payment |
| ivan.kipchoge | waiter | 1 | Restaurant | Station app → Tables |
| joyce.wambua | waiter | 1 | Restaurant | Station app → Tables |
| kevin.mutua | housekeeping | 1 | Housekeeping | Station app |
| lillian.chebet | grounds | 1 | Grounds | Station app |

**Everyone** also has the Staff app (5177): clock in, leave, alerts, profile.

### Things that will stop you (they are rules, not bugs)

- **Login limit: 5 sign-ins per minute** from one computer. Signing in as many
  people quickly → "too many attempts". Wait a minute.
- **Clock in first.** Taking orders, cooking, taking payments all need the
  person clocked in (Staff app → Clock). Clock-in only works on the resort's
  WiFi list — on your dev machine localhost is allowed.
- **One browser tab = one signed-in person** per app. To be two people at once
  (e.g. manager and chef), use a second browser or a private window.
- **Kitchen can't start an event dish before the event's day.**
- **Only a manager takes an event's money. Only front desk settles a villa.**

---

## 3. Test an event from start to finish (as a person would)

1. **Owner** (5174) → Events → set *Minimum booking fee* and *How far a manager may discount*.
2. **Manager** (5176) → Manage → Villas & venues → add a venue (fee, guests it holds).
3. **Manager** → Events → *+ Create Event* → pick the venue, guests, booking fee.
4. **Manager** → the event → *Staff & stock*:
   - add crew with a **job** (Kitchen, Bar, Service)
   - *Menu & bill*: add dishes × plates (discount + reason if any)
   - read the stock line — if short, *Put these on purchase requests*
   - *Take booking fee* → *Confirm it*
5. **Manager** → Manage → purchase requests → *Propose budget* → *Approve — buy it*;
   then *Receive* the delivery with a receipt photo.
6. **On the event's day, Manager** → *Send to kitchen & bar*.
7. **Chef** (cynthia.achieng) → Kitchen → **Events** tab → *Start Cooking* → *Ready for Pickup*.
   **Bar lead** (david.otieno) → Bar → Events tab → same.
8. **Waiters on the crew** → their screen shows "… ready — take it to <venue>".
9. **Manager** → event → *Take payment* → *Start* → *Finish*.
10. **Owner** → Events → cost, profit on food & drink, discount, owing.

## 4. Test a villa stay

1. **Front desk** (grace.muthoni) → Check-In → *+ New booking* → villa, guest, dates.
2. Arrivals → *Record deposit* → *Confirm* → *Check In* (room charged once, all nights).
3. **Waiter** → Tables → the villa → order food → **chef** marks ready → waiter marks served.
4. **Front desk** → Occupancy → *Change leaving date* (stay longer / leave early).
5. Occupancy → *Bill & pay* → pay → *Check out*.

---

## 5. Useful commands

```bash
# All backend tests (~3 min) + the timing tests run separately
.venv/bin/python -m pytest -n 4 -q
.venv/bin/python -m pytest -q -m production_hashing

# Type-check an app (plain `tsc --noEmit` checks NOTHING here)
cd station_pwa && npx tsc -b --force

# Send reminders that are due / check what events still need
FLASK_ENV=development .venv/bin/flask events deliver-due
FLASK_ENV=development .venv/bin/flask events check-readiness

# Rebuild the proposal page and PDF
.venv/bin/python scripts/build_proposal.py
.venv/bin/python scripts/proposal_pdf.py
# → docs/proposal/Waterfront_Juja_Proposal.pdf
```

## 6. Still open (next session)

- Event screenshots for the proposal (needs a capture run).
- Fill the five prices in the proposal.
- Two ways a bill with no guest name can still be opened; reorder drafts the
  manager never sees; display fixes ("90.00x", "× 1.0000", "Checked Out").
- Add `flask events check-readiness` hourly to the live server's cron (line in DEPLOY.md).
