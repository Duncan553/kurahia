import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Drawer, Skeleton, EmptyState, useToastStore, Combobox, SearchInput, ErrorBoundary } from '@shared'
import api from '../lib/axios'
import { RequireRole } from '../components/AuthGate'
import { useAuthStore } from '../stores/authStore'
import { todayKey } from '../lib/format'

const UNIT_SUGGESTIONS = [
  'kg', 'g', 'litre', 'ml',
  'bottle', 'crate of 24', 'crate of 12', 'can',
  'piece', 'pieces', 'pack', 'bundle', 'roll',
  'dozen', 'tray', 'bag', 'tablet', 'sachet',
  'tot (25ml)', 'double (50ml)', 'half-litre',
]

interface Department { id: string; name: string }

interface InventoryItem {
  id: string
  name: string
  unit: string
  department_id: string
  is_active: boolean
  current_stock: string
  reorder_level: string
  below_reorder: boolean
  is_watch_list: boolean
  is_staff_food: boolean
}

interface CountResult {
  id: string
  item: string
  counted: string
  prior_stock: string
  adjustment: string
  duplicate?: boolean
}

interface VarianceItem {
  item_id: string
  item_name: string
  no_closing_count?: boolean
  flagged?: boolean
  variance_pct?: string
  opening_stock?: string
  closing_stock?: string
  adjustment?: string
}

interface VarianceReport {
  period_start: string
  period_end: string
  items: VarianceItem[]
  flagged_count: number
}

interface PurchaseReq { id: string; item_name: string; quantity: string; status: string }

// Three tabs: overview dashboard, count entry, variance report
type Tab = 'overview' | 'count' | 'variance'

function genKey() { return crypto.randomUUID() }

function VarianceBadge({ adj, watchList }: { adj: string; watchList: boolean }) {
  const val = parseFloat(adj)
  if (val === 0) return null
  if (val > 0) return (
    <span className="text-xs font-medium tabular-nums text-blue-600">+{val}</span>
  )
  if (watchList) return (
    <span className="flex items-center gap-1 text-xs font-medium tabular-nums text-status-failed">
      <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" aria-hidden="true"><circle cx="5" cy="5" r="4"/></svg>
      {val}
    </span>
  )
  return <span className="text-xs font-medium tabular-nums text-status-pending">{val}</span>
}

/* ── Glass panel wrapper (matches HeadChefScreen / ManagerScreen pattern) ── */
function Glass({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`glass-card overflow-hidden ${className}`}>
      <div className="relative">
        {/* Subtle top highlight edge */}
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
        {children}
      </div>
    </div>
  )
}

/* ── Department icon — simple SVG per known dept name ── */
function DeptIcon({ name }: { name: string }) {
  const lower = name.toLowerCase()
  // Kitchen: chef hat
  if (lower.includes('kitchen') || lower.includes('chef')) return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M5 14h8v2H5zM4 8a5 5 0 0110 0c0 2-1.5 3.5-2 4H6c-.5-.5-2-2-2-4z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
  // Bar: cocktail glass
  if (lower.includes('bar')) return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M4 3h10l-4 6v4h2M8 13h2M6 17h6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
  // Housekeeping: broom/sparkle
  if (lower.includes('house') || lower.includes('clean')) return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M9 2v5M6 9h6l1 7H5l1-7z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
  // Spa: leaf
  if (lower.includes('spa') || lower.includes('wellness')) return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M9 15c0-6 5-8 7-10C14 7 9 9 9 15zM9 15c0-6-5-8-7-10C4 7 9 9 9 15z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
  // Default: box
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <rect x="3" y="6" width="12" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M3 6l6-3 6 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
}

/* ── Animation variants ── */
const fadeIn = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0 } }
const stagger = { visible: { transition: { staggerChildren: 0.06 } } }
const containerVariants = { hidden: {}, visible: { transition: { staggerChildren: 0.06 } } }
const itemVariants = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0, transition: { type: 'spring' as const, damping: 25, stiffness: 300 } } }

