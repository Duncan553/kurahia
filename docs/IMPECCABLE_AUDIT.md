# Impeccable AI-Slop Audit — Kurahia UI

> Run date: 2026-06-23
> Tool: `npx impeccable detect` + manual grep for 6 key patterns
> Scope: `employee_pwa/src/screens/`, `owner_pwa/src/screens/`, both `layouts/`

---

## CLI Results

### employee_pwa/src/screens/
**0 anti-patterns found.** Clean.

### owner_pwa/src/screens/
**1 anti-pattern found.**

```
owner_pwa/src/screens/AlertsScreen.tsx
  line 205: [side-tab] border-l-4
    → Thick colored border on one side of a card — the most recognizable tell
      of AI-generated UIs. Use a subtler accent or remove it entirely.
```

### employee_pwa/src/layouts/
**0 anti-patterns found.** Clean.

### owner_pwa/src/layouts/
**0 anti-patterns found.** Clean.

---

## Manual Grep Results (6 Key Patterns)

### 1. Side-tab borders (`border-l-`)

| File | Lines | Detail |
|---|---|---|
| `owner_pwa/src/screens/AlertsScreen.tsx` | 74-77, 205-206 | `border-l-4` on alert cards, color mapped by severity via `SEV_BORDER` dict. **This is the only side-tab in the entire codebase.** |

**Verdict:** 1 finding. The `border-l-4` on alert cards is a textbook AI-slop tell. Consider replacing with a small severity dot/icon, a colored badge, or a subtle top-border instead.

---

### 2. Purple/violet colors (`purple`, `violet`)

| File | Line | Detail |
|---|---|---|
| `owner_pwa/src/screens/PayrollDraftScreen.tsx` | 67 | `bg-violet-100 text-violet-700` used for DAILY payroll period badge |

**Verdict:** 1 finding. Single usage in a badge. Not part of a purple-to-blue gradient (no gradient involved), so this is a minor cosmetic choice, not a classic AI-slop pattern. Consider swapping to a color from the existing design system palette for consistency.

---

### 3. Bounce/elastic easing (`bounce`, `elastic`)

| File | Lines | Detail |
|---|---|---|
| `employee_pwa/src/screens/kiosk/KioskMenuScreen.tsx` | 269 | Comment only: "bounce to staff home" (navigation logic) |
| `employee_pwa/src/screens/kiosk/KioskWelcomeScreen.tsx` | 9 | Comment only: "bounce to staff home" (navigation logic) |

**Verdict:** 0 real findings. Both are code comments about redirect logic, not CSS bounce animations. Clean.

---

### 4. Custom shadows with bright RGBA colors (`shadow-.*rgba`)

| File | Lines | Detail |
|---|---|---|
| `employee_pwa/src/screens/LoginScreen.tsx` | 135, 162 | Focus ring: `shadow-[0_0_0_2px_rgba(250,92,41,0.12)]` — subtle 12% opacity, brand orange |
| `employee_pwa/src/screens/LoginScreen.tsx` | 189-190 | Button glow: `shadow-[0_4px_16px_rgba(250,92,41,0.3)]` / hover `0.4` — brand CTA |
| `owner_pwa/src/screens/LoginScreen.tsx` | 131, 158 | Same focus ring pattern as employee LoginScreen |
| `owner_pwa/src/screens/LoginScreen.tsx` | 185-186 | Same button glow pattern as employee LoginScreen |
| `employee_pwa/src/screens/PinEntryScreen.tsx` | 122 | `drop-shadow-[0_2px_12px_rgba(0,0,0,0.3)]` — black text shadow, not a glow |
| `employee_pwa/src/screens/PinEntryScreen.tsx` | 141 | `shadow-[0_0_0_3px_rgba(255,255,255,0.1)]` — white focus ring at 10% |

**Verdict:** 0 problematic findings. All shadows use the brand orange (#fa5c29) at low opacity for focus states and CTA buttons, or black/white for legitimate depth. No neon/bright color glows. These are intentional design choices, not AI-slop dark glows.

---

### 5. Cramped padding (`text-xs` with `p-2` or `p-1`)

Grep found many `text-xs` usages across screens. Cross-referencing with `p-1` or `p-2` on the same element:

**Verdict:** 0 findings. All `text-xs` usages pair with adequate padding (`p-3`, `p-4`, `px-3 py-1.5`, etc.) or are label/caption text that doesn't need large padding. No cramped touch targets from padding starvation.

---

### 6. Small touch targets (`min-h-[Xpx]` where X < 44)

| File | Line | Detail |
|---|---|---|
| `employee_pwa/src/screens/InventoryCountScreen.tsx` | 394 | `min-h-[36px]` on department filter pill buttons |

**Verdict:** 1 finding. Department filter pills in the inventory count screen have a 36px minimum height — 8px below the 44px mobile touch target guideline. Should be bumped to `min-h-[44px]`.

---

## Summary

| Pattern | Findings | Severity |
|---|---|---|
| Side-tab borders (`border-l-4`) | **1** — AlertsScreen.tsx:205 | Medium — classic AI-slop tell |
| Purple/violet colors | **1** — PayrollDraftScreen.tsx:67 | Low — isolated badge, no gradient |
| Bounce/elastic easing | **0** | Clean |
| Custom bright shadows | **0** | Clean — all brand-appropriate |
| Cramped padding | **0** | Clean |
| Small touch targets (<44px) | **1** — InventoryCountScreen.tsx:394 | Low — 36px filter pills |
| **Total** | **3** | |

### Recommended Fixes

1. **AlertsScreen.tsx:205** — Replace `border-l-4` with a severity dot, colored icon, or top-accent. This is the single most recognizable AI-generated UI pattern.

2. **PayrollDraftScreen.tsx:67** — Swap `bg-violet-100 text-violet-700` to a color from the existing design token palette (e.g. `bg-sky-100 text-sky-700` already used for HOURLY, or another on-brand neutral).

3. **InventoryCountScreen.tsx:394** — Bump `min-h-[36px]` to `min-h-[44px]` for mobile touch compliance.

---

*Generated by Impeccable CLI + manual grep audit.*
