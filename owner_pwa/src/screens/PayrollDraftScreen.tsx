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
  gross_pay: string | null
  meal_deduction: string
  deductions: string
  net_pay: string | null
}

interface PayrollData {
  period: string
  period_start: string
  period_end: string
  employees: PayrollEmployee[]
}

// ── Helpers ────────────────────────────────────────────────────────────────────

// Current month as YYYY-MM in Africa/Nairobi timezone
const _now = new Date()
const CURRENT_PERIOD = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, '0')}`

const kes = (n: number) =>
  `KSh ${n.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function downloadCSV(data: PayrollData) {
  const header = ['Name', 'Wage Period', 'Rate (KSh)', 'Hours Worked', 'Gross Pay (KSh)', 'Meal Deduction (KSh)', 'Net Pay (KSh)']
  const rows = data.employees.map(e => [
    e.employee_name,
    e.wage_period ?? '—',
    e.wage_rate ?? '—',
    e.hours_worked,
    e.gross_pay ?? '—',
    e.meal_deduction,
    e.net_pay ?? '—',
  ])
  const csv = [header, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })),
    download: `payroll_${data.period}.csv`,
  })
  a.click()
  URL.revokeObjectURL(a.href)
}

const PERIOD_BADGE: Record<string, string> = {
  HOURLY:  'bg-sky-100 text-sky-700',
  DAILY:   'bg-primary-main/10 text-[#fa5c29]',
  MONTHLY: 'bg-teal-100 text-teal-700',
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function PayrollDraftScreen() {
  const { data, isLoading, isError } = useQuery<PayrollData>({
    queryKey: ['payroll', CURRENT_PERIOD],
    queryFn: () =>
      api.get<PayrollData>(`/finance/payroll?period=${CURRENT_PERIOD}`)
        .then(r => r.data),
    staleTime: 5 * 60_000,
  })

  // Totals derived from backend-calculated values
  const totalGross = data?.employees.reduce((sum, e) =>
    e.gross_pay != null ? sum + parseFloat(e.gross_pay) : sum, 0) ?? 0

  const totalDeductions = data?.employees.reduce((sum, e) =>
    sum + parseFloat(e.deductions || '0'), 0) ?? 0

  const totalNet = data?.employees.reduce((sum, e) =>
    e.net_pay != null ? sum + parseFloat(e.net_pay) : sum, 0) ?? 0

  return (
    <div className="p-4 max-w-3xl mx-auto space-y-4">

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold text-ink-primary font-serif">Payroll Draft</h1>
          {data && (
            <p className="text-xs text-ink-tertiary mt-0.5">
              {data.period_start} &rarr; {data.period_end}
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
              const gross = e.gross_pay != null ? parseFloat(e.gross_pay) : null
              const meals = parseFloat(e.meal_deduction || '0')
              const net   = e.net_pay != null ? parseFloat(e.net_pay) : null
              return (
                <div key={e.employee_id}
                  className="flex items-center justify-between gap-4 px-4 py-3
                    rounded-2xl border border-white/10">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-ink-primary truncate">{e.employee_name}</p>
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
                    {/* Staff meal deduction line (only if > 0) */}
                    {meals > 0 && (
                      <p className="text-[10px] text-amber-400 mt-1">
                        Meals: &minus;{kes(meals)}
                      </p>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-xs text-ink-tertiary tabular-nums">{e.hours_worked}h worked</p>
                    {gross != null ? (
                      <>
                        <p className="text-xs text-ink-tertiary tabular-nums mt-0.5">
                          Gross: {kes(gross)}
                        </p>
                        <p className="text-sm font-bold text-ink-primary tabular-nums mt-0.5">
                          {kes(net ?? gross)}
                        </p>
                      </>
                    ) : (
                      <p className="text-xs text-ink-tertiary mt-0.5">No wage set</p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Summary footer */}
          <div className="space-y-2">
            <div className="flex items-center justify-between px-4 py-2 rounded-xl
              bg-white/5 text-ink-secondary text-xs">
              <span>Total gross</span>
              <span className="tabular-nums">{kes(totalGross)}</span>
            </div>
            {totalDeductions > 0 && (
              <div className="flex items-center justify-between px-4 py-2 rounded-xl
                bg-white/5 text-amber-400 text-xs">
                <span>Total deductions (meals)</span>
                <span className="tabular-nums">&minus;{kes(totalDeductions)}</span>
              </div>
            )}
            <div className="flex items-center justify-between px-4 py-3 rounded-2xl
              bg-ink-primary text-cream-card">
              <p className="text-sm font-semibold">Total net payroll</p>
              <p className="text-base font-bold tabular-nums">{kes(totalNet)}</p>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
