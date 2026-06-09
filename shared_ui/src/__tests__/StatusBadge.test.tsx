import { render, screen } from '@testing-library/react'
import { StatusBadge } from '../components/StatusBadge'
import type { StatusValue } from '../components/StatusBadge'

const ALL_STATUSES: StatusValue[] = [
  'paid', 'pending', 'failed', 'info',
  'active', 'inactive', 'held',
  'confirmed', 'checked-in', 'checked-out',
  'cancelled', 'no-show',
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

  test('all 12 status values render without crashing', () => {
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
})
