import { render, screen, fireEvent } from '@testing-library/react'
import { Card } from '../components/Card'

describe('Card', () => {
  test('renders children', () => {
    render(<Card>Hello card</Card>)
    expect(screen.getByText('Hello card')).toBeInTheDocument()
  })

  test('tappable card has role=button and responds to click', () => {
    const onClick = vi.fn()
    render(<Card tappable onClick={onClick}>Tap me</Card>)
    const card = screen.getByRole('button', { name: /tap me/i })
    fireEvent.click(card)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  test('tappable card fires on Enter and Space keydown', () => {
    const onClick = vi.fn()
    render(<Card tappable onClick={onClick}>Tap me</Card>)
    const card = screen.getByRole('button')
    fireEvent.keyDown(card, { key: 'Enter' })
    fireEvent.keyDown(card, { key: ' ' })
    expect(onClick).toHaveBeenCalledTimes(2)
  })

  test('selected card has aria-relevant class applied', () => {
    const { container } = render(<Card selected>Selected</Card>)
    const div = container.firstChild as HTMLElement
    expect(div.className).toContain('bg-sage-light')
    expect(div.className).toContain('border-sage-dark')
  })
})
