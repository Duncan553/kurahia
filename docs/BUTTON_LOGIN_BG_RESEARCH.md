# Button, Login & Background Research
> Deep research from 15+ sources. June 2026. Specific to Kurahia's dark glass dashboard.

---

## 1. MODERN BUTTON STYLES for Dark Glass Dashboards

### The Verdict: Gradient + Subtle Glow > Flat Solid

Every premium dark glass dashboard in 2025-2026 uses buttons that have **depth** — not flat
colored rectangles. The pattern is: gradient fill + soft glow shadow + glass hover state.
Apple's Liquid Glass (WWDC 2025) cemented this: buttons should feel like polished,
translucent hardware — not painted cardboard.

**Your current Button.tsx problem:** The `VARIANT` map uses flat solid backgrounds
(`bg-primary-dark`, `bg-cream-card`, `bg-transparent`). These look dead on a glass
dashboard. The login button (`bg-white/20 hover:bg-white/30`) is closer to right
but has no gradient or glow.

### Recipe A: "Emerald Gradient" (Primary Actions)

The hero button. Use for Sign In, Submit Order, Confirm Booking.

```
Tailwind classes:
  bg-gradient-to-b from-emerald-500 to-emerald-700
  border border-emerald-400/30
  shadow-[0_4px_14px_rgba(16,185,129,0.3)]
  text-white font-semibold tracking-wide
  rounded-xl

Hover:
  hover:from-emerald-400 hover:to-emerald-600
  hover:shadow-[0_6px_20px_rgba(16,185,129,0.4)]
  hover:border-emerald-300/40

Press (via Framer whileTap):
  scale: 0.97  (already doing this — good)

Focus:
  focus-visible:ring-2 focus-visible:ring-emerald-400/50 focus-visible:ring-offset-2
  focus-visible:ring-offset-transparent
```

CSS equivalent for `.gradient-hero` (update existing class):
```css
.gradient-hero {
  background: linear-gradient(to bottom, #10b981 0%, #047857 100%);
  border: 1px solid rgba(52, 211, 153, 0.3);
  box-shadow: 0 4px 14px rgba(16, 185, 129, 0.3);
  transition: all 0.2s ease;
}
.gradient-hero:hover {
  background: linear-gradient(to bottom, #34d399 0%, #059669 100%);
  box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
  border-color: rgba(52, 211, 153, 0.4);
}
.gradient-hero:active {
  transform: scale(0.97);
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
}
```

### Recipe B: "Glass Button" (Secondary Actions)

The glass-panel button. Use for Cancel, View Details, secondary nav actions.

```
Tailwind classes:
  bg-white/8 backdrop-blur-md
  border border-white/15
  text-slate-200 font-medium
  shadow-[0_2px_8px_rgba(0,0,0,0.2),inset_0_1px_0_rgba(255,255,255,0.06)]
  rounded-xl

Hover:
  hover:bg-white/14
  hover:border-white/25
  hover:shadow-[0_4px_16px_rgba(0,0,0,0.25)]

Press:
  active:bg-white/6

Focus:
  focus-visible:ring-2 focus-visible:ring-white/25
  focus-visible:ring-offset-2 focus-visible:ring-offset-transparent
```

CSS equivalent:
```css
.glass-btn {
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(12px) saturate(140%);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
  border: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow:
    0 2px 8px rgba(0, 0, 0, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
  transition: all 0.2s ease;
}
.glass-btn:hover {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.25);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
}
.glass-btn:active {
  background: rgba(255, 255, 255, 0.06);
}
```

### Recipe C: "Ghost Glow" (Tertiary / Text Actions)

Minimal button with glow on hover. Use for "Use PIN instead", "Forgot password",
link-style actions.

```
Tailwind classes:
  bg-transparent
  text-slate-400 font-medium text-sm
  rounded-lg px-3 py-2

Hover:
  hover:text-emerald-400
  hover:bg-emerald-500/8
  hover:shadow-[0_0_12px_rgba(16,185,129,0.15)]

Focus:
  focus-visible:ring-2 focus-visible:ring-emerald-400/30 rounded
```

