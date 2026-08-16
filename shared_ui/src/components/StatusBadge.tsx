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

function Check() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg> }
function Clock() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> }
function XCircle() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> }
function Info() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg> }
function Minus() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/></svg> }
function Pause() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> }
function ArrowIn() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg> }
function ArrowOut() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg> }
function UserX() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="17" y1="8" x2="22" y2="13"/><line x1="22" y1="8" x2="17" y2="13"/></svg> }

interface StatusConfig {
 colorClass: string
 icon: ReactNode
 label: string
}

const CONFIG: Record<StatusValue, StatusConfig> = {
 paid: { colorClass: 'bg-status-paid/15 text-status-paid border border-status-paid/25', icon: <Check />, label: 'Paid' },
 active: { colorClass: 'bg-status-paid/15 text-status-paid border border-status-paid/25', icon: <Check />, label: 'Active' },
 confirmed: { colorClass: 'bg-status-paid/15 text-status-paid border border-status-paid/25', icon: <Check />, label: 'Confirmed' },
 'checked-in': { colorClass: 'bg-status-paid/15 text-status-paid border border-status-paid/25', icon: <Check />, label: 'Checked In' },
 pending: { colorClass: 'bg-status-pending/15 text-status-pending border border-status-pending/30', icon: <Clock />, label: 'Pending' },
 held: { colorClass: 'bg-status-pending/15 text-status-pending border border-status-pending/30', icon: <Clock />, label: 'Held' },
 failed: { colorClass: 'bg-status-failed/15 text-status-failed border border-status-failed/25', icon: <XCircle />, label: 'Failed' },
 info: { colorClass: 'bg-status-neutral/15 text-status-neutral border border-status-neutral/25', icon: <Info />, label: 'Info' },
 'checked-out':{ colorClass: 'bg-status-neutral/15 text-status-neutral border border-status-neutral/25', icon: <ArrowOut />, label: 'Checked Out' },
 inactive: { colorClass: 'bg-ink-tertiary/10 text-ink-secondary border border-ink-tertiary/20', icon: <Minus />, label: 'Inactive' },
 cancelled: { colorClass: 'bg-ink-tertiary/10 text-ink-secondary border border-ink-tertiary/20', icon: <UserX />, label: 'Cancelled' },
 'no-show': { colorClass: 'bg-ink-tertiary/10 text-ink-secondary border border-ink-tertiary/20', icon: <UserX />, label: 'No Show' },
}

const SIZE: Record<BadgeSize, string> = {
 sm: 'text-xs gap-1 px-2 py-0.5',
 md: 'text-sm gap-1.5 px-2.5 py-1',
}

const SHAPE: Record<BadgeVariant, string> = {
 default: 'rounded-md',
 pill: 'rounded-full',
}

export function StatusBadge({ status, size = 'md', variant = 'default' }: StatusBadgeProps) {
 const { colorClass, icon, label } = CONFIG[status]
 return (
 <span className={['inline-flex items-center font-medium', SHAPE[variant], SIZE[size], colorClass].join(' ')}>
 {icon}
 {label}
 </span>
 )
}
