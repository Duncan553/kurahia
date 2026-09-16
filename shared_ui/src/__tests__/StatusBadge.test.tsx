/**
 * A label must never decide a page is unusable.
 *
 * StatusBadge destructured straight off its CONFIG map, so any status with no
 * entry threw "Cannot destructure property 'colorClass' of undefined" and took
 * the whole screen down through the nearest error boundary. Seen for real: the
 * owner's dispute queue showed "Couldn't load this" with all three rows
 * present in the response, because RESOLVED had been mapped to a value that
 * existed in the type union but not in the map.
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { StatusBadge } from '../components/StatusBadge'
import type { StatusValue } from '../components/StatusBadge'

describe('StatusBadge', () => {
  it('renders the words a person should actually read', () => {
    render(<StatusBadge status="resolved" />)
    expect(screen.getByText('Resolved')).toBeTruthy()
  })

  it('never calls a resolved complaint "Paid"', () => {
    // The money word leaking into non-money outcomes is a repeat mistake here:
    // an approved leave request once read "Paid" too.
    const { container } = render(<StatusBadge status="resolved" />)
    expect(container.textContent).not.toContain('Paid')
  })

  it('degrades to a neutral badge on a status it does not know', () => {
    // Cast deliberately: the point is what happens when the RUNTIME is handed
    // something the types promised could not arrive — a new API state, a stale
    // cached response, a typo in one caller's mapping.
    const render_unknown = () =>
      render(<StatusBadge status={'ESCALATED_TO_LABOUR_OFFICE' as StatusValue} />)
    expect(render_unknown).not.toThrow()
  })

  it('shows the unknown status rather than a blank chip', () => {
    const { container } = render(
      <StatusBadge status={'ESCALATED_TO_LABOUR_OFFICE' as StatusValue} />)
    // Better a person reads a raw status than an empty badge that tells them
    // nothing at all about the row they are looking at.
    expect(container.textContent).toContain('ESCALATED_TO_LABOUR_OFFICE')
  })

  it('covers every value in the union', () => {
    // The union and the map drifted apart once already — approved, rejected
    // and actioned were in the map but not the union; resolved and dismissed
    // were in neither. This walks the list so the next addition cannot land in
    // only one of the two places.
    const every: StatusValue[] = [
      'paid', 'pending', 'failed', 'info', 'active', 'inactive', 'held',
      'confirmed', 'checked-in', 'checked-out', 'cancelled', 'no-show',
      'approved', 'rejected', 'actioned', 'resolved', 'dismissed', 'under-review',
    ]
    for (const s of every) {
      const { container, unmount } = render(<StatusBadge status={s} />)
      expect(container.textContent!.trim().length).toBeGreaterThan(0)
      // A fallback badge would echo the raw key; a real entry gives a label.
      expect(container.textContent).not.toBe(s)
      unmount()
    }
  })
})