CSS equivalent:
```css
.ghost-glow {
  background: transparent;
  color: rgba(148, 163, 184, 0.8);
  transition: all 0.2s ease;
}
.ghost-glow:hover {
  color: #34d399;
  background: rgba(16, 185, 129, 0.08);
  box-shadow: 0 0 12px rgba(16, 185, 129, 0.15);
}
```

### Sources
- [Glassmorphism 2.0: Modern CSS Techniques for Depth (2026)](https://weblogtrips.com/technology/glassmorphism-2-0-css-techniques-2026/)
- [Dark Glassmorphism: The Aesthetic That Will Define UI in 2026](https://medium.com/@developer_89726/dark-glassmorphism-the-aesthetic-that-will-define-ui-in-2026-93aa4153088f)
- [Button States Explained (2026) — DesignRush](https://www.designrush.com/best-designs/websites/trends/button-states)
- [Best Button Design 2026: UX & Conversions — WeWeb](https://www.weweb.io/blog/best-button-design-ideas-ux-accessibility-conversions)
- [Complete Guide to Buttons in Web Design for 2026 — Clay](https://clay.global/blog/buttons-web-design)
- [Free Animated Gradient Glow Button — TailwindFlex](https://tailwindflex.com/@homayunmmdy/free-animated-gradient-glow-button-with-tailwind-css-open-source-ui-component)
- [Glassmorphism CSS Generator — Glass UI](https://ui.glass/generator)
- [Super Dev Resources — Quick Glassmorphism UI CSS](https://superdevresources.com/glassmorphism-ui-css/)

---

## 2. LOGIN SCREEN — Is Your Current Design Good or Cliche?

### Honest Assessment of Current LoginScreen.tsx

**What you have now:**
- Full-bleed resort aerial photo background (DJI_0669)
- Dark gradient overlay (primary-dark at 60-70%)
- Centered frosted glass card (bg-cream-card/25 backdrop-blur-xl)
- Logo icon + "Kurahia" serif heading + "Staff Portal" subtitle
- Two inputs with glass styling
- White/20 glass submit button
- "Use PIN instead" link at bottom

**Is this cliche?** Partially. The glass-card-over-photo pattern IS the single most
common login layout in 2025-2026 Dribbble/Behance. But that's because it works.
The question is: does yours execute it well or cheaply?

### What Makes It Cheap vs Premium

**CHEAP signals (fix these):**
1. **The submit button is flat glass** — `bg-white/20 hover:bg-white/30` with no gradient
   or glow. This is the weakest element. A premium login has ONE strong call-to-action
   that pulls your eye. Use Recipe A (Emerald Gradient) here.
2. **No visual hierarchy in the card** — inputs and button are all similar-weight glass.
   Premium logins use contrast: glass inputs + solid/gradient CTA button.
3. **The "K" logo box is generic** — a letter in a glass square is the #1 cliche move.
   Either use an actual logo/icon, or make the letter more distinctive (e.g., use
   Fraunces italic at a larger size, or add a subtle emerald gradient behind it).

**GOOD signals (keep these):**
1. **The resort photo** — it connects to the physical place. This is NOT generic.
   Generic is abstract gradients with no connection to the product. Your photo IS the brand.
2. **The gradient overlay** — necessary for text contrast. The from/via/to pattern is correct.
3. **The glass card with backdrop-blur-xl** — executed well. The border-white/20 and
   before pseudo-element gradient highlight are proper technique.
4. **Motion** — the fade-in, slide-up, and logo scale animations are tasteful, not over-done.
5. **Focus states with ring** — accessible. Keep the shadow-[0_0_0_3px...] pattern.

### Specific Recommendation: What to Change

**Layout** — Keep the centered card. Do NOT switch to split-screen (half photo, half form).
Split-screen is a desktop pattern; your PWA runs on resort tablets. Centered card
is correct for portrait/mobile-first.

**Card max-width** — `max-w-[400px]` is good. Don't go wider.

**Spacing** — Current `space-y-5` between form elements is fine. The `p-8` card padding
is generous — could tighten to `p-6` on mobile (`p-8` on `sm:`) but this is minor.

**The 3 Concrete Changes:**

1. **Submit button: swap glass for gradient**
   ```
   REMOVE: bg-white/20 hover:bg-white/30 backdrop-blur-sm border border-white/25
   ADD:    bg-gradient-to-b from-emerald-500 to-emerald-700
           border border-emerald-400/30
           shadow-[0_4px_14px_rgba(16,185,129,0.3)]
           hover:from-emerald-400 hover:to-emerald-600
           hover:shadow-[0_6px_20px_rgba(16,185,129,0.4)]
   ```

2. **Logo "K" icon: add emerald gradient tint**
   ```
   REMOVE: bg-white/15
   ADD:    bg-gradient-to-br from-emerald-500/20 to-emerald-700/10
   ```
   This subtly ties the logo to the brand color without being garish.

3. **"Use PIN instead" link: use ghost-glow pattern**
   ```
   REMOVE: text-white/60 hover:text-white
   ADD:    text-white/50 hover:text-emerald-400 hover:bg-emerald-500/8
           transition-all rounded-lg px-3 py-1.5
   ```

### Sources
- [Glassmorphism: The Most Beautiful Trap in Modern UI Design — Medium](https://medium.com/design-bootcamp/glassmorphism-the-most-beautiful-trap-in-modern-ui-design-a472818a7c0a)
- [50+ Login Page Examples for SaaS Designers (2026) — Eleken](https://www.eleken.co/blog-posts/login-page-examples)
- [60+ Best Login Screen Examples (2026) — Muzli](https://muz.li/inspiration/login-screen/)
- [Modern Login UI Design (Dark Theme) — Figma Community](https://www.figma.com/community/file/1627625580036318518/modern-login-ui-design-dark-theme-figma)
- [10 Mind-Blowing Glassmorphism Examples for 2026 — Onyx8](https://onyx8agency.com/blog/glassmorphism-inspiring-examples/)

---

## 3. BACKGROUND — Blurred Photo vs Pure Gradient Mesh

### The Answer: Keep the Blurred Photo. Here's Why.

**What the research says:**
Every major source agrees: gradient mesh (ambient color orbs) is the standard best
practice for dark glassmorphism dashboards. The pattern is smooth vector-like color
blobs — not photos.

**BUT** — and this is the key — those sources are talking about generic SaaS dashboards,
analytics tools, and dev platforms. They don't have a resort.

**Your case is different.** You have a physical place with beautiful grounds. The blurred
resort photo is doing two things gradient mesh cannot:

1. **Brand anchor** — it whispers "this is a real place" even at 60px blur. The color
   temperature, the greens of the landscape, the water — those come through the blur
   and create an atmosphere that pure CSS gradients can't replicate.

2. **Emotional warmth** — a resort app should feel warm and grounded, not like a crypto
   dashboard. Pure gradient mesh (the typical deep purple + neon blue + hot pink orbs)
   skews cold and tech-y.

### What the Best Dark Glass Dashboards Actually Use

The top-tier pattern from 2025-2026 sources:

| Type | Background | Use Case |
|------|-----------|----------|
| SaaS/Analytics | Pure gradient mesh (orbs) | No physical product to show |
| Finance/Trading | Solid dark (#060910) + subtle gradient | Information density is king |
| Hospitality/Lifestyle | Blurred photo + overlay | Brand connection matters |
| Apple visionOS | Blurred real-world pass-through + glass | Physical world IS the background |

Your app is hospitality. **You are the visionOS pattern** — the resort IS the world
behind the glass. This is architecturally correct.

### Your Current Implementation Review

```css
/* What you have now in index.css */
body::before {
  background: url('/images/resort-bg.jpg') center/cover no-repeat;
  filter: blur(60px) brightness(0.2) saturate(1.4);
}
body::after {
  background-color: rgba(8, 10, 18, 0.65);
  background-image:
    radial-gradient(ellipse at 15% 20%, hsla(35, 65%, 22%, 0.4) ...),
    radial-gradient(ellipse at 80% 40%, hsla(185, 60%, 18%, 0.35) ...),
    radial-gradient(ellipse at 30% 85%, hsla(155, 45%, 14%, 0.3) ...);
}
```

**This is already the hybrid approach. It's good.** The 3-layer stack (blurred photo +
dark overlay + gradient mesh orbs on top) is exactly what premium implementations do.
The gradient orbs add the color variation that glass panels need to refract, while the
photo underneath provides organic warmth.

### Specific Tuning Recommendations

**Keep as-is:**
- `blur(60px)` — correct. High enough to remove recognizable shapes, low enough to
  let color temperature through.
- `saturate(1.4)` — correct. Brings out the greens/blues from the resort photo.
- The 3 radial gradient orbs — correct positions and hues.

**One adjustment to consider:**
- `brightness(0.2)` is quite dark. Try `brightness(0.25)` — lets 25% more photo color
  through without hurting text contrast. The overlay at 65% opacity already handles
  darkening. Having both at aggressive levels double-darkens.

```css
/* Proposed tweak — slightly more photo warmth */
body::before {
  filter: blur(60px) brightness(0.25) saturate(1.4);
}
```

**Do NOT change:**
- Do NOT remove the photo and go pure gradient mesh. You'd lose the brand warmth.
- Do NOT reduce blur below 40px. Recognizable image details behind glass panels
  create visual noise and hurt text legibility.
- Do NOT add animation to the background orbs. Animated mesh looks premium in
  isolation but causes jank on tablet hardware and fights with the glass blur
  compositing. Keep it static.

### The Gradient Orb Colors (Current vs Recommendation)

Your current orbs use warm amber (hsla 35), cool teal (hsla 185), and green (hsla 155).
These are well-chosen for a resort palette — they echo the landscape colors that come
through the blurred photo.

**One optional addition** — a very faint 4th orb in the center to prevent a dead zone:

```css
body::after {
  background-image:
    radial-gradient(ellipse at 15% 20%, hsla(35, 65%, 22%, 0.4) 0%, transparent 55%),
    radial-gradient(ellipse at 80% 40%, hsla(185, 60%, 18%, 0.35) 0%, transparent 50%),
    radial-gradient(ellipse at 30% 85%, hsla(155, 45%, 14%, 0.3) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 50%, hsla(160, 30%, 12%, 0.15) 0%, transparent 60%);
}
```

This 4th orb (very low opacity, centered, neutral green) fills the center area where
glass panels sit, giving them slightly more to refract.

### Sources
- [Why Everything Is Going Glassmorphism (And How to Do It Right) — Clay](https://clay.global/blog/glassmorphism-ui)
- [Glassmorphism: CSS Recipe, Generator, Examples — Superdesign](https://www.superdesign.dev/styles/glassmorphism)
- [Dark Glassmorphism: The Aesthetic That Will Define UI in 2026 — Medium](https://medium.com/@developer_89726/dark-glassmorphism-the-aesthetic-that-will-define-ui-in-2026-93aa4153088f)
- [Glassmorphism: What It Is and How to Use It in 2026 — Inverness](https://invernessdesignstudio.com/glassmorphism-what-it-is-and-how-to-use-it-in-2026)
- [12 Glassmorphism UI Features, Best Practices — UXPilot](https://uxpilot.ai/blogs/glassmorphism-ui)
- [Dark Mode Color Palettes for Modern Websites — Colorhero](https://colorhero.io/blog/dark-mode-color-palettes-2025)
- [Premium Dark Gradient CSS — Gradient.page](https://gradient.page/ui-gradients/premium-dark)
- [Best Practices for Dark Mode in Web Design 2026 — NateBal](https://natebal.com/best-practices-for-dark-mode/)

---

## Summary: The 5 Actions

| # | What | Priority |
|---|------|----------|
| 1 | Update Button.tsx VARIANT map: primary = emerald gradient, secondary = glass-btn, ghost = ghost-glow | HIGH |
| 2 | Login submit button: swap flat glass for gradient CTA | HIGH |
| 3 | Login "K" logo: add emerald gradient tint | LOW |
| 4 | Background: bump brightness from 0.2 to 0.25, optionally add 4th center orb | LOW |
| 5 | Keep the blurred resort photo. Do NOT replace with pure gradient mesh. | DECISION (locked) |
