import { useEffect, useState } from 'react'

/** Tailwind's `md` breakpoint. Keep in sync with the `md:` classes in the UI. */
const DESKTOP_QUERY = '(min-width: 768px)'

/**
 * True from Tailwind's `md` breakpoint up.
 *
 * Use this when a responsive layout must render ONE subtree, not two. The
 * pattern this replaces — a `md:hidden` block and a `hidden md:flex` block that
 * each render the same children — puts both copies in the DOM permanently.
 * CSS hides one visually, but the duplicates are still real: duplicate `id`
 * attributes (so `<label htmlFor>` can bind to the invisible copy), duplicate
 * ARIA labels and landmarks, doubled `autoFocus`, and any child effect running
 * twice. It also makes `getByRole`/`getByLabel` ambiguous for tests.
 *
 * Prefer plain CSS when the SAME single subtree can just be restyled per
 * breakpoint — that has no JS cost and no resize flash. Reach for this hook only
 * when the two layouts are structurally different (e.g. two panes side by side
 * on desktop vs one pane at a time on a phone).
 */
export function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(DESKTOP_QUERY).matches
  )

  useEffect(() => {
    const mq = window.matchMedia(DESKTOP_QUERY)
    const onChange = (e: MediaQueryListEvent) => setIsDesktop(e.matches)
    mq.addEventListener('change', onChange)
    // Re-sync in case the viewport changed between first render and this effect.
    setIsDesktop(mq.matches)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  return isDesktop
}
