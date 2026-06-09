import { useId } from 'react'
import type { ComponentPropsWithoutRef } from 'react'

export interface SelectOption {
  value: string
  label: string
}

export interface SelectProps extends Omit<ComponentPropsWithoutRef<'select'>, 'children'> {
  label: string
  options: SelectOption[]
  placeholder?: string
  error?: string
}

// Chevron icon — inline so Select has no SVG file dependency
function ChevronDown() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M4 6l4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function Select({
  label,
  options,
  placeholder = 'Select...',
  error,
  id,
  disabled = false,
  ...rest
}: SelectProps) {
  const generatedId = useId()
  const selectId = id ?? generatedId
  const errorId = `${selectId}-err`

  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={selectId}
        className="text-sm font-medium text-ink-primary"
      >
        {label}
      </label>

      <div className="relative">
        {/* Native <select> — uses system picker on iOS/Android */}
        <select
          id={selectId}
          disabled={disabled}
          aria-invalid={error !== undefined ? true : undefined}
          aria-describedby={error !== undefined ? errorId : undefined}
          className={[
            'w-full appearance-none rounded border bg-cream-card text-ink-primary text-base',
            'px-3 pr-10 py-2 min-h-[44px]',
            'focus:outline-none focus:border-sage-dark focus:ring-0',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            error ? 'border-status-failed' : 'border-ink-tertiary',
          ].join(' ')}
          {...rest}
        >
          <option value="" disabled>
            {placeholder}
          </option>
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* Custom arrow — pointer-events-none so native select still receives clicks */}
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-tertiary pointer-events-none">
          <ChevronDown />
        </span>
      </div>

      {error !== undefined && (
        <p id={errorId} className="text-sm text-status-failed">
          {error}
        </p>
      )}
    </div>
  )
}
