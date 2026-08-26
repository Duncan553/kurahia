import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Input } from '../components/Input'
import { FormField } from '../components/FormField'

/**
 * These tests were rewritten 2026-08-26.
 *
 * The old ones rendered `<Input label="..." error="some message" />`, an API
 * that no longer exists: labelling and error TEXT moved out to FormField, and
 * Input's `error` became a boolean styling flag. Input is now a bare styled box.
 * A character-count test was also dropped — that feature was removed from the
 * component in the same refactor and is not coming back.
 */
describe('Input', () => {
  test('is a bare input — no label of its own', () => {
    render(<Input placeholder="e.g. mwangi_kitchen" />)
    const input = screen.getByPlaceholderText('e.g. mwangi_kitchen')
    expect(input.tagName).toBe('INPUT')
  })

  test('error={true} applies the failed-state border', () => {
    render(<Input error placeholder="Phone" />)
    expect(screen.getByPlaceholderText('Phone').className).toContain('border-status-failed')
  })

  test('error={false} keeps the neutral border', () => {
    render(<Input placeholder="Phone" />)
    const cls = screen.getByPlaceholderText('Phone').className
    expect(cls).toContain('border-white/15')
    expect(cls).not.toContain('border-status-failed')
  })

  test('forwards native input props through to the element', async () => {
    render(<Input type="password" maxLength={4} placeholder="PIN" />)
    const input = screen.getByPlaceholderText('PIN')
    expect(input).toHaveAttribute('type', 'password')
    // maxLength is really enforced, not just rendered as an attribute
    await userEvent.type(input, '123456')
    expect(input).toHaveValue('1234')
  })

  // ── Integration: how Input is ACTUALLY used everywhere in the app ──
  describe('inside FormField', () => {
    test('label is linked to the input via htmlFor/id', () => {
      render(
        <FormField label="Email address" htmlFor="email">
          <Input id="email" />
        </FormField>
      )
      expect(screen.getByLabelText('Email address').tagName).toBe('INPUT')
    })

    test('an error marks the input invalid and links the message to it', () => {
      render(
        <FormField label="Password" htmlFor="pw" error="Must be at least 8 characters">
          <Input id="pw" />
        </FormField>
      )
      const input = screen.getByLabelText('Password')
      expect(input).toHaveAttribute('aria-invalid', 'true')

      // The message must be programmatically linked, not just visually nearby —
      // otherwise a screen reader never tells the user why the field was rejected.
      const describedBy = input.getAttribute('aria-describedby')
      expect(describedBy).toBeTruthy()
      expect(document.getElementById(describedBy!)).toHaveTextContent(
        'Must be at least 8 characters'
      )
    })

    test('FormField pushes the error flag down so the box turns red too', () => {
      render(
        <FormField label="Phone" htmlFor="phone" error="Required">
          <Input id="phone" />
        </FormField>
      )
      // Regression guard: no call site passes `error` to Input by hand, so if
      // FormField stops injecting it the red border silently disappears again.
      expect(screen.getByLabelText('Phone').className).toContain('border-status-failed')
    })

    test('with no error the input is not marked invalid', () => {
      render(
        <FormField label="Full Name" htmlFor="name">
          <Input id="name" />
        </FormField>
      )
      expect(screen.getByLabelText('Full Name')).not.toHaveAttribute('aria-invalid')
    })
  })
})
