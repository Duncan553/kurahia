import { render, screen } from '@testing-library/react'
import { FormField } from '../components/FormField'
import { Input } from '../components/Input'

/**
 * New 2026-08-26. FormField had ZERO tests despite owning all label/error
 * wiring for every form in all 3 PWAs.
 */
describe('FormField', () => {
  test('renders the label and links it to the child control', () => {
    render(
      <FormField label="Username" htmlFor="username">
        <Input id="username" />
      </FormField>
    )
    expect(screen.getByLabelText('Username').tagName).toBe('INPUT')
  })

  test('required shows an asterisk', () => {
    render(
      <FormField label="Phone" htmlFor="phone" required>
        <Input id="phone" />
      </FormField>
    )
    expect(screen.getByText('*')).toBeInTheDocument()
  })

  test('help text renders and is linked to the control', () => {
    render(
      <FormField label="Username" htmlFor="username" help="This is what you'll log in with">
        <Input id="username" />
      </FormField>
    )
    const input = screen.getByLabelText('Username')
    const describedBy = input.getAttribute('aria-describedby')
    expect(document.getElementById(describedBy!)).toHaveTextContent(
      "This is what you'll log in with"
    )
  })

  test('error replaces help text rather than showing both', () => {
    render(
      <FormField label="Phone" htmlFor="phone" help="For shift alerts" error="Phone is required">
        <Input id="phone" />
      </FormField>
    )
    expect(screen.getByText('Phone is required')).toBeInTheDocument()
    // Showing a hint and a rejection at once is noise — the error wins.
    expect(screen.queryByText('For shift alerts')).not.toBeInTheDocument()
  })

  test('error is announced immediately via role="alert"', () => {
    render(
      <FormField label="Phone" htmlFor="phone" error="Phone is required">
        <Input id="phone" />
      </FormField>
    )
    // Without role="alert" the user only discovers the failure if they happen
    // to tab back onto the field.
    expect(screen.getByRole('alert')).toHaveTextContent('Phone is required')
  })

  test('injects the error flag and aria-invalid into the child', () => {
    render(
      <FormField label="Phone" htmlFor="phone" error="Phone is required">
        <Input id="phone" />
      </FormField>
    )
    const input = screen.getByLabelText('Phone')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input.className).toContain('border-status-failed')
  })

  test('clean state sets neither aria-invalid nor aria-describedby', () => {
    render(
      <FormField label="Phone" htmlFor="phone">
        <Input id="phone" />
      </FormField>
    )
    const input = screen.getByLabelText('Phone')
    expect(input).not.toHaveAttribute('aria-invalid')
    expect(input).not.toHaveAttribute('aria-describedby')
  })

  test('a non-element child still renders (clone is skipped safely)', () => {
    // Guard against the cloneElement path throwing on plain text children.
    render(<FormField label="Readonly" htmlFor="ro">just some text</FormField>)
    expect(screen.getByText('just some text')).toBeInTheDocument()
  })

  test('does not inject into a raw DOM child, and logs no React warning', () => {
    // `error` is not a real HTML attribute — cloning it onto a host element
    // would trip React's "unknown prop" console.error.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <FormField label="Notes" htmlFor="notes" error="Required">
        <textarea id="notes" />
      </FormField>
    )
    expect(screen.getByLabelText('Notes')).not.toHaveAttribute('aria-invalid')
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})
