# Google Stitch Prompt — Kurahia Resort System (ALL Dashboards)

Copy-paste into Google Stitch. Generate each dashboard separately, screenshot, drop into docs/references/.

---

## GLOBAL DESIGN SYSTEM

**Product:** Kurahia — resort management system for Waterfront Country Club, a lakeside resort in Juja, Kenya. Used on tablets mounted at stations (kitchen, bar, gate) and personal phones (staff).

**Color Palette:**
- `#171717` — Base background (near-black)
- `#F25623` — Orange accent (CTAs, active states ONLY — never splash everywhere)
- `#4D4D4D` — Dark gray (card surfaces, secondary elements)
- `#DEDEDE` — Light gray (primary text, headings)
- `#FFFFFF` at 6-8% opacity — Glass card backgrounds
- `#FFFFFF` at 8% opacity — Card borders
- Status: green `#22C55E` (paid/OK), amber `#F59E0B` (pending), red `#EF4444` (failed/alert)

**Glass Cards:**
- Background: `rgba(255,255,255,0.06)`
- Border: `1px solid rgba(255,255,255,0.08)`
- Border-radius: 16px
- Shadow: `0 8px 32px rgba(0,0,0,0.3)`, inset `0 1px 0 rgba(255,255,255,0.05)` (top edge highlight = frosted glass illusion)
- Backdrop-filter: `blur(20px) saturate(160%)`

**Background Treatment:**
- Base: solid `#171717`
- body::before: 3 ultra-subtle ambient gradient blobs (orange 4% bottom-left, gray 6% top-right, faint light 2% center) — these give glass panels content to blur through

**Typography:**
- Sans: Hanken Grotesk (body, UI labels)
- Serif: Fraunces (headings, brand)
- Mono: JetBrains Mono (financial numbers, tabular data)
- Labels: 10px, tracking-widest, uppercase, `rgba(222,222,222,0.35)`
- Body: 14px, `#DEDEDE`
- Headings: Fraunces, 24-32px, bold, white

**Icons:**
- SVG stroke icons only — NO emoji, no icon fonts
- 20×20 viewBox, strokeWidth 1.5, strokeLinecap="round", strokeLinejoin="round"
- Color: `rgba(222,222,222,0.5)` default, `#F25623` when active

**Motion (Framer Motion):**
- Page entry: opacity 0→1, y 8→0, staggerChildren 0.04
- Card hover: y: -2 (desktop only)
- Button press: scale 0.98
- Spring: damping 28, stiffness 350
- NO bounce, NO elastic, NO flashy — smooth and purposeful

**Buttons:**
- Primary: `bg-[#F25623]` flat with `shadow-[0_4px_14px_rgba(242,86,35,0.3)]` glow. Hover: `bg-[#FF6B3D]`
- Secondary: `bg-white/8` glass button with `border-white/15`, backdrop-blur
- Ghost: transparent, hover reveals orange tint `bg-[#F25623]/8`
- Danger: `bg-gradient-to-b from-red-500 to-red-700`
- All: rounded-xl, min-h-44px touch target, font-semibold

**Anti-patterns (AVOID):**
- Warm cream backgrounds with serif + terracotta
- Bright neon accents
- Wrapping everything in cards (let content breathe)
- Uniform grids (use mixed-size cards for hierarchy)
- Emoji icons
- Bounce/elastic animations
- Generic SaaS look — this is HOSPITALITY

---

## DASHBOARD 1: OWNER (observation, not operations)

> Owner sees the resort's health from a distance. Read-only metrics. No buttons to "do" things — they observe and get alerted.

**Layout:** Left sidebar nav (56px collapsed, 208px expanded) + main content area

**Sections:**
1. **Hero Tile** (full width) — "Good evening, Wachira" + today's revenue as large number (KSh 487,200) + small AreaChart showing today's revenue curve. Payment method donut (Cash 62%, M-Pesa 28%, Card 10%)
2. **Metric Grid** (3 columns, mixed sizes):
   - Occupancy: "4/6 villas" with occupancy % ring
   - Staff On Duty: "12/18" with clock icon
   - Open Tabs: count with balance total
   - Active Bands: count + total entry fees
   - Bookings Today: confirmed + pending
   - Judge Alerts: count with severity badge (red if critical)
   - Budget Health: mini sparkline per department
   - Guest Satisfaction: average rating
   - Kitchen Queue: orders waiting
   - Cash Reconciled: today's recon status
   - Equipment Due Service: count
   - Suggestions Inbox: unread count
