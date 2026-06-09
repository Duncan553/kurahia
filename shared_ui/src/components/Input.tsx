import { useId, useState } from 'react'
import type { ComponentPropsWithoutRef, ReactNode, ChangeEvent } from 'react'

export interface InputProps extends Omit<ComponentPropsWithoutRef<'input'>, 'type'> {
  label: string
  type?: 'text' | 'number' | 'password' | 'search' | 'tel'
  error?: string
  leftIcon?: ReactNode
  rightIcon?: ReactNode
}

export function Input({
  label,
  type = 'text',
  error,
  leftIcon,
  rightIcon,
  maxLength,
  id,
  disabled = false,
  onChange,
  ...rest
}: InputProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const errorId = `${inputId}-err`

  // Track char count via onChange so it works for both controlled and uncontrolled
  const [charCount, setCharCount] = useState(0)

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    setCharCount(e.target.value.length)
    onChange?.(e)
  }

  const nearLimit = maxLength !== undefined && charCount / maxLength > 0.9
  const hasAriaDesc = error !== undefined || maxLength !== undefined

  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={inputId}
        className="text-sm font-medium text-ink-primary"
      >
        {label}
      </label>

      <div className="relative">
        {leftIcon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-tertiary pointer-events-none">
            {leftIcon}
          </span>
        )}

        <input
          id={inputId}
          type={type}
          maxLength={maxLength}
          disabled={disabled}
          aria-invalid={error !== undefined ? true : undefined}
          aria-describedby={hasAriaDesc ? errorId : undefined}
          onChange={handleChange}
          className={[
            'w-full rounded border bg-cream-card text-ink-primary text-base',
            'px-3 py-2 min-h-[44px]',
            'focus:outline-none focus:border-sage-dark focus:ring-0',
            'placeholder:text-ink-tertiary',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            error ? 'border-status-failed' : 'border-ink-tertiary',
            leftIcon  ? 'pl-10' : '',
            rightIcon ? 'pr-10' : '',
          ].join(' ')}
          {...rest}
        />

        {rightIcon && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-tertiary pointer-events-none">
            {rightIcon}
          </span>
        )}
      </div>

      {/* Error and char count share the same describedby ID region */}
      {(error !== undefined || maxLength !== undefined) && (
        <div id={errorId} className="flex justify-between items-start gap-2">
          {error !== undefined ? (
            <p className="text-sm text-status-failed">{error}</p>
          ) : (
            <span />
          )}
          {maxLength !== undefined && (
            <p className={['text-sm tabular-nums', nearLimit ? 'text-status-failed' : 'text-ink-tertiary'].join(' ')}>
              {charCount}/{maxLength}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
