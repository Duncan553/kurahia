import { render, screen, fireEvent } from '@testing-library/react'
import { EmptyState } from '../components/EmptyState'

function BoxIcon() {
  return <svg width="48" height="48" viewBox="0 0 48 48" aria-hidden="true"><rect width="48" height="48" rx="8" /></svg>
}

describe('EmptyState', () => {
  test('renders icon, title, and description', () => {
    render(
      <EmptyState
        icon={<BoxIcon />}
        title="Nothing booked today."
        description="Bookings will appear here once guests reserve."
      />
    )
    expect(screen.getByText('Nothing booked today.')).toBeInTheDocument()
    expect(screen.getByText('Bookings will appear here once guests reserve.')).toBeInTheDocument()
  })

  test('renders without description', () => {
    const { container } = render(
      <EmptyState icon={<BoxIcon />} title="All clear." />
    )
    expect(container.querySelector('p')).toBeNull()
  })

  test('action button renders and fires callback', () => {
    const onAction = vi.fn()
    render(
      <EmptyState
        icon={<BoxIcon />}
        title="No orders yet."
        actionLabel="Add order"
        onAction={onAction}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /add order/i }))
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  test('no action button rendered when actionLabel or onAction is missing', () => {
    render(<EmptyState icon={<BoxIcon />} title="Empty." actionLabel="Add" />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})
