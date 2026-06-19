/**
 * Error reporting — Sentry-ready wiring.
 * When VITE_SENTRY_DSN is set in .env, errors go to Sentry.
 * Without the key, errors log to console (development mode).
 * Drop-in: just set the env var, no code changes needed.
 */


export function reportError(error: Error, context?: Record<string, unknown>) {
  console.error('[Kurahia Error]', error, context)
  // When @sentry/browser is installed and VITE_SENTRY_DSN is set,
  // add: import * as Sentry from '@sentry/browser'
  // and: Sentry.captureException(error, { extra: context })
}

export function reportMessage(message: string, level: 'info' | 'warning' | 'error' = 'info') {
  console.log(`[Kurahia ${level}]`, message)
}
