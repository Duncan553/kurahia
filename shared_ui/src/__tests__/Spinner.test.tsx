import { render, screen } from '@testing-library/react'
import { Spinner } from '../components/Spinner'

describe('Spinner', () => {
  test('has role=status and aria-label', () => {
    render(<Spinner label="Loading data…" />)
    const el = screen.getByRole('status')
    expect(el).toHaveAttribute('aria-label', 'Loading data…')
  })

  test('default label is "Loading…"', () => {
    render(<Spinner />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Loading…')
  })

  test('sm and lg sizes render different width/height attributes', () => {
    const { rerender, getByRole } = render(<Spinner size="sm" />)
    expect(getByRole('status')).toHaveAttribute('width', '16')
    rerender(<Spinner size="lg" />)
    expect(getByRole('status')).toHaveAttribute('width', '32')
  })

  test('sage and cream colors set different stroke on the circle', () => {
    const { container: sageContainer } = render(<Spinner color="sage" />)
    const { container: creamContainer } = render(<Spinner color="cream" />)
    const sageStroke = sageContainer.querySelector('circle')?.getAttribute('stroke')
    const creamStroke = creamContainer.querySelector('circle')?.getAttribute('stroke')
    expect(sageStroke).not.toBe(creamStroke)
  })
})
