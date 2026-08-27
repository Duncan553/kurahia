# UI Colour Research — Kurahia Dark Palette

**Date:** 2026-08-27
**Scope:** `shared_ui/src/styles/tokens.css` as consumed by `owner_pwa`, `employee_pwa`, `station_pwa`
**Question:** the owner says the UI looks dull. Is that instinct right, and is there a technical cause?

---

## 1. Verdict

**Yes. The owner is right, and there are three separate, measurable causes.**

This is not a taste judgement. Three things are measurably true of the current palette:

1. **The background and the accent are the same colour.** In OKLCh, `--color-cream-card` sits at hue **36.7°** and `--color-primary-main` at hue **37.2°** — **0.5° apart**. The orange is not a contrasting accent against a warm neutral; it is the *same hue as the wall*, differing only in chroma and lightness. There is nothing for it to pop against.
2. **The most-used text colour in the codebase fails WCAG AA.** `--color-ink-tertiary` at 0.55 alpha computes to **3.69:1** on the card surface and **2.35–2.90:1** on the glass surface the app actually renders. It is used **646 times** — more than `ink-primary` (534) — and **454 of those uses are at 9–12px**, where the 4.5:1 threshold applies with no large-text exemption.
3. **The surface users actually see is not the surface the tokens were designed against.** `.glass-card` is used **240 times** vs **31** for `bg-cream-card`. Glass is the real surface, and its composited backdrop measures **#3f302b–#a49c9a** depending on which part of the resort photo is behind it — a **2.69:1 to 9.13:1 swing** for the same white text.

Cause 1 is what "dull" actually means here. Causes 2 and 3 are what makes it also *hard to read*, which the eye reports as the same complaint.

**One important correction to the starting hypothesis.** The brief guessed the surfaces were "very desaturated". They are the opposite. Measured in OKLCh, the Kurahia surface ladder has mean chroma **0.0258** — roughly **6× Linear's** (0.0041), **4.7× Radix's** (0.0055), **1.7× GitHub Primer's** (0.0149), and infinitely more than Material 2 or Vercel Geist (both 0.0000). The surfaces are among the most saturated in any shipping dark UI, *and they are saturated in the accent's own hue*. That is the mechanism.

---

## 2. Method

All ratios are WCAG 2.x relative luminance, computed from first principles (sRGB → linear → `0.2126R + 0.7152G + 0.0722B`, ratio `(L₁+0.05)/(L₂+0.05)`). `rgba()` tokens are alpha-composited source-over onto their actual backdrop before measurement — an `rgba` token has no contrast ratio until you say what is behind it.

For glass surfaces the full stack was reproduced: `owner_pwa/public/images/resort-bg.jpg` (1600×1200) downsampled to approximate `blur(24px)`, then `body::after`'s overlay gradient, then `saturate(180%) brightness(1.05)`, then `.glass-card`'s own white gradient — in CSS's evaluation order.

Perceptual chroma/hue uses OKLCh, because HSL saturation is meaningless at these lightness levels (`#1e100c` reads as "42.9% saturated" in HSL, which tells you nothing useful).

---

## 3. Contrast tables

### 3a. Against `--color-cream-card` `#1e100c` (the nominal surface)

| Token | Raw | Effective after alpha | Ratio | AA normal (4.5:1) | AA large / UI (3:1) |
|---|---|---|---|---|---|
| `--color-ink-primary` | `#ffffff` | `#ffffff` | **18.51** | PASS | PASS |
| `--color-ink-secondary` | `rgba(255,235,225,.82)` | `#d6c4bb` | **10.97** | PASS | PASS |
| `--color-ink-tertiary` | `rgba(210,180,170,.55)` | `#816a63` | **3.69** | **FAIL** | PASS |
| `--color-ticket-ink` | `#f1f5f9` | `#f1f5f9` | **16.89** | PASS | PASS |
| `--color-primary-main` | `#fa5c29` | — | **5.84** | PASS | PASS |
| `--color-primary-light` | `#ffb59f` | — | **10.90** | PASS | PASS |
| `--color-primary-dark` | `#af3000` | — | **2.86** | **FAIL** | **FAIL** |
| `--color-status-paid` | `#10b981` | — | **7.30** | PASS | PASS |
| `--color-status-pending` | `#f59e0b` | — | **8.62** | PASS | PASS |
| `--color-status-failed` | `#ef4444` | — | **4.92** | PASS | PASS |
| `--color-status-neutral` | `#4A7889` | — | **3.82** | **FAIL** | PASS |
| `--color-honey` / `--color-accent-cool` | `#C68A28` | — | **6.23** | PASS | PASS |
| `--color-tea-brown` | `#d97706` | — | **5.81** | PASS | PASS |
| `--color-leaf-green` | `#10b981` | — | **7.30** | PASS | PASS |
| `--color-stamp-red` | `#ef4444` | — | **4.92** | PASS | PASS |

