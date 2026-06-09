import { render, screen, fireEvent } from '@testing-library/react'
import { Drawer } from '../components/Drawer'

function BottomWrapper({ open = true, onClose = vi.fn() }) {
  return (
    <Drawer open={open} onClose={onClose} title="Bottom Drawer" side="bottom">
      <p>Drawer content</p>
    </Drawer>
  )
}

function RightWrapper({ open = true, onClose = vi.fn() }) {
  return (
    <Drawer open={open} onClose={onClose} title="Right Drawer" side="right">
      <p>Right content</p>
    </Drawer>
  )
}

describe('Drawer', () => {
  test('bottom drawer renders with role=dialog when open', () => {
    render(<BottomWrapper />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Drawer content')).toBeInTheDocument()
  })

  test('bottom drawer does not render when closed', () => {
    render(<BottomWrapper open={false} />)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  test('right drawer renders title and content', () => {
    render(<RightWrapper />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Right Drawer')).toBeInTheDocument()
    expect(screen.getByText('Right content')).toBeInTheDocument()
  })

  test('Escape key calls onClose on bottom drawer', () => {
    const onClose = vi.fn()
    render(<BottomWrapper onClose={onClose} />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
