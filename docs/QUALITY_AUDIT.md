# Quality Audit — Screen Files

**Date:** 2026-06-23
**Scope:** 9 screen/layout files across employee_pwa and owner_pwa
**Auditor:** Automated quality sweep

---

## Summary

| Check                  | Status |
|------------------------|--------|
| Builds                 | PASS — both PWAs compile cleanly |
| Hooks rules            | PASS — all hooks at top level, unconditional |
| Loading/empty/error    | PASS — all data-dependent sections covered |
| Accessibility          | FIXED — added aria-labels, focus-visible rings |
| Cold color remnants    | FIXED — replaced non-palette colors with design tokens |
| Consistency            | FIXED — header sizing corrected |

---

## Files Audited

1. `owner_pwa/src/screens/DashboardScreen.tsx`
2. `owner_pwa/src/layouts/AppLayout.tsx`
3. `employee_pwa/src/screens/ClockScreen.tsx`
4. `employee_pwa/src/screens/WaiterTabsScreen.tsx`
5. `employee_pwa/src/screens/StationQueues.tsx`
6. `employee_pwa/src/screens/GateHubScreen.tsx`
7. `employee_pwa/src/screens/ManagerScreen.tsx`
8. `employee_pwa/src/screens/HeadChefScreen.tsx`
9. `employee_pwa/src/layouts/AppLayout.tsx`

---

## Findings & Fixes

### CRITICAL — Cold Color Palette Violations

#### Employee AppLayout.tsx
- **Issue:** Sidebar, mobile header, and bottom nav used `rgba(11, 17, 32, 0.95)` (cold blue-grey) instead of warm `rgba(30, 16, 12, 0.95)`.
- **Issue:** Nav links used `text-white/40`, `text-white/70` instead of warm tokens (`text-[#aa8980]`, `text-[#f9dcd5]`).
- **Issue:** Active nav state used `bg-white/8 text-white` instead of `bg-[#fa5c29]/10 text-[#ffb59f]`.
- **Fix:** Replaced all 3 background colors and all nav text colors with warm palette equivalents matching owner_pwa.

#### HeadChefScreen.tsx
- **Issue:** Used `text-emerald-400` (raw Tailwind) instead of `text-status-paid` design token.
- **Issue:** Used `text-emerald-400/10` and `bg-emerald-400/10` in ticket status.
- **Fix:** Replaced with `text-status-paid` and `bg-status-paid/10`.

#### ManagerScreen.tsx
- **Issue:** Used `text-white`, `text-white/30`, `text-white/60`, `text-white/80`, `text-white/40`, `text-white/20` throughout (14+ instances) instead of warm design tokens.
- **Fix:** Bulk-replaced: `text-white` -> `text-ink-primary`, `text-white/30` -> `text-ink-tertiary`, `text-white/60` -> `text-ink-secondary`, `text-white/80` -> `text-ink-primary/80`, `text-white/40` -> `text-ink-tertiary/80`, `text-white/20` -> `text-ink-tertiary/60`.

#### GateHubScreen.tsx
- **Issue:** Used `text-white` for body text (stats, headings, labels, results) — 15+ instances.
- **Fix:** Replaced body-text `text-white` with `text-ink-primary`. Kept `text-white` only on colored button backgrounds (bg-primary-dark, gradient-hero).

### HIGH — Accessibility Gaps

#### WaiterTabsScreen.tsx
- **Issue:** Wristband number input missing `aria-label`.
- **Issue:** Table card buttons missing `focus-visible` ring.
- **Issue:** Wristband input missing `focus-visible` ring.
- **Fix:** Added `aria-label="Wristband number"`, `focus-visible:ring-2 focus-visible:ring-[#fa5c29]`, and `aria-label="Open tab {reference}"` to card buttons.

#### StationQueues.tsx
- **Issue:** "Start Cooking", "Bump", and "Mark Ready" action buttons missing `aria-label` and `focus-visible` ring.
- **Fix:** Added dynamic `aria-label` (e.g., `Start cooking {item}`) and `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]` to all 3 button variants.

#### GateHubScreen.tsx
- **Issue:** "Issue Band" and "Look up" buttons missing `aria-label` and `focus-visible` ring.
- **Issue:** Band number input missing `focus-visible` ring.
- **Fix:** Added `aria-label` and `focus-visible:ring-2 focus-visible:ring-[#fa5c29]` to both buttons and the input.

### MEDIUM — Consistency

#### DashboardScreen.tsx (owner_pwa)
- **Issue:** Resort Health h2 used `text-xl` instead of standard `text-2xl` and used `text-ink-primary` instead of explicit `text-[#f9dcd5]`.
- **Fix:** Changed to `text-2xl font-serif font-bold text-[#f9dcd5]`.

---

## No Issues Found

- **owner_pwa/src/screens/DashboardScreen.tsx** — Clean use of design tokens, proper loading/error/empty states, good aria-labels, glass-card usage, tabular-nums on numbers.
- **owner_pwa/src/layouts/AppLayout.tsx** — Warm palette throughout, proper focus-visible rings, good nav labels.
- **employee_pwa/src/screens/ClockScreen.tsx** — Excellent: full loading skeleton, no-profile state, error state with retry, proper focus-visible ring on clock button, aria-labels on all interactive elements.

---

## Out of Scope (flagged for future audit)

Files not in audit list but containing non-palette colors:
- `employee_pwa/src/screens/VillaScreen.tsx` — uses `amber-200/40`, `amber-900/30`
- `employee_pwa/src/screens/ServicePayScreen.tsx` — uses `emerald-400`, `emerald-500`
- `employee_pwa/src/screens/StaffAccountsScreen.tsx` — uses `amber-600`, `amber-50`
