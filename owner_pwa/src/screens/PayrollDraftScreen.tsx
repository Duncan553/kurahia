import { useQuery } from '@tanstack/react-query'
import { Skeleton, EmptyState, Button } from '@shared'
import api from '../lib/axios'

// ── Types ──────────────────────────────────────────────────────────────────────

interface PayrollEmployee {
  employee_id: string
  employee_name: string
  wage_rate: string | null
  wage_period: string | null
  hours_worked: string
}

interface PayrollData {
  period_start: string
  period_end: string
  employees: PayrollEmployee[]
}

// ── Helpers ────────────────────────────────────────────────────────────────────

// Current-month bounds in Africa/Nairobi timezone
const _tz = 'Africa/Nairobi'
const _fmt = (d: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: _tz }).format(d)
const _now = new Date()
const MONTH_START = _fmt(new Date(_now.getFullYear(), _now.getMonth(), 1))
const MONTH_END   = _fmt(new Date(_now.getFullYear(), _now.getMonth() + 1, 0))

const kes = (n: number) =>
  `KSh ${n.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function computeGross(e: PayrollEmployee): number | null {
  if (!e.wage_rate || !e.wage_period) return null
  const rate  = parseFloat(e.wage_rate)
  const hours = parseFloat(e.hours_worked)
  if (isNaN(rate) || isNaN(hours)) return null
  if (e.wage_period === 'HOURLY')  return hours * rate
  if (e.wage_period === 'DAILY')   return (hours / 8) * rate
  if (e.wage_period === 'MONTHLY') return rate
  return null
}

function downloadCSV(data: PayrollData) {
  const header = ['Name', 'Wage Period', 'Rate (KSh)', 'Hours Worked', 'Gross Pay (KSh)']
  const rows = data.employees.map(e => {
    const g = computeGross(e)
    return [
      e.employee_name,
      e.wage_period ?? '—',
      e.wage_rate ?? '—',
      e.hours_worked,
      g != null ? g.toFixed(2) : '—',
    ]
  })
  const csv = [header, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })),
    download: `payroll_${data.period_start}_${data.period_end}.csv`,
  })
  a.click()
  URL.revokeObjectURL(a.href)
}

const PERIOD_BADGE: Record<string, string> = {
  HOURLY:  'bg-sky-100 text-sky-700',
  DAILY:   'bg-violet-100 text-violet-700',
  MONTHLY: 'bg-teal-100 text-teal-700',
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function PayrollDraftScreen() {
  const { data, isLoading, isError } = useQuery<PayrollData>({
    queryKey: ['payroll-draft', MONTH_START, MONTH_END],
    queryFn: () =>
      api.get<PayrollData>(`/hr/payroll-draft?start_date=${MONTH_START}&end_date=${MONTH_END}`)
        .then(r => r.data),
    staleTime: 5 * 60_000,
  })

  const totalGross = data?.employees.reduce((sum, e) => {
    const g = computeGross(e)
    return g != null ? sum + g : sum
  }, 0) ?? 0

  return (
    <div className="p-4 max-w-3xl mx-auto space-y-4">

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold text-white font-serif">Payroll Draft</h1>
          {data && (
            <p className="text-xs text-ink-tertiary mt-0.5">
              {data.period_start} → {data.period_end}
            </p>
          )}
        </div>
        {data && data.employees.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => downloadCSV(data)}>
            Export CSV
          </Button>
        )}
      </div>

      {/* States */}
      {isLoading && (
        <div className="space-y-3">
          {[1,2,3,4].map(i => <Skeleton key={i} variant="row" />)}
        </div>
      )}

      {isError && (
        <p className="text-sm text-status-failed text-center py-8">
          Failed to load payroll data.
        </p>
      )}

      {!isLoading && !isError && data?.employees.length === 0 && (
        <EmptyState
          icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <circle cx="20" cy="15" r="7" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M7 34c0-7.2 5.8-13 13-13s13 5.8 13 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>}
          title="No active employees with profiles yet."
        />
      )}

      {/* Employee cards */}
      {!isLoading && !isError && data && data.employees.length > 0 && (
        <>
          <div className="space-y-2">
            {data.employees.map(e => {
              const gross = computeGross(e)
              return (
                <div key={e.employee_id}
                  className="flex items-center justify-between gap-4 px-4 py-3
                    rounded-2xl border border-white/10">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-white truncate">{e.employee_name}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {e.wage_period && (
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${PERIOD_BADGE[e.wage_period] ?? 'bg-white/5 text-ink-tertiary'}`}>
                          {e.wage_period}
                        </span>
                      )}
                      {e.wage_rate && (
                        <span className="text-xs text-ink-tertiary tabular-nums">
                          {kes(parseFloat(e.wage_rate))} / {e.wage_period?.toLowerCase() ?? 'unit'}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-xs text-ink-tertiary tabular-nums">{e.hours_worked}h worked</p>
                    {gross != null ? (
                      <p className="text-sm font-bold text-white tabular-nums mt-0.5">{kes(gross)}</p>
                    ) : (
                      <p className="text-xs text-ink-tertiary mt-0.5">No wage set</p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Summary footer */}
          <div className="flex items-center justify-between px-4 py-3 rounded-2xl
            bg-ink-primary text-white">
            <p className="text-sm font-semibold">Total gross payroll</p>
            <p className="text-base font-bold tabular-nums">{kes(totalGross)}</p>
          </div>
        </>
      )}
    </div>
  )
}