3. **Bottom Bar** — Quick nav: Alerts, Finance, Staff, Bookings, Settings

**Key detail:** Numbers use JetBrains Mono tabular-nums. Status colors: green (healthy), amber (attention), red (critical). Every tile wrapped in ErrorBoundary.

---

## DASHBOARD 2: MANAGER (operations command center)

> Manager runs daily operations. Needs to see stock health, approve requests, manage staff, track budgets.

**Sections (mixed-size card layout):**
1. **Header** — "Good morning, [name]" + date + "Operations" subtitle
2. **Pending Approvals** (compact card, right of header) — big number, amber if > 0, click → purchases
3. **Stock Behavior** (wide 2/3 card) — bar chart (12 items, stock vs reorder level) + summary stats (Total / Low / OK)
4. **Department Stock** (narrow 1/3 card) — health bars per dept: Kitchen 18/20, Bar 12/12, etc. Green/amber/red based on health %
5. **Budget Burn** (half width) — progress bars per department showing % spent. Red when over budget
6. **Low Stock** (half width) — list of items below reorder level with current stock in red
7. **Manage Section** — 8 action tiles in 4×2 grid (mobile) / 8-col row (desktop):
   - Staff (person+ icon) — "Create accounts & assign tablets"
   - Menu (document icon) — "Add items, set prices & recipes"
   - Shifts (calendar icon) — "Schedule who works when"
   - Attendance (person✓ icon) — "Today's roster — who clocked in"
   - Front Desk (lock icon) — "Arrivals, departures, occupancy"
   - Cash (bill icon) — "Reconcile staff cash handovers"
   - Leave (calendar✓ icon) — "Approve or reject leave requests"
   - Purchases (cart icon) — "Review restock requests & budgets"

Each tile: glass-card-sage, SVG icon top, label + description below, left-aligned.

---

## DASHBOARD 3: HEAD CHEF (kitchen intelligence)

> Head chef oversees kitchen operations — stock levels, recipes, menu management, and the live queue.

**Sections:**
1. **Header** — "Kitchen" + chef's name
2. **Stock Overview** (wide card) — 3 big numbers: Total Items / Low / OK. Mini bar chart below
3. **Low Stock Alert** — if any items below reorder, show list with red quantities. If all healthy: "All stock levels healthy ✓" in green
4. **Quick Tiles** (2×2 grid):
   - Recipes — "Enter & edit recipes per dish" (document icon)
   - Menu — "Add new dishes" (list icon)
   - Variance — "Expected vs actual" (chart icon)
   - Kitchen — "Live orders" (pot icon)

Each tile: glass-card with SVG icon, title, subtitle.

---

## DASHBOARD 4: KITCHEN STATION (order queue)

> Mounted tablet at the kitchen pass. Shows incoming orders as receipt-style ticket cards.

**Layout:** Full-screen queue, no sidebar. Always-visible clock top-right (Fraunces serif, 1s updates).

**Elements:**
- **Header bar** — "Kitchen" title + clock + stock warnings badge + search + compact toggle
- **Order cards** — Receipt-style: white text on dark glass, JetBrains Mono for order numbers. Shows: table/reference, items with quantities, notes, time since sent
- **States:** SENT (orange border-left), RECEIVED (amber), READY (green glow)
- **Audio alerts** — bell icon indicates audio is active for new orders

---

## DASHBOARD 5: BAR STATION

> Same layout as kitchen but filtered to BAR prep station items. Different accent color possible.

---

## DASHBOARD 6: WAITER (tables + ordering)

> Waiter sees their open tables, opens new ones, charges wristbands.

**My Tables screen:**
1. **Header** — "My Tables" + count of open tables + "+ New Table" button (orange)
2. **Wristband Input** — number input + "Open Band" button. Charges to guest's gate credit
3. **Ready Pings** — green pulsing cards from kitchen: "Order ready for Table 7" — tap to dismiss
4. **Table List** — glass cards showing: reference name, opened time, balance (red if outstanding, green if settled)
5. **Empty State** — SVG briefcase icon + "No open tables. Tap + New Table to start."

