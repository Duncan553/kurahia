import type { ReactNode } from 'react'

export interface FormFieldProps {
  label: string
  htmlFor: string
  error?: string
  help?: string
  children: ReactNode
  required?: boolean
}

export function FormField({ label, htmlFor, error, help, children, required }: FormFieldProps) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={htmlFor}
        className="block text-sm font-semibold text-ink-secondary"
      >
        {label}
        {required && <span className="text-status-failed ml-1">*</span>}
      </label>
      {children}
      {error && (
        <p className="text-xs text-status-failed font-medium">{error}</p>
      )}
      {help && !error && (
        <p className="text-xs text-ink-tertiary">{help}</p>
      )}
    </div>
  )
}
