import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Toggle } from '../components/Toggle'

describe('Toggle', () => {
  test('renders with role="switch" and visible label', () => {
    render(<Toggle checked={false} onChange={() => {}} label="Enable notifications" />)
    const toggle = screen.getByRole('switch')
    expect(toggle).toBeInTheDocument()
    expect(screen.getByText('Enable notifications')).toBeInTheDocument()
  })

  test('clicking toggle calls onChange with opposite value', async () => {
    const handleChange = vi.fn()
    render(<Toggle checked={false} onChange={handleChange} label="Dark mode" />)
    await userEvent.click(screen.getByRole('switch'))
    expect(handleChange).toHaveBeenCalledWith(true)
  })

  test('aria-checked reflects the checked prop', () => {
    const { rerender } = render(
      <Toggle checked={false} onChange={() => {}} label="Feature flag" />
    )
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    rerender(<Toggle checked={true} onChange={() => {}} label="Feature flag" />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  })

  test('keyboard Space activates the switch', async () => {
    const handleChange = vi.fn()
    render(<Toggle checked={false} onChange={handleChange} label="Wi-Fi clock-in" />)
    const toggle = screen.getByRole('switch')
    toggle.focus()
    expect(toggle).toHaveFocus()
    await userEvent.keyboard(' ')
    expect(handleChange).toHaveBeenCalledWith(true)
  })
})
