import type { ComponentPropsWithoutRef } from 'react'

export interface InputProps extends ComponentPropsWithoutRef<'input'> {
  error?: boolean
}

export function Input({ className = '', error, ...props }: InputProps) {
  return (
    <input
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
}
