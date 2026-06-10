# F-11.8 Button + Contrast Audit

> Read-only audit. Fixes land in the follow-up commit (F-11.8b).

---

## Color palette (hex + approx WCAG luminance)

| Token            | Hex      | Lum   |
|------------------|----------|-------|
| `cream-card`     | #F4EDDF  | 0.87  |
| `cream-alt`      | #ECE3D0  | 0.80  |
| `ink-primary`    | #1F1B14  | 0.012 |
| `ink-secondary`  | #5C5147  | 0.09  |
| `ink-tertiary`   | #8C7E6F  | 0.24  |
| `primary-dark`   | #8C3E2C  | 0.097 |
| `primary-main`   | #B4533C  | 0.14  |
| `primary-light`  | #D88A6E  | 0.31  |
| `status-failed`  | #A04438  | 0.12  |

### Critical contrast pairs

| Text             | Background    | Ratio  | AA? (4.5:1) |
|------------------|---------------|--------|-------------|
| `cream-card`     | `primary-dark`| ~13:1  | ✓ AAA       |
| `cream-card`     | `status-failed`| ~10:1 | ✓ AAA       |
| `ink-primary`    | `cream-card`  | ~18:1  | ✓ AAA       |
| `ink-secondary`  | `cream-card`  | ~6:1   | ✓ AA        |
| `ink-secondary`  | `cream-alt`   | ~5.5:1 | ✓ AA        |
| `ink-tertiary`   | `cream-card`  | ~3.2:1 | ✗ FAIL      |
| `ink-tertiary`   | `cream-alt`   | ~2.9:1 | ✗ FAIL      |
| `primary-dark`   | `cream-card`  | ~6.3:1 | ✓ AA        |
| `status-failed`  | `cream-card`  | ~5.4:1 | ✓ AA        |
| `white/70`       | dark overlay  | ~4:1   | borderline  |

> **`ink-tertiary` on any cream surface fails WCAG AA.** Used heavily for inactive
> tab/chip labels and link-style text buttons — the main systemic contrast issue.

---

## Issue legend

| Code | Meaning                                |
|------|----------------------------------------|
| T    | Touch target < 44px                    |
| C    | Contrast < 4.5:1                       |
| D    | Disabled state missing or wrong        |
| V    | Wrong or inconsistent variant          |
| L    | Loading state missing                  |

---

## employee_pwa screens

### LoginScreen

| Button                     | Variant (raw) | Bg ctx           | Text color         | Issues |
|----------------------------|---------------|------------------|--------------------|--------|
| Submit "Sign in ↗"         | primary (raw) | `primary-dark`   | `cream-card`       | —      |
| "Use PIN instead"          | link (raw)    | dark hero overlay| `white/70`         | T, C   |

- **T**: "Use PIN instead" has zero padding — no explicit height, raw text inline. Tap area is only ~18px.
- **C**: `text-white/70` on dark overlay is ~4:1. Borderline — passes large-text AA (3:1) but not normal-text AA (4.5:1) at `text-xs`.
- Raw `<button>` instead of `<Button>` component. Both buttons manually implement spinners in JSX.

---

### PinEntryScreen

| Button                     | Variant        | Bg ctx       | Text color         | Issues |
|----------------------------|----------------|--------------|--------------------|--------|
| Digit keys (0–9)           | custom (raw)   | `white`      | `ink-primary`      | —      |
| Backspace (⌫)              | ghost (raw)    | transparent  | `ink-tertiary`     | C      |
| "Use password instead"     | link (raw)     | cream bg     | `ink-secondary`    | T      |
| Lockout modal OK           | secondary `<Button>` | `cream-card` | `ink-primary` | — ✓  |

- **C**: Backspace icon is `text-ink-tertiary` on transparent (cream bg) → 3.2:1. Fail.
- **T**: "Use password instead" is `text-xs` inline text, zero padding — ~18px tap target.
- Digit keys: `min-h-[64px]` ✓ excellent.

---

### PinSetupScreen

