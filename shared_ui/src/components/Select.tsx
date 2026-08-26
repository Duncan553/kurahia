import { useId } from 'react'
import type { ComponentPropsWithoutRef } from 'react'

export interface SelectOption {
  value: string
  label: string
}

export interface SelectProps extends ComponentPropsWithoutRef<'select'> {
  error?: boolean
  /**
   * Data-driven options. Use this OR children, not both.
   *
   * This prop was removed in the FormField refactor, but five screens were
   * never migrated and kept passing it — and because an unknown prop on a
   * component is silently dropped, they rendered a select with ZERO options.
   * `/inventory/quick-entry` was unusable: no item could be picked. Nothing
   * caught it because `tsc --noEmit` reads the root tsconfig, which has
   * `"files": []`, so it type-checked nothing at all (`tsc -b` is what the
   * build actually runs).
   */
  options?: SelectOption[]
  /** Optional visible label — same rationale as Input's, see that file. */
  label?: string
}

export function Select({ className = '', error, options, label, id, children, ...props }: SelectProps) {
  const generatedId = useId()
  const selectId = id ?? (label ? generatedId : undefined)

  const field = (
    <div className="relative">
      <select
        id={selectId}
        // The closed box respects our classes fine, but the OPEN dropdown
        // popup is rendered by the OS/browser shell, not our CSS — it was
        // falling back to the platform default (white panel), which the
        // page's own light text color then rendered against unreadably.
        // color-scheme: dark tells the browser to draw native form widgets,
        // including this popup, with its own dark-mode palette instead.
        style={{ colorScheme: 'dark' }}
        className={[
          'w-full px-4 py-3.5 min-h-[52px] rounded-xl appearance-none',
          'bg-white/[0.06] border text-ink-primary',
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
      >
        {options
          ? options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)
          : children}
      </select>
      {/* Dropdown arrow */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-ink-tertiary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
    </div>
  )

  if (!label) return field

  return (
    <div className="space-y-1.5">
      <label htmlFor={selectId} className="block text-sm font-semibold text-ink-secondary">
        {label}
      </label>
      {field}
    </div>
  )
}
