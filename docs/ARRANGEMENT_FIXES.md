# Arrangement Fixes — Final Pass

Applied interface design rules across 6 dashboard screens: focal point, spatial rhythm, 60/30/10, density.

---

## ManagerScreen.tsx

- **Hero focal point:** Pending approvals count scales to `text-5xl md:text-6xl` when > 0 (was uniform `text-4xl`). Gains extra padding (`py-6`) and the label turns bold `text-status-pending/80` to signal urgency.
- **Section breaks:** All major row gaps changed from `mb-6` to `mb-8` (32px breathing room between greeting, stock chart, budget, and action tiles).
- **Action tiles:** Section label spacing `mb-4`, gap-4 between tiles confirmed.

## HeadChefScreen.tsx

- **Hero focal point:** Stock numbers (Total/Low/Healthy) bumped from `text-4xl md:text-5xl` to `text-5xl md:text-6xl`. Low stock number dims to `/40` opacity when 0 (no false alarm visual weight).
- **Section breaks:** Left column changed from `space-y-4` to `space-y-8` (32px between Stock Overview and Low Stock Alerts). Header gap `mb-6` to `mb-8`.
- **Alert hierarchy:** Item name uses `font-bold` (was `font-semibold`). Detail text uses `text-ink-tertiary/60` (more muted). Alert count badge gets colored background (`bg-status-failed/15`) when items exist.
- **Right column:** Tightened to `space-y-3` (nav tiles are compact, tight grouping).

## WaiterTabsScreen.tsx

- **Hero focal point:** Ready pings moved ABOVE the wristband input, wrapped in their own `mb-8` section. Pings are now `p-5` (was `p-3`), `border-2` (was `border`), icon `text-3xl` (was `text-lg`), body text `text-base font-bold` (was `text-sm font-semibold`).
- **Spatial rhythm:** Replaced `space-y-5` on container with explicit section margins (`mb-6`, `mb-8`).
- **Bug fix:** Removed duplicate `glass-card` class on table card buttons.
- **Consistency:** Table cards grid gets `mb-8` bottom margin.

## GateHubScreen.tsx

- **Layout reorder:** Issue section moved ABOVE stats (action first, metrics second).
- **Hero focal point:** "Issue Wristband" button is now `py-5 text-lg font-bold` (was `py-4 text-base font-semibold`) with `shadow-lg shadow-[#fa5c29]/20` glow.
- **Stats demoted:** Stats cards shrunk to `p-3`, `text-base` numbers (was `text-3xl` on first card), uniform 3-column layout (removed `col-span-2`). Label text `text-ink-tertiary` (was `text-ink-secondary`).
- **Header upgraded:** Gate title changed to `font-serif text-3xl md:text-4xl` to match other screens. Section label changed to `text-xs uppercase tracking-wider text-ink-tertiary`.
- **Section breaks:** `mb-8` between header, issue section, and stats.

## StationQueues.tsx (Kitchen/Bar)

- **Hero focal point:** Active orders badge uses `text-sm font-bold text-[#fa5c29]` on `bg-[#fa5c29]/15` (was `text-xs font-semibold text-[#aa8980]` on `bg-white/8`). Dot pulses with `animate-pulse`. Badge is `px-4 py-1.5` (was `px-3 py-1`).
- **Filter pills:** Gap below pills `mb-6` (was `mb-5`).
- **Card consistency:** Padding `p-5` (was `p-4`). Header gap `mb-3` (was `mb-2`).

## InventoryCountScreen.tsx

- **Hero row:** Stat card numbers scaled from `text-2xl` to `text-4xl md:text-5xl`. Card padding `p-5` (was `p-4`). Label spacing `mb-2` (was `mb-1`). Description spacing `mt-2` (was `mt-0.5`). Added `leading-none` for tight number rendering.
- **Section breaks:** Header `mb-8` (was `mb-6`). Stat row `mb-8` (was `mb-6`).
- **Department health cards:** Padding `p-5` (was `p-4`). Section label `mb-4` (was `mb-3`).
- **Activity log:** Card padding `p-5` (was `p-4`). Section label `mb-4` (was `mb-3`).

---

## Rules applied

| Rule | What changed |
|------|-------------|
| ONE FOCAL POINT | Each screen has a clear hero: pending approvals (Manager), stock numbers (Chef), ready pings (Waiter), issue button (Gate), order count badge (Station), stat cards (Inventory) |
| SPATIAL RHYTHM | `mb-8` between major sections, `gap-4` within sections, tight `space-y-3` for nav tile groups |
| 60/30/10 | Stats demoted to secondary text colors, orange accent reserved for CTAs and urgent counts |
| DENSITY | Card padding standardized to `p-5`, section gaps `gap-4`, major breaks `mb-8` |