| Button                     | Variant        | Bg ctx        | Text color      | Issues |
|----------------------------|----------------|---------------|-----------------|--------|
| Digit keys (0–9)           | custom (raw)   | `white`       | `ink-primary`   | —      |
| Submit "Set PIN & sign in" | primary (raw)  | `primary-dark`| `cream-card`    | — ✓   |
| "Back to login"            | link (raw)     | cream bg      | `ink-secondary` | T      |

- **T**: "Back to login" is `text-xs uppercase` with zero padding — ~18px tap target.
- Submit uses `py-3.5` (~56px) ✓.

---

### ClockScreen

| Button                     | Variant       | Bg ctx (clock-in)      | Text        | Issues |
|----------------------------|---------------|------------------------|-------------|--------|
| Clock In / Clock Out       | primary (raw) | `primary-dark` / `cream-card` | `cream-card` / `primary-dark` | — ✓ |

- `h-16` = 64px, full-width ✓. Focus ring ✓. Disabled state ✓. Only screen that uses `motion.button` with whileTap natively ✓.
- No `<Button>` component but implementation is equivalent — not an issue.

---

### ScheduleScreen

| Button          | Variant      | Bg ctx                | Text             | Issues |
|-----------------|--------------|-----------------------|------------------|--------|
| "Retry" inline  | link (raw)   | `status-pending/10`   | inherited (none) | T, V   |

- **T + V**: `<button className="ml-2 underline font-medium">` — no color, no padding, no focus ring. Inherits `text-status-pending` from parent container. Touch target is near zero.

---

### NotificationsScreen

| Button               | Variant      | Bg ctx      | Text           | Issues |
|----------------------|--------------|-------------|----------------|--------|
| Notification rows    | ghost (raw)  | transparent | `ink-primary` (unread) / `ink-secondary` (read) | — |

- `py-4` = ~52px total ✓. Disabled state: `opacity-50 cursor-wait` ✓.

---

### ProfileScreen

| Button                  | Variant     | Bg ctx     | Text             | Issues |
|-------------------------|-------------|------------|------------------|--------|
| Navigation rows         | ghost (raw) | `cream-card`| `ink-primary`   | — ✓   |
| Sign Out                | danger (raw)| transparent | `status-failed` | — ✓   |

- Nav rows: `p-4 rounded-2xl` = ~48px+ ✓. Good spacing.
- Sign out: `py-3 text-status-failed` on cream bg → 5.4:1 ✓.

---

### LeaveRequestScreen

| Button                    | Variant         | Bg ctx                         | Text              | Issues |
|---------------------------|-----------------|--------------------------------|-------------------|--------|
| Leave type chips (active) | primary-tint (raw) | `primary-dark/10`           | `primary-dark`    | T      |
| Leave type chips (idle)   | secondary (raw) | `cream-card`                   | `ink-secondary`   | T      |
| Submit "Submit Request"   | primary (raw)   | `primary-dark`                 | `cream-card`      | — ✓   |

- **T**: Leave type chips are `py-2.5` (~40px) — close but below 44px on small phones.
- Submit: `py-4 rounded-2xl` → ~56px ✓. Disabled + loading ✓.

---

### AbsenceNoticeScreen

| Button                    | Variant         | Bg ctx            | Text              | Issues |
|---------------------------|-----------------|-------------------|-------------------|--------|
| Reason chips (active)     | primary-tint (raw)| `primary-dark/10`| `primary-dark`    | T      |
| Reason chips (idle)       | secondary (raw) | `cream-card`      | `ink-secondary`   | T      |
| Submit                    | primary (raw)   | `primary-dark`    | `cream-card`      | — ✓   |

- **T**: Reason chips `py-2` only → ~32px. Clear fail.

---

### ConductScreen

| Button                        | Variant           | Bg ctx (ready)  | Text           | Issues |
|-------------------------------|-------------------|-----------------|----------------|--------|
| "Sign Now" (scroll complete)  | primary (raw)     | `primary-dark`  | `cream-card`   | — ✓   |
| "Sign Now" (not ready)        | disabled (raw)    | `ink-tertiary/15`| `ink-tertiary`| C      |

- **C**: Not-ready state: `text-ink-tertiary` on `ink-tertiary/15` background ≈ ~1.5:1. Extremely low. Intentional "unavailable" feel but still renders clickable text.
- The `disabled` prop IS set when not ready, so it won't fire. But text is invisible in practice.

