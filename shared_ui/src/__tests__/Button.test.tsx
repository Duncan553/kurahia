import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Button } from '../components/Button'

describe('Button', () => {
  test('renders with correct label text', () => {
    render(<Button>Save changes</Button>)
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument()
  })

  test('disabled state prevents click and marks aria-disabled', async () => {
    const handleClick = vi.fn()
    render(<Button disabled onClick={handleClick}>Submit</Button>)
    const btn = screen.getByRole('button')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('aria-disabled', 'true')
    await userEvent.click(btn)
    expect(handleClick).not.toHaveBeenCalled()
  })

  test('loading state disables button and sets aria-busy', () => {
    render(<Button loading>Save</Button>)
    const btn = screen.getByRole('button')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('aria-busy', 'true')
    expect(btn).toHaveAttribute('aria-disabled', 'true')
  })

  test('keyboard: Enter activates button', async () => {
    const handleClick = vi.fn()
    render(<Button onClick={handleClick}>Confirm</Button>)
    const btn = screen.getByRole('button')
    btn.focus()
    expect(btn).toHaveFocus()
    await userEvent.keyboard('{Enter}')
    expect(handleClick).toHaveBeenCalledOnce()
  })
})
