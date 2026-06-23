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
function Glass({ children, className = '', onClick }: {
  children: React.ReactNode; className?: string; onClick?: () => void
}) {
  return (
    <div className={`glass-card overflow-hidden ${className}`} onClick={onClick} role={onClick ? 'button' : undefined}>
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

export default function HeadChefScreen() {
  const navigate = useNavigate()

  /* ── Existing query — inventory items ─────────────────────────────── */
  const { data: items = [] } = useQuery<InvItem[]>({
    queryKey: ['chef-stock'],
    queryFn: () => api.get<InvItem[]>('/inventory/items').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 30_000, refetchInterval: 60_000,
  })

  // Derived stats
  const low = items.filter(i => i.below_reorder)
  const healthy = items.length - low.length
  const healthPct = items.length > 0 ? Math.round((healthy / items.length) * 100) : 100

  // Current time for header
  const now = new Date()
  const timeStr = now.toLocaleTimeString('en-KE', {
    timeZone: 'Africa/Nairobi', hour: '2-digit', minute: '2-digit', hour12: false,
  })

  return (
    <RequireRole minLevel={5}>
      <div className="min-h-screen p-4 md:p-6">
        <motion.div className="max-w-6xl mx-auto"
          initial="hidden" animate="visible" variants={stagger}>

          {/* ── Page header: Kitchen + Chef name + Service badge ──────── */}
          <motion.div variants={fadeIn} transition={{ duration: 0.3 }}
            className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-6">
            <div>
              <h1 className="font-serif text-3xl md:text-4xl font-bold text-[#f9dcd5] tracking-tight">
                Kitchen
              </h1>
              <p className="text-sm text-[#aa8980] mt-1">Chef Dashboard</p>
            </div>

            {/* Service badge + time */}
            <div className="flex items-center gap-3 shrink-0">
              <span className="px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider
                bg-status-paid/15 text-status-paid border border-status-paid/20">
                Service Active
              </span>
              <span className="text-sm font-mono tabular-nums text-ink-tertiary">{timeStr}</span>
            </div>
          </motion.div>

          {/* ── BENTO GRID ────────────────────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">

            {/* LEFT COLUMN — Stock Overview + Low Stock Alerts */}
            <div className="space-y-4">

              {/* ── Stock Overview card ─────────────────────────────────── */}
              <motion.div variants={fadeIn} transition={{ duration: 0.3 }}>
                <ErrorBoundary level="tile">
                  <Glass>
                    <div className="p-5">
                      <SectionLabel>Stock Overview</SectionLabel>

                      {/* Hero numbers row */}
                      <div className="grid grid-cols-3 gap-4 mb-5">
                        {/* Total items */}
                        <div>
                          <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-1">
                            Total
                          </p>
                          <p className="text-4xl md:text-5xl font-bold tabular-nums text-[#f9dcd5] leading-none">
                            {items.length > 0 ? items.length.toLocaleString() : '—'}
                          </p>
                        </div>

                        {/* Low stock — red accent */}
                        <div>
                          <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-1">
                            Low Stock
                          </p>
                          <p className="text-4xl md:text-5xl font-bold tabular-nums text-[#fa5c29] leading-none">
                            {low.length}
                          </p>
                        </div>

                        {/* Healthy — green accent */}
                        <div>
                          <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-1">
                            Healthy
                          </p>
                          <p className="text-4xl md:text-5xl font-bold tabular-nums text-status-paid leading-none">
                            {healthy > 0 ? healthy.toLocaleString() : '—'}
                          </p>
                        </div>
                      </div>

                      {/* Stock health progress bar */}
                      <div className="mb-3">
                        <div className="flex items-center justify-between mb-1.5">
                          <p className="text-[10px] text-ink-tertiary tabular-nums">{healthPct}%</p>
                          <p className="text-[10px] text-ink-tertiary">100% capacity</p>
                        </div>
                        <div className="w-full h-2 rounded-full bg-white/10 overflow-hidden">
                          {/* Healthy portion (green) */}
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-status-paid to-status-paid/70 transition-all duration-500"
                            style={{ width: `${healthPct}%` }}
                          />
                        </div>
                      </div>

                      {/* Legend dots */}
                      <div className="flex items-center gap-4 text-[10px] text-ink-tertiary">
                        <span className="flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-status-paid" />
                          On Stock
                        </span>
                        <span className="flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-[#aa8980]" />
                          Purchased
                        </span>
                        <span className="flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-[#fa5c29]" />
                          Reordered
                        </span>
                      </div>
                    </div>
                  </Glass>
                </ErrorBoundary>
              </motion.div>

              {/* ── Low Stock Alerts card ───────────────────────────────── */}
              <motion.div variants={fadeIn} transition={{ duration: 0.3 }}>
                <ErrorBoundary level="tile">
                  <Glass>
                    <div className="p-5">
                      <div className="flex items-center justify-between mb-4">
                        <SectionLabel>Low Stock Alerts</SectionLabel>
                        <span className="text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
                          {low.length} item{low.length !== 1 ? 's' : ''}
                        </span>
                      </div>

                      {low.length > 0 ? (
                        <div className="space-y-0">
                          {low.slice(0, 5).map(i => {
                            const current = parseFloat(i.current_stock)
                            const target = parseFloat(i.reorder_level)
                            return (
                              <div key={i.id}
                                className="flex items-center justify-between gap-3 py-3 border-b border-white/5 last:border-0">
                                {/* Item icon + name + supplier */}
                                <div className="flex items-center gap-3 min-w-0 flex-1">
                                  {/* Small circle icon placeholder */}
                                  <div className="w-8 h-8 rounded-full bg-white/5 border border-white/10
                                    flex items-center justify-center shrink-0">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                                      className="text-ink-tertiary" aria-hidden="true">
                                      <path d="M20 7H4a1 1 0 00-1 1v10a2 2 0 002 2h14a2 2 0 002-2V8a1 1 0 00-1-1z"
                                        stroke="currentColor" strokeWidth="1.5" />
                                      <path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"
                                        stroke="currentColor" strokeWidth="1.5" />
                                    </svg>
                                  </div>
                                  <div className="min-w-0">
                                    <p className="text-sm font-semibold text-[#f9dcd5] truncate">{i.name}</p>
                                    <p className="text-[10px] text-ink-tertiary">
                                      Supplier: {i.unit}
                                    </p>
                                  </div>
                                </div>

                                {/* Quantity + target */}
                                <div className="text-right shrink-0 mr-3">
                                  <p className="text-sm font-bold tabular-nums text-[#fa5c29]">
                                    {current} {i.unit}
                                  </p>
                                  <p className="text-[10px] text-ink-tertiary tabular-nums">
                                    Target: {target} {i.unit}
                                  </p>
                                </div>

                                {/* Low stock indicator (read-only — chef can't reorder) */}
                                <span className="px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider
                                  bg-status-failed/15 text-status-failed shrink-0">
                                  Low
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      ) : (
                        <p className="text-sm text-status-paid/70 py-4">All stock levels healthy</p>
                      )}
                    </div>
                  </Glass>
                </ErrorBoundary>
              </motion.div>
            </div>

            {/* RIGHT COLUMN — Recipes, Menu, Variance, Kitchen tiles */}
            <div className="space-y-4">

              {/* Recipes tile — navigate to menu/recipe editor */}
              <motion.div variants={fadeIn} transition={{ duration: 0.3 }}
                whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}>
                <Glass className="cursor-pointer" onClick={() => navigate('/manager/menu')}>
                  <div className="p-5">
                    <p className="text-[10px] font-bold tracking-widest uppercase text-[#aa8980] mb-2">
                      Recipes
                    </p>
                    <p className="text-sm text-[#f9dcd5] mb-1">
                      Enter &amp; edit recipes per dish
                    </p>
                    <p className="text-[10px] text-[#fa5c29]">Open →</p>
                  </div>
                </Glass>
              </motion.div>

              {/* Menu tile — navigate to menu editor */}
              <motion.div variants={fadeIn} transition={{ duration: 0.3 }}
                whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}>
                <Glass className="cursor-pointer" onClick={() => navigate('/manager/menu')}>
                  <div className="p-5">
                    <p className="text-[10px] font-bold tracking-widest uppercase text-[#aa8980] mb-2">
                      Menu
                    </p>
                    <p className="text-sm text-[#f9dcd5] mb-1">
                      Add dishes, set prices
                    </p>
                    <p className="text-[10px] text-[#fa5c29]">Open →</p>
                  </div>
                </Glass>
              </motion.div>

              {/* Variance tile — navigate to inventory variance tab */}
              <motion.div variants={fadeIn} transition={{ duration: 0.3 }}
                whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}>
                <Glass className="cursor-pointer" onClick={() => navigate('/inventory/count')}>
                  <div className="p-5">
                    <p className="text-[10px] font-bold tracking-widest uppercase text-[#aa8980] mb-2">
                      Variance
                    </p>
                    <p className="text-sm text-[#f9dcd5] mb-1">
                      Expected vs actual use
                    </p>
                    <p className="text-[10px] text-[#fa5c29]">Open →</p>
                  </div>
                </Glass>
              </motion.div>

              {/* Kitchen queue tile — navigate to live queue */}
              <motion.div variants={fadeIn} transition={{ duration: 0.3 }}
                whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}>
                <Glass className="cursor-pointer" onClick={() => navigate('/pos/kitchen')}>
                  <div className="p-5">
                    <p className="text-[10px] font-bold tracking-widest uppercase text-[#aa8980] mb-2">
                      Kitchen Queue
                    </p>
                    <p className="text-sm text-[#f9dcd5] mb-1">
                      Live order queue
                    </p>
                    <p className="text-[10px] text-[#fa5c29]">Open →</p>
                  </div>
                </Glass>
              </motion.div>
            </div>
          </div>

        </motion.div>
      </div>
    </RequireRole>
  )
}