**Three failures:** `ink-tertiary` (3.69), `primary-dark` (2.86), `status-neutral` (3.82).

`primary-dark` is the worst of them — **2.86:1 fails even the 3:1 non-text threshold** — and `grep` shows **24 uses as `text-primary-dark`** against 28 as `bg-primary-dark`. As a fill it is fine. As text it is unreadable and should never have been used that way.

### 3b. Against the surface users actually see (`.glass-card`)

Composited over the real resort photo, per vertical band of the page:

| Page band | Composited glass bg | `ink-primary` | `ink-secondary` | `ink-tertiary` |
|---|---|---|---|---|
| top third, card top | `#614940` | 8.26 | 5.46 | **2.38** |
| top third, card bottom | `#553b30` | 10.26 | 6.61 | **2.72** |
| middle third, card top | `#5c4e3e` | 8.05 | 5.33 | **2.35** |
| middle third, card bottom | `#4f402f` | 10.00 | 6.46 | **2.68** |
| bottom third, card top | `#52472d` | 9.13 | 5.96 | **2.54** |
| bottom third, card bottom | `#44391c` | 11.42 | 7.26 | **2.90** |
| blown-out region (worst case) | `#a49c9a` | **2.31** | **1.68** | **1.14** |

**`ink-tertiary` fails the 3:1 large-text floor everywhere on glass.** Not "close to the line" — 2.35:1 against a required 4.5:1 at 10px.

And on the same glass backdrop, **every accent token fails AA-normal**:

| Token | On `#1e100c` | On real glass `#614940` |
|---|---|---|
| `primary-main` | 5.84 | **2.61** |
| `primary-dark` | 2.86 | **1.28** |
| `status-paid` | 7.30 | **3.27** |
| `status-pending` | 8.62 | **3.86** |
| `status-failed` | 4.92 | **2.20** |
| `status-neutral` | 3.82 | **1.71** |
| `honey` | 6.23 | **2.79** |
| `primary-light` | 10.90 | 4.88 (only pass) |

This is the finding that matters most: **you cannot fix this by picking better text colours.** No colour that still reads as orange, green or amber can clear 4.5:1 against a backdrop that ranges from `#3f302b` to `#a49c9a`. The variable backdrop has to be stabilised first. Chasing it with brighter tokens is unwinnable.

### 3c. Surface tier separation

| Token | Effective | Step vs previous | vs base |
|---|---|---|---|
| `--color-cream-card` `#1e100c` | `#1e100c` | — | 1.00:1 |
| `--color-cream-alt` | `#261713` | 1.070:1 | 1.070:1 |
| `--color-cream-deep` | `#34241f` | 1.168:1 | 1.250:1 |

The **step sizes are fine** — they match Linear (1.093, 1.187) and Radix (1.075, 1.107) almost exactly. The issue is that there are only **three tiers spanning 1.25:1**, where comparable systems run 4–6 tiers spanning 1.39–1.60:1. Less depth to work with, but this is a minor contributor, not a main cause.

---

## 4. Is pure `#ffffff` correct in 2026?

**No — and both major design systems say so explicitly.**