---

### SuggestionsScreen

| Button                  | Variant           | Bg ctx (active) | Text             | Issues |
|-------------------------|-------------------|-----------------|------------------|--------|
| Category chips (active) | primary-tint (raw)| `primary-main/10`| `primary-main`  | T      |
| Category chips (idle)   | ghost (raw)       | transparent     | `ink-secondary`  | T      |
| Submit                  | primary (raw)     | `primary-dark`  | `cream-card`     | — ✓   |

- **T**: Category chips inside tab-strip container, `flex overflow-hidden` with no min-height. Tap target ~36px.
- Submit `py-4` ✓.

---

### BandLookupScreen

| Button        | Variant       | Bg ctx        | Text        | Issues |
|---------------|---------------|---------------|-------------|--------|
| "Search"      | primary (raw) | `primary-dark`| `cream-card`| — ✓   |

- `px-5 py-3` → ~44px ✓. Disabled + focus ring ✓. Loading spinner ✓. Clean.

---

### WristbandScreen

| Button              | Variant         | Bg ctx        | Text             | Issues |
|---------------------|-----------------|---------------|------------------|--------|
| "Issue Band"        | primary (raw)   | `primary-dark`| `cream-card`     | — ✓   |
| Modal: Cancel       | secondary (raw) | transparent   | `ink-secondary`  | — ✓   |
| Modal: Confirm      | primary (raw)   | `primary-dark`| `cream-card`     | — ✓   |

- Issue Band: `py-4` ✓. Modal buttons: `py-3 flex-1` ≈ 44px with text ✓. Clean.

---

### CheckInScreen

| Button              | Variant        | Bg ctx        | Text           | Issues |
|---------------------|----------------|---------------|----------------|--------|
| Tab pills (active)  | primary (raw)  | `primary-dark`| `cream-card`   | T      |
| Tab pills (idle)    | ghost (raw)    | transparent   | `ink-secondary`| T, C   |
| Check In            | primary (raw)  | `primary-dark`| `cream-card`   | — ✓   |
| Check Out           | danger (raw)   | `status-failed`| `cream-card`  | — ✓   |
| "More" (drawer)     | secondary (raw)| `cream-alt`   | `ink-primary`  | — ✓   |

- **T**: Tab pills `py-2` → ~32px. Fail.
- **C**: Idle tab `text-ink-secondary` is fine (6:1) but inactive labels use `text-ink-tertiary` → 3.2:1.

---

### WaiverScreen

| Button        | Variant       | Bg ctx          | Text        | Issues |
|---------------|---------------|-----------------|-------------|--------|
| Submit waiver | primary (raw) | `primary-dark`  | `cream-card`| — ✓   |

- `py-4 rounded-2xl` ✓.

---

### SafetyCheckScreen

| Button                     | Variant       | Bg ctx          | Text              | Issues |
|----------------------------|---------------|-----------------|-------------------|--------|
| Equipment rows             | ghost (raw)   | `cream-card`    | `ink-primary`     | — ✓   |
| Back/header icon button    | ghost (raw)   | transparent     | `ink-secondary`   | T      |
| Check item rows            | ghost (raw)   | `cream-card`    | `ink-primary/secondary` | — |
| Submit "Submit Safety Log" | primary (raw) | `primary-dark`  | `cream-card`      | — ✓   |

- **T**: Back icon `p-1.5` = ~36px. Fail.
- Submit `py-4` ✓. Equipment rows `p-4` ✓.

---

### InventoryCountScreen

| Button                       | Variant         | Bg ctx           | Text              | Issues |
|------------------------------|-----------------|------------------|-------------------|--------|
| Dept chips (owner, active)   | primary (raw)   | `primary-dark`   | `cream-card`      | T      |
| Dept chips (owner, idle)     | secondary (raw) | `cream-card`     | `ink-secondary`   | T      |
| Tab pills (count/variance)   | ghost/primary   | `cream-card`/transparent | mixed     | T      |
| Submit count row             | primary-sm (raw)| `primary-dark`   | `cream-card`      | T      |
| Add Item icon (+ button)     | primary-sm (raw)| `primary-dark`   | `cream-card`      | T      |
| Watchlist toggle             | toggle (raw)    | conditional      | conditional       | T      |
| Add Item submit              | primary (raw)   | `primary-dark`   | `cream-card`      | — ✓   |
| "Generate Report"            | primary-sm (raw)| `primary-dark`   | `cream-card`      | — ✓   |

