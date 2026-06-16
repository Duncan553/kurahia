import type { ReactNode } from 'react'

export type StatusValue =
  | 'paid' | 'pending' | 'failed' | 'info'
  | 'active' | 'inactive' | 'held'
  | 'confirmed' | 'checked-in' | 'checked-out'
  | 'cancelled' | 'no-show'

export type BadgeSize = 'sm' | 'md'
export type BadgeVariant = 'default' | 'pill'

export interface StatusBadgeProps {
  status: StatusValue
  size?: BadgeSize
  variant?: BadgeVariant
}

// Icons — all 16×16, aria-hidden
function Check() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
    <path d="M3.5 6l1.8 1.8L8.5 4.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function Clock() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
    <path d="M6 3.5V6l1.5 1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
}
function XCircle() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
    <path d="M4.5 4.5l3 3M7.5 4.5l-3 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
}
function Info() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
    <path d="M6 5.5V8.5M6 3.5h.01" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
}
function Minus() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
    <path d="M4 6h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
}
function Pause() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
    <path d="M4.5 4v4M7.5 4v4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
}
function ArrowIn() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
    <path d="M4 6h4M6.5 4.5L8 6l-1.5 1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function ArrowOut() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
    <path d="M8 6H4M5.5 4.5L4 6l1.5 1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function UserX() {
  return <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <path d="M1.5 10c0-1.7 1.3-3 3-3h1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    <circle cx="5" cy="4" r="2" stroke="currentColor" strokeWidth="1.2" />
    <path d="M8.5 7.5l2 2M10.5 7.5l-2 2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
}

interface StatusConfig {
  colorClass: string
  icon: ReactNode
  label: string
}

const CONFIG: Record<StatusValue, StatusConfig> = {
  paid:         { colorClass: 'bg-status-paid/15 text-status-paid border border-status-paid/25',       icon: <Check />,    label: 'Paid'        },
  active:       { colorClass: 'bg-status-paid/15 text-status-paid border border-status-paid/25',       icon: <Check />,    label: 'Active'      },
  confirmed:    { colorClass: 'bg-status-paid/15 text-status-paid border border-status-paid/25',       icon: <Check />,    label: 'Confirmed'   },
  'checked-in': { colorClass: 'bg-status-paid/15 text-status-paid border border-status-paid/25',       icon: <ArrowIn />,  label: 'Checked In'  },
  pending:      { colorClass: 'bg-transparent text-status-pending border border-status-pending/50',    icon: <Clock />,    label: 'Pending'     },
  held:         { colorClass: 'bg-transparent text-status-pending border border-status-pending/50',    icon: <Pause />,    label: 'Held'        },
  failed:       { colorClass: 'bg-status-failed/15 text-status-failed border border-status-failed/25', icon: <XCircle />,  label: 'Failed'      },
  info:         { colorClass: 'bg-status-neutral/15 text-status-neutral border border-status-neutral/25', icon: <Info />,  label: 'Info'        },
  'checked-out':{ colorClass: 'bg-status-neutral/15 text-status-neutral border border-status-neutral/25', icon: <ArrowOut />, label: 'Checked Out' },
  inactive:     { colorClass: 'bg-ink-tertiary/10 text-ink-secondary border border-ink-tertiary/20',   icon: <Minus />,    label: 'Inactive'    },
  cancelled:    { colorClass: 'bg-ink-tertiary/10 text-ink-secondary border border-ink-tertiary/20',   icon: <XCircle />,  label: 'Cancelled'   },
  'no-show':    { colorClass: 'bg-ink-tertiary/10 text-ink-secondary border border-ink-tertiary/20',   icon: <UserX />,    label: 'No Show'     },
}

const SIZE: Record<BadgeSize, string> = {
  sm: 'text-xs gap-1 px-2 py-0.5',
  md: 'text-sm gap-1.5 px-2.5 py-1',
}

const SHAPE: Record<BadgeVariant, string> = {
  default: 'rounded-md',
  pill:    'rounded-full',
}

export function StatusBadge({ status, size = 'md', variant = 'default' }: StatusBadgeProps) {
  const { colorClass, icon, label } = CONFIG[status]
  return (
    <span className={[
      'inline-flex items-center font-medium whitespace-nowrap',
      colorClass, SIZE[size], SHAPE[variant],
    ].join(' ')}>
      {icon}
      {label}
    </span>
  )
}
