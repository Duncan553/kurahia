# Design Guidelines (from Anthropic + Vercel skills)

## Core Principle
Ground design in the SUBJECT MATTER — Waterfront Country Club, a Kenyan lakeside resort.
NOT generic templates. Every choice should reflect the resort's world.

## Three Defaults to AVOID
1. Warm cream backgrounds with serif display and terracotta accents ← WE DID THIS. Killed it.
2. Near-black with bright acid-green or vermilion accents ← DON'T fall into this either
3. Broadsheet style with hairlines, zero border-radius, dense columns

## What to DO Instead
- Identify the characteristic thing: WATER, NATURE, HOSPITALITY, WARMTH
- Use the resort photo as the actual environment (✅ already doing this)
- Glass panels = looking through a window at the resort (✅ already doing this)
- Typography = personality carrier, not decoration
- Structure encodes meaning (mixed-size cards show hierarchy)
- Motion serves the subject (water-like flow, gentle spring physics)

## Vercel Web Interface Rules (apply everywhere)
- Icon-only buttons need aria-label
- Inputs need labels
- Use button for actions, a/Link for navigation
- focus-visible:ring on all interactive elements
- Never outline-none without replacement
- prefers-reduced-motion honored
- Animate only transform + opacity
- tabular-nums for number columns
- text-wrap: balance on headings
- Handle long text (truncate/line-clamp)
- Handle empty states
- URL reflects state (filters, tabs in query params)
- Destructive actions need confirmation
- touch-action: manipulation on mobile
- Error messages include fix/next step
