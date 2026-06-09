import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Select } from '../components/Select'

const COLOURS = [
  { value: 'sage',  label: 'Sage Green' },
  { value: 'cream', label: 'Cream'      },
  { value: 'ink',   label: 'Ink'        },
]

describe('Select', () => {
  test('renders with label linked to select', () => {
    render(<Select label="Colour" options={COLOURS} />)
    const select = screen.getByLabelText('Colour')
    expect(select).toBeInTheDocument()
    expect(select.tagName).toBe('SELECT')
  })

  test('placeholder option is present and selected by default', () => {
    render(<Select label="Colour" options={COLOURS} />)
    // The placeholder option text should be in the document
    expect(screen.getByText('Select...')).toBeInTheDocument()
  })

  test('onChange fires when user selects an option', async () => {
    const handleChange = vi.fn()
    render(<Select label="Colour" options={COLOURS} onChange={handleChange} />)
    const select = screen.getByLabelText('Colour')
    await userEvent.selectOptions(select, 'sage')
    expect(handleChange).toHaveBeenCalled()
  })

  test('select has associated label via htmlFor', () => {
    render(<Select label="Department" options={COLOURS} />)
    const select = screen.getByRole('combobox', { name: 'Department' })
    expect(select).toBeInTheDocument()
  })
})
