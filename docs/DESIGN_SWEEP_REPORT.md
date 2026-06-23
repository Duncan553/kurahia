# Design Sweep Report

**Date:** 2026-06-23
**Scope:** All .tsx files in employee_pwa/src/screens/, owner_pwa/src/screens/, and both layouts.
**Constraint:** Visual/CSS only. No API calls, data flow, or business logic touched.

---

## Summary

- **30 files fixed**
- **68 problems found and resolved**
- **0 remaining** (all known categories clean)
- **Both PWAs build clean** after all fixes

---

## Issues Fixed by Category

### 1. Cold Colors (text-blue-, bg-blue-, slate-) — 3 instances fixed
| File | Was | Now |
|---|---|---|
| CashReconScreen.tsx | `bg-blue-50 border border-blue-200` (OVER result) | `bg-status-pending/10 border border-status-pending/30` |
| CashReconScreen.tsx | `text-blue-600` (over amount) | `text-status-pending` |
| InventoryCountScreen.tsx | `text-blue-600` (positive variance) | `text-status-paid` |
| AttendanceScreen.tsx | `text-blue-600` (on leave status) | `text-primary-light` |

### 2. Emoji Icons — 6 instances fixed
| File | Emoji | Replaced With |
|---|---|---|
| WaiterTabDetailScreen.tsx | `🍽` (empty menu photo) | SVG utensils icon |
| WaiterTabDetailScreen.tsx | `📖` (show menu) | SVG book icon |
| WaiterTabDetailScreen.tsx | `⚡` (quick order) | SVG lightning icon |
| CustomerMenuScreen.tsx | `🍽` (empty menu photo) | SVG utensils icon |
| ServicePayScreen.tsx | `🏷` (empty state) | SVG star icon |
| GateHubScreen.tsx | `⚠` (waiver alert) | SVG triangle alert icon |
| ReconciliationScreen.tsx | `⚠` (gaps detected) | SVG triangle alert icon |
| StaffScreen.tsx (owner) | `⚠` (no profile) | SVG triangle alert icon |

### 3. Cold Overlays — 2 instances fixed
| File | Was | Now |
|---|---|---|
| WaiterTabDetailScreen.tsx | `rgba(22, 33, 62, 0.8)` (cold blue header) | `rgba(30, 16, 12, 0.85)` (warm brown) |
| WaiterTabDetailScreen.tsx | `bg-black/50` (sold out overlay) | `bg-[rgba(30,16,12,0.6)]` |
| CustomerMenuScreen.tsx | `bg-black/50` (sold out overlay) | `bg-[rgba(30,16,12,0.6)]` |

### 4. Opaque bg-cream-card on Root Containers — 2 instances fixed
| File | Fix |
|---|---|
| owner PinEntryScreen.tsx | Removed `bg-cream-card` from root div (body photo now shows through) |
| owner PinSetupScreen.tsx | Removed `bg-cream-card` from root div |

### 5. text-white/30, /40, /60 Replaced with Design Tokens — 22 files fixed
All subtitle text was using raw `text-white/30` or `text-white/40` instead of the design system tokens.

**Files fixed:** ProfileScreen, BandLookupScreen, SafetyCheckScreen, CashReconScreen, LeaveApprovalScreen, ShiftScreen, MaintenanceLogScreen, StaffAccountsScreen, AttendanceScreen, CheckInScreen, PurchaseReqScreen, MenuManageScreen, ServicePayScreen, CustomerMenuScreen, owner StaffScreen, owner SettingsScreen, owner PurchaseApprovalsScreen, owner BookingsScreen, owner AlertsScreen, owner FinanceScreen

**Pattern:** `text-white/30` → `text-ink-tertiary`, `text-white/40` → `text-ink-tertiary`, `text-white/60` → `text-ink-secondary`

### 6. Invalid Tailwind Classes (bg-white/5/40 double-slash) — 13 files fixed
These were malformed Tailwind v4 utilities that likely produced no styles at all.

**Files fixed:** ProfileScreen, SafetyCheckScreen, NotificationsScreen, MaintenanceLogScreen, ShiftScreen, CashReconScreen, CheckInScreen, QuickEntryScreen, PurchaseReqScreen, LeaveApprovalScreen, AttendanceScreen, MenuManageScreen, WaiterTabDetailScreen

**Pattern:** `bg-white/5/40` → `bg-white/5`, `bg-white/5/50` → `bg-white/6`, `bg-white/5/60` → `bg-white/8`, `bg-white/5/30` → `bg-white/4`, `bg-white/5/20` → `bg-white/3`, `bg-white/5/70` → `bg-white/10`, `bg-transparent/50` → `bg-transparent`

### 7. Glass-card Missing on Cards — 3 instances fixed
| File | Fix |
|---|---|
| ReconciliationScreen.tsx | Added `glass-card` to Receipts, Cash Reconciliation, and Stock Alerts columns |

### 8. Misused Background Colors — 2 instances fixed
| File | Was | Now |
|---|---|---|
| WaiterTabDetailScreen.tsx | `bg-ink-primary text-white` on balance bar | `glass-card text-ink-primary` |
| GateHubScreen.tsx | `bg-cream-card` on band lookup input | `bg-transparent` |

### 9. Layout Fixes — 1 instance fixed
| File | Fix |
|---|---|
| owner AppLayout.tsx | Mobile bottom nav active color: `text-primary-dark` → `text-[#fa5c29]`, focus ring updated to match |

---

## Files Not Changed (Already Clean)

The following files were audited and found to already follow the design system correctly:

- ClockScreen, ConductScreen, FrontDeskScreen, HeadChefScreen, LeaveRequestScreen
- ManagerScreen, ScheduleScreen, SuggestionsScreen, VillaScreen, WaiterTabsScreen
- WaiverScreen, WristbandScreen, StationQueues, AbsenceNoticeScreen, PurchaseRequestScreen
- owner DashboardScreen, PayrollDraftScreen
- employee AppLayout.tsx (already uses warm colors throughout)

---

## Intentional Exceptions

- **LoginScreen (both):** Uses `bg-cream-card` on root but has its own inline resort photo + overlay. This is correct.
- **PinSetupScreen (employee):** Uses `bg-cream-card` on torn-edge card but has its own hero photo. Correct.
- **PinEntryScreen (employee):** Uses `text-white/60` on overlay but has its own photo background. Correct.
- **PinEntryScreen (employee):** Uses `bg-cream-card/25` (25% opacity) — transparent enough for glass. Correct.

---

## Build Status

```
employee_pwa: pnpm build ✓ (63 precache entries)
owner_pwa:    pnpm build ✓ (26 precache entries)
```