Material Design specifies **`#121212`** as the dark surface, not black, because "dark grey surfaces can express a wider range of colour, elevation, and depth, because it's easier to see shadows on grey", and applies white text at **87% / 60% / 38%** opacity for high / medium / disabled emphasis rather than at full strength — targeting **at least 15.8:1** between body text and background ([Material Design dark theme](https://m2.material.io/design/color/dark-theme.html), [Google Design](https://design.google/library/material-design-dark-theme)). Kurahia already gets the *background* half right — `#1e100c` is a tinted near-black, exactly as recommended, and `docs/DESIGN_RULES.md` records that decision deliberately. It is the *text* half that is off.

The physical reason is **halation**. On a dark field the pupil dilates; bright text then overstimulates the retina and the glyphs appear to bleed a glow into the background. It is worse for people with astigmatism — roughly **30–50% of adults** — for whom white-on-black text develops a visible fuzzy halo, forcing continuous refocusing and producing fatigue ([UX Movement](https://uxmovement.com/content/why-you-should-never-use-pure-black-for-text-or-backgrounds/), [Axess Lab on dark-mode legibility](https://axesslab.com/glassmorphism-meets-accessibility-can-frosted-glass-be-inclusive/)). The standard mitigation is an off-white around RGB 220–245 rather than 255.

Apple's guidance points the same way: the minimum is 4.5:1 but the recommendation is **7:1 for custom colours, especially small text**, and in Dark Mode iOS uses **two sets of background colours — base and elevated** — specifically to convey depth ([Apple HIG: Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode), [Apple HIG: Color and Contrast](https://developer.apple.com/design/human-interface-guidelines/accessibility)).

**Practical note for this codebase:** `#ffffff` on `#1e100c` is **18.51:1**, close to the 21:1 theoretical maximum. Dropping to `#f6ece7` gives **15.93:1** — still above Material's recommended 15.8:1 floor, comfortably above Apple's 7:1 preference, and it removes the halation while making the primary text *warm*, which reinforces the resort identity instead of fighting it. Right now `ink-primary` is the only token in the entire palette with zero chroma; it is the one element that reads as generic.

---

## 5. Why it reads as "dull" — causes ranked by impact

### Cause 1 — Everything is the same hue (highest impact)

Measured in OKLCh, the entire identity palette occupies a **7.4° hue window**:

| Token | OKLCh L | OKLCh C | OKLCh H |
|---|---|---|---|
| `cream-card` | 0.191 | 0.0252 | **36.7** |
| `cream-alt` (effective) | 0.223 | 0.0258 | **35.5** |
| `cream-deep` (effective) | 0.278 | 0.0263 | **38.1** |
| `ink-secondary` (effective) | 0.833 | 0.0239 | **48.4** |
| `ink-tertiary` (effective) | 0.545 | 0.0314 | **37.6** |
| `primary-dark` | 0.501 | 0.1701 | **36.4** |
| `primary-main` | 0.677 | 0.2027 | **37.2** |
| `primary-light` | 0.837 | 0.0921 | **37.2** |

Surfaces, all three text tiers, and all three accent tiers are the **same colour at different brightnesses**. This is a monochrome scheme that nobody chose — it emerged from applying "warm-tint everything" consistently.

Note that `ink-tertiary` at C=0.0314 is *more chromatic than the surface it sits on*. Even the muted text is orange.

The measurable consequence is the accent's headroom:

| | Surface → accent hue distance | Surface → accent chroma ratio |
|---|---|---|
| **Kurahia** | **0.5°** | **8.0×** |
| Linear (`#0f1011` → `#5e6ad2`) | **27.2°** | **60.1×** |

Linear's accent has 60× the chroma of its surface and sits 27° away in hue. Kurahia's has 8× and sits half a degree away. **That ratio is "pop", quantified.** An 8× chroma step at zero hue separation is what the eye reports as dull.

**This also answers the "is the accent used sparingly enough?" question — and the answer is no, but not for the expected reason.** `primary-main` appears **333 times** across the three apps. That is not sparse. Frequency is not the problem; the problem is that the accent has nowhere to stand out *from*. Meanwhile the tokens that would provide hue relief are effectively dead: `--color-honey` is used **once**, `--color-accent-cool` **three times**, `--color-status-neutral` **ten times** — and `honey` and `accent-cool` are defined as the *same hex* (`#C68A28`), so the "data-viz accent" section of the palette contains one colour used four times total. The system nominally has six hues. Functionally it has one, plus three status colours.

### Cause 2 — Low-alpha tertiary text (highest impact on readability)

`rgba(210, 180, 170, 0.55)` composites to `#816a63` — **3.69:1** on card, **2.35:1** on glass. It is the **most-used text token in the codebase (646 uses)** and its size distribution is the worst possible case:

| Size | Uses |
|---|---|
| `text-xs` (12px) | 183 |
| `text-[10px]` | 158 |
| `text-sm` (14px) | 100 |
| `text-[11px]` | 8 |
| `text-base` | 4 |
| `text-[9px]` | 1 |

**None of these qualify for WCAG's large-text exemption** (18.66px bold / 24px regular). All 454 sized occurrences need 4.5:1. And it is not decorative — grep shows it carrying meaning: `"Proposed by manager"`, `"Manager estimate:"`, timestamps in `AuditScreen`, empty-state copy, form placeholders, and **inactive tab labels** in `ServicePayScreen`.

Low alpha is also why this went unnoticed. `rgba(210,180,170,0.55)` *looks* like a light warm colour in the token file. Its actual rendered value, `#816a63`, is a mid-brown. **A designer reading `tokens.css` sees a palette that is one to two tiers brighter than what ships.** That gap is a large part of "it looks duller than I designed it".

### Cause 3 — Glass surfaces make contrast non-deterministic

`.glass-card` (240 uses) is the real surface of this app; `bg-cream-card` (31 uses) is not. But the glass card has no colour of its own — it inherits whatever part of `resort-bg.jpg` is behind it, and the photo's per-band means are `#98918c` / `#615a4a` / `#59673e`, with the overlay's middle stop dropping to only **0.48 alpha**. Result: the same white text ranges from **9.13:1 to 2.69:1** across the page.

This is the known, documented failure mode of glassmorphism: "when you place text over a transparent, blurred background, the contrast ratio is dynamic… most glass UIs fail WCAG AA contrast requirements for body text", and the standard mitigation is to layer a semi-opaque colour beneath the text to stabilise it ([Axess Lab](https://axesslab.com/glassmorphism-meets-accessibility-can-frosted-glass-be-inclusive/), [New Target](https://www.newtarget.com/web-insights-blog/glassmorphism/)). The `@media (prefers-reduced-transparency)` fallback already in `tokens.css` is correct and worth keeping — but it only helps the small fraction of users who have that OS setting on.

### Cause 4 — `saturate(180%)` is making it worse, not better

The brief asked whether `saturate(180%)` is "fighting an already-desaturated background". **It is not — the evidence shows something different and more damaging.**

The blurred backdrop under a glass card is *not* the brown `#1e100c`; it is the photo darkened by the overlay, which measures `#3f302b` / `#3b332a` / `#30291a` — olive-khaki, not orange. `saturate(180%)` amplifies **that** cast:

| Band | Backdrop | HSL S before → after | Chroma gain |
|---|---|---|---|
| top third | `#3f302b` | 19.1% → **33.7%** | +16.2/255 |
| middle third | `#3b332a` | 17.4% → **31.5%** | +14.1/255 |
| bottom third | `#30291a` | 29.9% → **55.7%** | +17.5/255 |

The bottom band nearly doubles in saturation *toward yellow-green*. After the filter the glass card sits at **OKLCh C ≈ 0.043 — higher chroma than the surface palette itself (0.025)**. The card becomes a coloured object competing with the accent, in a hue that is not the brand's. That is why cards read muddy rather than warm.

### Cause 5 — Only three surface tiers (low impact)

Three tiers spanning 1.25:1, where Material 2 runs four spanning 1.60:1 and Radix runs five spanning 1.44:1. Worth fixing while touching these tokens, but this is a polish item, not a cause of "dull".

---

## 6. How comparable products do it

Every mainstream dark UI measured keeps its surfaces **near-neutral** and reserves chroma for the accent. Measured in OKLCh from published palettes:

| System | Surface ladder | Tiers | Total span | **Mean surface chroma** |
|---|---|---|---|---|
| **Kurahia** | `#1e100c` → `#261713` → `#34241f` | 3 | 1.25:1 | **0.0258** |
| [Linear](https://linear.app/now/how-we-redesigned-the-linear-ui) | `#0f1011` → `#191a1b` → `#28282c` | 4 | 1.30:1 | 0.0041 |
| [Radix](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale) (mauve dark) | `#121113` → … → `#323035` | 12-step scale | 1.44:1 | 0.0055 |
| [Material 2](https://m2.material.io/design/color/dark-theme.html) | `#121212` → `#232323` → `#2e2e2e` → `#383838` | 0–24dp overlay | 1.60:1 | 0.0000 |
| [GitHub Primer](https://primer.style/) | `#0d1117` → `#161b22` → `#21262d` → `#30363d` | 4 | 1.55:1 | 0.0149 |
| [Vercel Geist](https://vercel.com/geist/colors) | `#000000` → `#0a0a0a` → `#171717` → `#262626` | background-100/200 + gray 100–1000 | 1.39:1 | 0.0000 |

**Kurahia's surfaces are 1.7×–6× more chromatic than any of them.** GitHub Primer is the most-tinted mainstream system at 0.0149 — and Kurahia is 1.7× beyond that.

The design intent behind this is stated explicitly by the teams involved:

- **Linear** generates its whole theme from three variables — *base colour, accent colour, contrast* — in **LCH**, chosen because "LCH has the benefit that it's perceptually uniform". They deliberately reduced chroma to get a "more neutral and timeless appearance", "limiting how much chrome (blue in our case) was used in the calculations applied to our colour system" — that is, they hold the accent hue *out* of the neutrals on purpose. Elevation is expressed as **background luminance steps** (white overlay 0.02 → 0.04 → 0.05), not shadows.
- **Vercel Geist** instructs designers to "**design in monochrome. Use colour only when it adds significant meaning to state, action, or data**", with non-colour cues as backup. Its scale encodes *intent* per step: 100 background, 200 hover, 300 active, 400–600 borders, 700–800 solid fills, **900 secondary text, 1000 primary text**.
- **Radix** splits its 12 steps the same way: **1–2 backgrounds, 3–5 component backgrounds (normal/hover/active), 6–8 borders, 9–10 solid fills, 11 low-contrast text, 12 high-contrast text**, with step 9 carrying "the highest chroma of all steps in the scale".
- **Material 2** expresses elevation by compositing progressively more opaque white over the surface — the higher the surface, the lighter it becomes.

**The common pattern, and the one Kurahia is missing:** *chroma is a scarce resource spent on the accent, and neutrals stay neutral so that spending registers.* Kurahia spends chroma everywhere, so the accent buys nothing.

Note that all of these systems separate **"low-contrast text" from "disabled text"**. Kurahia's `ink-tertiary` is doing both jobs at a value appropriate to neither — Radix step 11 and Geist gray-900 are legible secondary text, well above 4.5:1, not a 38%-opacity disabled state.

On the POS side, [Toast's KDS](https://pos.toasttab.com/hardware/kitchen-display-system) ships both light and dark modes and encodes ticket state through **heading colour plus animation** rather than colour alone — the same redundancy principle Geist states. That reinforces a specific point for Kurahia: `DESIGN_RULES.md` already requires text labels alongside status colours, which is correct and should survive any palette change.

---

## 7. Daylight readability

These are tablets used outdoors at a lakeside resort. WCAG's 4.5:1 was calibrated to compensate for the contrast-sensitivity loss of a user with roughly **20/40 vision** — typical of an 80-year-old — under normal indoor viewing ([W3C: Understanding SC 1.4.3](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html)). **It assumes nothing about ambient light.** Outdoors, reflected ambient light adds luminance to the dark and light parts of the screen *equally*, which compresses contrast toward 1:1. Displays engineering treats **Effective Contrast Ratio ≥ 5** as the floor for outdoor legibility and 10+ as comfortable, versus about 20:1 for newsprint in sunlight ([Riverdi on sunlight-readable displays](https://riverdi.com/blog/what-makes-a-monitor-sunlight-readable)).

Modelling reflected ambient as an additive luminance term `R` on both foreground and background:

**On `#1e100c` (solid card):**

| Token | Indoor | Shade (R=0.05) | Overcast (R=0.15) | Full sun (R=0.40) |
|---|---|---|---|---|
| `ink-primary` `#ffffff` | 18.51 | 10.31 | 5.80 | 3.17 |
| `ink-secondary` eff. | 10.99 | 6.31 | 3.74 | 2.24 |
| **`ink-tertiary` eff.** | **3.68** | **2.42** | **1.74** | **1.33** |
| `primary-main` | 5.84 | 3.57 | 2.33 | 1.60 |
| `status-neutral` | 3.82 | 2.50 | 1.78 | 1.35 |

**On the glass card (`#614940`):**

| Token | Indoor | Shade | Overcast | Full sun |
|---|---|---|---|---|
| `ink-primary` `#ffffff` | 8.28 | 6.22 | 4.34 | 2.75 |
| `ink-secondary` eff. | 4.92 | 3.81 | 2.80 | 1.94 |
| **`ink-tertiary` eff.** | **1.65** | **1.46** | **1.30** | **1.16** |
| `primary-main` | 2.61 | 2.16 | 1.74 | 1.39 |

**Implications:**

1. **Dark mode is the harder choice outdoors.** A dark UI has less emitted light to overcome reflection with, so it degrades faster than a light one. This does not mean abandoning dark mode — it means the *indoor* margin has to be large enough to survive the outdoor collapse.
2. **Treat 7:1 as the working floor for body text, not 4.5:1.** That is Apple's recommendation for custom colours anyway, and it is what leaves anything usable in shade. A token at 4.6:1 indoors is at ~2.9:1 in shade.
3. **Glassmorphism costs roughly half the contrast budget** — `ink-primary` drops from 18.51:1 to 8.28:1 just by being on a glass card indoors. Outdoors that becomes 2.75:1. Glass is affordable on the owner's phone indoors; it is expensive on a station tablet in daylight.
4. **Consider scoping glass by app.** `station_pwa` is the outdoor/bar/kitchen surface. The existing `prefers-reduced-transparency` fallback already contains the exact solid-surface treatment needed — making that the *default* for station and keeping glass for `owner_pwa` would be a small change with a large daylight benefit. This is a suggestion, not a token change; it needs a product decision.

---

## 8. Recommended token changes

Design constraints honoured: **keep the warm/orange identity, keep glass, no redesign.** Every value below is warm-hued; none is neutral grey. Total: 11 token edits and 3 additions.

### 8a. Text — fixes halation and the AA failure

| Token | From | To | Ratio on new card | Why |
|---|---|---|---|---|
| `--color-ink-primary` | `#ffffff` | `#f6ece7` | **15.51:1** | Removes halation on the ~30–50% of staff with astigmatism. Still clears Material's 15.8:1 target on the current card (15.93:1) and Apple's 7:1 by a wide margin. Makes the primary text warm — currently it is the only zero-chroma token in the palette. |
| `--color-ink-secondary` | `rgba(255,235,225,.82)` | `#dcc9c0` | **11.29:1** | Opaque, so its contrast is knowable rather than dependent on what is behind it. Visually near-identical to today's composited `#d6c4bb`, ~1 tier brighter. |
| `--color-ink-tertiary` | `rgba(210,180,170,.55)` | `#bda49b` | **7.68:1** | **The single highest-value change in this document.** Fixes 646 usages, 454 of them at 9–12px. Goes from 3.69:1 (fail) to 7.68:1 (clears Apple's 7:1). Opaque, so it survives being placed on glass. |

If a genuinely dimmed/disabled state is needed after this, add a **fourth** token — do not reuse tertiary for it:

```
--color-ink-disabled: #7d6a63;   /* ~3.2:1 — non-text, decorative and disabled states only */
```

### 8b. Surfaces — halve the chroma, keep the warmth, add two tiers

The goal is to move surface chroma from **0.0258** toward the **0.005–0.015** band every comparable system occupies, *without* going grey. These values stay unmistakably warm brown (OKLCh H 43–51°) while roughly halving chroma to **0.0167** and, critically, opening a **7.3°** hue gap to the accent.

| Token | From | To | OKLCh C | Step | Role |
|---|---|---|---|---|---|
| `--color-cream-base` *(new)* | — | `#140f0d` | 0.0094 | — | body / app background |
| `--color-cream-card` | `#1e100c` | `#1c1512` | 0.0129 | 1.056:1 | card surface |
| `--color-cream-alt` | `rgba(43,28,24,.6)` | `#261d18` | 0.0170 | 1.091:1 | raised / secondary surface |
| `--color-cream-deep` | `rgba(66,49,44,.6)` | `#322620` | 0.0212 | 1.128:1 | overlay / modal |
| `--color-cream-hover` *(new)* | — | `#3e302a` | 0.0230 | 1.159:1 | hover / active / selected |

Effect on the two headline measurements:

| | Before | After |
|---|---|---|
| Surface → accent hue distance | 0.5° | **7.3°** |
| Surface → accent chroma ratio | 8.0× | **15.7×** |
| Surface ladder span | 1.25:1 (3 tiers) | **1.51:1 (5 tiers)** |

Making `cream-alt` and `cream-deep` opaque is deliberate: as `rgba` they composite differently on every backdrop, which is why the current ladder is invisible on glass. The proposed ladder also matches Apple's base/elevated model and Radix's steps 1–5 role split.

All three text tokens clear AA on every tier of this ladder (`ink-tertiary` worst case **5.39:1** on `cream-hover`).

### 8c. Accents — fix the three failures and give the palette a second hue

| Token | From | To | Ratio | Why |
|---|---|---|---|---|
| `--color-primary-dark` | `#af3000` | *keep* | 2.86:1 | Fine as a fill (`bg-primary-dark`, gradient stop, border). Leave it. |
| `--color-primary-text` *(new)* | — | `#ff7a4d` | **7.18:1** | The 24 existing `text-primary-dark` usages are at 2.86:1 and must move to this. Splitting the token by role is the fix; recolouring `primary-dark` would break the 28 fill usages and `.gradient-hero`. |
| `--color-status-neutral` | `#4A7889` | `#7fb3c4` | **8.06:1** | Fixes the 3.82:1 failure. Also the only cool hue in the system — brightening it makes the teal actually visible, which is exactly the hue relief Cause 1 calls for. |
| `--color-status-failed` / `--color-stamp-red` | `#ef4444` | `#ff7a7a` | **7.33:1** | Passes today at 4.92:1 but collapses to 2.20:1 on glass and 2.9:1 in shade. Failure states are the worst place to be marginal. |
| `--color-status-paid` / `--color-leaf-green` | `#10b981` | `#34d399` | **9.63:1** | Same reasoning — 3.27:1 on glass. Material's advice to prefer the **200–50 tonal range** on dark surfaces applies directly; `#34d399` is emerald-400 to `#10b981`'s emerald-500. |
| `--color-status-pending` | `#f59e0b` | *keep* | 8.62:1 | Fine. |
| `--color-accent-cool` | `#C68A28` | `#7fb3c4` | 8.06:1 | Currently identical to `--color-honey`, so "cool" is a lie and the palette has no second hue. Aliasing it to the teal gives data-viz an actual contrasting colour. |
| `--color-honey` | `#C68A28` | *keep* | 6.23:1 | Fine. Used once — either adopt it for data-viz or delete it, but it is not a defect. |

### 8d. Glass — stabilise the backdrop

This is what makes accent colours legible again. Text tokens alone cannot fix §3b.

```css
.glass-card {
  /* was: linear-gradient(180deg, rgba(255,255,255,.12) 0%, rgba(255,255,255,.05) 100%) */
  background:
    linear-gradient(180deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.03) 100%),
    linear-gradient(180deg, rgba(28,21,18,0.72) 0%, rgba(20,15,13,0.82) 100%);

  /* was: blur(24px) saturate(180%) brightness(1.05) */
  backdrop-filter: blur(24px) saturate(110%) brightness(1.02);
  -webkit-backdrop-filter: blur(24px) saturate(110%) brightness(1.02);
}
```

Two changes, both evidence-backed:

1. **A warm dark scrim beneath the white sheen.** This is the documented standard fix for glass legibility — layer a semi-opaque colour under the text. The scrim is `#1c1512`-family, so glass cards now read as the *same warm brown* as solid cards instead of as whatever the photo happens to be.
2. **`saturate(180%)` → `saturate(110%)`.** Stops amplifying the photo's olive cast (§Cause 4) and drops glass chroma from OKC 0.043 to ~0.026, back in line with the surface palette.

Measured result — worst case across all four photo bands *including a fully blown-out region*:

| Token | Current worst | Proposed worst |
|---|---|---|
| `ink-primary` | 2.31 | **8.32** |
| `ink-secondary` | 1.68 | **6.06** |
| `ink-tertiary` | 1.14 | **4.12** |
| `primary-main` | 1.18 | **3.05** |
| `primary-light` | 1.58 | **5.69** |
| `status-paid` | 1.40 | **5.03** |
| `status-pending` | 1.25 | **4.50** |
| `status-failed` | 1.06 | **3.83** |
| `status-neutral` | 1.17 | **4.21** |

And the variability that was the root problem:

| | White-text contrast swing across the page |
|---|---|
| Current | **2.69:1 → 9.13:1** (3.4× swing, dips below AA-large) |
| Proposed | **9.66:1 → 14.33:1** (1.5× swing, always well above AA) |

The blur, the border, the inset highlights, the orange ring in `box-shadow`, and the `prefers-reduced-transparency` fallback all stay exactly as they are. The card still looks like glass — it just stops being transparent enough to leak the photo's luminance into the text.

### 8e. Priority order

1. **`--color-ink-tertiary` → `#bda49b`** — one line, fixes 646 usages and the worst accessibility failure in the system.
2. **`.glass-card` scrim + `saturate(110%)`** — one rule, makes every accent colour legible and eliminates the contrast swing.
3. **Surface ladder** (5 tiers, halved chroma) — the actual fix for "dull"; gives the orange somewhere to pop from.
4. **`--color-ink-primary` → `#f6ece7`** — halation and warmth.
5. **`--color-primary-text` for the 24 `text-primary-dark` uses** — 2.86:1 is the worst single number in the audit.
6. **`status-neutral`, `status-failed`, `status-paid`, `accent-cool`** — daylight margin and a second hue.

Items 1, 2 and 4 are single-line edits with no component changes. Item 3 requires the `rgba` → opaque swap on two tokens. Item 5 requires a find-and-replace on 24 call sites.

---

## 9. What is already right

Worth stating, because most of this palette is well-built:

- **Tinting the near-black warm instead of using `#000000`** is correct and matches Material's reasoning exactly. `DESIGN_RULES.md` records this as a deliberate choice; keep it.
- **The surface ladder's step sizes** (1.070, 1.168) already match Linear and Radix almost precisely. The tier count and the chroma need work, not the spacing.
- **`@media (prefers-reduced-transparency)`** with a solid fallback is exactly the mitigation the glassmorphism accessibility literature calls for, and many shipping glass UIs omit it.
- **`prefers-reduced-motion` on `.animate-pulse`**, `color-scheme: dark` on native controls, and the visible focus ring on inputs are all correct.
- **Status colours paired with text labels** (per `DESIGN_RULES.md`) satisfies the never-colour-alone principle that Geist and Toast both enforce.
- **`--color-primary-main` `#fa5c29` itself is a good accent** — 5.84:1, high chroma, strong identity. It is not the problem. It is being asked to stand out against a background wearing the same colour.

---

## Sources

- [Material Design — Dark theme](https://m2.material.io/design/color/dark-theme.html) — `#121212` surface, 87/60/38% emphasis opacities, elevation overlays, 15.8:1 body-text target
- [Google Design — Material Design's colour palette](https://design.google/library/material-design-dark-theme) — rationale for dark grey over black; desaturated 200–50 tonal range on dark surfaces
- [Apple Human Interface Guidelines — Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode) — base and elevated background sets
- [Apple Human Interface Guidelines — Accessibility / Color and Contrast](https://developer.apple.com/design/human-interface-guidelines/accessibility) — 4.5:1 minimum, 7:1 recommended for custom colours and small text
- [W3C — Understanding SC 1.4.3: Contrast (Minimum)](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html) — the 20/40-vision basis of the 4.5:1 threshold
- [Linear — How we redesigned the Linear UI](https://linear.app/now/how-we-redesigned-the-linear-ui) — LCH theme generation, three-variable system, deliberate chroma limiting, luminance-step elevation
- [Vercel Geist — Colors](https://vercel.com/geist/colors) and [Vercel design guidelines](https://vercel.com/design.md) — "design in monochrome", 10-step intent-encoded scales, background-100/200
- [Radix Colors — Understanding the scale](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale) — the 12-step role split; step 9 highest chroma; step 11 low-contrast vs step 12 high-contrast text
- [UX Movement — Why you should never use pure black for text or backgrounds](https://uxmovement.com/content/why-you-should-never-use-pure-black-for-text-or-backgrounds/) — halation mechanism, off-white recommendation
- [Axess Lab — Glassmorphism meets accessibility](https://axesslab.com/glassmorphism-meets-accessibility-can-frosted-glass-be-inclusive/) — dynamic contrast on translucent surfaces; astigmatism prevalence
- [New Target — Glassmorphism with website accessibility in mind](https://www.newtarget.com/web-insights-blog/glassmorphism/) — semi-opaque scrim beneath text as the standard mitigation
- [Riverdi — What makes a monitor sunlight readable](https://riverdi.com/blog/what-makes-a-monitor-sunlight-readable) — Effective Contrast Ratio thresholds for outdoor legibility
- [Toast POS — Kitchen Display System](https://pos.toasttab.com/hardware/kitchen-display-system) — light/dark modes, colour-plus-animation state encoding

**Local references:** `shared_ui/src/styles/tokens.css`, `docs/DESIGN_RULES.md`, `docs/DESIGN_GUIDELINES.md`, `docs/GLASSMORPHISM_SOLID_BG_RESEARCH.md`, `owner_pwa/public/images/resort-bg.jpg`
