import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { RequireRole } from '../components/AuthGate'
import { useAuthStore } from '../stores/authStore'
import { ErrorBoundary } from '@shared'
import api from '../lib/axios'

interface InvItem {
  id: string; name: string; unit: string; current_stock: string
  reorder_level: string; below_reorder: boolean
}

function Glass({ children, className = '', onClick }: {
  children: React.ReactNode; className?: string; onClick?: () => void
}) {
  return (
    <motion.div
      whileHover={onClick ? { y: -2 } : undefined}
      whileTap={onClick ? { scale: 0.98 } : undefined}
      onClick={onClick}
      className={`glass-card overflow-hidden ${onClick ? 'cursor-pointer' : ''} ${className}`}
    >
      <div className="relative">
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
        {children}
      </div>
    </motion.div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-amber-300/50 mb-3">{children}</p>
}

export default function HeadChefScreen() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)

  const { data: items = [] } = useQuery<InvItem[]>({
    queryKey: ['chef-stock'],
    queryFn: () => api.get<InvItem[]>('/inventory/items').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 30_000, refetchInterval: 60_000,
  })

  const low = items.filter(i => i.below_reorder)
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  const TILES: { label: string; desc: string; svg: React.ReactNode; path: string }[] = [
    { label: 'Recipes', desc: 'Enter & edit recipes per dish', path: '/manager/menu',
      svg: <svg width="22" height="22" viewBox="0 0 20 20" fill="none"><path d="M3 17V3h10l4 4v10a1 1 0 01-1 1H4a1 1 0 01-1-1z" stroke="currentColor" strokeWidth="1.4"/><path d="M7 10h6M7 13h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg> },
    { label: 'Menu', desc: 'Add new dishes', path: '/manager/menu',
      svg: <svg width="22" height="22" viewBox="0 0 20 20" fill="none"><rect x="3" y="1" width="14" height="18" rx="2" stroke="currentColor" strokeWidth="1.4"/><path d="M7 6h6M7 10h6M7 14h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg> },
    { label: 'Variance', desc: 'Expected vs actual', path: '/inventory/count',
      svg: <svg width="22" height="22" viewBox="0 0 20 20" fill="none"><path d="M3 17V7l4-4 3 5 4-6 3 3v12H3z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/></svg> },
    { label: 'Kitchen', desc: 'Live orders', path: '/pos/kitchen',
      svg: <svg width="22" height="22" viewBox="0 0 20 20" fill="none"><rect x="2" y="8" width="16" height="9" rx="1" stroke="currentColor" strokeWidth="1.4"/><path d="M5 8V5a5 5 0 0110 0v3" stroke="currentColor" strokeWidth="1.4"/><circle cx="10" cy="12" r="1.5" fill="currentColor"/></svg> },
  ]

  return (
    <RequireRole minLevel={5}>
      <div className="min-h-screen p-4 md:p-6">
        <div className="max-w-3xl mx-auto">

          <div className="mb-6">
            <p className="text-sm text-amber-300/60">{greeting}, Chef</p>
            <h1 className="font-serif text-3xl font-bold text-white tracking-tight">
              {user?.username ?? 'Head Chef'}
            </h1>
            <p className="text-xs text-amber-200/40 mt-1">
              Kitchen · {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'long' })}
            </p>
          </div>

          <motion.div
            initial="hidden" animate="visible"
            variants={{ visible: { transition: { staggerChildren: 0.08 } } }}
            className="grid grid-cols-1 md:grid-cols-2 gap-4"
          >
            {/* Kitchen Stock Overview */}
            <motion.div variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0 } }}
              className="col-span-full">
              <ErrorBoundary level="tile">
                <Glass>
                  <div className="p-5">
                    <Label>Kitchen Stock</Label>
                    <div className="grid grid-cols-3 gap-3 mb-4">
                      <div>
                        <p className="text-2xl font-bold tabular-nums text-white">{items.length}</p>
                        <p className="text-xs text-amber-200/40">Items</p>
                      </div>
                      <div>
                        <p className={`text-2xl font-bold tabular-nums ${low.length > 0 ? 'text-status-failed' : 'text-emerald-400'}`}>
                          {low.length}
                        </p>
                        <p className="text-xs text-amber-200/40">Low</p>
                      </div>
                      <div>
                        <p className="text-2xl font-bold tabular-nums text-emerald-400">{items.length - low.length}</p>
                        <p className="text-xs text-amber-200/40">OK</p>
                      </div>
                    </div>
                    {low.length > 0 && (
                      <div className="space-y-1.5 pt-3 border-t border-white/5">
                        {low.slice(0, 5).map(i => (
                          <div key={i.id} className="flex justify-between text-sm">
                            <span className="text-white">{i.name}</span>
                            <span className="text-status-failed tabular-nums font-semibold">
                              {parseFloat(i.current_stock)} {i.unit}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                    {low.length === 0 && (
                      <p className="text-sm text-emerald-300/60">All stock levels healthy ✓</p>
                    )}
                  </div>
                </Glass>
              </ErrorBoundary>
            </motion.div>

            {/* Quick tiles */}
            {TILES.map(t => (
              <motion.div key={t.label}
                variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0 } }}>
                <Glass onClick={() => navigate(t.path)}>
                  <div className="p-5">
                    <span className="text-white/50 mb-2 block">{t.svg}</span>
                    <p className="text-sm font-semibold text-white">{t.label}</p>
                    <p className="text-xs text-amber-200/50 mt-0.5">{t.desc}</p>
                  </div>
                </Glass>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </div>
    </RequireRole>
  )
}
