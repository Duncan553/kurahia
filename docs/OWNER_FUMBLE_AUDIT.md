# Owner PWA Accountability Audit

> Conducted 2026-06-16. Read-only. No code changes.
> Reference: `docs/FRONTEND_DESIGN.md` — Sections F-15, F-16, O-1 through O-6.
> Evidence: direct file reads of all owner_pwa/src/screens/*.tsx

---

## Summary Table

| Section | Status | Fumble Type | Evidence |
|---|---|---|---|
| 1. Dashboard 5 questions | PARTIAL | Calendar tile missing; week events not rendered; no dept spending chart; no last-period comparison | `DashboardScreen.tsx` — no CalendarTile, `week_calendar` fetched but unused |
| 2. Purchase approval (owner final sign-off) | MISSING | Dashboard shows `pending_approvals: 2` but no screen exists to approve/reject | No purchase approval screen in owner PWA router |
| 3. Budget control | MISSING | `department_budgets` returned by backend but `FinanceScreen` is a 9-line placeholder | `FinanceScreen.tsx` line 1-9 |
| 4. Staff control (create managers) | MISSING | `StaffScreen.tsx` is a 9-line placeholder. Owner cannot create managers from their phone. | `StaffScreen.tsx` line 1-9 |
| 5. Override & dispute authority | MISSING | No disputes screen. No suggestion reading/responding screen. SuggestionsTile shows count only, taps nowhere. | No disputes route in `main.tsx` |
| 6. Remote access + push | PASS | Tailscale documented, push wired (F-17), WhatsApp stub present | `docs/DEPLOY.md`, `sw.ts`, `app/services/notifications/whatsapp.py` |
| 7. JudgeAlert all 7 types | PARTIAL | Backend only fires 3 types (RATIO, SPOILAGE_SPIKE, SAFE_COUNT_MISMATCH). 4 others don't exist. DISMISSED status missing. | `app/judge/engine.py`, `AlertsScreen.tsx` |
| 8. Two-tier suggestion box (owner reads) | PARTIAL | SuggestionsTile shows split count. No screen to read or respond. No href on tile. | `DashboardScreen.tsx` SuggestionsTile — no `href` prop |
| 9. 4th frontline channel (employee OWNER_PRIVATE) | PASS | Employee SuggestionsScreen has OWNER_PRIVATE toggle, clearly labelled | `employee_pwa/src/screens/SuggestionsScreen.tsx` |
| 10. Period close | PASS | Hold-to-confirm, safe count entry, SAFE_COUNT_MISMATCH fires, freezes records | `ReconciliationScreen.tsx` |
| 11. Reports | PARTIAL | Reconciliation ✓, Payroll ✓. Finance dashboard (GET /finance/dashboard) not wired. Audit log — CLI only, no owner screen. | `FinanceScreen.tsx` placeholder |
| 12. Override audit trail | PARTIAL | AlertsScreen has Acknowledge but no AuditLine drilldown per spec. No dismiss-with-reason field. | `AlertsScreen.tsx` — ackMut sends no notes field |
| 13. Variance investigation flow | MISSING | AlertsScreen lists alerts but no tap-through to item variance detail or dept head explanation flow | `AlertsScreen.tsx` — no per-alert detail route |
| 14. Calendar & planning triggers | FUMBLE | `/dashboard/calendar` fetched but no tile renders it. `week_calendar` in overview fetched but never displayed anywhere on dashboard. | `DashboardScreen.tsx` — 9 tiles present, zero CalendarTile |
| 15. Cross-data pattern recognition | MISSING | No screen cross-references feedback scores with absence data. StaffTile shows top/bottom performers but not correlated with attendance. | No analytics/insights screen in router |
| 16. Daily ownership rhythm (judge async) | PASS | Judge runs via `flask judge run-daily` CLI, non-blocking | `app/judge/engine.py` |

---

## Detailed Findings

### Section 1 — Dashboard: what's built vs what spec says

**Spec (O-1, F-15):** 10 tiles, each loading independently. `week_calendar` data included. Top bar: Revenue today | Alerts open | Bookings this weekend.

**Built:**
- 10 tiles ✓ (Revenue, ActiveGuests, OpenBookings, StaffOnDuty, Alerts, LowStock, Finance, Feedback, Suggestions, Equipment)
- Top bar ✓ (Revenue | Alerts | Active Bookings)
- Tile-level independent loading ✓

**Missing:**
- `week_calendar` is included in the `/dashboard/overview` API response but NO tile renders it. Calendar data hits the network and is silently discarded.
- No comparison to last period (not in spec either, but worth noting)
- No department spending bar chart (FinanceScreen placeholder means there's nowhere for this)
- SuggestionsTile has no `href` — owner sees the count but can't tap through to read them

---

### Section 2 — Purchase approval

**Spec (F-11, manager chunk):** Three-tier: staff submits → manager proposes → owner approves. `POST /inventory/purchase-requests/<id>/approve` is the owner's endpoint.

**Backend state:** `GET /dashboard/finance` returns `pending_approvals: 2` — live right now.

**Built in owner PWA:** Nothing. FinanceTile on dashboard shows "Pending approvals: 2" as text only. No screen to navigate to, no approve/reject action. The owner sees the number and is helpless.

---

### Section 3 — Budget control

**Spec:** Set monthly budgets per department. See spending vs budget with 80%/90%/100% warnings. Block requests when over budget (owner unlocks).

**Backend state:** `GET /dashboard/finance` returns `department_budgets: [{'budgeted': '0', 'department': 'General'}, ...]` — 0 across all depts because no budgets set.

**Built:** FinanceScreen.tsx is 9 lines: card + "Coming in F-7+". Nothing.

---

### Section 4 — Staff control

**Spec:** Owner creates managers from owner PWA. Reset locked accounts. Set initial PINs.

**Backend:** All endpoints exist (`POST /users`, `POST /auth/reset-lockout/<id>`).

**Built:** StaffScreen.tsx is 9 lines: card + "Coming in F-7+". Manager creation must be done via employee PWA at `/manager/staff` — which means the owner must log into the employee app on their phone to create a manager. This is architecturally wrong for the solo-owner model.

---

### Section 5 — Override & dispute authority

**Spec:** Owner sees disputes escalated past manager. Owner responds to OWNER_PRIVATE suggestions.

**Built:** Nothing. No disputes screen. No suggestion detail screen. The DashboardScreen `StaffData` type includes `open_disputes: { management: number; owner_private: number }` but it's fetched and not rendered in any tile. The SuggestionsTile shows the count but has no `href` to navigate anywhere.

---

### Section 7 — JudgeAlert types

**Spec says 7 alert types (from user reference):** RATIO, SPOILAGE_SPIKE, CASH_SHORTFALL_PATTERN, MPESA_FLAGGED, BANK_FLAGGED, VOID_ABUSE, SAFE_COUNT_MISMATCH, BUDGET_EXCEEDED.

**What backend actually fires:**
- RATIO ✓ (`engine.py` — ratio analysis)
- SPOILAGE_SPIKE ✓ (`engine.py` — spoilage analysis)
- SAFE_COUNT_MISMATCH ✓ (fired by `POST /finance/close-period`)
- CASH_SHORTFALL_PATTERN ✗ — does not exist in engine
- MPESA_FLAGGED ✗ — does not exist in engine
- BANK_FLAGGED ✗ — does not exist in engine
- VOID_ABUSE ✗ — does not exist in engine
- BUDGET_EXCEEDED ✗ — does not exist in engine

**AlertStatus lifecycle:**
- OPEN ✓
- ACKNOWLEDGED ✓ (implemented in AlertsScreen and backend)
- RESOLVED ✗ — not in `AlertStatus` enum
- DISMISSED ✗ — not in `AlertStatus` enum, spec says "dismissed alerts move to separate section, don't disappear"

**AlertsScreen icons:** Only has `RatioIcon`, `SpoilageIcon`, and a generic `SafeIcon` for everything else. No icons for the 5 missing types.

---

### Section 8 — Two-tier suggestions

**Backend:** `GET /dashboard/suggestions` correctly returns `management: []` and `owner_private: []` separately. Query-level filter is structural — owner sees all, non-owners see empty `owner_private`.

**Frontend:** SuggestionsTile shows `owner_private: {newPrivate}` and `management: {newMgmt}` count. That's it. No `href`. Owner sees "Owner-private: 0 · Management: 0" and can't click through. No screen exists to read or respond to suggestions in the owner PWA.

---

### Section 10 — Period close (PASS — evidence)

`ReconciliationScreen.tsx` correctly implements:
- Date picker + `/finance/reconciliation?date=` query ✓
- Three-column layout: Receipts | Cash Reconciliation | Stock Alerts ✓
- Hold-to-confirm (2s) for Close Period ✓
- Safe count entry modal before submitting ✓
- `POST /finance/close-period` with `{ date, safe_count, idempotency_key }` ✓
- `period_closed` flag renders "Period closed" state ✓

---

### Section 11 — Reports

| Report | Status | Evidence |
|---|---|---|
| Three-way reconciliation | ✓ BUILT | `ReconciliationScreen.tsx` |
| Payroll draft (export CSV) | ✓ BUILT | `PayrollDraftScreen.tsx` |
| Financial dashboard `GET /finance/dashboard` | ✗ MISSING | `FinanceScreen.tsx` placeholder |
| Audit log access for owner | ✗ MISSING | CLI only: `flask audit verify-chain` |

---

### Section 12 — Alert acknowledge with audit trail

**Spec (O-3):** "AlertCard shows AuditLine drilldown. Dismissed alerts move to separate section."

**Built:** AlertsScreen sends `POST /judge/alerts/<id>/acknowledge` with no body. No notes/reason field. No AuditLine component rendered below each alert. No DISMISSED filter — only open | acknowledged | all.

---

### Section 14 — Calendar (FUMBLE)

`DashboardScreen` fetches `week_calendar` as part of the `OverviewData` type:
```typescript
interface OverviewData {
  week_calendar: { title: string; date: string; is_peak: boolean; type: string }[]
  // ...
}
```

The data is fetched on every dashboard load. It is never rendered. Zero lines of JSX reference `data!.week_calendar`. The backend `/dashboard/calendar` endpoint returns `calendar_entries` and `events` — also never rendered.

The 10-tile grid has: Revenue, ActiveGuests, OpenBookings, StaffOnDuty, Alerts, LowStock, Finance, Feedback, Suggestions, Equipment. No CalendarTile. The calendar data travels from backend to frontend and disappears.

---

## O-6: SettingsScreen — The Biggest Fumble

**Spec (O-6):** "Department management, role creation, judge baseline tuning, socket status. Four tabs: Departments | Roles | Judge Baselines | Socket Status. Backend: GET/POST/PATCH /admin/departments, /admin/roles, /admin/baselines, GET /finance/mpesa/status, /finance/bank/status, /finance/card/status, /notifications/whatsapp/status"

**Built:**
```tsx
export default function SettingsScreen() {
  const { size: fontSize, changeSize: changeFontSize } = useFontSizePref()
  return (
    <div className="p-4 max-w-md mx-auto space-y-6">
      <h1>Settings</h1>
      // Font size toggle — S / M / L
    </div>
  )
}
```

**What's missing:** The entire screen. All four admin tabs. Dept management, role creation, judge baseline tuning, socket status diagnostics — none of it exists. What's there (font size) belongs in a profile/preferences section, not the owner's admin Settings screen.

The backend for all four tabs is fully built and tested.

---

## LIST A — Features in Owner PWA NOT in the Locked Reference

1. **Font size settings as the entire SettingsScreen** — The spec says Settings should be Departments | Roles | Judge Baselines | Socket Status. Font size is a personal preference (built correctly in the employee ProfileScreen). Having it as the only content in the owner's Settings screen is wrong.

2. **Finance nav item** — Leads to a 9-line placeholder. If it's not built, it shouldn't be in the nav. A missing screen is better than a nav item that dead-ends.

3. **BookingsScreen "Coming in F-7+"** placeholder — The route exists, the nav item exists, the screen says "Coming in F-7+". F-7 shipped. Either build it or remove it from nav until it's built.

4. **StaffScreen "Coming in F-7+"** — Same issue. F-7+ shipped. The placeholder has been sitting there since Phase D began.

---

## LIST B — Owner Authority from the Reference Missing from the Frontend

1. **Purchase request final approval** — `pending_approvals: 2` is live in the DB right now. Owner cannot act on it from the PWA.

2. **Budget setting per department** — All dept budgets are KSh 0 because there's no UI to set them.

3. **Manager account creation from owner PWA** — Owner must log into the employee PWA to create managers. Architecturally wrong.

4. **Read and respond to OWNER_PRIVATE suggestions** — Count is visible. Content is not.

5. **Read and respond to disputes escalated past manager** — No disputes screen at all.

6. **Calendar tile on dashboard** — Planning triggers, Kenyan holidays, school holiday periods — all seeded, none visible.

7. **Alert dismiss with reason + AuditLine drilldown** — Only acknowledge (no notes). No audit line below each alert.

8. **Alert types: CASH_SHORTFALL_PATTERN, MPESA_FLAGGED, BANK_FLAGGED, VOID_ABUSE, BUDGET_EXCEEDED** — Not in backend engine. Backend can't fire them. Frontend can't show them. Both sides need work.

9. **Alert RESOLVED and DISMISSED status lifecycle** — Only OPEN → ACKNOWLEDGED exists. The spec says dismissed alerts stay visible in a separate section.

10. **Financial dashboard** — `GET /finance/dashboard` (revenue by method, period breakdowns) is not wired to any owner screen. FinanceScreen is a placeholder.

11. **Audit log access from owner PWA** — Currently CLI-only (`flask audit verify-chain`). Owner should be able to spot-check without SSH access.

12. **Dept management, role creation, judge baseline tuning, socket status diagnostics** — The entire O-6 Settings/Admin spec is unbuilt.

13. **Staff performance scores by employee** — PayrollDraftScreen shows payroll hours only. No per-staff performance scores (spec: "per-staff performance scores from guest feedback").

14. **Variance investigation flow** — Tap alert → see item/amount/dept detail → dept head explanation → owner accept/escalate. Only step 1 exists (see the alert).

15. **Cross-data insights** — "Spa rating dropped — Amina's absence may be a factor." No analytics screen exists.

---

*End of audit. No code changes. Waiting for instruction on what to fix first.*