- **T**: Dept chips `py-2 px-3` → ~32px. Tab pills `py-2` → ~32px. Submit count `py-2.5` → ~40px. All fail.
- Add Item submit `py-4` ✓.

---

### PurchaseRequestScreen

| Button        | Variant       | Bg ctx        | Text        | Issues |
|---------------|---------------|---------------|-------------|--------|
| Submit        | primary (raw) | `primary-dark`| `cream-card`| — ✓   |

- `py-4` ✓. Disabled states ✓. Clean.

---

### QuickEntryScreen

| Button              | Variant         | Bg ctx          | Text             | Issues |
|---------------------|-----------------|-----------------|------------------|--------|
| Tab pills           | ghost/primary   | mixed           | mixed            | T      |
| Submit              | primary (raw)   | `primary-dark`  | `cream-card`     | — ✓   |

- Tab pills `py-2` → 32px. Fail.
- Submit `py-4` ✓.

---

### MaintenanceLogScreen

| Button                  | Variant         | Bg ctx           | Text             | Issues |
|-------------------------|-----------------|------------------|------------------|--------|
| Filter chips            | ghost/primary   | mixed            | mixed            | T      |
| Equipment rows          | ghost (raw)     | `cream-card`     | `ink-primary`    | — ✓   |
| Submit log              | primary (raw)   | `primary-dark`   | `cream-card`     | — ✓   |

- Filter chips `px-3 py-1.5` → ~28px. Fail (worst offender).
- Submit `py-4` ✓.

---

### ManagerScreen

| Button                       | Variant          | Bg ctx        | Text              | Issues |
|------------------------------|------------------|---------------|-------------------|--------|
| Deactivate/Reactivate staff  | danger-outline (raw)| `cream-card`| `status-failed`  | T, V   |

- **T**: `px-4 py-2` → ~32px. Fail.
- **V**: Uses `border-2 border-status-failed/30` — faint border. Not clearly communicating "danger action". Inconsistent with ShiftScreen/LeaveApproval which use solid `bg-status-failed`.

---

### CashReconScreen

| Button                     | Variant          | Bg ctx         | Text              | Issues |
|----------------------------|------------------|----------------|-------------------|--------|
| HoldToConfirm (short)      | custom component | `primary-dark` | `cream-card`      | — (need to check) |
| Submit "Reconcile"         | primary (raw)    | `primary-dark` | `cream-card`      | — ✓   |
| Cash source accordion rows | ghost (raw)      | transparent    | `ink-secondary`   | — ✓   |
| "Show breakdown" link      | link (raw)       | transparent    | `primary-dark`    | T      |
| Payment source options     | list item (raw)  | `white`        | `ink-primary`     | — ✓   |
| "Link payment" link        | link (raw)       | transparent    | `primary-dark`    | T      |

- **T**: "Show breakdown" and "Link payment" are `text-xs` links, zero padding → ~18px. Fail.
- Submit `py-4` ✓. HoldToConfirm appears to use a full-width `py-4` design.

---

### LeaveApprovalScreen

| Button                     | Variant           | Bg ctx           | Text              | Issues |
|----------------------------|-------------------|------------------|-------------------|--------|
| Filter pills (All/Pending/…)| ghost/primary    | mixed            | mixed             | T      |
| Quick Approve (list)       | primary-sm (raw)  | `primary-dark`   | `cream-card`      | T      |
| Quick Reject (list)        | danger-outline (raw)| `status-failed/5`| `status-failed`| T, V   |
| Detail Cancel              | secondary (raw)   | transparent      | `ink-secondary`   | — ✓   |
| Detail Approve             | primary (raw)     | `primary-dark`   | `cream-card`      | — ✓   |
| Detail Reject              | danger (raw)      | `status-failed`  | `cream-card`      | — ✓   |

