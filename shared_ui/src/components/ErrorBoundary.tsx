import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  level?: 'screen' | 'tile'
}

interface State { hasError: boolean; error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    if (this.props.fallback) return this.props.fallback

    if (this.props.level === 'tile') {
      return (
        <div className="p-4 rounded-2xl border border-cream-alt bg-cream-card text-center">
          <p className="text-xs text-ink-tertiary mb-2">Couldn&rsquo;t load this</p>
          <button onClick={() => this.setState({ hasError: false, error: null })}
            className="text-xs font-semibold text-primary-dark hover:underline">
            Retry
          </button>
        </div>
      )
    }

    return (
      <div className="min-h-screen flex items-center justify-center bg-cream-card p-6">
        <div className="max-w-sm w-full text-center space-y-4">
          <div className="w-14 h-14 mx-auto rounded-full bg-cream-alt flex items-center justify-center">
            <span className="text-2xl text-ink-tertiary">!</span>
          </div>
          <h2 className="text-lg font-bold text-ink-primary font-serif">Something went wrong</h2>
          <p className="text-sm text-ink-secondary">
            This screen hit an unexpected error. Your data is safe.
          </p>
          <div className="flex gap-2 justify-center">
            <button onClick={() => window.history.back()}
              className="px-4 py-2.5 rounded-xl border border-cream-alt text-sm font-semibold
                text-ink-secondary hover:bg-cream-alt/40 transition-colors">
              ← Back
            </button>
            <button onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2.5 rounded-xl bg-primary-dark text-cream-card text-sm font-semibold
                hover:bg-primary-dark/90 transition-colors">
              Reload
            </button>
          </div>
        </div>
      </div>
    )
  }
}
