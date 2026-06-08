# FRONTEND_DESIGN.md — Kurahia Hospitality Management System

> **Status: DESIGN PHASE COMPLETE — code begins after this doc is locked**
>
> Version: v1.0 | Date: 2026-06-08
>
> Companion documents: `docs/SYSTEM_OVERVIEW.md`, `PAYMENTS_DESIGN.md`, `CLAUDE.md`

---

## Executive Summary

Kurahia's frontend is two installable Progressive Web Apps sharing a design system and a
single Flask backend. The **Employee PWA** runs on shared tablets across the resort — gate,
bar, kitchen, front desk, water activities. The **Owner PWA** runs on the owner's personal
phone via Tailscale, giving full visibility into operations from anywhere. Both apps are
offline-capable, role-gated, and designed for the real conditions of a Kenyan resort: variable
WiFi, shared hardware, gloves-and-sunscreen hands on touchscreens, and staff who are
operationally skilled but not technically trained. Every design decision traces back to the
backend's 213 endpoints, the 18 blueprints, and the invariants locked in `CLAUDE.md`.

---

## Section 1 — The Two PWAs

### Why two apps, not one

A single app serving every role would require bundling all screens, all logic, and all
permissions into one download. It would present a security boundary problem (owner-only data
handled by the same session as a waiter's login), and it would make the bundle too heavy
for a shared tablet with limited storage. Two apps makes the split clean:

- **Employee PWA** (`employee_pwa/`) — all staff from level 1 (waiter) to level 5 (manager).
  Shared tablets, PIN login, short sessions, role-aware navigation. Installed on every
  tablet and staff phone on the hotel LAN.
- **Owner PWA** (`owner_pwa/`) — owner only (role level 10). Personal phone. Tailscale VPN.
  Long sessions. Full visibility: alerts, judge analysis, financial dashboard, audit trail.

### Repo structure

```
kurahia/
├── app/                     ← existing Flask backend (unchanged)
├── employee_pwa/            ← React PWA for all staff (levels 1–5)
│   ├── src/
│   │   ├── components/      ← local overrides + domain composites
│   │   ├── pages/           ← all 22 staff screens
│   │   ├── hooks/           ← React Query hooks, auth, role gate
│   │   ├── stores/          ← Zustand stores (auth state, toast queue)
│   │   └── lib/             ← axios instance, token refresh, formatters
│   ├── public/
│   └── vite.config.ts
├── owner_pwa/               ← React PWA for owner (level 10)
│   ├── src/
│   │   ├── components/
│   │   ├── pages/           ← 6 owner screens
│   │   ├── hooks/
│   │   ├── stores/
│   │   └── lib/
│   ├── public/
│   └── vite.config.ts
└── shared_ui/               ← design tokens + component library (shared)
    ├── src/
    │   ├── tokens/          ← color, type, spacing constants
    │   ├── components/      ← all 17 shared components
    │   └── index.ts         ← barrel export
    └── package.json
```

### Shared backend

Both apps hit the same Flask instance. Role checks happen on the backend on every request
(`@require_active_user` + `actor.role.level < THRESHOLD`). The frontend trusts the backend's
role checks; it does not enforce permissions independently.

### Both are installable

Both apps include a `manifest.json` and a service worker. Staff can add the Employee PWA
to their home screen. The owner can install the Owner PWA on their phone. Once installed,
both run full-screen with no browser chrome, offline capability, and push notification support.

---

## Section 2 — Color System

Three palettes. Each has a defined scope — mixing them outside their scope is a mistake.

### Why three palettes

The SYSTEM palette (sage + cream) is the operational aesthetic: calm, readable, professional.
It covers 95% of the app. The TICKET palette (warm paper + ink + stamp) is a deliberate
texture shift for the POS and kitchen experience — it reads like a physical docket, which
is familiar to kitchen and bar staff. STATUS colors communicate outcomes (paid, pending,
failed) and must be immediately legible under bright outdoor light and dim bar light alike.

### SYSTEM palette — operational aesthetic

Used everywhere except kitchen tickets and menu browse kiosk.

```
Backgrounds:
  sage-main:    #9CB39A  ← primary app background
  sage-light:   #B8C8B0  ← section dividers, subtle surface
  sage-dark:    #7A9374  ← active nav, primary button

Cards:
  cream-card:   #F2EBDD  ← default card background
  cream-alt:    #EBE2CE  ← alternate card, table stripes

Text:
  ink-primary:   #2A2620  ← headings, primary labels
  ink-secondary: #5C5147  ← body text, sublabels
  ink-tertiary:  #8C7E6F  ← placeholders, disabled, timestamps
```

### TICKET palette — menu browse + kitchen/bar tickets ONLY

Used in: kitchen queue screen, bar queue screen, kiosk menu browse, receipt display.

```
Paper:
  ticket-paper:  #EFE6D2  ← ticket background (primary)
  ticket-alt:    #E5DAC1  ← ticket background (alternate)

Text:
  ticket-ink:    #1F1B14  ← all text on tickets

Accent:
  stamp-red:     #9A3E32  ← status SENT, urgent, voided items
  leaf-green:    #708A4F  ← status READY, completed items
  tea-brown:     #6B4A2E  ← section headers on tickets
```

### STATUS palette — transaction and state outcomes

Used in StatusBadge, AlertCard, financial summaries, and anywhere a discrete outcome
(paid / pending / failed) must be communicated.

```
success-paid:    #4A7A4A  ← payment confirmed, check complete, booking confirmed
warning-pending: #B88838  ← awaiting action, pending reconciliation, partial
danger-failed:   #A04438  ← declined, failed, critical alert, overdue
info-neutral:    #4A7889  ← informational, notes, secondary actions
```

### Rules

- **No dark mode in v1.** The resort operates in good light; the added complexity is not
  worth it at launch. Dark mode can be added in v2.
- **No hardcoded hex values in component code.** Every color reference goes through the
  Tailwind config as a named token. `bg-sage-main`, `text-ink-primary`, etc.
- **Status colors obey the three-signal rule** (Section 13): every STATUS color is paired
  with an icon and a text label. Color is never the only signal.

### Tailwind config structure

```ts
// tailwind.config.ts — token encoding
colors: {
  sage: { main: '#9CB39A', light: '#B8C8B0', dark: '#7A9374' },
  cream: { card: '#F2EBDD', alt: '#EBE2CE' },
  ink: { primary: '#2A2620', secondary: '#5C5147', tertiary: '#8C7E6F' },
  ticket: { paper: '#EFE6D2', alt: '#E5DAC1', ink: '#1F1B14',
            'stamp-red': '#9A3E32', leaf: '#708A4F', brown: '#6B4A2E' },
  status: { paid: '#4A7A4A', pending: '#B88838',
            failed: '#A04438', neutral: '#4A7889' },
}
```

---

## Section 3 — Typography

### Font families

**Inter** — primary system font. Used for all operational text: labels, values, navigation,
forms, tables, error messages. Inter is legible at small sizes on low-quality screens and
loads from Google Fonts with a `font-display: swap` strategy.

**Cormorant Garamond** — decorative/aesthetic font. Used ONLY in the TICKET palette contexts:
kitchen ticket headers, bar ticket headers, menu browse kiosk titles, receipt footers. It
creates the "printed docket" aesthetic. Never used for operational UI — it's not legible
enough at small sizes for real data entry.

### Type scale — Major Third (ratio 1.250)

Eight sizes. No custom sizes outside this scale.

| Token | Size | Use |
|---|---|---|
| `text-xs`   | 12px | Timestamps, tertiary labels, tooltips |
| `text-sm`   | 14px | Table rows, supporting text, sublabels |
| `text-base` | 16px | Body text, form labels, input values |
| `text-lg`   | 20px | Card titles, section headers |
| `text-xl`   | 25px | Page titles, drawer headers |
| `text-2xl`  | 31px | Key metrics (tab balance, headcount) |
| `text-3xl`  | 39px | Dashboard hero numbers |
| `text-4xl`  | 49px | Kiosk display numbers, entry fee |

### Weights

Three only: `400` (regular), `500` (medium), `700` (bold). No `300`, no `600`, no `800`.

### Tabular numbers

All money values, quantities, and counts use `font-variant-numeric: tabular-nums`. This
prevents layout shift when numbers change (live queue counts, real-time tab balances).
Apply via Tailwind class `tabular-nums`.

### Other rules

- **Letter spacing:** Labels and section headers use `tracking-wide` (0.025em). Body text
  uses default. Ticket palette headings use `tracking-widest` for the docket aesthetic.
- **Line height:** Body text `leading-relaxed` (1.625). Compact table rows `leading-tight` (1.25).
- **Locale:** English only for operational text. Swahili phrases ("Karibu", "Asante") acceptable
  in empty states and kiosk welcome screens. Latin script only — no Arabic numerals in amounts,
  no Devanagari. This is a practical constraint for font-loading reliability.
- **Decorative motifs** from the reference design images (leaf borders, subtle watermark
  textures on kiosk screens) are acceptable as CSS/SVG ornaments, not as additional font imports.

---

## Section 4 — Component Library

Seventeen components in `shared_ui/`. Four primitives. Four containers. Four feedback
components. Five domain composites. Every component follows the five-state rule (Section 5):
default, hover, active, disabled, loading. Error state added where the component can fail.

---

### 4.1 Button

The most-used primitive. Every interactive action goes through Button.

```ts
Props:
  variant: 'primary' | 'secondary' | 'ghost' | 'danger'
  size: 'sm' | 'md' | 'lg'
  state: 'default' | 'hover' | 'active' | 'disabled' | 'loading'
  icon?: ReactNode     // left of label
  iconRight?: ReactNode
  fullWidth?: boolean
  onClick: () => void
```

**Variants:**
- `primary` — sage-dark bg, cream text. Main actions (Save, Confirm, Assign).
- `secondary` — cream-card bg, ink-primary text, sage-dark border. Secondary actions (Cancel, Back).
- `ghost` — transparent bg, ink-secondary text. Tertiary actions (Edit, View).
- `danger` — status-failed bg, white text. Destructive actions (Disable, Forfeit).

**Sizes:**
- `sm` — 32px height, 12px text. Inline table actions.
- `md` — 44px height, 16px text. Standard form actions. Default.
- `lg` — 56px height, 20px text. Kiosk CTAs, primary screen actions.

**States:**
- `loading` — label replaced with inline Spinner + "..." — button width locks to prevent reflow.
- `disabled` — opacity 0.4, cursor not-allowed, pointer-events none.
- Error feedback: after a failed async action, button briefly shows `danger` variant for 800ms
  before returning to its original variant. Not a permanent state — the Toast handles the message.

**Touch targets:** `md` and `lg` meet the 44×44px minimum. `sm` pads to 44px vertically
with invisible padding to keep touch area accessible without visual bulk.

**Animation:** Scale to 0.97 on active (tap). 100ms ease-out. Framer Motion `whileTap`.

---

### 4.2 Input

Text and numeric inputs. Single component handles all field types.

```ts
Props:
  type: 'text' | 'number' | 'password' | 'search' | 'tel'
  value: string
  onChange: (val: string) => void
  label?: string
  placeholder?: string
  icon?: ReactNode      // left icon (e.g. KES currency symbol)
  iconRight?: ReactNode // right icon (e.g. eye for password)
  error?: string        // displays below input, red
  hint?: string         // displays below input, tertiary
  maxLength?: number    // shows character count when set
  disabled?: boolean
  required?: boolean
```

**States:**
- Default: cream-card bg, ink-primary border, ink-primary text.
- Focus: sage-dark border (2px), no outline (custom focus ring).
- Error: status-failed border, error message below in status-failed color.
- Disabled: opacity 0.5, cursor not-allowed, no focus ring.
- With icon: 40px left/right padding to avoid text under icon.

**Character count:** Shows `{value.length}/{maxLength}` in ink-tertiary below the input
when `maxLength` is set. Turns status-failed when > 90% full.

---

### 4.3 Select

Dropdown selector. Wraps the native `<select>` with custom styling for cross-platform
consistency. On mobile, the native picker opens — don't fight the platform.

```ts
Props:
  options: Array<{ value: string; label: string; disabled?: boolean }>
  value: string
  onChange: (val: string) => void
  label?: string
  placeholder?: string  // "Select..." default
  error?: string
  disabled?: boolean
```

**Touch behaviour:** Full-width on mobile. Tap opens native picker on iOS/Android.
On desktop, opens a styled dropdown overlay. The same component handles both — feature
detection via `matchMedia`.

---

### 4.4 Toggle

On/off switch. Used for feature flags, active/inactive states, channel configs.

```ts
Props:
  checked: boolean
  onChange: (checked: boolean) => void
  label: string         // always visible — never toggle without a label
  description?: string  // secondary label
  disabled?: boolean
```

**States:** Off (cream-alt track, ink-tertiary thumb). On (sage-dark track, white thumb).
Transition: 150ms ease. Focus ring on keyboard navigation.

---

### 4.5 Card

Foundation container. Every screen content block is a Card or a variant of it.

```ts
Props:
  padding?: 'sm' | 'md' | 'lg'   // default: 'md'
  border?: boolean                 // subtle border on cream-alt
  shadow?: 'none' | 'sm' | 'md'  // default: 'sm'
  onClick?: () => void             // makes Card tappable
  selected?: boolean               // active state (sage-light bg)
  className?: string
```

**Variants by use:**
- Default: cream-card bg, shadow-sm, rounded-xl.
- Tappable: hover lifts (shadow-md, -2px translate). Active: scale 0.99.
- Selected: sage-light bg, sage-dark border (2px).

---

### 4.6 Modal

Full blocking overlay. Used for confirmations, forms, and detail views that require
the user to complete an action before returning.

```ts
Props:
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode    // action buttons
  size?: 'sm' | 'md' | 'lg' | 'full'
  preventClose?: boolean  // hold-to-confirm modals set this
```

**Animation:** Backdrop fades in (200ms). Modal slides up from bottom on mobile (drawer
feel), fades+scales from center on desktop. Exit is the reverse. Framer Motion `AnimatePresence`.

**Accessibility:** Focus traps inside modal when open. `Escape` closes unless `preventClose`.
`aria-modal="true"`, `role="dialog"`, `aria-labelledby` points to title.

---

### 4.7 Drawer

Slides in from screen edge. For supplementary actions and detail panels that don't fully
block the main screen. Used heavily in mobile-first flows.

```ts
Props:
  open: boolean
  onClose: () => void
  side: 'bottom' | 'right'   // bottom for mobile actions, right for desktop detail
  title?: string
  children: ReactNode
  snapPoints?: number[]       // for bottom drawer: [0.4, 0.85, 1.0]
```

**Mobile bottom drawer:** Supports snap points (swipe up to expand, swipe down to
dismiss). Handle bar visible at top. Drag gesture with Framer Motion drag constraints.

**Desktop right drawer:** 400px wide. Slides in from right. Backdrop overlay behind it.

---

### 4.8 Toast

Non-blocking notification. Appears at top of screen (mobile: bottom). Auto-dismisses.
The primary output channel for success and non-critical errors.

```ts
Props:
  type: 'success' | 'error' | 'warning' | 'info'
  message: string
  duration?: number   // ms. Default: success=3000, error=5000, warning=4000
  action?: { label: string; onClick: () => void }  // undo, retry
```

**Positioning:** `top-4 right-4` on desktop. `bottom-20 left-4 right-4` on mobile
(above bottom nav). Multiple toasts stack vertically with 8px gap.

**Animation:** Slide in from the edge, fade out. Spring physics on enter, ease-out on exit.
Toasts never overlap the nav bar.

**Tone:** Success toasts confirm what just happened ("Tab closed. Receipt saved.").
Error toasts state the problem and the next step ("Payment failed. Check M-Pesa code and retry.").

---

### 4.9 StatusBadge

Compact tag for transaction and state outcomes. Always uses three-signal rule: color +
icon + text.

```ts
Props:
  status: 'paid' | 'pending' | 'failed' | 'info' |
          'active' | 'inactive' | 'held' | 'confirmed' |
          'checked-in' | 'checked-out' | 'cancelled' | 'no-show'
  size?: 'sm' | 'md'
  pill?: boolean   // rounded-full vs rounded-md
```

**Examples:**
- `paid` → green badge + checkmark + "Paid"
- `pending` → amber badge + clock + "Pending"
- `failed` → red badge + × + "Failed"
- `checked-in` → green badge + person + "Checked In"
- `cancelled` → neutral grey badge + slash + "Cancelled"

---

### 4.10 Skeleton

Loading placeholder. Matches the layout shape of the content it replaces — not a generic
grey block. The skeleton gives the user a preview of the structure, reducing perceived
load time.

```ts
Props:
  variant: 'text' | 'heading' | 'card' | 'row' | 'avatar' | 'badge' | 'button'
  lines?: number    // for 'text': how many lines to simulate
  className?: string
```

**Animation:** Pulse shimmer (opacity 0.6 → 1.0 → 0.6, 1.4s ease-in-out infinite).
Use `bg-cream-alt` as the base colour.

**Rule:** Every skeleton layout must match the real content's grid. A two-column card
grid gets a skeleton with two placeholder cards, not a full-width bar.

---

### 4.11 Spinner

Inline loading indicator. Used inside Buttons (loading state) and for single-value loads.
Not for whole pages — use Skeleton for that.

```ts
Props:
  size?: 'sm' | 'md' | 'lg'   // 16px / 24px / 32px
  color?: 'sage' | 'cream' | 'ink'
  label?: string   // screen-reader-only "Loading..."
```

**Animation:** Single arc rotating at 360deg/0.8s. No bounce. No multi-ring complexity.

---

### 4.12 EmptyState

Full-area empty state with illustration, message, and CTA. Never show a blank screen.

```ts
Props:
  icon: ReactNode        // SVG illustration — matches domain
  title: string          // short, framed as achievement or status
  description?: string   // what to do next
  action?: { label: string; onClick: () => void }
```

**Framing rule:** Empty states are achievements or neutral states, not failures.
- Kitchen queue empty → "All orders delivered. Great shift." (achievement)
- No bookings today → "Nothing booked today. Floor is yours." (neutral)
- No alerts → "All clear. Judge found no anomalies." (achievement)

---

### 4.13 BookingCard

Domain composite for bookings in lists and timeline views.

```ts
Props:
  booking: {
    id: string; guest_name: string; resource_name: string;
    check_in_date: string; check_out_date: string;
    status: BookingStatus; base_total: string; deposit_paid: string;
  }
  onAction?: (action: 'confirm' | 'check-in' | 'check-out' | 'cancel') => void
  compact?: boolean
```

**Displays:** Resource + status badge + date range + base_total. Compact mode shows
three lines. Expanded mode shows deposit progress bar (deposit_paid / base_total).

---

### 4.14 AlertCard

Severity-aware card for JudgeAlerts and system notifications. Owner PWA only.

```ts
Props:
  alert: {
    id: string; alert_type: string; severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
    description: string; created_at: string; status: 'OPEN' | 'ACKNOWLEDGED';
  }
  onAcknowledge: (id: string) => void
```

**Visual:** Left border color matches severity (status-neutral / status-warning /
status-failed / danger-failed at full opacity). Icon in severity color. Acknowledged
alerts show with reduced opacity and a checkmark.

---

### 4.15 AuditLine

Single audit log entry. Timestamp + actor + action + target.

```ts
Props:
  entry: {
    actor: string; action: string; target?: string;
    details?: string; created_at_utc: string;
  }
  condensed?: boolean
```

**Displays:** `[Time ago]  actor  →  action  →  target  details`
Example: `14 min ago  wachira  →  inventory.purchase  →  Cooking Oil  qty=5 cost=800`

---

### 4.16 StockRow

Inventory item row with real-time stock level and variance indicator.

```ts
Props:
  item: {
    id: string; name: string; unit: string;
    current_stock: string; last_count_qty?: string;
    variance?: string; is_watch_list: boolean;
  }
  onRecord?: () => void
```

**Variance awareness:** If `variance` is positive (more stock than expected), show in
status-neutral. If negative (less stock than expected), show in status-warning. If
negative AND `is_watch_list=true`, show in status-failed with a flag icon.

---

### 4.17 ChecklistRow

One row in a structured safety checklist. Stateful toggle.

```ts
Props:
  itemKey: string              // e.g. "life_jackets_on_board"
  label: string                // human-readable label
  checked: boolean
  note: string
  onChange: (key: string, checked: boolean, note: string) => void
  required: boolean
```

**States:** Unchecked (cream-alt bg, empty checkbox). Checked (sage-light bg, green
checkmark, note field collapses). Note field expands on tap when checked, for optional
notes. Required items show a red asterisk when unchecked.

---

### Other domain composites (referenced but abbreviated)

**MaintenanceRow** — equipment + last service date + `is_due_service` flag. Red badge
when overdue. Tap opens maintenance log drawer.

**FeedbackCard** — 1–5 star rating display + comment + department tag + timestamp.
Stars use leaf-green fill for filled, cream-alt for empty.

**SuggestionCard** — category badge (MANAGEMENT vs OWNER_PRIVATE) + body + status.
OWNER_PRIVATE shown only to owner (backend-enforced; frontend never receives these for non-owners).

**GuestTabCard** — consolidated billing view for a tab. Current balance prominently
displayed in `text-2xl tabular-nums`. Line items collapsible. Payment method icons.

**KitchenTicket** — full TICKET palette. Cormorant Garamond for ticket header
("ORDER #42 · BAR · TABLE 7"). Inter for item lines. stamp-red for "SENT BACK".
leaf-green for "READY". Optimised for glance-readability at arm's length.

---

## Section 5 — State Coverage Rules + 20 Build Chunks

### The data shape philosophy

> "Frontend is a respectful client of the backend, not an architect of new data shapes.
> Where backend has weekly variance, frontend shows weekly variance. Where backend has
> daily takings, frontend rolls up to weekly. Where backend gates by role, frontend hides
> accordingly. The backend is the source of truth; the frontend is the user-friendly
> window into it."

**Practical rule:** Frontend never invents aggregations the backend doesn't support. If the
owner dashboard needs weekly revenue, and the backend only ships daily `GET /finance/dashboard`
data, the frontend calls the endpoint for each day and aggregates client-side — OR waits
for a backend report endpoint. Frontend never assumes the shape of data that hasn't been
verified against a live response.

### Five mandatory states per screen

Every screen implements all five states. No exceptions.

| State | Description | Implementation |
|---|---|---|
| LOADING | Data is in flight | Skeleton matching layout shape. <200ms: nothing. 200ms–2s: skeleton. |
| SUCCESS | Real content displayed | The normal view. |
| ERROR | Request failed | WHAT + WHY + ACTION. Placement by stakes (Section 7). |
| EMPTY | Request succeeded, no data | EmptyState with framing message + next action. Never blank. |
| PARTIAL | Some sections loaded, some failed | Each section degrades independently. No full-page error for a sidebar failure. |

### 20 Build Chunks

---

**F-0: Project Skeleton**

Scope: Vite + React 19 + TypeScript. Tailwind CSS with token config. Framer Motion.
React Router v7. TanStack Query v5. Zustand. `vite-plugin-pwa`. Two apps (`employee_pwa/`,
`owner_pwa/`) + shared package (`shared_ui/`). ESLint + Prettier. `pnpm` workspaces.
No screens. No backend calls. Just the scaffold compiling clean.

Gate: `pnpm dev` in both apps starts dev servers. Tailwind tokens render in a colour
swatch page. TypeScript compiles with zero errors.

---

**F-1: Design Tokens + Base Styles**

Scope: Full Tailwind config with all three palettes (SYSTEM, TICKET, STATUS). Typography
config (Inter + Cormorant Garamond). Type scale as custom Tailwind classes. Global CSS
reset + base layer. `tabular-nums` utility. Responsive breakpoints (`sm: 640`, `md: 768`,
`lg: 1024`, `xl: 1280`). Spacing scale. All tokens documented in a Storybook-style token
page (static HTML, no framework).

Gate: Token page renders all 24 colours with their hex values and names. Inter and
Cormorant Garamond load correctly. All 8 type scale sizes visible.

---

**F-2: Component Library — Primitives**

Scope: Button, Input, Select, Toggle. All variants, all sizes, all states. Accessible.
Animated with Framer Motion. Unit-tested with Vitest + React Testing Library (4 tests
per component: renders, states, keyboard, ARIA).

Gate: Storybook (or equivalent story page) shows all 17 Button variants + all Input
states. axe-core reports zero critical violations.

---

**F-3: Component Library — Containers**

Scope: Card, Modal, Drawer, Toast. Full spec per Section 4. Toast queue (Zustand store).
Modal focus trap. Drawer snap points on mobile.

Gate: Modal focus trap works (keyboard cannot leave modal while open). Drawer snaps to
defined heights on drag. Toast auto-dismisses at correct durations.

---

**F-4: Component Library — Feedback**

Scope: StatusBadge, Skeleton, Spinner, EmptyState. All status variants. Skeleton animation.
EmptyState with all domain variants (kitchen, bookings, alerts, inventory).

Gate: Skeleton pulse animation smooth at 60fps on a mid-range Android device. All status
colours pass WCAG AA contrast against their background.

---

**F-5: Auth + Routing Skeleton**

Scope: Login screen (username + password). PIN entry screen (4-digit keypad — large
touch targets). Token storage (access token in memory, refresh token in httpOnly cookie).
Axios interceptor for transparent token refresh. Zustand auth store (user, role, token).
React Router protected routes (redirect to login if not authenticated, redirect to
role-appropriate home if authenticated). Role gate HOC. Logout (clears memory + calls
`POST /auth/refresh` revocation if needed). Kill-switch handling (403 → force logout).

Backend endpoints: `POST /auth/login`, `POST /auth/pin-login`, `POST /auth/refresh`.

Gate: Login → PIN setup flow works end-to-end against live backend. 403 response forces
logout. Access token never written to localStorage. Role mismatch redirects correctly.

---

**F-6: Domain Composites**

Scope: All domain composites from Section 4 (BookingCard, AlertCard, AuditLine, StockRow,
MaintenanceRow, ChecklistRow, FeedbackCard, SuggestionCard, GuestTabCard, KitchenTicket).
All in `shared_ui/`. Seeded with fixture data for visual development. Not connected to
backend yet.

Gate: Every composite renders its five states (loading / success / error / empty / partial)
with fixture data. KitchenTicket renders correctly in TICKET palette.

---

**F-7: Employee PWA — Universal Screens**

Scope: Five screens all staff levels see.

1. **Clock-in / Clock-out** — large single-tap button. Shows current shift time.
   Backend: `POST /hr/clock-in`, `POST /hr/clock-out`.
2. **My Schedule** — shift cards for the next 7 days. Today's shift highlighted.
   Backend: `GET /hr/shifts`.
3. **Notification Inbox** — unread items with mark-read. Planning alerts, leave decisions,
   assignment notifications. Backend: `GET /notifications/inbox`, `POST /notifications/<id>/mark-read`.
4. **Code of Conduct** — shows current version, sign button if unsigned, compliance badge if signed.
   Backend: `GET /conduct/rules`, `POST /conduct/sign`.
5. **Suggestion Box** — anonymous OWNER_PRIVATE or identified MANAGEMENT submission.
   Backend: `POST /suggestions`.

Gate: Clock-in records a ClockEvent in the DB. Notification inbox clears after mark-read.

---

**F-8: Employee PWA — Front Desk Screens**

Scope: Three screens for role level 3 (gate/front desk).

1. **Wristband Issuance** — payment method select, issue band. Shows today's headcount.
   Backend: `POST /gate/issue-band`, `GET /gate/active-bands`.
2. **Booking Check-in** — search by name/booking ref, confirm waiver present, check in.
   Backend: `GET /bookings/today`, `POST /bookings/<id>/check-in`.
3. **Waiver Record** — collect and record liability waiver signature before water activity.
   Backend: `POST /waivers`.

Gate: Issuing a band creates a wristband record and opens a BAND-type Tab. Check-in opens
a Villa-type Tab.

---

**F-9: Employee PWA — Department Head Screens**

Scope: Three screens for department-level staff.

1. **Inventory Count** — list items, enter physical count, submit. Variance computed
   server-side. Backend: `GET /inventory/items`, `POST /inventory/counts`, `GET /inventory/variance`.
2. **Purchase Request** — select item, enter quantity, submit request.
   Backend: `POST /inventory/purchase-requests`.
3. **Spoilage + Staff Meals** — quick-entry for spoilage and staff meal movements.
   Backend: `POST /inventory/movements/spoilage`, `POST /inventory/movements/staff-meal`.

Gate: Physical count submission creates a StockMovement(COUNT) row. Variance report shows
updated variance after count.

---

**F-10: Employee PWA — Water Activities (Safety Checklist + Fuel Log)**

Scope: Two screens. Depends on Phase Q-3.2 (structured 5-item checklist — already shipped).

1. **Pre-Use Safety Check** — fetch template for equipment type via
   `GET /equipment/checklist-templates/<type>`. Render 5 ChecklistRow components.
   All must be checked before submit enables. Submit calls `POST /equipment/<id>/safety-check`
   with structured `check_items`.
2. **Equipment Fuel/Maintenance Log** — log a maintenance event.
   Backend: `POST /equipment/<id>/maintenance`.

Gate: Submit button disabled until all 5 items checked. Submitting with one unchecked item
returns 400 and inline error on the specific item.

---

**F-11: Employee PWA — Manager Screens**

Scope: Six screens visible to role level 5.

1. **Shift Management** — today's roster, create shift, cancel shift.
   Backend: `GET /hr/shifts`, `POST /hr/shifts`, `POST /hr/shifts/<id>/cancel`.
2. **Cash Reconciliation** — per-staff actual cash vs POS expected.
   Backend: `GET /finance/cash/pending`, `POST /finance/cash/reconcile`.
3. **Attendance** — today's clock-ins, late arrivals, absences.
   Backend: `GET /hr/attendance/today`, `GET /hr/absence-notices`.
4. **Leave Requests** — approve or reject pending leave.
   Backend: `GET /hr/leave-requests`, `POST /hr/leave-requests/<id>/approve`, `.../reject`.
5. **Purchase Approval** — list pending purchase requests, approve or reject.
   Backend: `POST /inventory/purchase-requests/<id>/propose`,
   `POST /inventory/purchase-requests/<id>/approve`.
6. **Front Desk Today** — arrivals, departures, villa status summary.
   Backend: `GET /front-desk/today`.

Gate: Cash reconciliation records a CashReconciliation row with SHORT/BALANCED/OVER status.
Leave approval triggers a DELIVERED notification to the employee.

---

**F-12: Kiosk Mode — Menu Browse**

Scope: Read-only menu browser in TICKET aesthetic. No login. Waiter PIN to exit kiosk.
Customers scroll menu, no ordering. Categories collapsible. Photos optional.
Backend: `GET /menu/items`.

Rules: No back button, no browser chrome. Exit only via waiter PIN or 10-min inactivity
timeout. TICKET palette throughout. Cormorant Garamond for category headers.

Gate: Menu loads and renders in TICKET aesthetic. Inactivity timeout returns to lock screen.

---

**F-13: Kiosk Mode — Waiver Signing**

Scope: Single-document lock. Customer reads waiver text, draws signature on touchscreen,
staff PIN confirms, form submits. Backend: `GET /conduct/rules` (for latest version),
`POST /waivers`.

Rules: Full-screen. No navigation. Back button disabled. Exit only via submission or
staff PIN override.

Gate: Submitted waiver creates a Waiver row. Signature image (base64) stored in
`signature_proof` field.

---

**F-14: Kiosk Mode — Guest Feedback**

Scope: Three-step flow. Step 1: 1–5 star rating (one tap). Step 2: department (optional).
Step 3: comment (optional). 30-second target for full flow. Auto-submits after 60s idle
with whatever is filled in. Backend: `POST /feedback`.

Rules: No login required. Anonymous. Staff member can optionally associate their employee
ID (pre-populated from context). Kiosk returns to welcome screen after submission.

Gate: Feedback creates a GuestFeedback row. Rolling performance score updates for the
linked employee (computed, not stored).

---

**F-15: Owner PWA — Dashboard**

Scope: The main screen. Ten metric tiles scrollable vertically. Quick-action buttons for
the day's most common tasks. Backend: `GET /dashboard/overview`, `/inventory`, `/finance`,
`/bookings`, `/staff`, `/conduct`, `/suggestions`, `/calendar`, `/feedback`, `/equipment`.

Displays:
- Today's revenue (derived from daily takings, prominently displayed)
- Active wristbands + headcount
- Open bookings / tonight's occupancy
- Staff on duty (clocked-in count)
- Pending judge alerts (badge count, tap to navigate)
- Unread suggestions

Always-present top bar: Revenue today | Alerts open | Bookings this weekend.

Gate: All 10 dashboard tiles load independently (PARTIAL state — one tile failure doesn't
break others). Revenue number matches what's in `GET /finance/dashboard`.

---

**F-16: Owner PWA — Alerts + Approvals + Reports**

Scope: Three screens.

1. **Judge Alerts** — list of OPEN alerts grouped by severity. Acknowledge or dismiss.
   AuditLine visible below each alert. Backend: `GET /judge/alerts`,
   `POST /judge/alerts/<id>/acknowledge`.
2. **Payroll Draft** — hours per employee, derived from clock events.
   Backend: `GET /hr/payroll-draft`.
3. **Three-Way Reconciliation** — daily report: POS receipts + cash handed in + stock alerts.
   Backend: `GET /finance/reconciliation`. Period close action: `POST /finance/close-period`.

Gate: Acknowledging an alert updates its status to ACKNOWLEDGED in the backend. Period close
fires a SAFE_COUNT_MISMATCH alert if gap exceeds threshold.

---

**F-17: PWA Install + Offline + Push Notifications**

Scope: `manifest.json` for both apps. Service worker with Workbox. Cache strategies (see
Section 10). Install prompt (deferred prompt API). Push notification registration and
routing. Online/offline status banner.

Gate: Both apps installable via Chrome "Add to Home Screen". Core screens function offline
(cached data visible). Push notification received and routes to correct screen.

---

**F-18: Accessibility + Power-User Features**

Scope: Font-size slider (Small/Normal/Large, stored in localStorage). Keyboard navigation
audit (tab order, Escape, Enter). ARIA audit (axe-core, zero critical violations). Screen
reader testing (VoiceOver on iOS, TalkBack on Android). Reduced-motion media query support
(disables Framer Motion animations). Language: English + Swahili placeholder for empty states.

Gate: Lighthouse accessibility score ≥ 90 on both apps. Zero axe-core critical violations.

---

**F-19: Final Pass + Visual Regression Tests**

Scope: Cross-browser test (Chrome, Safari, Firefox). Cross-device test (iPhone SE,
Samsung A-series, iPad). Visual regression snapshot tests (Playwright). Performance
profiling (Lighthouse performance score ≥ 80 on mid-range Android). Bundle size audit
(each app < 500KB gzipped initial load). Final commit message: `Phase D-1 COMPLETE`.

Gate: All regression tests pass. Both apps install and function on target devices.

---

**Estimated total: 60–90 hours across 8–12 weeks.**
Dependencies: F-2 before F-3 before F-4 before all screen chunks. F-5 before F-7. F-6
before any domain screens. F-10 depends on Q-3.2 (already shipped). F-13 depends on
backend waiver endpoints (already shipped). F-17 depends on Q-3.3 WhatsApp socket
(already shipped).

---

## Section 6 — Loader Strategy

### The five loader types

| Type | When to use | Duration range | Example |
|---|---|---|---|
| **Nothing / Optimistic** | Sub-200ms actions or optimistic updates | <200ms | Mark notification read |
| **Skeleton** | Whole page or large section initial load | 500ms–3s | Dashboard tiles, booking list |
| **Inline Spinner** | Single-button async action | 1–15s | Cash reconciliation submit |
| **Spinner + Static Text** | Action with known pending state | 2–5s | "Saving..." on form submit |
| **Changing Text Spinner** | Long async wait (payment, callback) | 5–30s | STK Push waiting for customer PIN |

### Timing thresholds

- **< 200ms:** No loader. Optimistic UI update immediately.
- **200ms–1s:** Show skeleton (if data load) or spinner (if action). No loading text.
- **1–2s:** Spinner + brief static text ("Loading bookings...").
- **2–5s:** Spinner + static text. If still loading at 5s, switch to changing text.
- **5–15s:** Changing text spinner. Rotate through status messages every 3s.
- **> 15s:** Hard timeout. Show error + retry. Never spin indefinitely.

### Changing text spinner — STK Push example

The STK Push flow waits for the customer to enter their M-Pesa PIN. This can take 5–30
seconds. A static spinner with "Waiting..." feels broken. Rotate messages:

```
0s:  "Prompt sent to customer's phone..."
3s:  "Waiting for M-Pesa PIN..."
6s:  "Customer is entering their PIN..."
9s:  "Almost there..."
12s: "Still waiting — customer may need more time..."
15s: "Taking longer than expected. Ask customer to check their phone."
20s: [Hard timeout] "M-Pesa prompt expired. Ask customer to try again."
```

### Backend endpoint → loader mapping

| Endpoint group | Loader type | Notes |
|---|---|---|
| `GET /dashboard/*` | Skeleton per tile | Tiles load independently — PARTIAL state |
| `POST /hr/clock-in` | Inline spinner → optimistic | Show "Clocked in" immediately |
| `POST /finance/mpesa/charge` | Changing text spinner | 5–30s STK Push wait |
| `POST /inventory/counts` | Inline spinner + static text | "Saving count..." |
| `GET /kitchen/queue`, `GET /bar/queue` | Skeleton → poll 15s | Live queue — auto-refresh |
| `POST /tabs` | Optimistic | Opens tab instantly, syncs in background |
| `POST /order-items/<id>/ready` | Inline spinner | Kitchen marks ready |
| `GET /bookings/today` | Skeleton | Full-page load on front desk screen |
| `POST /finance/close-period` | Progress bar + static text | "Closing day..." (takes 2–4s) |
| `GET /finance/reconciliation` | Skeleton | Complex report, may take 1–2s |
| `POST /waivers` | Inline spinner | Waiver sign + submit |
| `GET /inventory/variance` | Skeleton | Computed server-side, can be slow |
| `POST /equipment/<id>/safety-check` | Inline spinner | Should be fast (<500ms) |
| `GET /judge/alerts` | Skeleton | Owner dashboard load |
| `GET /notifications/inbox` | Nothing (cached) | Instant if cache warm |

### Auto-refresh policy

Kitchen queue and bar queue auto-refresh every 15 seconds. All other screens refresh
on user interaction (navigate back, pull-to-refresh, explicit Refresh button). No
background polling for financial data.

---

## Section 7 — Error Message Rules

### Three-part error contract

Every error message tells the user three things: **WHAT** happened, **WHY** it happened,
and **WHAT** to do next.

**Wrong:** "Error 400"
**Wrong:** "Request failed"
**Right:** "Payment not saved. The M-Pesa code QJN4X3 has already been used for tab #42. Check the code and try again."

The backend already returns plain-English errors on all endpoints (invariant in `CLAUDE.md`).
Frontend displays them verbatim. No translation layer. No "user-friendly rewording" that
strips the useful detail.

### Three placement patterns

| Stakes | Pattern | When |
|---|---|---|
| Low (informational) | **Toast** — auto-dismisses | Failed mark-read, minor validation |
| Medium (actionable) | **Inline** — below the field/button | Form validation, single-field error |
| High (blocks flow) | **Modal error** — must be dismissed | Payment failed, check-in blocked, session expired |

**Rule:** Never place a high-stakes error in a toast that auto-dismisses before the user
has time to act.

### No silent failures

If a request fails and the user did not receive feedback, that is a bug. Every catch block
must either show a toast, show an inline error, or show an error modal. `console.error`
alone is not acceptable in production.

### Error handling + backend pairing

| Backend response | HTTP code | Frontend action |
|---|---|---|
| `{"error": "..."}` | 400 | Inline error on the form field / Toast |
| `{"error": "Manager or above required."}` | 403 | Toast: "You don't have access to this." + nav back |
| `{"error": "Not found."}` | 404 | EmptyState on the page |
| `{"error": "Token has expired."}` | 401 | Redirect to login, clear auth state |
| `{"error": "Too many login attempts..."}` | 429 | Modal with cooldown timer |
| 5xx | 500+ | Modal: "Something went wrong. Try again in a moment." + retry button |
| Network offline | — | Offline banner (top of screen). Show cached data if available. |

---

## Section 8 — Form Rules

Six rules. Every form in both PWAs follows all six.

**Rule 1 — Disable submit until valid.**
Submit button is disabled (`disabled` state, visual + pointer-events) until all required
fields are non-empty and pass inline validation. No "submit then show errors" pattern.

**Rule 2 — Validate inline on blur.**
Errors appear when the user leaves a field (`onBlur`), not on every keystroke. Exception:
password/PIN fields validate live during typing (Rule 5).

**Rule 3 — Show character count when limit exists.**
Any field with `maxLength` shows `{length}/{max}` below the field. Turns status-failed
colour when > 90% full. Backend constraint is the authority; frontend mirrors it.

**Rule 4 — Pre-fill what's known.**
- Booking form: pre-fill guest name if guest record exists.
- Purchase request: pre-fill item if navigated from inventory item screen.
- Cash reconciliation: pre-fill expected amount from backend `GET /finance/cash/pending`.
- Clock-in: pre-fill employee name from auth store.
- Payment forms: pre-fill tab balance as the suggested amount.

**Rule 5 — Show password and PIN requirements live.**
PIN field shows requirements as the user types: "4 digits required". Checkmarks as each
criterion is met. Same pattern as the reference design from the UX series.

**Rule 6 — Be forgiving with formatting.**
- Phone numbers: accept `0712345678`, `+254712345678`, `254712345678` — backend WhatsApp
  socket normalises them (Q-3.3). Frontend strips spaces and hyphens before submitting.
- Money amounts: accept `1,500.00`, `1500`, `1.5k` — parse to Decimal before submitting.
- Dates: accept multiple formats, coerce to ISO-8601 before submitting.
- M-Pesa codes: strip spaces and uppercase before submitting.

### Backend-aware form examples

**Booking form (POST /bookings):**
Pre-fill: resource_id if navigated from resource page. Validation: check_in_date must be
today or future. check_out_date must be after check_in. `GET /bookings/availability` called
on date change — show "Not available" if resource is blocked. Submit creates HELD booking.

**M-Pesa STK Push (POST /finance/mpesa/charge):**
Phone field validates Kenyan format live. Amount pre-filled from tab balance. `tab_id`
hidden field from navigation context. Submit triggers changing-text spinner. On success:
Toast "Prompt sent to 0712..." On failure: Modal with exact Daraja error message.

**Purchase Request (POST /inventory/purchase-requests):**
Item dropdown from `GET /inventory/items`. Quantity field: numeric, positive, decimal
allowed. Notes optional. Submit creates PENDING purchase request, redirects to request
list with success toast.

---

## Section 9 — Friction Budget + Confirmation Patterns

### Tap budget table

The tap budget is the maximum number of taps from landing on a screen to completing the
primary action. More taps = more friction = more errors under pressure.

| Action | Max taps | Rationale |
|---|---|---|
| Clock in / clock out | 1 tap | Highest-frequency action. Must be instant. |
| Open a new tab | 2 taps | Tap "New Tab" + confirm table/name |
| Add item to order | 2 taps | Tap menu item + tap "Add" |
| Record M-Pesa payment (manual) | 3 taps | Amount + code + submit |
| Issue wristband | 3 taps | Payment method + amount confirm + issue |
| Mark notification read | 1 tap | Tap mark-read icon |
| Submit physical count for one item | 2 taps | Tap item + enter quantity (numeric) |
| Log maintenance event | 3 taps | Tap equipment + tap "Log Service" + confirm |
| Submit leave request | 4 taps | Select dates + reason + submit + confirm |
| Approve leave request | 2 taps | Tap "Approve" + confirm modal |
| Close a tab (balance = 0) | 2 taps | Tap "Close Tab" + confirm |
| Acknowledge judge alert | 2 taps | Tap alert + tap "Acknowledge" |

### Four confirmation patterns

**Pattern 1 — Toast + disabled button (1.5s grayout)**
For low-stakes irreversible actions. The action fires immediately. The button grays out
for 1.5 seconds to prevent double-tap. A toast confirms what happened.
Use for: mark-read, spoilage entry, clock-in, add-to-order.

**Pattern 2 — "Are you sure?" Modal**
For medium-stakes actions. Modal asks with a clear plain-English question. Two buttons:
confirm (primary) and cancel (secondary). Confirm fires the action.
Use for: cancel a booking, reject a leave request, close a tab, disable a menu item.

**Pattern 3 — Hold-to-Confirm (2 seconds)**
For high-stakes actions where the user must demonstrate intent, not just tap quickly.
A filled progress arc surrounds the button. User holds for 2 seconds. Releasing early
cancels. `preventClose` on the modal holding the button.
Use for: forfeit wristband credits, reject a purchase request with notes, close period
(lock the day's records), disable a staff account.

**Pattern 4 — Type-to-Confirm**
Reserved for critical destructive actions where a mistake would require manual recovery.
User must type a specific word/amount to unlock the confirm button.
Use for: bulk void an entire table's orders, manual cash adjustment that fires a JudgeAlert.
Not used in v1 for any other action — this pattern is expensive friction.

---

## Section 10 — Offline + PWA Install + Notifications

### PWA install prompts

Both apps intercept the `beforeinstallprompt` event and defer it. After the user
completes their first successful login, show an install prompt card at the top of the
home screen: "Add to Home Screen for faster access." If dismissed, don't show again
for 7 days. If accepted, call `prompt()` on the deferred event.

### Service worker cache strategies

| Data type | Strategy | TTL |
|---|---|---|
| App shell (HTML, JS, CSS) | Cache-first, update in background | Indefinite (version-keyed) |
| Static assets (fonts, icons) | Cache-first | Indefinite |
| Menu items | Network-first, fallback to cache | 1 hour stale-ok |
| Bookings today | Network-first, fallback to cache | 15 min stale-ok |
| Kitchen/bar queue | Network-only, no cache | Real-time, no stale |
| Notifications inbox | Network-first, fallback to cache | 5 min stale-ok |
| Auth tokens | Never cached (memory only) | Per session |
| Financial data | Network-only, no cache | Never stale |

### Offline behaviour table

| Screen | Offline behaviour |
|---|---|
| Clock-in / clock-out | Show cached shift. Clock action queued (IndexedDB). Syncs when online. |
| Kitchen / bar queue | Show cached queue with "Last updated X min ago" banner. Cannot submit when offline. |
| Dashboard | Show last-known data with staleness banner. No actions available offline. |
| Bookings list | Show cached list. Check-in/check-out disabled offline. |
| Notifications inbox | Show cached inbox. Mark-read queued, syncs when online. |

### Push notification routing

Push notifications are delivered via the Web Push API to registered service workers.
On notification tap, the service worker routes to the correct screen.

| Notification type | Source | Route on tap |
|---|---|---|
| Leave approved/rejected | `POST /hr/leave-requests/<id>/approve` trigger | My Schedule screen |
| Event assignment | `POST /events/<id>/assignments` trigger | Notification Inbox |
| Planning alert (calendar) | Calendar trigger offset days | Owner Dashboard |
| Judge alert (high severity) | `fire_alert_if_absent()` | Owner Alerts screen |
| Cash reconciliation reminder | End-of-shift cron | Cash Reconciliation screen |
| Booking arrival | `bookings flag-no-shows` cron | Front Desk Today screen |
| Budget exceeded | Budget check inline trigger | Owner Finance Dashboard |

### WhatsApp integration (Phase Q-3.3)

When `WHATSAPP_PROVIDER=twilio` and all four env vars are set, the dispatcher
(`app/services/notifications/dispatcher.py`) delivers to WhatsApp when a user is not
clocked in. The frontend does not know or care about the delivery channel — it reads
from `GET /notifications/inbox` regardless. The `channel` field on a notification tells
the audit log how it was delivered; the inbox shows it regardless.

Diagnostic: `GET /notifications/whatsapp/status` — manager can check socket status.
Frontend shows this in a settings/status screen (Owner PWA only).

---

## Section 11 — Auth Strategy

### Token storage

| Token | Storage | Why |
|---|---|---|
| Access token (15-min JWT) | In-memory (Zustand store) | Never persists across tab close. XSS cannot steal it from localStorage. |
| Refresh token (7-day JWT) | httpOnly cookie | Cannot be read by JavaScript. Sent automatically by the browser. |

### Refresh flow

Axios interceptor on every 401 response: call `POST /auth/refresh` (cookie is sent
automatically). If refresh succeeds, retry the original request with the new access token.
If refresh fails (expired or revoked), clear auth state and redirect to login. The refresh
is completely transparent — the user never sees it happen.

### Session idle timeouts

**Employee PWA:** 10 minutes of inactivity triggers auto-logout on any screen marked
`sensitive` (cash reconciliation, purchase approval, staff management). Non-sensitive
screens (kitchen queue, menu browse) do not auto-logout.

**Owner PWA:** 7-day idle timeout (enforced by refresh token TTL). Manual logout always
available.

### Kill-switch handling

Any 403 response with `"error": "Manager or above required."` or `"error": "Account is
deactivated."` → immediate force logout. Clear auth store. Redirect to login screen.
Show Toast: "Your session was ended. Please log in again."

The JWT may still be cryptographically valid — the kill-switch fires at the application
layer (Section 3.1 of SYSTEM_OVERVIEW.md). Frontend must respect 403 as a signal to
clear auth state.

### Shared tablet pattern

Kurahia's tablets are shared hardware — a waiter at the bar uses the same tablet as the
next waiter after their shift. This is the expected use case, not an edge case.

**Flow:**
1. Previous user's session times out (10 min idle) or they manually log out.
2. PIN entry screen appears. Large 4-digit keypad, easy to use with wet or gloved hands.
3. Staff enters 4-digit PIN (Argon2-hashed in backend). `POST /auth/pin-login`.
4. System loads the user's role-appropriate home screen.
5. All audit trail entries from this point use the authenticated user's username —
   not "the tablet." The backend enforces this.

**First login:** New staff use password login for first session, complete PIN setup
(`POST /auth/set-pin`), then use PIN for all future logins on tablets.

**Manager onboarding:** Manager creates user account (`POST /auth/users`), assigns role
and department, sets a temporary password. Staff logs in the first time with that password,
is prompted to set their PIN, and then uses PIN for all future logins.

### Role gates on the frontend

Frontend renders nothing if the user's role level is below what a screen requires. This
is implemented via the role gate HOC and confirmed via React Router protected routes.

If a user navigates directly to a URL their role cannot access:
1. Backend returns 403.
2. Frontend intercepts 403, shows EmptyState: "You don't have access to this area."
3. Navigation offers a Back button.
4. Backend audit log records the attempt.

Frontend never bypasses role checks. Frontend never modifies the role level in the
auth store to gain elevated access.

---

## Section 12 — Kiosk Mode

Three kiosk modes. All triggered by staff activating them from their normal screen. Customers
use kiosk screens without any login.

### What kiosk mode means

- No customer login. Staff PIN activates the kiosk; the tablet switches to kiosk presentation.
- No back button, no browser navigation, no swipe-to-go-back.
- No access to any other part of the app.
- Exit: staff PIN entry, submission of the kiosk flow, or 10-minute inactivity timeout.
- Full-screen display. Navigation chrome hidden.

### Kiosk 1 — Menu Browse

**Trigger:** Waiter activates from their POS screen. Tablet placed at a table or near the bar.

**Experience:** Customer scrolls through the menu. Categories are collapsible headers.
Each item shows name, description, price. No ordering — this is display-only.

**Aesthetic:** Full TICKET palette. Cormorant Garamond for category titles. Inter for
prices and descriptions. Images optional (shown if provided in menu item record).

**Exit:** Staff enters their PIN in a small hidden tap target (corner of screen).
Or: 10 minutes of inactivity → returns to staff login screen.

**Backend:** `GET /menu/items` — public data, no auth required for this endpoint.

### Kiosk 2 — Waiver Signing

**Trigger:** Front desk or water activities staff activates before a guest does a water activity.

**Experience:**
1. Full-screen waiver text (latest version from `GET /conduct/rules`). Customer reads.
2. "I have read and agree" checkbox at the bottom.
3. Signature canvas. Customer draws signature with finger.
4. "Submit Signature" button. Requires: checkbox ticked + signature drawn.
5. Staff confirms with their PIN. `POST /waivers` submitted.
6. Success screen: "Waiver recorded. Enjoy your activity!" — fades after 5 seconds.

**Security:** The submitted `signature_proof` field in the waiver is a base64 PNG of the
drawn signature. This is a legal record. The waiver record is append-only in the backend.

**Exit:** Only via submission or staff PIN override (if guest refuses to sign).

### Kiosk 3 — Guest Feedback

**Trigger:** Staff activates at end of a guest's visit. Tablet placed at exit or reception.

**Experience:**
1. Welcome screen: "How was your visit today?" (English + Swahili welcome).
2. 1–5 star rating. One tap. Stars animate on selection.
3. Department selector (optional): bar, restaurant, spa, water activities, housekeeping.
4. Comment field (optional): large text area, max 500 characters.
5. Submit. `POST /feedback`.
6. Thank-you screen for 5 seconds. Returns to welcome.

**Anonymous:** No customer login. No linking to a specific customer record unless a
booking ID or band ID is passed in from context when the kiosk is activated.

**30-second target:** The flow is designed to be completable in 30 seconds (just the star
rating). The 60-second auto-submit sends whatever is filled in.

---

## Section 13 — Accessibility

### Three-signal rule

Every status, outcome, or alert communicates via three channels: **colour + icon + text**.
No status is communicated by colour alone.

| Status | Colour | Icon | Text label |
|---|---|---|---|
| Payment confirmed | status-paid green | ✓ checkmark | "Paid" |
| Awaiting reconciliation | status-pending amber | ⏳ clock | "Pending" |
| Payment failed | status-failed red | ✕ cross | "Failed" |
| Judge alert — high | status-failed red | ⚠ triangle | "High Severity" |
| Equipment overdue | status-failed red | 🔧 wrench | "Service Overdue" |

### Font-size slider

Three settings: Small (14px base), Normal (16px base, default), Large (18px base).
Stored in `localStorage` under `kurahia:fontSize`. Applied via CSS custom property
`--font-size-base` on `<html>`. All `text-*` Tailwind classes scale relative to base.

### Semantic HTML

Use the correct HTML element for every interactive component.

- Buttons: `<button type="button">` — never a div with an onClick.
- Forms: `<form>` with `onSubmit`. Never a div containing inputs.
- Navigation: `<nav>` with `<ul><li><a>` structure.
- Headings: correct hierarchy (`h1` → `h2` → `h3`). Never skip a level.
- Tables: `<table><thead><tbody><tr><th><td>` for tabular data.
- Modals: `role="dialog"`, `aria-modal="true"`, `aria-labelledby`.
- Toast: `role="status"` for success, `role="alert"` for errors.

### ARIA labels

- Loading state: `aria-busy="true"` on the loading container. `aria-label="Loading bookings"` on Spinner.
- Icons without text: `aria-label` on the icon element. Never bare icon-only buttons without a label.
- Modal: `aria-label` or `aria-labelledby` on the dialog element.
- Form validation errors: `aria-describedby` linking the input to its error message.
- Status changes: `aria-live="polite"` on toast container.

### Keyboard navigation

- Tab order follows visual reading order.
- `Escape` closes modals and drawers.
- `Enter` and `Space` activate buttons and checkboxes.
- PIN keypad supports physical keyboard (digits 0–9).
- Kitchen queue keyboard: arrow keys to navigate items, Enter to mark ready.

### Performance + score targets

- Lighthouse accessibility score ≥ 90 on both apps.
- Zero axe-core critical violations. Zero axe-core serious violations in core flows.
- All interactive elements ≥ 44×44px touch target (WCAG 2.5.5).

---

## Section 14 — Animation Rules

### Framer Motion — three layers

Framer Motion is the only animation library. No CSS keyframes for interaction animations
(CSS keyframes acceptable for Skeleton shimmer only).

**Layer 1 — Micro-interactions (100–150ms)**
Button presses, toggle switches, checkbox checks. Small, immediate, tactile.
- Button tap: `whileTap={{ scale: 0.97 }}`, 100ms ease-out.
- Toggle switch: `layout` transition on thumb, 150ms spring.
- Checkbox check: `animate={{ scale: [0.8, 1.15, 1.0] }}`, 150ms.

**Layer 2 — Page + section transitions (200–300ms)**
Screen navigations, drawer open/close, modal enter/exit.
- Page navigation: slide + fade (`x: 40 → 0`, `opacity: 0 → 1`), 250ms ease-out.
- Modal enter: scale + fade (`scale: 0.95 → 1`, `opacity: 0 → 1`), 200ms ease-out.
- Drawer enter (bottom): `y: 100% → 0`, 300ms spring (`stiffness: 300, damping: 30`).
- Toast enter: `x: 20 → 0`, `opacity: 0 → 1`, 200ms ease-out.

**Layer 3 — Status changes (300–400ms)**
Meaningful state transitions that deserve emphasis.
- Tab balance updates: number count-up animation, 400ms ease-out.
- Payment confirmed: StatusBadge changes from "Pending" to "Paid" with spring scale,
  300ms. Brief glow in status-paid colour.
- Safety check item checked: row slides to sage-light bg, checkmark springs in, 300ms.
- Alert acknowledged: card fades to 40% opacity, checkmark animates in, 300ms.

### Never use

- Decorative animation (parallax, floating particles, hover text effects).
- Animations > 400ms. If it takes longer than that, it's too slow.
- Animations that block user input (no disabling interactions during transitions).
- Animations that play every time the user performs a frequent action
  (e.g., don't animate every clock-event tick — only animate state changes that
  carry meaning).
- `AnimatePresence` without a stable `key` — causes ghost elements.

### Reduced motion

All Layer 1 and Layer 3 animations respect `prefers-reduced-motion`. When set, substitute
instant show/hide for all transitions. Skeleton shimmer replaced with static appearance.

---

## Section 15 — Audit-Aware UI + Role-Aware States

### Every modified record shows its author

Any record that can be edited or actioned shows: "Last changed by [Name], [Time ago]."
This applies to: tab payments, bookings, leave requests, purchase approvals, cash
reconciliations, equipment maintenance logs.

Tapping the "Last changed by" line opens a Drawer showing the AuditLine for that action.
The AuditLine component (Section 4.15) renders: timestamp + actor username + action +
target + details. No raw JSON — human-readable format only.

### Role-aware empty states

The same empty data set reads differently depending on who is looking at it.

| Screen | Empty state for staff (level 1) | Empty state for manager (level 5) |
|---|---|---|
| My open tabs | "No open tabs. Start a new one." | "No staff tabs open. Quiet shift." |
| Leave requests | "No pending requests." | "No leave requests to review." |
| Notifications | "You're all caught up." | "No pending notifications." |
| Kitchen queue | "No orders waiting." | "All orders delivered." |

| Screen | Empty state for manager (level 5) | Empty state for owner (level 10) |
|---|---|---|
| Judge alerts | "No open alerts." | "All clear. No anomalies detected." (achievement) |
| Suggestions | "No new suggestions." | "No owner-private suggestions." |
| Finance reconciliation | "No pending items." | "All clear for this period." |

### Always-present numbers (top bar per role)

The top navigation bar shows live numbers relevant to the user's role. These are derived
from cached data (refreshed on screen focus, not on a background timer).

| Role | Top bar shows |
|---|---|
| Cashier / waiter (level 1) | My open tabs count · My tables count |
| Gate / front desk (level 3) | Active wristbands · Today's headcount |
| Manager (level 5) | Approvals pending · Alerts open · Staff on duty |
| Owner (level 10) | Revenue today · Alerts open · Bookings this weekend |

---

## Section 16 — Every Screen Mapped

31 screens total. 22 Employee PWA + 3 kiosk modes + 6 Owner PWA.

---

### E-1: Login / PIN Entry

**Visible to:** All roles (pre-auth screen)
**Purpose:** Authenticate staff. Password login for first session; PIN for subsequent sessions.
**Backend:** `POST /auth/login`, `POST /auth/pin-login`
**States:**
- Loading: Spinner on submit button.
- Success: Redirect to role-appropriate home screen.
- Error: Inline error below PIN field. "Wrong PIN. 2 attempts remaining." After lockout: Modal "Account locked for 5 minutes."
- Empty: N/A — always shows the login form.
- Partial: N/A — all-or-nothing auth.
**Friction budget:** 1 tap (PIN keypad → confirm)
**Notes:** PIN keypad digits are large (80×80px min). Password field shown only on first login.

---

### E-2: Clock-In / Clock-Out

**Visible to:** Level 1+ (all staff)
**Purpose:** Record start and end of shift. Single most frequent action in the app.
**Backend:** `POST /hr/clock-in`, `POST /hr/clock-out`
**States:**
- Loading: Button grays out for 500ms (optimistic — no loader shown on first tap).
- Success: Button flips from "Clock In" to "Clock Out" (or vice versa). Toast: "Clocked in at 08:45."
- Error: Toast: "Clock-in failed. Check your connection and try again."
- Empty: N/A — button always present.
- Partial: If shift schedule unavailable, show button only without schedule context.
**Friction budget:** 1 tap
**Notes:** Shows current shift time (if clocked in: "On duty: 2h 34m"). Offline: queues the event.

---

### E-3: My Schedule

**Visible to:** Level 1+ (all staff)
**Purpose:** View assigned shifts for the next 7 days.
**Backend:** `GET /hr/shifts`
**States:**
- Loading: Skeleton — 7 date rows with placeholder shift cards.
- Success: Date rows with shift cards (time, department, notes).
- Error: Toast + Retry button. Cached schedule shown with staleness banner.
- Empty: EmptyState: "No shifts scheduled this week. Check with your manager."
- Partial: If one day fails, show that day as error card; others load normally.
**Friction budget:** N/A (read-only screen)
**Notes:** Today's shift highlighted. Pull-to-refresh.

---

### E-4: Notification Inbox

**Visible to:** Level 1+ (all staff)
**Purpose:** In-app notifications: assignments, leave decisions, planning alerts, system alerts.
**Backend:** `GET /notifications/inbox`, `POST /notifications/<id>/mark-read`
**States:**
- Loading: Skeleton — 5 notification row placeholders.
- Success: Notification list. Unread bold, read at 60% opacity.
- Error: Toast. Cached inbox shown.
- Empty: EmptyState: "You're all caught up." with a checkmark illustration.
- Partial: N/A — list loads atomically.
**Friction budget:** 1 tap (mark-read)
**Notes:** Badge count in bottom nav. Tap notification routes to relevant screen.

---

### E-5: Code of Conduct

**Visible to:** Level 1+ (all staff)
**Purpose:** Read current conduct rules, sign if unsigned.
**Backend:** `GET /conduct/rules`, `POST /conduct/sign`
**States:**
- Loading: Skeleton — document placeholder.
- Success: Rules text + "Signed on [date]" badge OR "Sign Now" button.
- Error: Toast + Retry.
- Empty: EmptyState: "No conduct rules published yet."
- Partial: N/A.
**Friction budget:** 2 taps (scroll to bottom + Sign)
**Notes:** Scroll-to-confirm required — Sign button only activates after scrolling 90% of document.

---

### E-6: Suggestion Box

**Visible to:** Level 1+ (all staff)
**Purpose:** Submit anonymous or identified suggestions (MANAGEMENT or OWNER_PRIVATE).
**Backend:** `POST /suggestions`
**States:**
- Loading: Spinner on submit.
- Success: Toast "Suggestion submitted. Thank you." Form resets.
- Error: Inline errors on empty required fields.
- Empty: N/A — always shows form.
- Partial: N/A.
**Friction budget:** 3 taps (category + body + submit)
**Notes:** OWNER_PRIVATE toggle clearly labelled: "Send directly to owner (managers cannot see this)."

---

### E-7: Leave Request

**Visible to:** Level 1+ (all staff)
**Purpose:** Submit leave request. View request history and status.
**Backend:** `POST /hr/leave-requests`, `GET /hr/leave-requests`
**States:**
- Loading: Skeleton on history list.
- Success: Form submission → Toast + new item appears in history list.
- Error: Inline errors (dates required, end after start).
- Empty: EmptyState in history list: "No leave requests yet."
- Partial: History fails, form still usable.
**Friction budget:** 4 taps (start date + end date + reason + submit)

---

### E-8: Absence Notice

**Visible to:** Level 1+ (all staff)
**Purpose:** Record an unplanned absence (calling in sick, emergency).
**Backend:** `POST /hr/absence-notices`
**States:**
- Loading: Spinner on submit.
- Success: Toast "Absence recorded. Your manager has been notified."
- Error: Toast if network failure.
- Empty: N/A.
- Partial: N/A.
**Friction budget:** 2 taps (reason + submit)

---

### E-9: Kitchen Queue

**Visible to:** Level 1+ (kitchen and bar staff)
**Purpose:** See live order queue. Mark items received, mark items ready.
**Backend:** `GET /kitchen/queue`, `POST /order-items/<id>/ready`, `POST /order-items/<id>/receive`
**States:**
- Loading: Skeleton — KitchenTicket placeholders.
- Success: Live queue of KitchenTicket cards (TICKET palette).
- Error: Banner: "Queue unavailable. Last updated 3 min ago."
- Empty: EmptyState: "No orders waiting. Great work."
- Partial: If one order fails to update, that ticket shows an error badge.
**Friction budget:** 2 taps (tap item + mark ready)
**Notes:** Auto-refreshes every 15s. Swipe left on item to mark received. stamp-red for URGENT orders.

---

### E-10: Bar Queue

**Visible to:** Level 1+ (bar staff)
**Purpose:** Mirror of Kitchen Queue for bar-only orders.
**Backend:** `GET /bar/queue`, `POST /order-items/<id>/ready`
**States:** Same as E-9.
**Friction budget:** 2 taps

---

### E-11: Open Tab / Order Entry (Waiter)

**Visible to:** Level 1+ (waiters)
**Purpose:** Open a tab, browse menu, add items to order, send to queue.
**Backend:** `POST /tabs`, `GET /menu/items`, `POST /orders`, `POST /orders/<id>/send`
**States:**
- Loading: Menu loads with Skeleton. Tab opens instantly (optimistic).
- Success: Menu grid visible. Running order sidebar shows current items.
- Error: If menu fails, show cached menu with staleness banner.
- Empty: Empty menu → EmptyState: "No items available right now."
- Partial: One menu category fails → show other categories, error badge on failed one.
**Friction budget:** 2 taps (tap item + tap Add)
**Notes:** Menu is category-tabbed. Search field for large menus. Running total visible at all times.

---

### E-12: Tab Detail / Payment

**Visible to:** Level 1+ (waiters)
**Purpose:** View open tab, see current balance, record payment, close tab.
**Backend:** `GET /tabs/<id>`, `POST /tabs/<tab_id>/payments`, `POST /tabs/<tab_id>/close`
**States:**
- Loading: Skeleton — tab balance placeholder.
- Success: Balance prominent (`text-2xl`). Line items list. Payment form.
- Error: Payment failed → Modal with specific error from backend.
- Empty: Tab exists but no charges → "No items ordered yet."
- Partial: If balance calculation fails, show "Balance unavailable" — never show 0 incorrectly.
**Friction budget:** 3 taps (amount + payment method + submit)
**Notes:** Tab balance uses `tabular-nums`. GuestTabCard composite for consolidated view.

---

### E-13: Wristband Issuance (Gate)

**Visible to:** Level 3+ (gate staff)
**Purpose:** Issue numbered wristband to day visitor. Record payment.
**Backend:** `POST /gate/issue-band`, `GET /gate/active-bands`
**States:**
- Loading: Spinner on issue button.
- Success: "Band #42 issued. Payment KSh 3,000 recorded." Current headcount updates.
- Error: Modal if payment recording fails.
- Empty: N/A — action screen, not a list.
- Partial: Headcount fails to load → issue button still usable.
**Friction budget:** 3 taps (payment method + confirm amount + issue)
**Notes:** Band number assigned server-side (SELECT FOR UPDATE — no duplicates). Shows today's running total.

---

### E-14: Wristband Lookup (Gate)

**Visible to:** Level 1+ (all staff)
**Purpose:** Look up an active wristband by number. See tab balance.
**Backend:** `GET /gate/bands/<num>`
**States:**
- Loading: Spinner on search.
- Success: Band details + current tab balance.
- Error: "Band not found." inline.
- Empty: N/A — search result state.
- Partial: N/A.
**Friction budget:** 2 taps (enter number + search)

---

### E-15: Booking Check-In (Front Desk)

**Visible to:** Level 3+ (front desk/manager)
**Purpose:** Check in arriving guests. Confirm deposit. Open villa tab.
**Backend:** `GET /bookings/today`, `POST /bookings/<id>/check-in`
**States:**
- Loading: Skeleton — today's arrivals list.
- Success: Arrivals listed with BookingCard components. Check-in opens Villa tab, shows confirmation.
- Error: "Check-in failed." with specific backend error (e.g., "Waiver required first").
- Empty: EmptyState: "No arrivals today."
- Partial: N/A.
**Friction budget:** 3 taps (tap booking + confirm waiver + check in)
**Notes:** `GET /front-desk/today` provides the aggregated view.

---

### E-16: Waiver Record (Front Desk / Water Activities)

**Visible to:** Level 1+ (front desk, water activities staff)
**Purpose:** Record signed liability waiver before water activity starts.
**Backend:** `POST /waivers`
**States:**
- Loading: Spinner on submit.
- Success: Toast "Waiver recorded for [Name]." Returns to previous screen.
- Error: "Waiver not saved. Check connection and retry."
- Empty: N/A — action screen.
- Partial: N/A.
**Friction budget:** 3 taps (guest name + activity type + submit)
**Notes:** Signature canvas optional — text acknowledgment + staff witness is minimum. Kiosk signing (E-K2) is the preferred flow for the guest to sign themselves.

---

### E-17: Pre-Use Safety Check (Water Activities Lead)

**Visible to:** Level 1+ (water activities staff / manager)
**Purpose:** Complete structured 5-item pre-use checklist before operating equipment.
**Backend:** `GET /equipment/checklist-templates/<type>`, `POST /equipment/<id>/safety-check`
**States:**
- Loading: Skeleton — 5 ChecklistRow placeholders.
- Success: All 5 items rendered. Submit enables only when all checked.
- Error (submit): Inline — specific unchecked item highlighted in status-failed. "life_jackets_on_board must be confirmed before submitting."
- Empty: N/A — equipment selection always provides a template.
- Partial: Template load fails → generic 5-item checklist with text fields.
**Friction budget:** 6 taps (5 item taps + submit)
**Notes:** Depends on Q-3.2 (shipped). Template fetched from `GET /equipment/checklist-templates/jetski` etc. Submit disabled until all items checked.

---

### E-18: Inventory Count (Department Head)

**Visible to:** Level 5+ (manager / department head)
**Purpose:** Submit physical stock count. View variance report.
**Backend:** `GET /inventory/items`, `POST /inventory/counts`, `GET /inventory/variance`
**States:**
- Loading: Skeleton — item list with count input placeholders.
- Success: Items list with inline numeric inputs. Variance report tab.
- Error: "Count submission failed." Toast + keep form state.
- Empty: EmptyState: "No inventory items configured yet."
- Partial: Variance report fails to load → count submission still usable.
**Friction budget:** 2 taps per item (tap field + enter number)
**Notes:** StockRow composites. Variance column colour-coded (Section 4.16).

---

### E-19: Purchase Request (Department Head)

**Visible to:** Level 1+ (any staff can request; manager approves)
**Purpose:** Request a purchase. See request history and approval status.
**Backend:** `POST /inventory/purchase-requests`, `GET /inventory/items`
**States:**
- Loading: Skeleton on item dropdown.
- Success: Form submitted → Toast + request appears in history.
- Error: Inline validation (item required, quantity required, positive quantity).
- Empty: No prior requests → EmptyState.
- Partial: N/A.
**Friction budget:** 4 taps (item + quantity + notes + submit)

---

### E-20: Equipment Log (Manager / Dept Head)

**Visible to:** Level 5+ (manager)
**Purpose:** Log maintenance event for equipment. See maintenance history.
**Backend:** `GET /equipment`, `POST /equipment/<id>/maintenance`
**States:**
- Loading: Skeleton — equipment list.
- Success: List with MaintenanceRow composites. Overdue items badged.
- Error: "Log not saved." Toast.
- Empty: EmptyState: "No equipment records."
- Partial: Maintenance history fails → log action still usable.
**Friction budget:** 3 taps (select equipment + add notes + log)

---

### E-21: Cash Reconciliation (Manager)

**Visible to:** Level 5+ (manager)
**Purpose:** Record actual cash handed in vs POS expected. Mark SHORT / BALANCED / OVER.
**Backend:** `GET /finance/cash/pending`, `POST /finance/cash/reconcile`
**States:**
- Loading: Skeleton — per-staff cash summary.
- Success: Per-staff rows with expected vs actual. Overall reconciliation status.
- Error: Modal if reconciliation fails.
- Empty: EmptyState: "No cash handovers pending."
- Partial: One staff member's data fails → others still reconcilable.
**Friction budget:** 3 taps (enter actual amount + select status + submit)
**Notes:** Uses Hold-to-Confirm (2s) for submissions where SHORT amount exceeds threshold. AuditLine shows previous reconciliations.

---

### E-22: Staff Attendance + Shift Management (Manager)

**Visible to:** Level 5+ (manager)
**Purpose:** View today's attendance. Manage shifts. Approve leave.
**Backend:** `GET /hr/attendance/today`, `GET /hr/shifts`, `POST /hr/shifts`,
`GET /hr/leave-requests`, `POST /hr/leave-requests/<id>/approve`
**States:**
- Loading: Skeleton — attendance grid.
- Success: Tabbed view: Today's Attendance | Shifts | Leave Requests.
- Error: Per-tab error handling (one tab fails, others work).
- Empty: Empty attendance: "No staff clocked in yet."
- Partial: Shift creation fails → attendance view still works.
**Friction budget:** 2 taps to approve leave (tap request + confirm)

---

### K-1: Kiosk — Menu Browse

**Visible to:** Public (no auth). Staff PIN to exit.
**Purpose:** Read-only menu display for customers at tables or bar.
**Backend:** `GET /menu/items`
**States:** See Section 12.
**Friction budget:** 0 taps (browse only)

---

### K-2: Kiosk — Waiver Signing

**Visible to:** Public (no auth). Staff activates + confirms.
**Purpose:** Collect digital waiver signature before water activity.
**Backend:** `GET /conduct/rules`, `POST /waivers`
**States:** See Section 12.
**Friction budget:** 3 taps (checkbox + draw signature + submit)

---

### K-3: Kiosk — Guest Feedback

**Visible to:** Public (no auth).
**Purpose:** Collect 1–5 star rating + optional comment at end of visit.
**Backend:** `POST /feedback`
**States:** See Section 12.
**Friction budget:** 1 tap (star rating only, minimum)

---

### O-1: Owner Dashboard

**Visible to:** Level 10 (owner only)
**Purpose:** All-up resort status at a glance. Ten metric tiles.
**Backend:** `GET /dashboard/overview`, `/inventory`, `/finance`, `/bookings`, `/staff`,
`/conduct`, `/suggestions`, `/calendar`, `/feedback`, `/equipment`, `/alerts`
**States:**
- Loading: Each tile shows its Skeleton independently (PARTIAL state by design).
- Success: All 10 tiles populated.
- Error: Per-tile error badge. Other tiles unaffected.
- Empty: Each tile shows its zero-state (revenue=0, alerts=0, etc.).
- Partial: Standard tile-level degradation.
**Friction budget:** 1 tap (navigate to detail from any tile)
**Notes:** Revenue today is the most prominent tile (`text-3xl`). Alerts badge drives urgency.

---

### O-2: Finance Dashboard

**Visible to:** Level 10 (owner only)
**Purpose:** Daily and period revenue breakdown. Reconciliation status. Period close.
**Backend:** `GET /finance/dashboard`, `GET /finance/reconciliation`, `POST /finance/close-period`
**States:**
- Loading: Skeleton — revenue chart placeholder.
- Success: Revenue by method. Pending reconciliation count. Period close button.
- Error: "Finance data unavailable. Try again."
- Empty: "No transactions recorded yet for this period."
- Partial: Reconciliation fails → revenue data still shown.
**Friction budget:** 2 taps (period close: button + hold-to-confirm 2s)

---

### O-3: Judge Alerts

**Visible to:** Level 10 (owner only)
**Purpose:** List open anomalies detected by the judge engine. Acknowledge or dismiss.
**Backend:** `GET /judge/alerts`, `POST /judge/alerts/<id>/acknowledge`
**States:**
- Loading: Skeleton — AlertCard placeholders.
- Success: Grouped by severity. CRITICAL first, then HIGH, MEDIUM, LOW.
- Error: Toast + Retry.
- Empty: EmptyState: "All clear. Judge found no anomalies this period." (achievement framing)
- Partial: N/A — list loads atomically.
**Friction budget:** 2 taps (tap alert + acknowledge)
**Notes:** AlertCard shows AuditLine drilldown. Dismissed alerts move to separate section, don't disappear.

---

### O-4: Staff Performance + Payroll Draft

**Visible to:** Level 10 (owner only)
**Purpose:** Per-staff performance scores from guest feedback. Draft payroll from hours.
**Backend:** `GET /hr/performance/<id>`, `GET /hr/payroll-draft`, `GET /feedback/staff/<id>`
**States:**
- Loading: Skeleton — staff list with score placeholders.
- Success: Staff list with rolling performance scores. Payroll draft table.
- Error: "Performance data unavailable."
- Empty: "No feedback recorded yet. Scores will appear after guests submit ratings."
- Partial: Payroll draft fails → performance scores still shown.
**Friction budget:** N/A (read-only + export)

---

### O-5: Booking Management

**Visible to:** Level 10 (owner, but manager can also access level 5)
**Purpose:** All bookings, upcoming arrivals, guest records, deposits.
**Backend:** `GET /bookings`, `GET /guest-records`, `GET /booking-payments`
**States:**
- Loading: Skeleton — BookingCard list.
- Success: Filterable list. Filter by status, resource, date.
- Error: Toast + cached list.
- Empty: EmptyState: "No bookings in this period."
- Partial: Guest records fail → bookings still shown.
**Friction budget:** 1 tap (navigate to booking detail)

---

### O-6: Settings / Admin

**Visible to:** Level 10 (owner only)
**Purpose:** Department management, role creation, judge baseline tuning, socket status.
**Backend:** `GET/POST/PATCH /admin/departments`, `GET/POST/PATCH /admin/roles`,
`GET/PATCH /admin/baselines`, `GET /finance/mpesa/status`, `GET /finance/bank/status`,
`GET /finance/card/status`, `GET /notifications/whatsapp/status`
**States:**
- Loading: Skeleton per settings section.
- Success: Four tabs: Departments | Roles | Judge Baselines | Socket Status.
- Error: Per-section error handling.
- Empty: Each section shows zero state.
- Partial: One tab fails → others work.
**Friction budget:** 3 taps (navigate to tab + edit field + save)
**Notes:** Socket status section shows all four sockets (M-Pesa, Bank, Card, WhatsApp) with
their `configured: bool` and `message: str` from diagnostic endpoints. Green/amber/red indicator.

---

## Section 17 — Build Order + Gating Discipline

### The principle

Same gated discipline as backend Phase A, Phase B, Phase Q. Each chunk:
- Has a clear, bounded scope
- Ends with a commit milestone
- Has a **Gate** — a specific verification action against the live backend (not mocks)
- Stops and reports before proceeding to the next chunk

A gate is not "it looks right in the browser." A gate is "I made this specific request
to the backend and verified the response in the network tab / DB record."

### Build order rationale

**Foundation first (F-0 to F-6):** No screen is built until design tokens, components,
and auth are working. Building screens on an unstable foundation causes rework. The
component library in `shared_ui/` is the single source of design truth for both apps.

**Employee PWA second (F-7 to F-11):** The employee app is operationally critical. The
resort cannot open without clock-in, order entry, cash reconciliation, and wristband
issuance. Owner monitoring is valuable but secondary.

**Kiosk mode third (F-12 to F-14):** Customer-facing flows that depend on the employee
infrastructure (menu data, waiver backend, feedback endpoint).

**Owner PWA fourth (F-15 to F-16):** Monitoring and management. Can launch after the
resort has been running on the employee app for a week or two.

**Polish last (F-17 to F-19):** PWA install prompts, offline behaviour, visual regression
tests, accessibility audit, and bundle optimisation. These are the difference between
"it works" and "it's production-quality."

### Dependency map

```
F-0 ── F-1 ── F-2 ── F-3 ── F-4 ── F-5 ── F-6
                                      │       │
                              F-7 ───┘       │
                              F-8 ───────────┤
                              F-9 ───────────┤
                              F-10 (needs Q-3.2 ✅)
                              F-11 ──────────┘
                              F-12 (needs menu backend ✅)
                              F-13 (needs waivers backend ✅)
                              F-14 (needs feedback backend ✅)
                              F-15 ─── F-16
                              F-17 (needs Q-3.3 WhatsApp ✅)
                              F-18
                              F-19
```

All backend dependencies (Q-3.2 safety checklist, Q-3.3 WhatsApp socket, waiver endpoints,
feedback endpoint) are already shipped as of Phase Q-3 COMPLETE.

### What stops forward progress

- A Gate fails: fix it before moving on.
- A backend endpoint returns a different shape than expected: understand it before
  building UI against it.
- A component fails its accessibility test: fix before building screens that use it.

There is no "fix it later" in this build. Later never comes.

### Estimated timeline

| Phase | Chunks | Estimated hours |
|---|---|---|
| Foundation | F-0 to F-6 | 20–28h |
| Employee PWA | F-7 to F-11 | 20–28h |
| Kiosk | F-12 to F-14 | 6–8h |
| Owner PWA | F-15 to F-16 | 8–10h |
| Polish | F-17 to F-19 | 8–12h |
| **Total** | | **62–86h** |

---

## Footer

---

> "End of design phase. Code begins after this doc is signed off."

**Reference documents:**
- `docs/SYSTEM_OVERVIEW.md` — full backend reference, every endpoint
- `PAYMENTS_DESIGN.md` — payment socket architecture + activation runbooks
- `CLAUDE.md` — project context, invariants, commands, communication style

**Version:** v1.0
**Date:** 2026-06-08
**Status:** DESIGN PHASE COMPLETE

---

*The backend is production-ready: 479 tests, 18 blueprints, 213 endpoints, all three
payment sockets dormant and activatable. The component library, design tokens, and
every screen spec are in this document. The next action is F-0: Project Skeleton.*
