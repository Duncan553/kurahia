import { useId } from 'react'
import type { ComponentPropsWithoutRef } from 'react'

export interface InputProps extends ComponentPropsWithoutRef<'input'> {
  error?: boolean
  /**
   * Optional visible label, rendered above the field and wired via htmlFor.
   *
   * Prefer <FormField> when you also need error/help text — it owns that whole
   * block. This prop exists because ~18 call sites across the three apps kept
   * passing `label` after the FormField refactor removed it. React spreads an
   * unknown prop straight onto the DOM node, so those screens rendered
   * `<input label="Item *">` — an invalid attribute, no visible label, and
   * nothing linked for a screen reader. Supporting it here fixes every one of
   * them at once and produces correct markup.
   */
  label?: string
}

export function Input({ className = '', error, label, id, ...props }: InputProps) {
  // Only used when the caller didn't supply an id — the label needs something
  // concrete to point at.
  const generatedId = useId()
  const inputId = id ?? (label ? generatedId : undefined)

  const input = (
    <input
      id={inputId}
      // Same fix as Select.tsx: type="date"/"time"/"datetime-local" all open
      // an OS-rendered popup that ignores page CSS and needs this to render
      // in dark mode instead of the platform's light default.
      style={{ colorScheme: 'dark' }}
      className={[
        'w-full px-4 py-3.5 min-h-[52px] rounded-xl',
        'bg-white/[0.06] border text-ink-primary placeholder:text-ink-tertiary/50',
        'text-base font-medium',
        'transition-all duration-200',
        'focus:outline-none focus:ring-2 focus:ring-primary-main/30 focus:border-primary-main',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        error
          ? 'border-status-failed/50 focus:border-status-failed focus:ring-status-failed/20'
          : 'border-white/15 hover:border-white/25',
        className,
      ].join(' ')}
      {...props}
    />
  )

  if (!label) return input

  return (
    <div className="space-y-1.5">
      <label htmlFor={inputId} className="block text-sm font-semibold text-ink-secondary">
        {label}
      </label>
      {input}
    </div>
  )
}
