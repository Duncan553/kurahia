import { render, screen, fireEvent } from '@testing-library/react'
import { Modal } from '../components/Modal'

function Wrapper({ open = true, preventClose = false, onClose = vi.fn() }) {
  return (
    <Modal open={open} onClose={onClose} title="Test Modal" preventClose={preventClose}>
      <button>Inside button</button>
      <button>Second button</button>
    </Modal>
  )
}

describe('Modal', () => {
  test('renders with role=dialog and aria-modal when open', () => {
    render(<Wrapper />)
    const dialogs = screen.getAllByRole('dialog')
    expect(dialogs.length).toBeGreaterThan(0)
    expect(dialogs[0]).toHaveAttribute('aria-modal', 'true')
  })

  test('does not render dialog when closed', () => {
    render(<Wrapper open={false} />)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  test('Escape key calls onClose', () => {
    const onClose = vi.fn()
    render(<Wrapper onClose={onClose} />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('Escape does NOT call onClose when preventClose=true', () => {
    const onClose = vi.fn()
    render(<Wrapper onClose={onClose} preventClose />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
  })
})
