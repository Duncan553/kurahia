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
      className={`rounded-2xl border border-white/8 overflow-hidden ${onClick ? 'cursor-pointer' : ''} ${className}`}
      style={{ background: 'rgba(40, 30, 20, 0.6)', backdropFilter: 'blur(16px)' }}
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

  const TILES = [
    { label: 'Recipes', desc: 'Enter & edit recipes per dish', icon: '📝', path: '/manager/menu' },
    { label: 'Menu Items', desc: 'Add new dishes to the menu', icon: '🍽', path: '/manager/menu' },
    { label: 'Variance', desc: 'Expected vs actual ingredient use', icon: '📊', path: '/inventory/count' },
    { label: 'Kitchen Queue', desc: 'See live orders', icon: '🔥', path: '/pos/kitchen' },
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
                    <span className="text-2xl mb-2 block">{t.icon}</span>
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
