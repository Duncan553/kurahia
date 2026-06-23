import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { RequireRole } from '../components/AuthGate'
import { ErrorBoundary } from '@shared'
import api from '../lib/axios'

interface InvItem {
  id: string; name: string; unit: string; current_stock: string
  reorder_level: string; below_reorder: boolean
}

/* Reusable glass panel */
function Glass({ children, className = '' }: {
  children: React.ReactNode; className?: string
}) {
  return (
    <div className={`glass-card overflow-hidden ${className}`}>
      <div className="relative">
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
        {children}
      </div>
    </div>
  )
}

/* Section heading label */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-sm font-bold tracking-widest uppercase text-[#aa8980] mb-3">{children}</h2>
  )
}

/* Animation variants */
const fadeIn = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0 } }
const stagger = { visible: { transition: { staggerChildren: 0.08 } } }

/* Day labels for calendar row */
const WEEKDAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

export default function HeadChefScreen() {
  const navigate = useNavigate()

  /* ── Existing query — inventory items ─────────────────────────────── */
  const { data: items = [] } = useQuery<InvItem[]>({
    queryKey: ['chef-stock'],
    queryFn: () => api.get<InvItem[]>('/inventory/items').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 30_000, refetchInterval: 60_000,
  })

  const low = items.filter(i => i.below_reorder)

  /* Placeholder station throughput data (no backend endpoint yet) */
  const stations = [
    { name: 'Saute', pct: 72 },
    { name: 'Grill', pct: 85 },
    { name: 'Garde Manger', pct: 55 },
    { name: 'Pastry', pct: 40 },
    { name: 'Expo', pct: 90 },
    { name: 'Prep', pct: 65 },
  ]

  /* Dates for the delivery calendar row (current week starting Monday) */
  const now = new Date()
  const dayOfWeek = now.getDay()
  // JS getDay: 0=Sun. Shift so Monday=0
  const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
  const monday = new Date(now)
  monday.setDate(now.getDate() + mondayOffset)
  const calendarDays = WEEKDAYS.map((label, i) => {
    const d = new Date(monday)
    d.setDate(monday.getDate() + i)
    return { label, date: d.getDate() }
  })

  return (
    <RequireRole minLevel={5}>
      <div className="min-h-screen p-4 md:p-6">
        <motion.div className="max-w-6xl mx-auto"
          initial="hidden" animate="visible" variants={stagger}>

          {/* ── Page header: Service Status + stats ─────────────────── */}
          <motion.div variants={fadeIn} transition={{ duration: 0.3 }}
            className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 mb-6">
            <div>
              <h1 className="font-serif text-3xl md:text-4xl font-bold text-[#f9dcd5] tracking-tight">
                Service Status
              </h1>
              <p className="text-sm text-[#aa8980] mt-1 max-w-md">
                Real-time overview of inventory levels, station pacing, and critical kitchen
                metrics for the evening service.
              </p>
            </div>

            {/* Top-right stat badges */}
            <div className="flex gap-3 shrink-0">
              <div className="glass-card rounded-xl px-4 py-2 text-center">
                <p className="text-[10px] font-bold tracking-widest uppercase text-[#aa8980]">
                  Covers Tonight
                </p>
                <p className="text-xl font-bold tabular-nums text-[#f9dcd5]">
                  {items.length > 0 ? items.length * 4 : '—'}
                </p>
              </div>
              <div className="glass-card rounded-xl px-4 py-2 text-center">
                <p className="text-[10px] font-bold tracking-widest uppercase text-[#aa8980]">
                  Avg Ticket Time
                </p>
                <p className="text-xl font-bold tabular-nums text-[#f9dcd5]">18 min</p>
              </div>
            </div>
          </motion.div>

          {/* ── Row 1: Low Stock Alerts + Station Performance ───────── */}
          <motion.div variants={fadeIn} transition={{ duration: 0.3 }}
            className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-4 mb-6">

            {/* Low Stock Alerts card */}
            <ErrorBoundary level="tile">
              <Glass>
                <div className="p-5">
                  <div className="flex items-center justify-between mb-4">
                    <SectionLabel>Low Stock Alerts</SectionLabel>
                    {low.length > 0 && (
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide
                        bg-[#fa5c29]/20 text-[#fa5c29]">
                        Critical
                      </span>
                    )}
                  </div>

                  {low.length > 0 ? (
                    <div className="space-y-3">
                      {low.slice(0, 4).map(i => (
                        <div key={i.id} className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-sm font-semibold text-[#f9dcd5] truncate">{i.name}</p>
                            <p className="text-[10px] text-[#aa8980]">
                              {i.unit} &middot; Est. Depletion: —
                            </p>
                          </div>
                          <div className="text-right shrink-0">
                            <p className="text-sm font-bold tabular-nums text-[#fa5c29]">
                              {parseFloat(i.current_stock)} {i.unit} left
                            </p>
                            <p className="text-[10px] text-[#aa8980]">Action Req.</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-status-paid/70 py-4">All stock levels healthy</p>
                  )}

                  <button
                    onClick={() => navigate('/inventory/count')}
                    className="mt-4 text-xs font-semibold text-[#fa5c29] hover:text-[#fa5c29]/80
                      transition-colors underline underline-offset-2">
                    View Full Inventory
                  </button>
                </div>
              </Glass>
            </ErrorBoundary>

            {/* Station Performance card */}
            <ErrorBoundary level="tile">
              <Glass>
                <div className="p-5">
                  <div className="flex items-center justify-between mb-4">
                    <SectionLabel>Station Performance</SectionLabel>
                    <div className="flex gap-2">
                      <span className="text-[10px] font-semibold text-[#aa8980]">Heart</span>
                      <span className="text-[10px] font-semibold text-[#f9dcd5]">Service</span>
                    </div>
                  </div>

                  {/* Bar chart */}
                  <div className="flex items-end gap-3 h-32">
                    {stations.map(s => (
                      <div key={s.name} className="flex-1 flex flex-col items-center gap-1">
                        <div className="w-full rounded-t-sm bg-[#aa8980]/30 relative overflow-hidden"
                          style={{ height: `${s.pct}%` }}>
                          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-[#fa5c29] to-[#aa8980]
                            rounded-t-sm" style={{ height: '100%' }} />
                        </div>
                        <span className="text-[9px] text-[#aa8980] leading-tight text-center truncate w-full">
                          {s.name}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </Glass>
            </ErrorBoundary>
          </motion.div>

          {/* ── Row 2: Inventory Delivery Calendar ──────────────────── */}
          <motion.div variants={fadeIn} transition={{ duration: 0.3 }} className="mb-6">
            <Glass>
              <div className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <SectionLabel>Inventory Delivery Calendar</SectionLabel>
                  <button className="text-[10px] font-semibold text-[#aa8980] hover:text-[#f9dcd5] transition-colors">
                    Manage Schedule
                  </button>
                </div>

                {/* Weekly grid */}
                <div className="grid grid-cols-7 gap-2">
                  {calendarDays.map(day => (
                    <div key={day.label} className="text-center">
                      <p className="text-[10px] font-bold tracking-wider uppercase text-[#aa8980] mb-1">
                        {day.label}
                      </p>
                      <div className="rounded-lg border border-white/10 bg-white/5 px-1 py-3 min-h-[48px]
                        flex items-center justify-center">
                        <span className="text-xs tabular-nums text-[#f9dcd5]/60">{day.date}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Glass>
          </motion.div>

          {/* ── Row 3: Active Tickets table ─────────────────────────── */}
          <motion.div variants={fadeIn} transition={{ duration: 0.3 }}>
            <Glass>
              <div className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <SectionLabel>Active Tickets</SectionLabel>
                  <button
                    onClick={() => navigate('/pos/kitchen')}
                    className="text-[10px] font-semibold text-[#fa5c29] hover:text-[#fa5c29]/80 transition-colors">
                    View All &rarr;
                  </button>
                </div>

                {/* Table header */}
                <div className="grid grid-cols-5 gap-2 pb-2 border-b border-white/10 mb-2">
                  {['TICKET #', 'TABLE', 'KEY ITEMS', 'TIME OPEN', 'STATUS'].map(h => (
                    <p key={h} className="text-[10px] font-bold tracking-widest uppercase text-[#aa8980]">
                      {h}
                    </p>
                  ))}
                </div>

                {/* Placeholder rows — will be replaced by live kitchen query */}
                {[
                  { ticket: '#T-8942', table: 'Table 42 (VIP)', items: '2x Wagyu Ribeye, 1x Scallops, 1x Tru...', time: '24:15', status: 'Delayed - Grill', statusColor: 'text-[#fa5c29] bg-[#fa5c29]/10' },
                  { ticket: '#T-8943', table: 'Table 12', items: '4x Tasting Menu (Course 3)', time: '12:38', status: 'Plating', statusColor: 'text-[#aa8980] bg-[#aa8980]/10' },
                  { ticket: '#T-8944', table: 'Bar Seat 4', items: '1x Oysters (Half Dozen), 1x Tuna Tart...', time: '04:18', status: 'Fired', statusColor: 'text-status-paid bg-status-paid/10' },
                ].map(row => (
                  <div key={row.ticket}
                    className="grid grid-cols-5 gap-2 py-3 border-b border-white/5 items-center last:border-0">
                    <p className="text-sm font-semibold tabular-nums text-[#f9dcd5]">{row.ticket}</p>
                    <p className="text-sm text-[#f9dcd5]">{row.table}</p>
                    <p className="text-xs text-[#aa8980] truncate">{row.items}</p>
                    <p className="text-sm font-bold tabular-nums text-[#f9dcd5]">{row.time}</p>
                    <span className={`text-[10px] font-bold px-2 py-1 rounded-md text-center ${row.statusColor}`}>
                      {row.status}
                    </span>
                  </div>
                ))}
              </div>
            </Glass>
          </motion.div>

        </motion.div>
      </div>
    </RequireRole>
  )
}