- **T**: Filter pills `py-2` → 32px. Quick action buttons `py-2.5` → 40px. Both fail.
- **V**: Quick Reject uses `bg-status-failed/5 text-status-failed` (outline-danger) while Detail Reject uses `bg-status-failed text-cream-card` (solid danger). Inconsistent for the same action.
- Detail buttons `py-3 flex-1` ≈ 44px ✓.

---

### ShiftScreen

| Button                   | Variant          | Bg ctx         | Text              | Issues |
|--------------------------|------------------|----------------|-------------------|--------|
| Tab pills                | ghost/primary    | mixed          | mixed             | T      |
| Create shift CTA         | primary (raw)    | `primary-dark` | `cream-card`      | — ✓   |
| Shift detail Cancel btn  | secondary (raw)  | transparent    | `ink-secondary`   | — ✓   |
| Shift detail Cancel shift| danger (raw)     | `status-failed`| `cream-card`      | — ✓   |
| Delete shift icon        | danger-ghost (raw)| transparent   | `status-failed/70`| T, C  |

- **T + C**: Delete icon `text-xs text-status-failed/70` with no padding → ~18px, and `status-failed/70` is ~3.7:1 on cream. Fail both.
- Create shift CTA `py-4` ✓.

---

### AttendanceScreen

| Button              | Variant        | Bg ctx       | Text            | Issues |
|---------------------|----------------|--------------|-----------------|--------|
| Tab pills           | ghost/primary  | mixed        | mixed           | T      |
| Staff rows          | ghost (raw)    | `cream-card` | `ink-primary`   | — ✓   |

- Tab pills `py-2` → 32px. Fail.
- Staff rows `px-4 py-3` ≈ 44px ✓.

---

### PurchaseReqScreen

| Button                    | Variant           | Bg ctx           | Text              | Issues |
|---------------------------|-------------------|------------------|-------------------|--------|
| Filter pills              | ghost/primary     | mixed            | mixed             | T      |
| Quick Accept (list)       | primary-sm (raw)  | `primary-dark`   | `cream-card`      | T      |
| Quick Review (list)       | secondary-sm (raw)| `primary-dark/40`| `primary-dark`   | T, C   |
| Detail Cancel             | secondary (raw)   | transparent      | `ink-secondary`   | — ✓   |
| Detail Approve            | primary (raw)     | `primary-dark`   | `cream-card`      | — ✓   |
| Submit cost est.          | primary (raw)     | `primary-dark`   | `cream-card`      | — ✓   |

- **T**: Filter pills `py-2` → 32px. Quick action buttons `py-2.5 mt-1` → ~40px. Both fail.
- **C**: Quick Review button `border-2 border-primary-dark/40 text-primary-dark` — `primary-dark` text on cream = 6.3:1 ✓, but `border-primary-dark/40` is barely visible.

---

### FrontDeskScreen

| Button        | Variant       | Bg ctx  | Text    | Issues |
|---------------|---------------|---------|---------|--------|
| Tab pills     | ghost/primary | mixed   | mixed   | T      |

- Tab pills only visible buttons in this screen. `py-2` → 32px. Fail.

---

## owner_pwa screens

### LoginScreen

| Button                | Variant           | Bg ctx        | Text        | Issues |
|-----------------------|-------------------|---------------|-------------|--------|
| Submit "Sign in ↗"   | `<Button>` primary| `primary-dark`| `cream-card`| — ✓   |

- `size="lg"` → `py-3 min-h-[44px]` ✓. `loading` prop ✓. `disabled` prop ✓. Clean — best login impl.

---

### PinEntryScreen (owner)

| Button                      | Variant              | Bg ctx        | Text              | Issues |
|-----------------------------|----------------------|---------------|-------------------|--------|
| Digit keys (0–9)            | custom (raw)         | `white`       | `ink-primary`     | — ✓   |
| Backspace (⌫)               | ghost (raw)          | transparent   | `ink-tertiary`    | C      |
| Submit "Sign in"            | `<Button>` primary   | `primary-dark`| `cream-card`      | — ✓   |
| "Use password instead"      | link (raw)           | cream bg      | `ink-tertiary`    | T, C   |
| Lockout modal OK            | `<Button>` secondary | `cream-card`  | `ink-primary`     | — ✓   |

