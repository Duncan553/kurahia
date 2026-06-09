import { render } from '@testing-library/react'
import { Skeleton } from '../components/Skeleton'

describe('Skeleton', () => {
  test('text variant renders a single shimmer element', () => {
    const { container } = render(<Skeleton variant="text" />)
    const el = container.querySelector('.sk-pulse')
    expect(el).toBeInTheDocument()
    expect(el).toHaveAttribute('aria-hidden', 'true')
  })

  test('text variant with lines=3 renders 3 elements', () => {
    const { container } = render(<Skeleton variant="text" lines={3} />)
    expect(container.querySelectorAll('.sk-pulse').length).toBe(3)
  })

  test('avatar variant is circle-shaped (rounded-full)', () => {
    const { container } = render(<Skeleton variant="avatar" />)
    expect((container.querySelector('.sk-pulse') as HTMLElement).className)
      .toContain('rounded-full')
  })

  test('card variant has card-shaped classes (h-48 + rounded-xl)', () => {
    const { container } = render(<Skeleton variant="card" />)
    const cls = (container.querySelector('.sk-pulse') as HTMLElement).className
    expect(cls).toContain('h-48')
    expect(cls).toContain('rounded-xl')
  })
})
