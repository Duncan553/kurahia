import { render, screen } from '@testing-library/react'
import { StatusBadge } from '../components/StatusBadge'
import type { StatusValue } from '../components/StatusBadge'

// The union and the CONFIG map drifted apart once already: approved, rejected
// and actioned were in the map but not the union, and resolved, dismissed and
// under-review were in neither — so the dispute queue asked for a badge that
// did not exist. Every value lives in this list so the next addition cannot
// land in only one of the two places.
const ALL_STATUSES: StatusValue[] = [
  'paid', 'pending', 'failed', 'info',
  'active', 'inactive', 'held',
  'confirmed', 'checked-in', 'checked-out',
  'cancelled', 'no-show',
  'approved', 'rejected', 'actioned',
  'resolved', 'dismissed', 'under-review',
]

describe('StatusBadge', () => {
  test('three-signal rule: color class, icon SVG, and text label all present', () => {
    const { container } = render(<StatusBadge status="paid" />)
    const badge = container.firstChild as HTMLElement
    // Color class present
    expect(badge.className).toContain('text-status-paid')
    // Icon SVG present (aria-hidden)
    expect(container.querySelector('svg')).toBeInTheDocument()
    // Text label present
    expect(screen.getByText('Paid')).toBeInTheDocument()
  })

  test('every status value renders without crashing', () => {
    ALL_STATUSES.forEach((status) => {
      const { unmount } = render(<StatusBadge status={status} />)
      unmount()
    })
    // If we reach here, none threw
    expect(true).toBe(true)
  })

  test('pill variant has rounded-full class', () => {
    const { container } = render(<StatusBadge status="active" variant="pill" />)
    expect((container.firstChild as HTMLElement).className).toContain('rounded-full')
  })

  test('sm size applies smaller text and padding classes', () => {
    const { container: smContainer } = render(<StatusBadge status="pending" size="sm" />)
    const { container: mdContainer } = render(<StatusBadge status="pending" size="md" />)
    const smClass = (smContainer.firstChild as HTMLElement).className
    const mdClass = (mdContainer.firstChild as HTMLElement).className
    expect(smClass).toContain('text-xs')
    expect(mdClass).toContain('text-sm')
  })

  // ── What a badge must never do ─────────────────────────────────────────────
  //
  // StatusBadge destructured straight off CONFIG, so a status with no entry
  // threw "Cannot destructure property 'colorClass' of undefined" and took the
  // whole SCREEN down through the nearest error boundary. Seen for real: the
  // owner's dispute queue showed "Couldn't load this" with all three rows
  // sitting in the response, because RESOLVED mapped to a value the map did
  // not have. A label does not get to decide a page is unusable.

  test('degrades instead of crashing on a status it does not know', () => {
    // Cast deliberately — the point is what the RUNTIME does when handed
    // something the types promised could not arrive: a new API state, a stale
    // cached response, a typo in one caller's mapping.
    const unknown = () =>
      render(<StatusBadge status={'ESCALATED_TO_LABOUR_OFFICE' as StatusValue} />)
    expect(unknown).not.toThrow()
  })

  test('shows the unknown status rather than an empty chip', () => {
    const { container } = render(
      <StatusBadge status={'ESCALATED_TO_LABOUR_OFFICE' as StatusValue} />)
    // Better a person reads a raw status than a blank badge that tells them
    // nothing about the row in front of them.
    expect(container.textContent).toContain('ESCALATED_TO_LABOUR_OFFICE')
  })

  // ── The money word ─────────────────────────────────────────────────────────
  //
  // 'paid' kept leaking into outcomes that have nothing to do with money,
  // because it was the green one: an approved leave request read "Paid", and
  // then a resolved complaint did too — on a complaint that was ABOUT pay.

  test('a resolved complaint is never labelled "Paid"', () => {
    const { container } = render(<StatusBadge status="resolved" />)
    expect(container.textContent).toContain('Resolved')
    expect(container.textContent).not.toContain('Paid')
  })

  test('a claimed complaint says someone is looking at it', () => {
    const { container } = render(<StatusBadge status="under-review" />)
    // It used to say "Active" — the word for a live wristband, not for the one
    // thing the person waiting wants to know.
    expect(container.textContent).toContain('Under review')
  })
})
