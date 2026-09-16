/**
 * The bug this file exists for.
 *
 * `position: fixed` is fixed to the VIEWPORT only while no ancestor has a
 * transform, filter, perspective or `contain`. Any one of those promotes that
 * ancestor to the containing block, and a fixed overlay silently anchors to it.
 *
 * Both traps are everywhere in this app: `.glass-card` sets
 * `contain: layout paint`, and every framer-motion row keeps a `transform`
 * after animating. So on /events, opening "Staff & stock" put a 594px drawer
 * inside a 285px card — it hung off the TOP of the card and the heading, the
 * lifecycle buttons and half the form were cut off the screen.
 *
 * jsdom does not do layout, so this cannot be asserted in pixels. It asserts
 * the thing that CAUSES the pixels: the overlay must not be a DOM descendant
 * of the card. A portal is the only fix a component can apply on its own — a
 * call site cannot know what its ancestors do.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Drawer } from '../components/Drawer'
import { Modal } from '../components/Modal'

// A card that reproduces BOTH traps at once, exactly as the real app does.
function TrappingCard({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-testid="card"
      style={{ contain: 'layout paint', transform: 'translateY(-1px)' }}
    >
      {children}
    </div>
  )
}

describe('overlays escape a containing-block ancestor', () => {
  it('renders the drawer outside the card that would capture it', async () => {
    render(
      <TrappingCard>
        <Drawer open onClose={vi.fn()} title="Staff & stock">
          <p>Nothing set aside.</p>
        </Drawer>
      </TrappingCard>,
    )

    const card = screen.getByTestId('card')
    const panel = await screen.findByRole('dialog')

    expect(card.contains(panel)).toBe(false)
    expect(document.body.contains(panel)).toBe(true)
  })

  it('renders the modal outside the card too', async () => {
    render(
      <TrappingCard>
        <Modal open onClose={vi.fn()} title="Log an item">
          <p>Description</p>
        </Modal>
      </TrappingCard>,
    )

    const card = screen.getByTestId('card')
    const panel = await screen.findByRole('dialog')

    expect(card.contains(panel)).toBe(false)
    expect(document.body.contains(panel)).toBe(true)
  })
})
