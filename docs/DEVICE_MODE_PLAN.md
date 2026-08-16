# Device Mode — Station Tablet Setup Plan

## The problem

The employee PWA serves two completely different use cases:

- **Personal phone** — employee installs it themselves. Sees: Clock, HR (leave, profile, alerts, calendar, incidents).
- **Station tablet** — shared device fixed in one location (Kitchen, Bar, Gate, etc.). Sees: work dashboard only. No clock, no HR.

The original code used the user's department to decide which view to show. That's wrong — department is *who you are*, not *which device you're on*.

## Current state (Option A — localStorage toggle)

A `kurahia:station_mode` flag in localStorage flips the device between personal and station mode. A manager logs in on a tablet and toggles it in the sidebar.

**Fragile:** if the browser clears site data (OS update, accidental reset), the flag disappears and the tablet silently becomes a personal phone. Manager has to set it up again.

---

## Planned fix: Option C — Self-healing URL param

### How it works

1. Manager sets up a station tablet by visiting:
   ```
   http://[server-ip]:5176/?mode=station
   ```
2. On load, the app reads `?mode=station`, writes `kurahia:station_mode = true` to localStorage, then strips the param from the URL (clean address bar).
3. Manager saves the tablet's home screen shortcut / PWA bookmark as that URL (with `?mode=station`).
4. Even if localStorage is ever cleared, the next time the tablet opens from its home screen shortcut, the param re-enables station mode automatically. **Self-healing.**

Personal phones just open `http://[server-ip]:5176/` — no param, defaults to personal mode.

### What to build

**1. Read the param on app load — `src/main.tsx`**

Before mounting React, check for `?mode=station` or `?mode=personal` and write to localStorage:

```typescript
const params = new URLSearchParams(window.location.search)
const mode = params.get('mode')
if (mode === 'station') localStorage.setItem('kurahia:station_mode', 'true')
if (mode === 'personal') localStorage.removeItem('kurahia:station_mode')
// Strip param so the URL stays clean
if (mode) {
  const url = new URL(window.location.href)
  url.searchParams.delete('mode')
  window.history.replaceState({}, '', url)
}
```

**2. Remove the manager toggle from AppLayout sidebar**

The toggle was a workaround. With URL-based setup, it's no longer needed. Manager just visits the setup URL on the tablet instead of logging in and flipping a UI control.

**3. Optional: dedicated setup screen `/device-setup`**

A pretty screen the manager opens on a new tablet:

- Shows current mode (Personal / Station)
- A "Switch to Station Mode" button that redirects to `?mode=station`
- A "Switch to Personal Mode" button that redirects to `?mode=personal`
- No auth required — this is a local device config, not a backend operation

**4. Deployment URLs**

When the app goes live on LAN (e.g., `192.168.1.100:5000`), the setup URLs become:

| Device | Bookmark URL |
|---|---|
| Personal phone | `http://192.168.1.100:5176/` |
| Kitchen tablet | `http://192.168.1.100:5176/?mode=station` |
| Bar tablet | `http://192.168.1.100:5176/?mode=station` |
| Gate tablet | `http://192.168.1.100:5176/?mode=station` |

All station tablets use the same URL — the work dashboard shown depends on which user account is logged into that device.

### Why this is better than what's currently built

| | Option A (current) | Option C (planned) |
|---|---|---|
| Setup method | Manager logs in, flips toggle | Visit a URL |
| Storage cleared | Mode lost, manual re-setup | Auto-restores on next open |
| Manager login required | Yes | No |
| Setup URL shareable | No | Yes (text it to anyone) |
| Code complexity | Same | +5 lines in main.tsx |

---

## What was already done (don't redo)

- `src/lib/deviceMode.ts` — `isStationDevice()` / `setStationMode()` helpers. Keep these, Option C still uses them.
- `AppLayout.tsx` — NAV_ITEMS split into `mode: 'personal' | 'station' | 'both'`. The filtering logic using `stationMode` is correct. Keep it.
- The redirect block (auto-jump to work screen on login) is gated on `stationMode`. Keep it.

Only additions needed: the param-reading block in `main.tsx` + remove the sidebar toggle.
