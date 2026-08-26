/**
 * Calendar dates for the resort's own timezone.
 *
 * Never build a business date with `new Date().toISOString().slice(0, 10)`.
 * `toISOString()` is UTC, but a "day" or a "month" here means the resort's
 * local calendar — and Kenya is UTC+3, so the two disagree every night between
 * 00:00 and 03:00 EAT, and on the 1st of the month they disagree about the
 * MONTH.
 *
 * That is not hypothetical. owner_pwa's finance period picker did:
 *
 *     new Date(now.getFullYear(), now.getMonth() - i, 1).toISOString().slice(0, 7)
 *
 * `new Date(y, m, 1)` is LOCAL midnight; converting it to UTC rolls it back
 * three hours into the previous month. On 2026-08-26 in Africa/Nairobi the
 * dropdown offered 2026-07, 2026-06, 2026-05 — the owner could not select the
 * current month at all, and Profit & Loss silently defaulted to last month.
 *
 * Intl.DateTimeFormat with an explicit timeZone is the only reliable way to ask
 * "what is today's date *there*", and 'en-CA' formats as YYYY-MM-DD.
 */

/** The resort's timezone. Matches the backend's business_day_timezone setting. */
export const RESORT_TZ = 'Africa/Nairobi'

/** Today at the resort, as `YYYY-MM-DD`. */
export function resortToday(d: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: RESORT_TZ }).format(d)
}

/** The current month at the resort, as `YYYY-MM`. */
export function resortMonth(d: Date = new Date()): string {
  return resortToday(d).slice(0, 7)
}

/** A date `days` from now at the resort, as `YYYY-MM-DD`. */
export function resortDatePlus(days: number, from: Date = new Date()): string {
  return resortToday(new Date(from.getTime() + days * 86_400_000))
}

/**
 * The last `count` months at the resort, newest first, as `YYYY-MM`.
 * Month arithmetic is done on the resort's own year/month, never on a UTC
 * instant, so the current month is always the first entry.
 */
export function resortRecentMonths(count: number, from: Date = new Date()): string[] {
  const [y, m] = resortMonth(from).split('-').map(Number)
  return Array.from({ length: count }, (_, i) => {
    // Date handles the year rollover when m - 1 - i goes negative.
    const d = new Date(Date.UTC(y, m - 1 - i, 1))
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
  })
}
