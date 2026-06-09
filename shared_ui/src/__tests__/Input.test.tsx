import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Input } from '../components/Input'

describe('Input', () => {
  test('renders with label linked to input', () => {
    render(<Input label="Email address" />)
    const input = screen.getByLabelText('Email address')
    expect(input).toBeInTheDocument()
    expect(input.tagName).toBe('INPUT')
  })

  test('error state shows message and sets aria-invalid', () => {
    render(<Input label="Password" error="Must be at least 8 characters" />)
    const input = screen.getByLabelText('Password')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Must be at least 8 characters')).toBeInTheDocument()
  })

  test('character count appears when maxLength set and turns red past 90%', async () => {
    render(<Input label="Bio" maxLength={10} />)
    const input = screen.getByLabelText('Bio')
    // Initially 0/10 — within limit
    expect(screen.getByText('0/10')).toBeInTheDocument()
    // Type 10 chars (100% = past 90% threshold)
    await userEvent.type(input, 'abcdefghij')
    expect(screen.getByText('10/10')).toBeInTheDocument()
    // The count element should now have the red class
    const count = screen.getByText('10/10')
    expect(count.className).toContain('text-status-failed')
  })

  test('input is described by error element when error is present', () => {
    render(<Input label="Name" error="Name is required" />)
    const input = screen.getByLabelText('Name')
    const describedById = input.getAttribute('aria-describedby')
    expect(describedById).toBeTruthy()
    const errorEl = document.getElementById(describedById!)
    expect(errorEl).toHaveTextContent('Name is required')
  })
})