**Order Detail screen (when table tapped):**
1. **Entry choice** — "Show Menu" (→ customer menu view) or "Straight to Order"
2. **Two-pane layout** — Menu items left (photo grid), order summary right
3. **Payment section** — method selector (Cash/M-Pesa/Card/Bank) + amount input + "Exact" shortcut

---

## DASHBOARD 7: GATE HUB (entry + wristbands)

> Gate staff handles guest entry. Two paths: day guest (pay KSh 3,000 + get band) or booked guest (verify booking + admit).

**Sections:**
1. **Header** — "Gate" + today's stats (bands issued, total entry fees)
2. **Issue Band Card** (primary action) — payment method selector + "Issue Wristband" orange button
3. **Booking Check-In** — search by booking reference, verify + admit
4. **Band Lookup** — search by band number, see status/balance
5. **Today's Stats** — bands issued, total fees, active bands count

---

## DASHBOARD 8: SPA / GYM / WATER ACTIVITIES (unified POS)

> Service departments sell activities, view their stock (read-only), and request restocks from manager.

**3-tab layout:**
1. **Sell tab** — POS grid of service items with +/- quantity buttons, total bar, "Proceed to Payment" orange CTA
2. **Stock tab** — read-only list with progress bars (green = OK, red = low). Low stock warning banner
3. **Request tab** — textarea + "Send Request to Manager" button. Goes as suggestion to manager

---

## DASHBOARD 9: VILLA / HOUSEKEEPING

> Shows villa cards with real photos, current guests, booking status.

**Grid of villa cards:**
- Each card: villa photo (or placeholder), villa name, capacity, nightly rate
- Status overlay: OCCUPIED (green) / AVAILABLE (gray) / MAINTENANCE (amber)
- Current guest name + check-out date if occupied

---

## DASHBOARD 10: FRONT DESK (universal cashier)

> Handles walk-in payments, receipt lookups, waivers.

**Sections:**
1. **Today's Activity** — arrivals, departures, occupancy rate
2. **Receipt Search** — search by tab reference or date
3. **Waiver Management** — guest waivers for activities

---

## DASHBOARD 11: LOGIN SCREEN

> Clean, centered, no resort photo. Premium feel.

**Layout:**
- Solid `#171717` background with faint orange ambient glow behind card (4% opacity radial gradient)
- Centered glass card (max-width 380px, glass-card class)
- Brand mark: 56px rounded square with "K" in Fraunces serif, subtle orange tint border
- "Kurahia" in Fraunces 36px bold + "Staff Portal" / "Owner Portal" subtitle
- Username input + Password input (bg-white/8, orange focus ring)
- Orange submit button (flat `#F25623`, not gradient)
- Error state: red-tinted glass card with exclamation + message
- "Use PIN instead" link below (employee only)

---

## DASHBOARD 12: CLOCK IN/OUT (personal phone)

> Staff personal phone screen. Big clock button.

**Layout:**
- Current time (large, Fraunces serif)
- Status: "Clocked In since 8:00 AM" or "Not Clocked In"
- Big circular button: "Clock In" (green ring) or "Clock Out" (red ring)
- Today's shift info if assigned
- Duty time counter

---

## DASHBOARD 13: CUSTOMER MENU (shown to guests)

> Read-only menu grouped by category. Shown on waiter's tablet to the guest.

**Layout:**
- "Our Menu" in Fraunces 40px, centered + "Waterfront Country Club" subtitle
- Categories as section headers with border-bottom
- Photo grid cards (2 col mobile, 3 col tablet): item photo, name, price in orange
- Sold-out items: 40% opacity with "Sold Out" overlay
- "Open to Order →" orange button at bottom

---

## HOW TO USE THIS IN STITCH

Generate each dashboard one at a time. Use the global design system above + the specific dashboard description. Screenshot each result and save to `docs/references/stitch-[dashboard-name].png`.

Key instruction for Stitch: "Do NOT use emoji. Use SVG stroke icons. Do NOT use bright colors except the orange accent #F25623 on primary buttons only. The look should feel like Apple VisionOS — frosted glass panels on a dark surface. Premium hospitality, not generic SaaS."