- **T + C**: "Use password instead" `text-sm text-ink-tertiary` inline text, zero padding → ~22px. `ink-tertiary` on cream = 3.2:1.
- Backspace: `ink-tertiary` on transparent cream → 3.2:1. Fail.

---

### PinSetupScreen (owner)

| Button                | Variant           | Bg ctx        | Text        | Issues |
|-----------------------|-------------------|---------------|-------------|--------|
| Digit keys (0–9)      | custom (raw)      | `white`       | `ink-primary`| — ✓  |
| Submit "Set PIN"      | `<Button>` primary| `primary-dark`| `cream-card`| — ✓   |

- `<Button size="lg">` ✓. Loading ✓. Clean.

---

### PlaceholderDashboard

| Button         | Variant             | Bg ctx       | Text        | Issues |
|----------------|---------------------|--------------|-------------|--------|
| Sign out       | `<Button>` ghost    | transparent  | `ink-secondary` | — ✓ |

- Ghost variant `hover:bg-cream-alt` ✓.

---

### DashboardScreen / BookingsScreen / FinanceScreen / AlertsScreen / StaffScreen / SettingsScreen

No buttons yet — all are placeholder/stub screens with no interactive elements.

---

## Findings summary by issue type

### T — Touch target < 44px (most widespread)

| Screen                   | Affected elements                         | Actual height |
|--------------------------|-------------------------------------------|---------------|
| MaintenanceLogScreen     | Filter chips (`py-1.5 px-3`)              | ~28px ✗✗     |
| ShiftScreen              | Delete icon (no padding)                  | ~18px ✗✗     |
| PinEntryScreen (both)    | "Switch to password" link                 | ~18px ✗✗     |
| PinSetupScreen (emp)     | "Back to login" link                      | ~18px ✗✗     |
| LoginScreen (emp)        | "Use PIN instead" link                    | ~18px ✗✗     |
| owner_pwa PinEntryScreen | "Use password instead" link               | ~22px ✗      |
| CashReconScreen          | "Show breakdown" / "Link payment" links   | ~18px ✗✗     |
| ScheduleScreen           | Retry inline link                         | ~18px ✗✗     |
| ManagerScreen            | Deactivate btn (`py-2 px-4`)              | ~32px ✗      |
| All tab-bar screens      | `py-2` tab/filter pills                   | ~32px ✗      |
| LeaveApprovalScreen      | Quick action btns (`py-2.5`)              | ~40px ✗      |
| LeaveRequestScreen       | Leave type chips (`py-2.5`)               | ~40px ✗      |
| AbsenceNoticeScreen      | Reason chips (`py-2`)                     | ~32px ✗      |
| CheckInScreen            | Tab pills (`py-2`)                        | ~32px ✗      |
| InventoryCountScreen     | Dept chips, tab pills, count submit       | ~32–40px ✗   |

### C — Contrast < 4.5:1

| Location                          | Pair                              | Ratio  |
|-----------------------------------|-----------------------------------|--------|
| All screens (inactive tabs/chips) | `ink-tertiary` on `cream-card`    | ~3.2:1 |
| All screens (inactive tabs/chips) | `ink-tertiary` on `cream-alt`     | ~2.9:1 |
| PinEntry backspace (both PWAs)    | `ink-tertiary` on transparent     | ~3.2:1 |
| owner PinEntry link               | `ink-tertiary` on transparent     | ~3.2:1 |
| ConductScreen (not ready)         | `ink-tertiary` on `ink-tertiary/15`| ~1.5:1|
| ShiftScreen delete icon           | `status-failed/70` on transparent | ~3.7:1 |
| LoginScreen link (emp)            | `white/70` on dark overlay        | ~4.0:1 |

### V — Variant inconsistency

