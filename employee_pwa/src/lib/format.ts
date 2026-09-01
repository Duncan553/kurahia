const NBI = 'Africa/Nairobi'

// "14:35" — 24h Nairobi time
export function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('en-KE', {
    timeZone: NBI, hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(iso))
}

// "9 Jun 2025, 14:35"
export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat('en-KE', {
    timeZone: NBI, day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(iso))
}

// Today's date key in Nairobi tz
export function todayKey(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: NBI }).format(new Date())
}

// "2h 34m" or "45m" — duty timer display
export function dutyTime(totalMinutes: number): string {
  const h = Math.floor(totalMinutes / 60)
  const m = totalMinutes % 60
  if (h === 0) return `${m}m`
  return m === 0 ? `${h}h` : `${h}h ${m}m`
}

// "3 min ago", "2h ago", "1d ago"
export function timeAgo(iso: string): string {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}
