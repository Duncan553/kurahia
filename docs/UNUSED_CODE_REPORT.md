# Unused Code Report

Scanned: `employee_pwa/src/`, `owner_pwa/src/`, `shared_ui/src/`, `app/models/__init__.py`
Date: 2026-06-19

---

## 1. Unused Imports

No unused imports found in any `.ts` or `.tsx` file across both PWAs and shared_ui.

---

## 2. Components Defined but Never Imported

No orphan components found. Every component, screen, and page file is
lazy-imported in its respective `main.tsx` or imported by another file.

---

## 3. Exported Functions/Variables Never Imported Elsewhere

### DEAD FILE: `employee_pwa/src/lib/errorReporting.ts`

- **Exports:** `reportError`, `reportMessage`
- **Used elsewhere:** No. Zero imports anywhere.
- **Purpose:** Sentry-ready wiring (placeholder — Sentry is not installed).
- **Safe to remove?** YES. The file is a stub with console.log wrappers.
  Nothing calls it. Remove the entire file.

### DEAD FILE: `employee_pwa/src/hooks/useIdleTimeout.ts`

- **Exports:** `useIdleTimeout`
- **Used elsewhere:** No. Zero imports anywhere.
- **Purpose:** Redirects to /pin after 10 min idle. Comment says "Wire now — apply per-screen in F-7+."
- **Safe to remove?** YES, but note the intent: this was pre-built for a future
  feature (idle screen lock). If that feature is still planned, keep it. If not,
  delete it. Either way it currently does nothing.

### Not actually dead (internal use only):

- `employee_pwa/src/lib/notificationRoutes.ts` — `ROUTE_MAP` is exported but
  only consumed internally by `routeFor()` in the same file. `routeFor` is
  imported by `sw.ts` and `NotificationsScreen.tsx`. **Not unused** — but the
  `export` on `ROUTE_MAP` could be removed (make it a plain `const`).

---

## 4. CSS Classes Defined but Never Referenced

### `employee_pwa/src/index.css` + `owner_pwa/src/index.css`

| Class | Defined in | Used? | Safe to remove? |
|---|---|---|---|
| `.screen-hero-torn` | Both CSS files | NO references in any `.tsx`/`.ts` | YES — no component uses it |
| `.glass-shine` (+ `::before`) | Both CSS files | NO references in any `.tsx`/`.ts` | YES — no component uses it |
| `.gradient-warm` | Both CSS files | NO references in any `.tsx`/`.ts` | YES — no component uses it |
| `.gradient-danger` | Both CSS files | NO references in any `.tsx`/`.ts` | YES — no component uses it |

### Tailwind `@theme` tokens defined but never referenced as utilities:

| Token | Defined in | Used? | Safe to remove? |
|---|---|---|---|
| `--color-honey` | Both CSS files | NO (`honey` never appears in any `.tsx`/`.ts`) | YES from employee_pwa; owner_pwa defines it too but also unused |
| `--color-slate-mid` | Both CSS files | NO (`slate-mid` never appears in any `.tsx`/`.ts`) | YES from both |

Note: These are Tailwind v4 `@theme` tokens. They generate utility classes like
`text-honey`, `bg-slate-mid`, etc. — but none of those utilities are used.

---

## 5. Models Imported in `__init__.py` but Never Used Elsewhere

All models imported in `app/models/__init__.py` are used in the codebase
(routes, services, tests, or CLI commands). No dead models.

**Minor inconsistency (not unused code):** `PendingSTKPush` and `SystemSetting`
are imported in `__init__.py` but missing from the `__all__` list. Both are
actively used — they just need to be added to `__all__` for completeness.

---

## Summary

| Category | Count | Action |
|---|---|---|
| Unused imports | 0 | None needed |
| Dead components/screens | 0 | None needed |
| Dead files (entire file unused) | 2 | Remove `errorReporting.ts` and `useIdleTimeout.ts` |
| Unnecessary `export` keyword | 1 | Make `ROUTE_MAP` a plain `const` in `notificationRoutes.ts` |
| Dead CSS classes | 4 | Remove `.screen-hero-torn`, `.glass-shine`, `.gradient-warm`, `.gradient-danger` from both CSS files |
| Dead CSS theme tokens | 2 | Remove `--color-honey` and `--color-slate-mid` from both CSS files |
| `__all__` gaps | 2 | Add `PendingSTKPush` and `SystemSetting` to `__all__` |