export default function InventoryCountScreen() {
  const addToast    = useToastStore((s) => s.addToast)
  const queryClient = useQueryClient()
  const user        = useAuthStore((s) => s.user)
  const userDept    = user?.department ?? null
  const isOwner     = (user?.role_level ?? 0) >= 10

  // ── Department picker (owner selects dept; manager auto-scoped by backend) ─
  const [selectedDeptId, setSelectedDeptId] = useState<string>('') // '' = All (owner only)

  const [searchQ, setSearchQ] = useState('')
  // Default to overview tab (the dashboard)
  const [tab, setTab] = useState<Tab>('overview')

  // ── Add-item drawer ────────────────────────────────────────────────────────
  const [addOpen,    setAddOpen]    = useState(false)
  const [newName,    setNewName]    = useState('')
  const [newUnit,    setNewUnit]    = useState('')
  const [newDeptId,  setNewDeptId]  = useState('')
  const [newReorder, setNewReorder] = useState('')
  const [newWatch,   setNewWatch]   = useState(false)

  const { data: departments } = useQuery<Department[]>({
    queryKey: ['departments'],
    queryFn: () => api.get<Department[]>('/admin/departments').then((r) => Array.isArray(r.data) ? r.data : []),
    staleTime: 5 * 60_000,
  })

  // Pre-select the currently viewed department when drawer opens
  function openAddDrawer() {
    if (selectedDeptId) {
      setNewDeptId(selectedDeptId)
    } else {
      const match = departments?.find((d) => d.name === userDept)
      setNewDeptId(match?.id ?? departments?.[0]?.id ?? '')
    }
    setNewName('')
    setNewUnit('')
    setNewReorder('')
    setNewWatch(false)
    setAddOpen(true)
  }

  const addItemMutation = useMutation({
    mutationFn: () => api.post('/inventory/items', {
      name:           newName.trim(),
      unit:           newUnit.trim(),
      department_id:  newDeptId,
      reorder_level:  newReorder ? parseFloat(newReorder) : 0,
      is_watch_list:  newWatch,
    }).then((r) => r.data),
    onSuccess: (data: { name: string }) => {
      addToast({ type: 'success', message: `"${data.name}" added to inventory.` })
      queryClient.invalidateQueries({ queryKey: ['inventory-items'] })
      setAddOpen(false)
      setNewName(''); setNewUnit(''); setNewReorder(''); setNewWatch(false)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Could not add item. Try again.'
      addToast({ type: 'error', message: msg })
    },
  })

  const addFormValid = newName.trim() && newUnit.trim() && newDeptId

  // Per-item input values and submission state
  const [inputs,  setInputs]  = useState<Record<string, string>>({})
  const [keys,    setKeys]    = useState<Record<string, string>>({})
  const [results, setResults] = useState<Record<string, CountResult>>({})
  const [pending, setPending] = useState<Set<string>>(new Set())

  // Variance date range — default to today
  const today = todayKey()
  const [fromDate, setFromDate] = useState(today)
  const [toDate,   setToDate]   = useState(today)
  const [varTriggered, setVarTriggered] = useState(false)

  const itemsQueryKey = isOwner && selectedDeptId
    ? ['inventory-items', selectedDeptId, searchQ]
    : ['inventory-items', searchQ]

  const { data: items, isLoading, isError } = useQuery<InventoryItem[]>({
    queryKey: itemsQueryKey,
    queryFn: () => {
      const params = new URLSearchParams()
      if (isOwner && selectedDeptId) params.set('department', selectedDeptId)
      if (searchQ) params.set('q', searchQ)
      const url = `/inventory/items${params.toString() ? `?${params}` : ''}`
      return api.get<InventoryItem[]>(url).then((r) => Array.isArray(r.data) ? r.data : [])
    },
    // For owner with no dept selected, skip the query (show dept picker instead)
    enabled: !isOwner || !!selectedDeptId,
  })

  // ── All items query (for overview — no dept filter, no search filter) ──
  const { data: allItems } = useQuery<InventoryItem[]>({
    queryKey: ['inventory-items-all'],
    queryFn: () => api.get<InventoryItem[]>('/inventory/items').then((r) => Array.isArray(r.data) ? r.data : []),
    staleTime: 30_000,
  })

  // ── Pending purchase requests (for overview stat card) ──
  const { data: pendingOrders = [] } = useQuery<PurchaseReq[]>({
    queryKey: ['inv-pending-orders'],
    queryFn: () => api.get<PurchaseReq[]>('/inventory/purchase-requests', { params: { status: 'PENDING' } })
      .then((r) => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })

  const { data: variance, isFetching: varFetching, refetch: refetchVariance } = useQuery<VarianceReport>({
    queryKey: ['inventory-variance', fromDate, toDate],
    queryFn: () => api.get<VarianceReport>(
      `/inventory/variance?from=${fromDate}T00:00:00&to=${toDate}T23:59:59`
    ).then((r) => r.data),
    enabled: varTriggered,
  })

  function getKey(itemId: string) {
    if (!keys[itemId]) {
      const k = genKey()
      setKeys((prev) => ({ ...prev, [itemId]: k }))
      return k
    }
    return keys[itemId]
  }

  function submitCount(item: InventoryItem) {
    const raw = inputs[item.id]?.trim()
    if (!raw || isNaN(parseFloat(raw))) {
      addToast({ type: 'error', message: `Enter a valid number for ${item.name}.` })
      return
    }
    const idemKey = getKey(item.id)
    setPending((prev) => new Set(prev).add(item.id))

    api.post<CountResult>('/inventory/counts', {
      item_id:         item.id,
      counted_amount:  parseFloat(raw),
      idempotency_key: idemKey,
    })
      .then((r) => {
        const data = r.data
        setResults((prev) => ({ ...prev, [item.id]: data }))
        // Fresh key so retry = new submission
        setKeys((prev) => ({ ...prev, [item.id]: genKey() }))
        if (data.duplicate) {
          addToast({ type: 'warning', message: `Count already submitted for ${data.item}.` })
        } else {
          const adj = parseFloat(data.adjustment)
          const sign = adj >= 0 ? '+' : ''
          addToast({ type: 'success', message: `Count saved for ${data.item}. Variance: ${sign}${adj} ${item.unit}.` })
        }
      })
      .catch((err) => {
        const msg = err?.response?.data?.error ?? 'Count submission failed.'
        addToast({ type: 'error', message: msg })
      })
      .finally(() => {
        setPending((prev) => { const s = new Set(prev); s.delete(item.id); return s })
      })
  }

  // Non-staff-food items for counting
  const countItems = useMemo(() => (items ?? []).filter((i) => !i.is_staff_food), [items])

  // ── Overview derived data ──────────────────────────────────────────────────
  // Department name lookup
  const deptName = (id: string) => departments?.find((d) => d.id === id)?.name ?? 'Other'

  // Use allItems for overview (unfiltered), fall back to items if allItems not loaded
  const overviewItems = allItems ?? items ?? []
  const lowStockItems = useMemo(() => overviewItems.filter((i) => i.below_reorder), [overviewItems])

  // Department health: (items NOT below reorder / total items) per department
  const byDept = useMemo(() => {
    return overviewItems.reduce<Record<string, { total: number; low: number; deptId: string }>>((acc, i) => {
      const name = deptName(i.department_id)
      if (!acc[name]) acc[name] = { total: 0, low: 0, deptId: i.department_id }
      acc[name].total++
      if (i.below_reorder) acc[name].low++
      return acc
    }, {})
  }, [overviewItems, departments])

  // Activity log from recent count results (session-based)
  const activityLog = useMemo(() => {
    return Object.entries(results)
      .filter(([, r]) => !r.duplicate)
      .map(([itemId, r]) => {
        const item = overviewItems.find((i) => i.id === itemId)
        const adj = parseFloat(r.adjustment)
        return { id: r.id, itemName: r.item, adj, unit: item?.unit ?? '', dept: item ? deptName(item.department_id) : '' }
      })
      .reverse() // most recent first
      .slice(0, 6)
  }, [results, overviewItems, departments])

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 md:p-6 max-w-6xl mx-auto">
        <motion.div initial="hidden" animate="visible" variants={stagger}>

          {/* ══════════════════════════════════════════════════════════════
              HEADER: Title + subtitle + action buttons
              ══════════════════════════════════════════════════════════ */}
          <motion.div variants={fadeIn} className="flex flex-col md:flex-row md:items-start md:justify-between gap-3 mb-6">
            <div>
              <h1 className="font-serif text-3xl md:text-4xl font-bold text-[#f9dcd5] tracking-tight">
                Inventory Overview
              </h1>
              <p className="text-sm text-[#aa8980] mt-1">
                Live stock metrics and recent movements
              </p>
            </div>
            {/* Right: Stock Count button + Add item button */}
            <div className="flex items-center gap-2 shrink-0">
              <motion.button
                whileTap={{ scale: 0.97 }}
                onClick={() => setTab('count')}
                className="min-h-[44px] flex items-center gap-1.5 px-4 rounded-xl
                  glass-card text-[#f9dcd5] text-xs font-semibold
                  hover:bg-white/10 transition-colors
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                  <rect x="2" y="3" width="10" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
                  <path d="M5 6h4M5 8.5h2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
                Stock Count
              </motion.button>
              <motion.button
                whileTap={{ scale: 0.97 }}
                onClick={openAddDrawer}
                className="shrink-0 min-h-[44px] flex items-center gap-1.5 px-4 rounded-xl
                  bg-[#fa5c29] text-white text-xs font-semibold
                  hover:bg-[#fa5c29]/90 transition-colors
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                  <path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
                New PO
              </motion.button>
            </div>
          </motion.div>

          {/* ── Department picker (owner only) ──────────────────────── */}
          {isOwner && tab !== 'overview' && (
            <motion.div variants={fadeIn} className="mb-4">
              <p className="text-[10px] uppercase tracking-widest text-[#aa8980] font-medium mb-2">Department</p>
              <div className="flex gap-2 overflow-x-auto scrollbar-none pb-1">
                {departments?.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => setSelectedDeptId(d.id)}
                    className={[
                      'px-3 py-1.5 min-h-[36px] rounded-lg text-xs font-semibold transition-all whitespace-nowrap shrink-0',
                      selectedDeptId === d.id
                        ? 'bg-[#fa5c29] text-white'
                        : 'bg-white/5 text-[#aa8980] hover:bg-white/10',
                    ].join(' ')}
                  >
                    {d.name}
                  </button>
                ))}
              </div>
              {!selectedDeptId && (
                <p className="mt-3 text-sm text-[#aa8980]">Select a department to view its inventory.</p>
              )}
            </motion.div>
          )}

          {/* ── Manager dept label ─────────────────────────────────── */}
          {!isOwner && userDept && tab !== 'overview' && (
            <motion.div variants={fadeIn} className="flex items-center gap-2 mb-4">
              <span className="text-[10px] uppercase tracking-widest text-[#aa8980] font-medium">Dept</span>
              <span className="px-3 py-1 rounded-lg bg-[#fa5c29]/10 text-[#fa5c29] text-xs font-semibold">
                {userDept}
              </span>
            </motion.div>
          )}

          {/* ── Tab navigation ─────────────────────────────────────── */}
          <motion.div variants={fadeIn} className="flex gap-1 bg-white/5 rounded-xl p-1 mb-6">
            {([
              { key: 'overview' as Tab, label: 'Overview' },
              { key: 'count' as Tab, label: 'Count' },
              { key: 'variance' as Tab, label: 'Variance Report' },
            ]).map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={[
                  'flex-1 py-2 min-h-[44px] rounded-lg text-xs font-medium transition-all',
                  tab === t.key
                    ? 'bg-white/8 shadow-sm text-[#f9dcd5]'
                    : 'text-[#aa8980] hover:text-[#f9dcd5]/70',
                ].join(' ')}
              >
                {t.label}
              </button>
            ))}
          </motion.div>

          {/* ══════════════════════════════════════════════════════════════
              OVERVIEW TAB — Dashboard matching Stitch design
              ══════════════════════════════════════════════════════════ */}
          {tab === 'overview' && (
            <>
              {/* ── Top stat cards row: 3 cards ────────────────────── */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
                {/* Total Items */}
                <ErrorBoundary level="tile">
                  <motion.div variants={fadeIn}>
                    <Glass>
                      <div className="p-4">
                        <p className="text-[10px] font-bold tracking-widest uppercase text-[#aa8980] mb-1">Total Items</p>
                        <p className="text-2xl font-bold tabular-nums text-[#f9dcd5]">{overviewItems.length}</p>
                        <p className="text-[10px] text-[#aa8980] mt-0.5">
                          {overviewItems.length - lowStockItems.length} healthy
                        </p>
                      </div>
                    </Glass>
                  </motion.div>
                </ErrorBoundary>

                {/* Low Stock Items */}
                <ErrorBoundary level="tile">
                  <motion.div variants={fadeIn}>
                    <Glass>
                      <div className="p-4">
                        <p className="text-[10px] font-bold tracking-widest uppercase text-[#aa8980] mb-1">Low Stock Items</p>
                        <p className={`text-2xl font-bold tabular-nums ${lowStockItems.length > 0 ? 'text-status-failed' : 'text-status-paid'}`}>
                          {lowStockItems.length}
                        </p>
                        <p className="text-[10px] text-[#aa8980] mt-0.5">
                          {lowStockItems.length > 0 ? 'Requires immediate attention' : 'All above reorder level'}
                        </p>
                      </div>
                    </Glass>
                  </motion.div>
                </ErrorBoundary>

                {/* Pending Orders */}
                <ErrorBoundary level="tile">
                  <motion.div variants={fadeIn}>
                    <Glass>
                      <div className="p-4">
                        <p className="text-[10px] font-bold tracking-widest uppercase text-[#aa8980] mb-1">Pending Orders</p>
                        <p className={`text-2xl font-bold tabular-nums ${pendingOrders.length > 0 ? 'text-status-pending' : 'text-[#f9dcd5]'}`}>
                          {pendingOrders.length}
                        </p>
                        <p className="text-[10px] text-[#aa8980] mt-0.5">
                          {pendingOrders.length > 0
                            ? `${pendingOrders.length} arriving today`
                            : 'No pending requests'}
                        </p>
                      </div>
                    </Glass>
                  </motion.div>
                </ErrorBoundary>
              </div>

              {/* ── Main grid: Departmental Health + Activity Log ───── */}
              <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-4">

                {/* LEFT: Departmental Health */}
                <ErrorBoundary level="tile">
                  <motion.div variants={fadeIn}>
                    <p className="text-sm font-bold tracking-widest uppercase text-[#aa8980] mb-3">
                      Departmental Health
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {Object.entries(byDept).map(([dept, { total, low }]) => {
                        // Health % = items NOT below reorder / total
                        const healthPct = total > 0 ? Math.round(((total - low) / total) * 100) : 100
                        return (
                          <motion.div key={dept} variants={fadeIn} whileHover={{ y: -2 }}>
                            <Glass>
                              <div className="p-4">
                                {/* Dept icon + name */}
                                <div className="flex items-center gap-2 mb-3">
                                  <span className="text-[#fa5c29]">
                                    <DeptIcon name={dept} />
                                  </span>
                                  <span className="font-semibold text-[#f9dcd5] text-sm">{dept}</span>
                                </div>
                                {/* Health percentage */}
                                <div className="flex items-center justify-between mb-2">
                                  <span className="text-[10px] text-[#aa8980]">Overall Stock</span>
                                  <span className="text-xs tabular-nums font-bold text-[#f9dcd5]">{healthPct}%</span>
                                </div>
                                {/* Progress bar */}
                                <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                                  <motion.div
                                    initial={{ width: 0 }}
                                    animate={{ width: `${healthPct}%` }}
                                    transition={{ duration: 0.8, ease: 'easeOut' }}
                                    className={`h-full rounded-full ${
                                      healthPct === 100 ? 'bg-status-paid'
                                        : healthPct > 60 ? 'bg-status-pending'
                                        : 'bg-status-failed'
                                    }`}
                                  />
                                </div>
                                {/* Low stock callout */}
                                {low > 0 && (
                                  <p className="text-[10px] text-status-failed/70 mt-1.5">
                                    {low} item{low !== 1 ? 's' : ''} below reorder
                                  </p>
                                )}
                              </div>
                            </Glass>
                          </motion.div>
                        )
                      })}
                      {/* Empty state if no departments loaded yet */}
                      {Object.keys(byDept).length === 0 && (
                        <div className="col-span-2 py-8 text-center">
                          <p className="text-sm text-[#aa8980]">No inventory data yet</p>
                        </div>
                      )}
                    </div>
                  </motion.div>
                </ErrorBoundary>

                {/* RIGHT: Activity Log */}
                <ErrorBoundary level="tile">
                  <motion.div variants={fadeIn}>
                    <p className="text-sm font-bold tracking-widest uppercase text-[#aa8980] mb-3">
                      Activity Log
                    </p>
                    <Glass>
                      <div className="p-4">
                        {activityLog.length === 0 ? (
                          <div className="py-6 text-center">
                            <p className="text-sm text-[#aa8980]">No recent activity</p>
                            <p className="text-[10px] text-[#aa8980]/60 mt-1">
                              Counts submitted this session appear here
                            </p>
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {activityLog.map((entry) => (
                              <div key={entry.id} className="flex items-start gap-2">
                                {/* Dot indicator */}
                                <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                                  entry.adj < 0 ? 'bg-status-failed' : entry.adj > 0 ? 'bg-status-paid' : 'bg-[#aa8980]'
                                }`} />
                                <div className="min-w-0 flex-1">
                                  <p className="text-xs text-[#f9dcd5] truncate">
                                    {entry.itemName} counted
                                    {entry.adj !== 0 && (
                                      <span className={`ml-1 tabular-nums font-medium ${
                                        entry.adj > 0 ? 'text-status-paid' : 'text-status-failed'
                                      }`}>
                                        ({entry.adj > 0 ? '+' : ''}{entry.adj} {entry.unit})
                                      </span>
                                    )}
                                  </p>
                                  {entry.dept && (
                                    <p className="text-[10px] text-[#aa8980]">{entry.dept}</p>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                        {/* Low stock alerts as pseudo-activity */}
                        {activityLog.length === 0 && lowStockItems.length > 0 && (
                          <div className="mt-3 pt-3 border-t border-white/5 space-y-2">
                            {lowStockItems.slice(0, 4).map((item) => (
                              <div key={item.id} className="flex items-start gap-2">
                                <span className="mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 bg-status-failed" />
                                <div className="min-w-0 flex-1">
                                  <p className="text-xs text-[#f9dcd5] truncate">
                                    {item.name} stock critical
                                  </p>
                                  <p className="text-[10px] text-[#aa8980]">
                                    {parseFloat(item.current_stock)} {item.unit} remaining
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                        {/* View full log link (navigates to count tab) */}
                        <button
                          onClick={() => setTab('count')}
                          className="mt-3 text-[10px] font-semibold text-[#aa8980] hover:text-[#f9dcd5] transition-colors w-full text-center"
                        >
                          View Full Log
                        </button>
                      </div>
                    </Glass>
                  </motion.div>
                </ErrorBoundary>
              </div>
            </>
          )}

          {/* ══════════════════════════════════════════════════════════════
              COUNT TAB — existing count functionality (preserved)
              ══════════════════════════════════════════════════════════ */}
          {tab === 'count' && (
            <>
              {/* Owner must select dept first */}
              {isOwner && !selectedDeptId ? (
                <motion.div variants={fadeIn} className="mb-4">
                  <p className="text-[10px] uppercase tracking-widest text-[#aa8980] font-medium mb-2">Department</p>
                  <div className="flex flex-wrap gap-2">
                    {departments?.map((d) => (
                      <button
                        key={d.id}
                        onClick={() => setSelectedDeptId(d.id)}
                        className="px-3 py-1.5 min-h-[44px] rounded-lg text-xs font-semibold transition-all
                          bg-white/5 text-[#aa8980] hover:bg-white/10"
                      >
                        {d.name}
                      </button>
                    ))}
                  </div>
                  <p className="mt-3 text-sm text-[#aa8980]">Select a department to view its inventory.</p>
                </motion.div>
              ) : (
                <>
                  <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search inventory..." label="Search inventory" />

                  {searchQ && countItems.length === 0 && !isLoading && (
                    <p className="text-sm text-[#aa8980] text-center py-8">No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu</p>
                  )}

                  {isLoading && (
                    <div className="space-y-3 mt-4">
                      {[1,2,3,4].map((i) => (
                        <div key={i} className="rounded-xl bg-white/5 p-3 flex items-center justify-between gap-3">
                          <Skeleton variant="text" className="w-32" />
                          <Skeleton variant="button" className="w-24 h-9" />
                        </div>
                      ))}
                    </div>
                  )}

                  {isError && (
                    <div className="p-4 rounded-xl bg-white/5 text-sm text-[#aa8980] text-center mt-4">
                      Couldn't load items. Check connection.
                    </div>
                  )}

                  {!isLoading && !isError && countItems.length === 0 && (
                    <EmptyState
                      icon={<svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
                        <rect x="8" y="12" width="32" height="28" rx="3" stroke="currentColor" strokeWidth="2"/>
                        <path d="M16 12V8a4 4 0 018 0v4M32 12V8a4 4 0 018 0v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                        <path d="M16 24h16M16 30h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                      </svg>}
                      title="No inventory items configured yet."
                      description="Ask the owner to add items first."
                    />
                  )}

                  {!isLoading && countItems.length > 0 && (
                    <motion.div initial="hidden" animate="visible" variants={containerVariants} className="space-y-3 mt-4">
                      {countItems.map((item) => {
                        const result = results[item.id]
                        const submitted = !!result && !result.duplicate
                        const adj = result ? parseFloat(result.adjustment) : null

                        return (
                          <motion.div
                            key={item.id}
                            variants={itemVariants}
                            whileHover={{ y: -2 }}
                            className={[
                              'rounded-xl border p-3 space-y-2 transition-colors',
                              submitted ? 'bg-[#fa5c29]/10 border-[#fa5c29]/30' : 'glass-card',
                            ].join(' ')}
                          >
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-medium text-[#f9dcd5]">{item.name}</span>
                              <span className="text-xs text-[#aa8980]">{item.unit}</span>
                              {item.below_reorder && (
                                <span className="text-[10px] font-semibold uppercase tracking-wide
                                  bg-status-pending/10 text-status-pending rounded-full px-2 py-0.5">
                                  Reorder
                                </span>
                              )}
                              {item.is_watch_list && (
                                <span className="text-[10px] font-semibold uppercase tracking-wide
                                  bg-status-failed/10 text-status-failed rounded-full px-2 py-0.5">
                                  Watch
                                </span>
                              )}
                              {submitted && (
                                <span className="ml-auto text-[#fa5c29]">
                                  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                                    <circle cx="8" cy="8" r="8" opacity="0.2"/>
                                    <path d="M4.5 8l2.5 2.5L11.5 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                                  </svg>
                                </span>
                              )}
                            </div>

                            <div className="flex items-center gap-2">
                              <span className="text-xs text-[#aa8980] tabular-nums shrink-0">
                                System: {item.current_stock} {item.unit}
                              </span>
                              {adj !== null && <VarianceBadge adj={result!.adjustment} watchList={item.is_watch_list} />}
                            </div>

                            <div className="flex gap-2">
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                inputMode="decimal"
                                placeholder="Counted qty"
                                value={inputs[item.id] ?? ''}
                                onChange={(e) => setInputs((prev) => ({ ...prev, [item.id]: e.target.value }))}
                                disabled={pending.has(item.id)}
                                className="flex-1 rounded-xl border border-white/10 bg-transparent px-3 py-2
                                  text-sm text-[#f9dcd5] focus:outline-none focus:border-[#fa5c29]
                                  focus:ring-2 focus:ring-[#fa5c29]/20 disabled:opacity-50"
                              />
                              <motion.button
                                whileTap={{ scale: 0.97 }}
                                onClick={() => submitCount(item)}
                                disabled={pending.has(item.id) || !inputs[item.id]?.trim()}
                                className={[
                                  'px-4 py-2 min-h-[44px] rounded-xl text-sm font-semibold transition-all shrink-0',
                                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]',
                                  'disabled:opacity-40 disabled:cursor-not-allowed',
                                  submitted
                                    ? 'bg-[#fa5c29]/20 text-[#fa5c29] hover:bg-[#fa5c29]/30'
                                    : 'bg-[#fa5c29] text-white hover:bg-[#fa5c29]/90',
                                ].join(' ')}
                              >
                                {pending.has(item.id) ? (
                                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                                    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
                                    <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                                  </svg>
                                ) : submitted ? 'Re-count' : 'Save'}
                              </motion.button>
                            </div>
                          </motion.div>
                        )
                      })}
                    </motion.div>
                  )}
                </>
              )}
            </>
          )}

          {/* ══════════════════════════════════════════════════════════════
              VARIANCE TAB — existing variance functionality (preserved)
              ══════════════════════════════════════════════════════════ */}
          {tab === 'variance' && (
            <div className="space-y-4">
              {isOwner && !selectedDeptId && (
                <motion.div variants={fadeIn} className="mb-4">
                  <p className="text-[10px] uppercase tracking-widest text-[#aa8980] font-medium mb-2">Department</p>
                  <div className="flex flex-wrap gap-2">
                    {departments?.map((d) => (
                      <button
                        key={d.id}
                        onClick={() => setSelectedDeptId(d.id)}
                        className="px-3 py-1.5 min-h-[44px] rounded-lg text-xs font-semibold transition-all
                          bg-white/5 text-[#aa8980] hover:bg-white/10"
                      >
                        {d.name}
                      </button>
                    ))}
                  </div>
                  <p className="mt-3 text-sm text-[#aa8980]">Select a department first.</p>
                </motion.div>
              )}
              {(!isOwner || selectedDeptId) && (
                <>
                  <div className="flex gap-2 items-end">
                    <div className="flex-1">
                      <label className="block text-xs font-medium text-[#aa8980] mb-1">From</label>
                      <input
                        type="date"
                        value={fromDate}
                        onChange={(e) => setFromDate(e.target.value)}
                        className="w-full rounded-xl border border-white/10 bg-transparent px-3 py-2.5
                          text-sm text-[#f9dcd5] focus:outline-none focus:border-[#fa5c29]
                          focus:ring-2 focus:ring-[#fa5c29]/20"
                      />
                    </div>
                    <div className="flex-1">
                      <label className="block text-xs font-medium text-[#aa8980] mb-1">To</label>
                      <input
                        type="date"
                        value={toDate}
                        onChange={(e) => setToDate(e.target.value)}
                        className="w-full rounded-xl border border-white/10 bg-transparent px-3 py-2.5
                          text-sm text-[#f9dcd5] focus:outline-none focus:border-[#fa5c29]
                          focus:ring-2 focus:ring-[#fa5c29]/20"
                      />
                    </div>
                    <button
                      onClick={() => { setVarTriggered(true); refetchVariance() }}
                      disabled={varFetching}
                      className="px-4 py-2.5 rounded-xl bg-[#fa5c29] text-white text-sm font-semibold
                        hover:bg-[#fa5c29]/90 disabled:opacity-50 transition-all shrink-0"
                    >
                      {varFetching ? '...' : 'Run'}
                    </button>
                  </div>

                  {varFetching && (
                    <div className="space-y-2">
                      {[1,2,3].map((i) => <Skeleton key={i} variant="row" />)}
                    </div>
                  )}

                  {!varFetching && variance && (
                    <>
                      {variance.flagged_count > 0 && (
                        <div className="rounded-xl bg-status-failed/5 border border-status-failed/20 p-3">
                          <p className="text-sm text-status-failed font-medium">
                            {variance.flagged_count} item{variance.flagged_count > 1 ? 's' : ''} flagged for review
                          </p>
                        </div>
                      )}
                      <motion.div className="space-y-2" initial="hidden" animate="visible" variants={containerVariants}>
                        {variance.items.map((v) => (
                          <motion.div
                            key={v.item_id}
                            variants={itemVariants}
                            whileHover={{ y: -2 }}
                            className={[
                              'rounded-xl border px-4 py-3',
                              v.flagged
                                ? 'border-status-failed/40 bg-status-failed/5'
                                : 'glass-card',
                            ].join(' ')}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-medium text-[#f9dcd5] text-sm">{v.item_name}</span>
                              {v.no_closing_count ? (
                                <span className="text-xs text-[#aa8980] italic">Not yet counted</span>
                              ) : (
                                <div className="flex items-center gap-2">
                                  <span className="text-xs tabular-nums text-[#aa8980]">
                                    {v.opening_stock} → {v.closing_stock}
                                  </span>
                                  {v.adjustment && (
                                    <VarianceBadge adj={v.adjustment} watchList={false} />
                                  )}
                                </div>
                              )}
                            </div>
                            {v.variance_pct && !v.no_closing_count && (
                              <p className={`text-[11px] mt-0.5 ${v.flagged ? 'text-status-failed' : 'text-[#aa8980]'}`}>
                                {parseFloat(v.variance_pct) > 0 ? '+' : ''}{v.variance_pct}% variance
                              </p>
                            )}
                          </motion.div>
                        ))}
                      </motion.div>
                    </>
                  )}

                  {!varFetching && !variance && (
                    <p className="text-center text-sm text-[#aa8980] py-6">
                      Select a date range and tap Run.
                    </p>
                  )}
                </>
              )}
            </div>
          )}

        </motion.div>
      </div>

      {/* ── Add item drawer ─────────────────────────────────────────── */}
      <Drawer open={addOpen} onClose={() => setAddOpen(false)} title="Add inventory item">
        <form
          onSubmit={(e) => { e.preventDefault(); if (addFormValid) addItemMutation.mutate() }}
          className="space-y-4"
        >
          {/* Name -- combobox autocompletes from existing items */}
          <Combobox
            label="Item name *"
            value={newName}
            onChange={setNewName}
            suggestions={(items ?? []).map((i) => i.name)}
            placeholder="e.g. Tusker Lager, Cooking oil"
            allowFreeEntry
          />

          {/* Unit -- combobox with common units + free entry */}
          <Combobox
            label="Unit *"
            value={newUnit}
            onChange={setNewUnit}
            suggestions={UNIT_SUGGESTIONS}
            placeholder="e.g. bottle, kg, crate of 24"
            allowFreeEntry
          />

          {/* Department */}
          <div>
            <label className="block text-sm font-medium text-[#aa8980] mb-1.5">
              Department *
            </label>
            <select
              value={newDeptId}
              onChange={(e) => setNewDeptId(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3
                text-sm text-[#f9dcd5] focus:outline-none focus:border-[#fa5c29]
                focus:ring-2 focus:ring-[#fa5c29]/20"
            >
              {!departments?.length && (
                <option value="">Loading departments...</option>
              )}
              {departments?.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>

          {/* Reorder level */}
          <div>
            <label className="block text-sm font-medium text-[#aa8980] mb-1.5">
              Reorder level <span className="font-normal text-[#aa8980]/60">(optional)</span>
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={newReorder}
              onChange={(e) => setNewReorder(e.target.value)}
              placeholder="Alert threshold quantity"
              className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3
                text-sm text-[#f9dcd5] focus:outline-none focus:border-[#fa5c29]
                focus:ring-2 focus:ring-[#fa5c29]/20"
            />
          </div>

          {/* Watch list toggle */}
          <button
            type="button"
            onClick={() => setNewWatch((w) => !w)}
            className={[
              'w-full flex items-center justify-between px-4 py-3 rounded-xl border transition-all text-sm',
              newWatch
                ? 'border-status-failed/40 bg-status-failed/5 text-status-failed'
                : 'border-white/10 bg-white/5 text-[#aa8980]',
            ].join(' ')}
          >
            <span className="font-medium">Flag as watch-list item</span>
            <span className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 ${
              newWatch ? 'border-status-failed bg-status-failed' : 'border-white/20'
            }`}>
              {newWatch && (
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M2 5l2.5 2.5L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
            </span>
          </button>
          <p className="text-xs text-[#aa8980] -mt-2 px-1">
            Watch-list items show a red alert when stock drops below reorder level.
          </p>

          <button
            type="submit"
            disabled={!addFormValid || addItemMutation.isPending}
            className="w-full py-4 rounded-2xl text-base font-semibold transition-all
              bg-[#fa5c29] text-white hover:bg-[#fa5c29]/90 active:scale-[0.99]
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29] focus-visible:ring-offset-2
              disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {addItemMutation.isPending ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
                  <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
                Adding...
              </span>
            ) : 'Add to inventory'}
          </button>
        </form>
      </Drawer>

    </RequireRole>
  )
}
