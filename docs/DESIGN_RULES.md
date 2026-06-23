# Design Rules Checklist — Apply to EVERY screen

## From Impeccable (AI slop detectors)
- [ ] No side-tab borders (border-l-2 on nav = AI tell)
- [ ] No dark glows on buttons (shadow with color = AI tell)
- [ ] No bounce/elastic easing (use ease-out or spring damping 25+)
- [ ] No pure black or gray — always TINT warm (#1e100c not #000)
- [ ] Padding minimum p-4 on cards (p-3 = cramped)
- [ ] Touch targets minimum 44x44px (min-h-[44px])
- [ ] No emoji as structural icons — SVG only

## From UI/UX Pro Max (priority rules)
- [ ] Accessibility: 4.5:1 contrast ratio for text
- [ ] Touch: 44x44pt minimum, 8px spacing between targets
- [ ] Performance: transform/opacity animations ONLY (never width/height)
- [ ] Animation: 150-300ms duration, meaningful motion
- [ ] Typography: line-height 1.5-1.75, measure 65-75 chars
- [ ] Forms: visible labels (not placeholder-only), errors near fields
- [ ] Navigation: bottom nav ≤5 items
- [ ] Mobile-first: design mobile first, layer desktop

## From Anthropic Frontend Design
- [ ] Ground in subject matter (lakeside resort, not generic SaaS)
- [ ] Hero thesis: lead with THE most important thing for this role
- [ ] Structure encodes meaning: big card = important, small = secondary
- [ ] Single orchestrated motion: one page-load sequence, not scattered
- [ ] Two-pass: plan design THEN build (don't jump to CSS)
- [ ] Typography = personality carrier (Fraunces for headings = warmth)
- [ ] Copy: active voice, plain language, errors explain what went wrong

## Arrangement & Layout (from Bento Grid + Impeccable layout)
- [ ] Bento grid: mix 1x1, 1x2, 2x1, 2x2 cells — NOT uniform grids
- [ ] Hero block: the most important data gets the BIGGEST card
- [ ] 4px spacing base: gaps of 8/12/16/24/32px (use gap-2/3/4/6/8)
- [ ] Squint test: squint at screen — can you tell what's important?
- [ ] No monotonous card grids — vary sizes for visual rhythm
- [ ] Internal padding: p-4 minimum (p-5 or p-6 for hero cards)
- [ ] Gap between cards: gap-4 (16px) standard, gap-6 for sections
- [ ] Breathing room: sections separated by mb-6 or mb-8
- [ ] Max content width: max-w-6xl for dashboards, max-w-3xl for forms
- [ ] Column layout: lg:grid-cols-[2fr_1fr] for main+sidebar, NOT 50/50

## Kurahia-specific
- [ ] Warm palette: #1e100c bg, #f9dcd5 text, #fa5c29 accent (sparingly)
- [ ] Glass: resort photo body::before, warm overlay body::after
- [ ] Glass cards: glass-card class on ALL card elements
- [ ] No opaque bg-cream-card on root containers (kills glass)
- [ ] Headers: font-serif text-2xl font-bold + subtitle explaining screen
- [ ] Numbers: tabular-nums class (JetBrains Mono)
- [ ] Status: green=paid/OK, amber=pending, red=failed (+ text labels)
- [ ] Department pills: horizontal scroll, not flex-wrap
