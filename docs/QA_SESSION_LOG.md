# Kurahia full-system test log — started 2026-08-25

Backend logic (positive+negative, RBAC, idempotency) is already exhaustively covered
by pytest (769 tests). This log focuses on what pytest CAN'T see: real frontend flows
across all 3 apps (owner_pwa, employee_pwa, station_pwa), for every role, clicking
through every dashboard — plus spot-checking audit trail coverage and noting any
"this is harder than it needs to be" UX friction.

Legend: ✅ pass  ❌ bug (see note)  ⚠️ friction note (works, but clunky)

## Coverage plan
- [ ] owner_pwa: Dashboard, Staff, Roster, Finance, Purchase Approvals, Alerts/Judge,
      Bookings, Disputes, Suggestions, Calendar, Equipment, Reports
- [ ] employee_pwa personal: Clock, Alerts, Profile(+payment), Calendar, Incident,
      Leave, Absence, Conduct
- [ ] employee_pwa manager: Manager hub, Staff, Menu, Cash, Shifts, Attendance,
      Purchases, Front-desk, Roster, Leave approval, Performance
- [ ] station_pwa: full payment flow, waiver signing, safety check submit, band
      lookup real search, check-in real flow (already did nav+landing for all depts)
- [ ] Audit trail spot-check: pick 5 write actions across domains, confirm AuditLog row
- [ ] Negative/edge cases per screen: wrong role, bad input, double-submit

## Findings

### owner_pwa (as amara/owner) — all 10 screens
✅ Dashboard, Alerts, Finance, Purchase Approvals, Reconciliation, Payroll, Staff,
   Feedback, Bookings, Settings — zero console errors, zero unexpected HTTP errors,
   all render real data.
⚠️ Payroll: every recreated staff account (all 11) shows "No wage set" / "0.0h
   worked". Expected — the real register→approve→promote flow never collects wage
   data, only the original seed script did. Someone needs to go set wage_rate per
   employee via Staff screen before payroll is usable for real payroll runs.
✅ Bookings: "Wanjiru Kamau" Checked In at Villa 6, Deposit 0/100,000 shown in
   warning orange — RESOLVED, not a bug. Row is from `app/cli/bookings.py`'s
   demo-seed command (created 2026-08-17, predates this session), which inserts
   a Booking directly at CHECKED_IN for a nice-looking demo card, bypassing the
   API. Verified in code: the real POST /bookings/<id>/confirm endpoint correctly
   rejects confirming with deposit_paid < deposit_required. No fix needed.

### owner_pwa RBAC (as brian/manager, level 5 — should be blocked entirely)
❌→✅ FOUND+FIXED: logging in with a manager's *correct* password silently bounced
   back to the login form, fields cleared, no error — AuthGate correctly blocks
   level<10 on every route, but LoginScreen didn't know that and called
   setAuth+navigate regardless, so AuthGate immediately reversed it with zero
   explanation. Indistinguishable from a wrong password. Likely explains some of
   the earlier "front end refuses login" reports. Fixed: LoginScreen now shows
   "This app is for the owner account only. Use the Kurahia Staff app instead."
   Commit 5ca446d.
