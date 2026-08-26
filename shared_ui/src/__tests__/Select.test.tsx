import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Select } from '../components/Select'
import { FormField } from '../components/FormField'

/**
 * Rewritten 2026-08-26, same reason as Input.test.tsx.
 *
 * The old tests passed `label="Colour"` and an `options={[...]}` array. Neither
 * prop exists: Select takes plain <option> children, and labelling lives in
 * FormField. The old suite also asserted a 'Select...' placeholder option the
 * component never renders — the caller supplies that as a child if they want it.
 */
const COLOURS = [
  { value: 'sage',  label: 'Sage Green' },
  { value: 'cream', label: 'Cream'      },
  { value: 'ink',   label: 'Ink'        },
]

// How every call site actually builds one.
function ColourSelect(props: React.ComponentProps<typeof Select>) {
  return (
    <Select {...props}>
      <option value="">Select...</option>
      {COLOURS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
    </Select>
  )
}

describe('Select', () => {
  test('renders the option children it is given', () => {
    render(<ColourSelect aria-label="Colour" />)
    expect(screen.getByRole('combobox', { name: 'Colour' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Sage Green' })).toBeInTheDocument()
  })

  test('onChange fires when the user picks an option', async () => {
    const handleChange = vi.fn()
    render(<ColourSelect aria-label="Colour" onChange={handleChange} />)
    await userEvent.selectOptions(screen.getByRole('combobox'), 'sage')
    expect(handleChange).toHaveBeenCalled()
  })

  test('error={true} applies the failed-state border', () => {
    render(<ColourSelect aria-label="Colour" error />)
    expect(screen.getByRole('combobox').className).toContain('border-status-failed')
  })

  test('inside FormField the label is linked to the select', () => {
    render(
      <FormField label="Department" htmlFor="dept">
        <ColourSelect id="dept" />
      </FormField>
    )
    expect(screen.getByRole('combobox', { name: 'Department' })).toBeInTheDocument()
  })

  test('inside FormField an error marks the select invalid and links the message', () => {
    render(
      <FormField label="Department" htmlFor="dept" error="Pick a department">
        <ColourSelect id="dept" />
      </FormField>
    )
    const select = screen.getByRole('combobox', { name: 'Department' })
    expect(select).toHaveAttribute('aria-invalid', 'true')
    const describedBy = select.getAttribute('aria-describedby')
    expect(document.getElementById(describedBy!)).toHaveTextContent('Pick a department')
  })
})
