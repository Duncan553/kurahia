import type { ComponentPropsWithoutRef } from 'react'

export interface SelectProps extends ComponentPropsWithoutRef<'select'> {
  error?: boolean
}

export function Select({ className = '', error, children, ...props }: SelectProps) {
  return (
    <div className="relative">
      <select
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
        {children}
      </select>
      {/* Dropdown arrow */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-ink-tertiary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
    </div>
  )
}
