/**
 * Icon — the single source of truth for inline SVG icons across all 3 PWAs.
 *
 * Why this exists: icons were previously either copy-pasted <svg> blocks or raw
 * emoji literals (📍 ✓ ⚠ 🔔). Emoji render differently on every OS/browser, can't
 * inherit text colour reliably, and break the design system. This replaces both.
 *
 * Design rules (from docs/DESIGN_GUIDELINES.md):
 *   - stroke only, never fill
 *   - 24x24 viewBox, strokeWidth 1.5
 *   - colour comes from `currentColor`, so the parent's text-* class controls it
 */

// Each entry is just the inner <path>/<circle> markup for a 24x24 stroke icon.
// Adding a new icon = add one line here. Nothing else needs to change.
const PATHS = {
  // ✓ — completion, success, "done"
  check: <path d="M4 12.5l5 5L20 6.5" />,
  // ✗ — failure, imbalance, "not done"
  x: <path d="M6 6l12 12M18 6L6 18" />,
  // ⚠ — warning, allergens, urgency
  alert: (
    <>
      <path d="M12 3.5L22 20H2L12 3.5z" />
      <path d="M12 10v4M12 17v.5" />
    </>
  ),
  // ○ — an unmet requirement / not-started state (pairs with `check` for met)
  circle: <circle cx="12" cy="12" r="8" />,
  // ◐ — work in progress (half-filled circle)
  progress: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4a8 8 0 010 16z" fill="currentColor" stroke="none" />
    </>
  ),
  // 📍 — a physical location
  pin: (
    <>
      <path d="M12 21s7-6.2 7-11a7 7 0 10-14 0c0 4.8 7 11 7 11z" />
      <circle cx="12" cy="10" r="2.5" />
    </>
  ),
  // 👤 — a person (guest, employee)
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" />
    </>
  ),
  // 🔔 — alerts/sound ON
  bell: (
    <>
      <path d="M6 9a6 6 0 1112 0c0 5 2 6 2 6H4s2-1 2-6z" />
      <path d="M10 19a2 2 0 004 0" />
    </>
  ),
  // 🔇 — alerts/sound MUTED (bell with a strike-through)
  bellOff: (
    <>
      <path d="M6 9a6 6 0 019.5-4.9M18 12c0 3 2 3 2 3H7" />
      <path d="M10 19a2 2 0 004 0" />
      <path d="M3 3l18 18" />
    </>
  ),
  // 🎉 — celebration / successful completion of a flow
  celebrate: (
    <>
      <path d="M4 20l5-13 8 8-13 5z" />
      <path d="M15 4v2M19 8h2M17.5 5.5l1.5-1.5" />
    </>
  ),
} as const

// The icon names callers can pass. Typo'd names become a TypeScript error.
export type IconName = keyof typeof PATHS

export interface IconProps {
  name: IconName
  /** Rendered pixel size, width and height. Defaults to 20 (the design-system default). */
  size?: number
  /** Extra Tailwind classes — use text-* here to colour the icon. */
  className?: string
  /** Line weight. Bump to 2+ when the icon is rendered large. */
  strokeWidth?: number
  /**
   * Screen-reader label. Omit for purely decorative icons (they get aria-hidden),
   * pass a string when the icon is the ONLY thing conveying the meaning.
   */
  label?: string
}

export function Icon({ name, size = 20, className = '', strokeWidth = 1.5, label }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`inline-block shrink-0 ${className}`}
      // Decorative by default; only announced when the caller gives it a label.
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {PATHS[name]}
    </svg>
  )
}