| Inconsistency                                       | Screens affected                                   |
|-----------------------------------------------------|----------------------------------------------------|
| Danger action: `bg-status-failed` vs `bg-status-failed/5 border text-status-failed` | LeaveApprovalScreen (quick vs detail reject) |
| Danger action: `border-2 border-status-failed/30 text-status-failed` (ghost) | ManagerScreen, vs solid danger elsewhere |
| Primary CTA: `<Button>` component vs raw `<button>` with identical styles | owner PWA uses `<Button>`; employee PWA does not |
| Loading state: `<Button loading>` prop vs manual SVG spinner inline | emp PWA builds its own spinner everywhere |

### D — Disabled state missing or wrong

| Location                     | Issue                                                  |
|------------------------------|--------------------------------------------------------|
| ConductScreen "not ready"    | Visual state faked via class, but `disabled` IS set. Visually confusing — text nearly invisible (1.5:1) even to sighted users |
| ScheduleScreen Retry         | No `disabled` state at all — can spam-click during refetch |
| PurchaseReqScreen "Review"   | No `disabled` when already in review state?            |

### L — Loading state missing

| Location                     | Issue                                                  |
|------------------------------|--------------------------------------------------------|
| employee_pwa LoginScreen     | Implements loading manually (SVG). Works but diverges from `<Button loading>` |
| employee_pwa PinSetupScreen  | Same — manual SVG spinner                              |
| Most other employee screens  | Manual spinner inline. Consistent with each other but not with `<Button>` |

---

## Fix plan for F-11.8b

Ordered by impact. Scope: fixes only — no new features, no structural refactors.

### Fix 1 — Touch targets on link-style buttons (6 buttons across 5 screens)

Add `min-h-[44px] flex items-center justify-center` (or equivalent `py-3`) to every
naked text link that acts as a button:

- `LoginScreen` (emp): "Use PIN instead"
- `PinEntryScreen` (emp): "Use password instead"
- `PinSetupScreen` (emp): "Back to login"
- `owner PinEntryScreen`: "Use password instead"
- `ScheduleScreen`: Retry — also needs color + focus ring
- `CashReconScreen`: "Show breakdown" and "Link payment" text links

### Fix 2 — Tab/filter pill touch targets (11 screens)

Add `min-h-[44px]` to every `py-2 rounded-lg/xl` tab pill. Screens:
InventoryCountScreen, CashReconScreen, LeaveApprovalScreen, ShiftScreen,
AttendanceScreen, PurchaseReqScreen, FrontDeskScreen, SafetyCheckScreen,
QuickEntryScreen, CheckInScreen, MaintenanceLogScreen.

### Fix 3 — PinEntry backspace contrast (both PWAs)

Change backspace button from `text-ink-tertiary` to `text-ink-secondary` (6:1 → passes AA).

### Fix 4 — ConductScreen "not-ready" state

The `bg-ink-tertiary/15 text-ink-tertiary` combo is ~1.5:1. Replace with
`bg-cream-alt text-ink-tertiary` — same visual "muted" feel but background lifts contrast.
Actually simpler: use `opacity-40` on the whole button when not ready rather than
swapping the class entirely.

### Fix 5 — ShiftScreen delete icon

Add `p-2 min-h-[44px] flex items-center` to the icon button.

### Fix 6 — Danger variant standardisation

Pick one pattern and use it everywhere:
- **Primary danger** (destructive, irreversible): `bg-status-failed text-cream-card` — use for deactivate, reject, cancel shift.
- **Outline danger** (reversible warning): `border border-status-failed text-status-failed hover:bg-status-failed/10` — use for "flag" or "request review" type actions.

Affected: ManagerScreen deactivate, LeaveApproval quick-reject.

### Fix 7 — SafetyCheckScreen back icon

Add `p-2` → brings it to ~36px, which is still below 44px. Better solution: wrap in `min-h-[44px] flex items-center`.

### SKIP — ink-tertiary color token

Raising `ink-tertiary` contrast would affect every label, description, and placeholder across both PWAs. That's a design-system decision requiring a visual review pass, not a bug fix. Flag for a separate colour-token audit.

### SKIP — `<Button>` adoption across employee PWA

Migrating all 23+ raw `<button>` elements to `<Button>` is a large refactor with no functional regression risk. Raw buttons already have matching styles. Defer to a dedicated cleanup pass.

---

*Audit complete — fixes in F-11.8b.*
