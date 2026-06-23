# Design Rules Audit — Full Sweep

**Date:** 2026-06-23
**Scope:** Every screen in `employee_pwa/src/screens/` (38 files + kiosk) and `owner_pwa/src/screens/` (12 files), plus both `AppLayout.tsx` files.
**Rules source:** `docs/DESIGN_RULES.md`
**Result:** Both PWAs build clean after all fixes.

---

## Summary of violations found and fixed

### 1. border-l-2 on active nav (AI slop tell) — 2 files fixed

| File | Fix |
|------|-----|
| `employee_pwa/src/layouts/AppLayout.tsx` | Removed `border-l-2 border-[#fa5c29]` on active nav, kept `bg-[#fa5c29]/10 text-[#ffb59f]` |
| `owner_pwa/src/layouts/AppLayout.tsx` | Same fix on SideLink component |

### 2. text-white -> text-[#f9dcd5] (warm text) — 40+ files fixed

Every screen had at least 1 `text-white` violation. Fixed on: headings, form inputs, textarea fields, tab active states, employee/guest names, amounts, hover states.

**Exception kept:** `text-white` on colored button backgrounds (`bg-[#fa5c29]`, `bg-ink-primary`, `bg-primary-main`, `gradient-hero`, `bg-status-*`) is acceptable for contrast.

### 3. bg-cream-card on root containers — 4 files fixed

| File | Fix |
|------|-----|
| `employee_pwa/src/screens/LoginScreen.tsx` | `bg-cream-card` -> `bg-[#1e100c]` |
| `employee_pwa/src/screens/PinSetupScreen.tsx` | `bg-cream-card` -> `glass-card` |
| `employee_pwa/src/screens/PinEntryScreen.tsx` | `bg-cream-card/25` -> `glass-card` |
| `owner_pwa/src/screens/LoginScreen.tsx` | `bg-cream-card` -> `bg-transparent` |
| `employee_pwa/src/screens/FrontDeskScreen.tsx` | Active tab `bg-cream-card` -> `bg-white/8` |

### 4. p-3 on cards -> p-4 minimum — 15+ instances fixed

Fixed across: InventoryCountScreen, MenuManageScreen, VillaScreen, ServicePayScreen, PurchaseApprovalsScreen, StaffScreen, CashReconScreen, BandLookupScreen, CheckInScreen, FrontDeskScreen, ClockScreen, AbsenceNoticeScreen, AttendanceScreen, WaiterTabDetailScreen.

### 5. gap-2/gap-3 between card grids -> gap-4 — 20+ instances fixed

Fixed across: LeaveRequestScreen, InventoryCountScreen, WristbandScreen, ServicePayScreen, WaiterTabDetailScreen, WaiterTabsScreen, VillaScreen, HeadChefScreen, ManagerScreen, AttendanceScreen, DashboardScreen (owner).

### 6. mb-4 between sections -> mb-6/mb-8 — 12+ instances fixed

Fixed across: ManagerScreen (3 sections), HeadChefScreen (2 sections), GateHubScreen, BookingsScreen, FinanceScreen, PurchaseApprovalsScreen, StaffScreen, AttendanceScreen, CheckInScreen, ServicePayScreen.

### 7. Bento grid (mixed card sizes) — 4 dashboard screens fixed

| Screen | Before | After |
|--------|--------|-------|
| `ManagerScreen` | `grid-cols-4 md:grid-cols-8` actions | `grid-cols-2 sm:grid-cols-4` |
| `ManagerScreen` | `md:grid-cols-2` budget+stock | `lg:grid-cols-[2fr_1fr]` |
| `HeadChefScreen` | `md:grid-cols-2` uniform | `lg:grid-cols-[2fr_1fr]` (stock wider) |
| `GateHubScreen` | `grid-cols-3` uniform stats | Hero stat (Inside Now) spans 2 cols, 3xl text |
| `DashboardScreen` (owner) | `lg:grid-cols-3` uniform tiles | Bento: tile[0] spans 2 cols on lg |

### 8. max-w violations — 4 files fixed

| File | Before | After |
|------|--------|-------|
| `HeadChefScreen.tsx` | `max-w-5xl` | `max-w-6xl` |
| `WaiterTabsScreen.tsx` | `max-w-5xl` | `max-w-6xl` |
| `WristbandScreen.tsx` | `max-w-5xl` | `max-w-6xl` |
| `FinanceScreen.tsx` | `max-w-3xl` | `max-w-6xl` (dashboard, not form) |
| `ReconciliationScreen.tsx` | `max-w-4xl` | `max-w-6xl` |

### 9. Dark glow shadows on buttons — 2 files fixed

| File | Fix |
|------|-----|
| `employee_pwa/src/screens/LoginScreen.tsx` | Removed `shadow-[0_4px_16px_rgba(250,92,41,0.3)]` |
| `owner_pwa/src/screens/LoginScreen.tsx` | Same fix |

### 10. Tab active state pattern fix (AI slop)

All owner PWA tab filters had `bg-transparent text-white shadow-sm` for active state.
Changed to: `bg-white/10 text-[#f9dcd5]` (glass-compatible, warm text, no shadow).

Fixed in: FinanceScreen, BookingsScreen, PurchaseApprovalsScreen, StaffScreen, SettingsScreen.

---

## Rules with zero violations found

- **bounce/elastic easing:** Not found anywhere. All springs use proper damping.
- **emoji as icons:** Not found. All icons are inline SVG.
- **border-l-2 (outside nav):** None.

## Files that were already clean

- `StationQueues.tsx` — already uses warm palette throughout
- `WaiverScreen.tsx` — already uses `text-ink-primary`, correct `max-w-3xl`
- `owner_pwa PinEntryScreen.tsx` — already clean
- `owner_pwa PinSetupScreen.tsx` — already clean

---

## Build verification

```
employee_pwa: pnpm build -> clean (63 precache entries)
owner_pwa:    pnpm build -> clean (26 precache entries)
```
