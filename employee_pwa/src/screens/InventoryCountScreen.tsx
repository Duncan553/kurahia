import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Drawer, Skeleton, EmptyState, useToastStore, Combobox, SearchInput } from '@shared'
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

type Tab = 'count' | 'variance'

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

export default function InventoryCountScreen() {
  const addToast    = useToastStore((s) => s.addToast)
  const queryClient = useQueryClient()
  const user        = useAuthStore((s) => s.user)
  const userDept    = user?.department ?? null
  const isOwner     = (user?.role_level ?? 0) >= 10

  // Animation variants
  const containerVariants = { hidden: {}, visible: { transition: { staggerChildren: 0.06 } } }
  const itemVariants = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0, transition: { type: 'spring' as const, damping: 25, stiffness: 300 } } }

  // ── Department picker (owner selects dept; manager auto-scoped by backend) ─
  const [selectedDeptId, setSelectedDeptId] = useState<string>('') // '' = All (owner only)

  const [searchQ, setSearchQ] = useState('')
  const [tab, setTab] = useState<Tab>('count')

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

  return (
    <RequireRole minLevel={5}>
      <motion.div className="p-4 max-w-3xl mx-auto space-y-4" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ type: 'spring', damping: 25, stiffness: 300 }}>

        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-white font-serif">Inventory Count</h1>
            <p className="text-xs text-white/30 mt-0.5">Stock counts, variance, adjustments</p>
          </div>
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={openAddDrawer}
            className="shrink-0 min-h-[44px] flex items-center gap-1.5 px-3 rounded-xl
              bg-primary-dark text-white text-xs font-semibold
              hover:bg-primary-dark/90 transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Add item
          </motion.button>
        </div>

        {/* ── Department picker (owner only) ──────────────────────── */}
        {isOwner && (
          <div>
            <p className="text-[10px] uppercase tracking-widest text-ink-tertiary font-medium mb-2">Department</p>
            <div className="flex flex-wrap gap-2">
              {departments?.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDeptId(d.id)}
                  className={[
                    'px-3 py-1.5 min-h-[44px] rounded-lg text-xs font-semibold transition-all',
                    selectedDeptId === d.id
                      ? 'bg-primary-dark text-white'
                      : 'bg-white/5 text-ink-secondary hover:bg-cream-deep',
                  ].join(' ')}
                >
                  {d.name}
                </button>
              ))}
            </div>
            {!selectedDeptId && (
              <p className="mt-3 text-sm text-ink-tertiary">Select a department to view its inventory.</p>
            )}
          </div>
        )}

        {/* ── Manager dept label ───────────────────────────────────── */}
        {!isOwner && userDept && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-widest text-ink-tertiary font-medium">Dept</span>
            <span className="px-3 py-1 rounded-lg bg-primary-dark/10 text-primary-dark text-xs font-semibold">
              {userDept}
            </span>
          </div>
        )}

        {/* ── Tab bar + content (owner must select dept first) ────── */}
        {(!isOwner || selectedDeptId) && (<>
        <div className="flex gap-1 bg-white/5/50 rounded-xl p-1">
          {(['count', 'variance'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={[
                'flex-1 py-2 min-h-[44px] rounded-lg text-xs font-medium capitalize transition-all',
                tab === t
                  ? 'bg-transparent shadow-sm text-white'
                  : 'text-ink-tertiary hover:text-ink-secondary',
              ].join(' ')}
            >
              {t === 'count' ? 'Count' : 'Variance Report'}
            </button>
          ))}
        </div>

        {/* ── COUNT TAB ────────────────────────────────────────────── */}
        {tab === 'count' && (
          <>
            <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search inventory..." label="Search inventory" />

            {searchQ && countItems.length === 0 && !isLoading && (
              <p className="text-sm text-ink-tertiary text-center py-8">No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu</p>
            )}

            {isLoading && (
              <div className="space-y-3">
                {[1,2,3,4].map((i) => (
                  <div key={i} className="rounded-xl bg-white/5/40 p-3 flex items-center justify-between gap-3">
                    <Skeleton variant="text" className="w-32" />
                    <Skeleton variant="button" className="w-24 h-9" />
                  </div>
                ))}
              </div>
            )}

            {isError && (
              <div className="p-4 rounded-xl bg-white/5/40 text-sm text-ink-tertiary text-center">
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
              <motion.div initial="hidden" animate="visible" variants={containerVariants} className="space-y-3">
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
                        submitted ? 'bg-primary-light/20 border-primary-main/30' : 'bg-white/5/30 glass-card',
                      ].join(' ')}
                    >
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-white">{item.name}</span>
                        <span className="text-xs text-ink-tertiary">{item.unit}</span>
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
                          <span className="ml-auto text-primary-dark">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                              <circle cx="8" cy="8" r="8" opacity="0.2"/>
                              <path d="M4.5 8l2.5 2.5L11.5 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                            </svg>
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-xs text-ink-tertiary tabular-nums shrink-0">
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
                            text-sm text-white focus:outline-none focus:border-primary-dark
                            focus:ring-2 focus:ring-primary-dark/20 disabled:opacity-50"
                        />
                        <motion.button
                          whileTap={{ scale: 0.97 }}
                          onClick={() => submitCount(item)}
                          disabled={pending.has(item.id) || !inputs[item.id]?.trim()}
                          className={[
                            'px-4 py-2 min-h-[44px] rounded-xl text-sm font-semibold transition-all shrink-0',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                            'disabled:opacity-40 disabled:cursor-not-allowed',
                            submitted
                              ? 'bg-primary-main/20 text-primary-dark hover:bg-primary-main/30'
                              : 'bg-primary-dark text-white hover:bg-primary-dark/90',
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

        {/* ── VARIANCE TAB ─────────────────────────────────────────── */}
        {tab === 'variance' && (
          <div className="space-y-4">
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <label className="block text-xs font-medium text-ink-tertiary mb-1">From</label>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="w-full rounded-xl border border-white/10 bg-transparent px-3 py-2.5
                    text-sm text-white focus:outline-none focus:border-primary-dark
                    focus:ring-2 focus:ring-primary-dark/20"
                />
              </div>
              <div className="flex-1">
                <label className="block text-xs font-medium text-ink-tertiary mb-1">To</label>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="w-full rounded-xl border border-white/10 bg-transparent px-3 py-2.5
                    text-sm text-white focus:outline-none focus:border-primary-dark
                    focus:ring-2 focus:ring-primary-dark/20"
                />
              </div>
              <button
                onClick={() => { setVarTriggered(true); refetchVariance() }}
                disabled={varFetching}
                className="px-4 py-2.5 rounded-xl bg-primary-dark text-white text-sm font-semibold
                  hover:bg-primary-dark/90 disabled:opacity-50 transition-all shrink-0"
              >
                {varFetching ? '…' : 'Run'}
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
                          : 'glass-card bg-white/5/30',
                      ].join(' ')}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-white text-sm">{v.item_name}</span>
                        {v.no_closing_count ? (
                          <span className="text-xs text-ink-tertiary italic">Not yet counted</span>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className="text-xs tabular-nums text-ink-tertiary">
                              {v.opening_stock} → {v.closing_stock}
                            </span>
                            {v.adjustment && (
                              <VarianceBadge adj={v.adjustment} watchList={false} />
                            )}
                          </div>
                        )}
                      </div>
                      {v.variance_pct && !v.no_closing_count && (
                        <p className={`text-[11px] mt-0.5 ${v.flagged ? 'text-status-failed' : 'text-ink-tertiary'}`}>
                          {parseFloat(v.variance_pct) > 0 ? '+' : ''}{v.variance_pct}% variance
                        </p>
                      )}
                    </motion.div>
                  ))}
                </motion.div>
              </>
            )}

            {!varFetching && !variance && (
              <p className="text-center text-sm text-ink-tertiary py-6">
                Select a date range and tap Run.
              </p>
            )}
          </div>
        )}
      </>)}

      </motion.div>

      {/* ── Add item drawer ─────────────────────────────────────────── */}
      <Drawer open={addOpen} onClose={() => setAddOpen(false)} title="Add inventory item">
        <form
          onSubmit={(e) => { e.preventDefault(); if (addFormValid) addItemMutation.mutate() }}
          className="space-y-4"
        >
          {/* Name — combobox autocompletes from existing items */}
          <Combobox
            label="Item name *"
            value={newName}
            onChange={setNewName}
            suggestions={(items ?? []).map((i) => i.name)}
            placeholder="e.g. Tusker Lager, Cooking oil"
            allowFreeEntry
          />

          {/* Unit — combobox with common units + free entry */}
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
            <label className="block text-sm font-medium text-ink-secondary mb-1.5">
              Department *
            </label>
            <select
              value={newDeptId}
              onChange={(e) => setNewDeptId(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3
                text-sm text-white focus:outline-none focus:border-primary-dark
                focus:ring-2 focus:ring-primary-dark/20"
            >
              {!departments?.length && (
                <option value="">Loading departments…</option>
              )}
              {departments?.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>

          {/* Reorder level */}
          <div>
            <label className="block text-sm font-medium text-ink-secondary mb-1.5">
              Reorder level <span className="font-normal text-ink-tertiary">(optional)</span>
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
                text-sm text-white focus:outline-none focus:border-primary-dark
                focus:ring-2 focus:ring-primary-dark/20"
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
                : 'border-white/10 bg-white/5/30 text-ink-secondary',
            ].join(' ')}
          >
            <span className="font-medium">Flag as watch-list item</span>
            <span className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 ${
              newWatch ? 'border-status-failed bg-status-failed' : 'border-cream-deep'
            }`}>
              {newWatch && (
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M2 5l2.5 2.5L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
            </span>
          </button>
          <p className="text-xs text-ink-tertiary -mt-2 px-1">
            Watch-list items show a red alert when stock drops below reorder level.
          </p>

          <button
            type="submit"
            disabled={!addFormValid || addItemMutation.isPending}
            className="w-full py-4 rounded-2xl text-base font-semibold transition-all
              bg-primary-dark text-white hover:bg-primary-dark/90 active:scale-[0.99]
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-2
              disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {addItemMutation.isPending ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
                  <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
                Adding…
              </span>
            ) : 'Add to inventory'}
          </button>
        </form>
      </Drawer>

    </RequireRole>
  )
}
