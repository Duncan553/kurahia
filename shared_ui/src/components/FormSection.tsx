import type { ReactNode } from 'react'

export interface FormSectionProps {
  title: string
  description?: string
  children: ReactNode
}

export function FormSection({ title, description, children }: FormSectionProps) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-bold text-ink-primary">{title}</h3>
        {description && <p className="text-sm text-ink-tertiary mt-0.5">{description}</p>}
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  )
}
