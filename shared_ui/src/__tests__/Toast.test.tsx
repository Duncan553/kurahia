import { render, screen, act } from '@testing-library/react'
import { ToastContainer } from '../components/Toast'
import { useToastStore } from '../stores/toastStore'

beforeEach(() => {
  // Reset store between tests
  useToastStore.setState({ toasts: [] })
})

describe('Toast', () => {
  test('renders a success toast with role=status', () => {
    render(<ToastContainer />)
    act(() => {
      useToastStore.getState().addToast({ type: 'success', message: 'Saved!' })
    })
    expect(screen.getAllByText('Saved!').length).toBeGreaterThan(0)
    // success toasts use role=status
    const statuses = screen.getAllByRole('status')
    expect(statuses.length).toBeGreaterThan(0)
  })

  test('renders an error toast with role=alert', () => {
    render(<ToastContainer />)
    act(() => {
      useToastStore.getState().addToast({ type: 'error', message: 'Something failed' })
    })
    const alerts = screen.getAllByRole('alert')
    expect(alerts.length).toBeGreaterThan(0)
  })

  test('auto-dismisses success toast after 3000ms', () => {
    vi.useFakeTimers()
    render(<ToastContainer />)
    act(() => {
      useToastStore.getState().addToast({ type: 'success', message: 'Auto-dismiss me' })
    })
    expect(useToastStore.getState().toasts).toHaveLength(1)
    act(() => { vi.advanceTimersByTime(3001) })
    expect(useToastStore.getState().toasts).toHaveLength(0)
    vi.useRealTimers()
  })

  test('auto-dismisses error toast after 5000ms (not 3000ms)', () => {
    vi.useFakeTimers()
    render(<ToastContainer />)
    act(() => {
      useToastStore.getState().addToast({ type: 'error', message: 'Error stays longer' })
    })
    act(() => { vi.advanceTimersByTime(3001) })
    // Still present at 3s
    expect(useToastStore.getState().toasts).toHaveLength(1)
    act(() => { vi.advanceTimersByTime(2001) })
    // Gone after 5s
    expect(useToastStore.getState().toasts).toHaveLength(0)
    vi.useRealTimers()
  })
})
