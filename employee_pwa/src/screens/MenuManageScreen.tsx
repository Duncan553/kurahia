import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Select, Skeleton, useToastStore, Drawer, Combobox, SearchInput, ErrorBoundary } from '@shared'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'

// Manager: add, price, disable, enable menu items + set recipes per dish.
// prep_station controls routing: KITCHEN/BAR → queue; NONE → instant (spa/gym/water).
// Creating/disabling/enabling notifies owner automatically.

interface MenuItem {
  id: string; name: string; price: string; category: string | null
  prep_station: string; department_id: string; is_active: boolean
  food_cost: string | null; gross_margin: string | null
  food_cost_pct: string | null; in_stock: boolean | null
  image_path: string | null
  stock_tracking: 'RECIPE' | 'DIRECT' | 'SERVICE' | 'UNTRACKED'
  inventory_item_id: string | null
}
interface InvItem {
  id: string; name: string; unit: string; cost_per_unit: string | null
  pack_size: string | null; pack_unit: string | null; category: string | null
}
interface RecipeLine {
  id: string; inventory_item_id: string; inventory_item_name: string | null
  quantity: string; unit: string
}
interface DraftLine { invItemId: string; invItemName: string; unit: string; quantity: string }
interface Meta { departments: { id: string; name: string }[] }

// `image` holds the file the user picked BEFORE the item exists. The picture is
// what a guest actually chooses from, so it belongs in the act of creating the
// item — not as a second trip back through the list afterwards.
const BLANK = { name: '', price: '', category: '', station: 'KITCHEN', deptId: '', isAlcoholic: false }
const STATIONS = [
  { value: 'KITCHEN', label: 'Kitchen (food queue)' },
  { value: 'BAR',     label: 'Bar (drinks queue)' },
  { value: 'NONE',    label: 'No queue (spa / gym / activities)' },
]
const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

// food_cost_pct color: lower % = better margin
function marginClass(pct: string | null): string {
  if (!pct) return ''
  const n = parseFloat(pct)
  if (n < 25)  return 'text-status-paid'
  if (n < 34)  return 'text-ink-secondary'
  if (n <= 40) return 'text-status-pending'
  return 'text-status-failed'
}

// Map prep_station to inventory department name
function stationDeptId(station: string, depts: { id: string; name: string }[]): string {
  const map: Record<string, string> = { KITCHEN: 'Kitchen', BAR: 'Bar' }
  const target = map[station]
  return target ? (depts.find(d => d.name === target)?.id ?? '') : ''
}

export default function MenuManageScreen() {
  const qc         = useQueryClient()
  const addToast   = useToastStore(s => s.addToast)
  const user       = useAuthStore(s => s.user)
  const isOwner    = (user?.role_level ?? 0) >= 10

  const [searchQ, setSearchQ]    = useState('')
  const [f, setF]               = useState(BLANK)
  const [adding, setAdding]     = useState(false)
  const [priceEdit, setPriceEdit] = useState<{ id: string; price: string } | null>(null)

  // Recipe drawer
  const [recipeFor,  setRecipeFor]  = useState<MenuItem | null>(null)
  const [draftLines, setDraftLines] = useState<DraftLine[]>([])
  const [newIngName, setNewIngName] = useState('')
  const [newQty,     setNewQty]     = useState('')
  const [copySource, setCopySource] = useState('')
  const [templateType, setTemplateType] = useState('')

  // ── Data ──────────────────────────────────────────────────────────────────

  const { data: items = [], isLoading } = useQuery<MenuItem[]>({
    queryKey: ['menu-manage', searchQ],
    queryFn: () => api.get<MenuItem[]>('/menu/items', {
      params: { include_disabled: 'true', ...(searchQ ? { q: searchQ } : {}) },
    }).then(r => r.data),
    refetchInterval: 60_000,
  })
  const { data: meta } = useQuery<Meta>({
    queryKey: ['users-meta'],
    queryFn: () => api.get<Meta>('/auth/users/meta').then(r => r.data),
  })

  // Inventory items for the ingredient combobox — scoped to the dish's station dept
  const invDeptId = recipeFor ? stationDeptId(recipeFor.prep_station, meta?.departments ?? []) : ''
  const invUrl    = isOwner && invDeptId
    ? `/inventory/items?department=${invDeptId}`
    : '/inventory/items'

  const { data: invItems = [] } = useQuery<InvItem[]>({
    queryKey: ['inv-items-recipe', invDeptId],
    queryFn: () => api.get<InvItem[]>(invUrl).then(r => Array.isArray(r.data) ? r.data : []),
    enabled: !!recipeFor,
    staleTime: 60_000,
  })

  // Current saved recipe — loaded when drawer opens
  const { data: savedLines } = useQuery<RecipeLine[]>({
    queryKey: ['recipe', recipeFor?.id],
    queryFn: () => api.get<RecipeLine[]>(`/menu/items/${recipeFor!.id}/recipe`).then(r => r.data),
    enabled: !!recipeFor,
  })

  // Sync saved lines → draft when drawer first opens (or recipe reloads)
  useEffect(() => {
    if (savedLines) {
      setDraftLines(savedLines.map(l => ({
        invItemId:   l.inventory_item_id,
        invItemName: l.inventory_item_name ?? '',
        unit:        l.unit,
        quantity:    l.quantity,
      })))
    }
  }, [savedLines])

  // Copy recipe from another dish
  const { data: copyRecipe } = useQuery<RecipeLine[]>({
    queryKey: ['recipe', copySource],
    queryFn: () => api.get<RecipeLine[]>(`/menu/items/${copySource}/recipe`).then(r => r.data),
    enabled: !!copySource,
  })
  useEffect(() => {
    if (copySource && copyRecipe) {
      setDraftLines(copyRecipe.map(l => ({
        invItemId:   l.inventory_item_id,
        invItemName: l.inventory_item_name ?? '',
        unit:        l.unit,
        quantity:    l.quantity,
      })))
      setCopySource('')
    }
  }, [copyRecipe, copySource])

  // Live food cost preview — computed client-side from draft lines + inv costs
  const draftCost = useMemo(() => {
    if (!draftLines.length || !recipeFor) return null
    let total = 0
    for (const line of draftLines) {
      const inv = invItems.find(i => i.id === line.invItemId)
      if (!inv?.cost_per_unit) return null
      const cpu = parseFloat(inv.cost_per_unit)
      const ps  = inv.pack_size ? parseFloat(inv.pack_size) : 0
      const unitCost = ps > 0 ? cpu / ps : cpu
      total += parseFloat(line.quantity || '0') * unitCost
    }
    const price = parseFloat(recipeFor.price)
    return {
      food_cost: total,
      gross_margin: price - total,
      pct: price > 0 ? (total / price) * 100 : null,
    }
  }, [draftLines, invItems, recipeFor])

  // ── Mutations ─────────────────────────────────────────────────────────────

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['menu-manage'] })
    qc.invalidateQueries({ queryKey: ['menu-items'] })
  }
  const ok   = (msg: string) => { invalidate(); addToast({ type: 'success', message: msg }) }
  const fail = (e: unknown)  => addToast({ type: 'error', message: extractErr(e) })

  // Picked in the create form, uploaded as part of creating the item.
  const [newImage, setNewImage] = useState<File | null>(null)

  const createMut = useMutation({
    // Upload FIRST, then create with the path already attached, so an item is
    // never born without its picture. If the upload fails the item is not
    // created at all — better than a half-made row nobody goes back to fix.
    mutationFn: async () => {
      let image_path: string | null = null
      if (newImage) {
        const form = new FormData()
        form.append('file', newImage)
        const { data } = await api.post<{ path: string }>('/uploads/menu', form)
        image_path = data.path
      }
      return api.post('/menu/items', {
        name: f.name.trim(), price: f.price,
        category: f.category.trim() || null,
        prep_station: f.station, department_id: f.deptId,
        is_alcoholic: f.isAlcoholic,
        image_path,
      })
    },
    onSuccess: () => {
      ok('Item added to the menu. Owner notified.')
      setF(BLANK); setNewImage(null); setAdding(false)
    },
    onError: fail,
  })

  const toggleMut = useMutation({
    mutationFn: (it: MenuItem) =>
      api.post(`/menu/items/${it.id}/${it.is_active ? 'disable' : 'enable'}`),
    onSuccess: (_d, it) => ok(
      it.is_active ? 'Item removed from sale. Owner notified.' : 'Item back on sale. Owner notified.'
    ),
    onError: fail,
  })

  /**
   * Set how an item's sale moves stock.
   *
   * This is the control that unblocks selling. An UNTRACKED item cannot be put
   * on sale at all — deliberately, because it would take money without moving
   * inventory — and until now there was no way to classify one from the UI, so
   * the block had no escape hatch.
   *
   * RECIPE and DIRECT are set implicitly by writing a recipe or linking a stock
   * item, so the only thing worth choosing by hand is SERVICE: "this genuinely
   * consumes nothing", which is a statement a person makes, not a default.
   */
  const trackingMut = useMutation({
    mutationFn: (v: { id: string; value: string }) =>
      api.patch(`/menu/items/${v.id}`, { stock_tracking: v.value }).then(r => r.data),
    onSuccess: () => ok('Stock tracking updated.'),
    onError: fail,
  })

  const priceMut = useMutation({
    mutationFn: ({ id, price }: { id: string; price: string }) =>
      api.patch(`/menu/items/${id}`, { price }),
    onSuccess: () => { ok('Price updated.'); setPriceEdit(null) },
    onError: fail,
  })

  // Image upload: POST file to /uploads/menu, then PATCH item with returned path
  const imageMut = useMutation({
    mutationFn: async ({ id, file }: { id: string; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post<{ path: string }>('/uploads/menu', form)
      await api.patch(`/menu/items/${id}`, { image_path: data.path })
      return data.path
    },
    onSuccess: () => { ok('Image uploaded.') },
    onError: fail,
  })

  const recipeMut = useMutation({
    mutationFn: () => api.post(`/menu/items/${recipeFor!.id}/recipe`, {
      lines: draftLines.map(l => ({
        inventory_item_id: l.invItemId,
        quantity: parseFloat(l.quantity),
      })),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['recipe', recipeFor?.id] })
      invalidate()
      addToast({ type: 'success', message: `Recipe saved for ${recipeFor?.name}.` })
      setRecipeFor(null)
    },
    onError: fail,
  })

  // Recipe template — loads starter lines from server
  interface TemplateLine { role: string; quantity: number; unit: string }
  const { data: templateData } = useQuery<{ type: string; lines: TemplateLine[] }>({
    queryKey: ['recipe-template', templateType],
    queryFn: () => api.get(`/menu/items/templates?type=${templateType}`).then(r => r.data),
    enabled: !!templateType,
  })
  useEffect(() => {
    if (templateType && templateData?.lines) {
      setDraftLines(templateData.lines.map(l => ({
        invItemId: '', invItemName: `[${l.role}]`, unit: l.unit, quantity: String(l.quantity),
      })))
      setTemplateType('')
    }
  }, [templateData, templateType])

  // ── Recipe drawer helpers ─────────────────────────────────────────────────

  function openRecipe(it: MenuItem) {
    setRecipeFor(it)
    setDraftLines([])
    setNewIngName('')
    setNewQty('')
    setCopySource('')
    setTemplateType('')
  }

  function addIngredient() {
    const inv = invItems.find(i => i.name === newIngName)
    if (!inv || !newQty || parseFloat(newQty) <= 0) return
    setDraftLines(prev => {
      const exists = prev.find(l => l.invItemId === inv.id)
      if (exists) {
        // Update quantity if ingredient already in draft
        return prev.map(l => l.invItemId === inv.id ? { ...l, quantity: newQty } : l)
      }
      return [...prev, { invItemId: inv.id, invItemName: inv.name, unit: inv.unit, quantity: newQty }]
    })
    setNewIngName('')
    setNewQty('')
  }

  // ── Grouping ──────────────────────────────────────────────────────────────

  const deptName = (id: string) => meta?.departments.find(d => d.id === id)?.name ?? '—'
  const grouped  = items.reduce<Record<string, MenuItem[]>>((acc, it) => {
    ;(acc[deptName(it.department_id)] ??= []).push(it); return acc
  }, {})

  // Available dishes for "copy from another dish" — all active items
  const copyItems = recipeFor ? items.filter(i => i.id !== recipeFor.id && i.is_active) : []

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-4">
      <ErrorBoundary level="tile">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-serif text-ink-primary">Menu &amp; Services</h1>
          <p className="text-xs text-ink-tertiary mt-0.5">Add, price, disable items &amp; manage recipes</p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setAdding(a => !a)}>
          {adding ? 'Close' : '+ Add Item'}
        </Button>
      </div>

      <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search menu items…" label="Search menu" />

      {/* ── Add form ───────────────────────────────────────────────────── */}
      {adding && (
        <form
          onSubmit={e => { e.preventDefault(); createMut.mutate() }}
          className="p-4 rounded-2xl glass-card space-y-3"
        >
          <label htmlFor="menu-item-name" className="sr-only">Item name</label>
          <input
            id="menu-item-name" required
            placeholder="Name — e.g. Grilled Tilapia, 60-min Massage"
            value={f.name} onChange={e => setF({ ...f, name: e.target.value })}
            className="w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm
              focus:outline-none focus:border-primary-main"
          />
          <div className="grid grid-cols-2 gap-2">
            <label htmlFor="menu-item-price" className="sr-only">Price (KSh)</label>
            <input
              id="menu-item-price" required type="number" min="0" step="0.01"
              inputMode="decimal" placeholder="Price (KSh)"
              value={f.price} onChange={e => setF({ ...f, price: e.target.value })}
              className="rounded-xl glass-card bg-transparent px-4 py-3 text-sm
                focus:outline-none focus:border-primary-main"
            />
            <label htmlFor="menu-item-category" className="sr-only">Category (optional)</label>
            <input
              id="menu-item-category" placeholder="Category (optional)"
              value={f.category} onChange={e => setF({ ...f, category: e.target.value })}
              className="rounded-xl glass-card bg-transparent px-4 py-3 text-sm
                focus:outline-none focus:border-primary-main"
            />
          </div>
          {/* Picture — first-class, not an afterthought. This is the thing a
              guest actually picks from, so it sits in the create form beside
              name and price rather than behind a second visit to the list. */}
          <div className="flex items-center gap-3">
            {newImage ? (
              <img
                src={URL.createObjectURL(newImage)} alt=""
                className="w-16 h-16 rounded-xl object-cover shrink-0"
              />
            ) : (
              <div className="w-16 h-16 rounded-xl glass-surface shrink-0 flex items-center
                justify-center text-[10px] text-ink-tertiary text-center px-1">
                No photo
              </div>
            )}
            <div className="flex-1 min-w-0">
              <label
                htmlFor="menu-item-image"
                className="inline-block px-3 py-2 rounded-xl glass-card text-xs font-semibold
                  cursor-pointer hover:border-primary-main"
              >
                {newImage ? 'Change photo' : 'Add photo'}
              </label>
              <input
                id="menu-item-image" type="file" accept="image/*" className="sr-only"
                onChange={e => setNewImage(e.target.files?.[0] ?? null)}
              />
              <p className="mt-1 text-[10px] text-ink-tertiary truncate">
                {newImage ? newImage.name : 'Guests choose from the picture.'}
              </p>
            </div>
          </div>

          <Select
            label="Routes to" required value={f.station}
            onChange={e => setF({ ...f, station: e.target.value })}
            options={STATIONS}
          />

          {/* Alcohol is a manager-only list on the backend (pos/menu.py). Shown
              to everyone so the rule is visible, and the 403 explains itself if
              a chef tries. */}
          <label className="flex items-center gap-2 px-1 text-sm cursor-pointer">
            <input
              type="checkbox" checked={f.isAlcoholic}
              onChange={e => setF({ ...f, isAlcoholic: e.target.checked })}
              className="w-4 h-4 accent-primary-main"
            />
            <span>Contains alcohol — beer, wine or a cocktail</span>
          </label>
          <Select
            label="Department" required value={f.deptId}
            onChange={e => setF({ ...f, deptId: e.target.value })}
            options={[
              { value: '', label: 'Department…' },
              ...(meta?.departments ?? []).map(d => ({ value: d.id, label: d.name })),
            ]}
          />
          <Button type="submit" variant="primary" size="lg" className="w-full"
            loading={createMut.isPending}>
            Add to Menu
          </Button>
        </form>
      )}

      {isLoading && (
        <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} variant="row" />)}</div>
      )}

      {/* ── Item list grouped by department ────────────────────────────── */}
      {searchQ && items.length === 0 && !isLoading && (
        <p className="text-sm text-ink-tertiary text-center py-8">
          No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu
        </p>
      )}
      {Object.entries(grouped).map(([dept, deptItems]) => (
        <div key={dept}>
          <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-2">{dept}</p>
          <div className="space-y-2">
            {deptItems.map(it => (
              <div
                key={it.id}
                className={`flex items-center gap-2 p-4 rounded-xl glass-card
                  ${!it.is_active ? 'opacity-50' : ''}`}
              >
                {/* Item image: show thumbnail if exists, upload button always */}
                <label className="shrink-0 cursor-pointer group relative">
                  {it.image_path ? (
                    <img src={it.image_path} alt={it.name}
                      className="w-10 h-10 rounded-lg object-cover glass-card" />
                  ) : (
                    <div className="w-10 h-10 rounded-lg border border-dashed border-white/20
                      flex items-center justify-center text-ink-tertiary group-hover:border-primary-main
                      transition-colors">
                      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                        <rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" strokeWidth="1.5"/>
                        <path d="M2 14l4-4 3 3 4-5 5 6" stroke="currentColor" strokeWidth="1.5"
                          strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </div>
                  )}
                  <input type="file" accept="image/*" className="sr-only"
                    onChange={e => {
                      const file = e.target.files?.[0]
                      if (file) imageMut.mutate({ id: it.id, file })
                      e.target.value = ''
                    }} />
                </label>

                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-ink-primary truncate">{it.name}</p>
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-xs text-ink-tertiary">
                      {it.prep_station === 'NONE' ? 'no queue' : it.prep_station.toLowerCase()}
                      {it.category ? ` · ${it.category}` : ''}
                    </p>
                    {it.food_cost_pct && (
                      <span className={`text-[10px] font-semibold tabular-nums ${marginClass(it.food_cost_pct)}`}>
                        {parseFloat(it.food_cost_pct).toFixed(0)}% cost
                      </span>
                    )}
                    {/* Why this item can or cannot be sold. UNTRACKED is the
                        only blocking state and says so plainly — "not tracked"
                        alone would leave the manager guessing what to do. */}
                    {it.stock_tracking === 'UNTRACKED' ? (
                      <span className="text-[10px] font-semibold uppercase tracking-wide
                        bg-status-failed/10 text-status-failed rounded-full px-1.5 py-0.5">
                        not tracked — cannot sell
                      </span>
                    ) : (
                      <span className="text-[10px] font-semibold uppercase tracking-wide
                        bg-status-paid/10 text-status-paid rounded-full px-1.5 py-0.5">
                        {it.stock_tracking === 'RECIPE' ? 'recipe'
                          : it.stock_tracking === 'DIRECT' ? 'direct stock'
                          : 'service'}
                      </span>
                    )}
                    {it.in_stock === false && (
                      <span className="text-[10px] font-semibold uppercase tracking-wide
                        bg-status-failed/10 text-status-failed rounded-full px-1.5 py-0.5">
                        Sold out
                      </span>
                    )}
                  </div>
                </div>

                {/* "Consumes nothing" — the one tracking state a human sets by
                    hand. RECIPE and DIRECT follow automatically from writing a
                    recipe or linking a stock item, so offering those here would
                    invite a claim the data does not support. Shown only while
                    the item is blocked, so it does not clutter settled rows. */}
                {it.stock_tracking === 'UNTRACKED' && (
                  <button
                    onClick={() => trackingMut.mutate({ id: it.id, value: 'SERVICE' })}
                    disabled={trackingMut.isPending}
                    aria-label={`Mark ${it.name} as consuming no stock`}
                    className="shrink-0 min-h-[44px] px-3 rounded-xl text-xs font-semibold
                      glass-card text-ink-primary hover:border-primary-main
                      focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main
                      disabled:opacity-50 whitespace-nowrap"
                  >
                    Consumes nothing
                  </button>
                )}

                {/* Recipe button — only for kitchen/bar items */}
                {it.prep_station !== 'NONE' && (
                  <button
                    onClick={() => openRecipe(it)}
                    aria-label={`Edit recipe for ${it.name}`}
                    className="shrink-0 text-xs text-ink-tertiary hover:text-primary-dark
                      underline decoration-dotted transition-colors whitespace-nowrap"
                  >
                    Recipe
                  </button>
                )}

                {priceEdit?.id === it.id ? (
                  <>
                    <input
                      autoFocus type="number" min="0" step="0.01" inputMode="decimal"
                      aria-label={`New price for ${it.name} (KSh)`}
                      value={priceEdit.price}
                      onChange={e => setPriceEdit({ id: it.id, price: e.target.value })}
                      onKeyDown={e => e.key === 'Enter' && priceMut.mutate(priceEdit)}
                      className="w-20 rounded-lg border border-primary-main px-2 py-1.5 text-sm tabular-nums"
                    />
                    <Button variant="primary" size="sm" loading={priceMut.isPending}
                      onClick={() => priceMut.mutate(priceEdit)}>Save</Button>
                  </>
                ) : (
                  <button
                    onClick={() => setPriceEdit({ id: it.id, price: it.price })}
                    className="text-sm font-bold tabular-nums text-ink-primary underline decoration-dotted shrink-0"
                  >
                    KSh {parseFloat(it.price).toLocaleString('en-KE')}
                  </button>
                )}

                <Button
                  variant={it.is_active ? 'ghost' : 'primary'} size="sm"
                  loading={toggleMut.isPending && toggleMut.variables?.id === it.id}
                  onClick={() => toggleMut.mutate(it)}
                >
                  {it.is_active ? 'Remove' : 'Restore'}
                </Button>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* ── Recipe drawer ───────────────────────────────────────────────── */}
      <Drawer
        open={!!recipeFor}
        onClose={() => setRecipeFor(null)}
        title={recipeFor ? `Recipe — ${recipeFor.name}` : ''}
      >
        {recipeFor && (
          <div className="space-y-5 pb-6">

            {/* Current draft lines */}
            {draftLines.length > 0 ? (
              <div className="space-y-2">
                <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
                  Ingredients
                </p>
                {draftLines.map((line, i) => (
                  <div key={line.invItemId}
                    className="flex items-center gap-2 p-2 rounded-xl bg-white/6">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-ink-primary">{line.invItemName}</p>
                      <p className="text-xs text-ink-tertiary">
                        {(() => {
                          const inv = invItems.find(x => x.id === line.invItemId)
                          return inv?.pack_unit ?? line.unit
                        })()}
                      </p>
                    </div>
                    <input
                      type="number" min="0.001" step="0.001" inputMode="decimal"
                      aria-label={`Quantity for ${line.invItemName}`}
                      value={line.quantity}
                      onChange={e => setDraftLines(prev =>
                        prev.map((l, j) => j === i ? { ...l, quantity: e.target.value } : l))}
                      className="w-20 rounded-lg glass-card bg-transparent px-2 py-1.5
                        text-sm tabular-nums focus:outline-none focus:border-primary-main"
                    />
                    <button
                      onClick={() => setDraftLines(prev => prev.filter((_, j) => j !== i))}
                      aria-label={`Remove ${line.invItemName} from recipe`}
                      className="text-status-failed/60 hover:text-status-failed transition-colors px-1 text-lg leading-none"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink-tertiary text-center py-2">
                No ingredients yet. Add one below.
              </p>
            )}

            {/* Add ingredient */}
            <div className="space-y-2">
              <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
                Add Ingredient
              </p>
              <Combobox
                label="Ingredient"
                value={newIngName}
                onChange={setNewIngName}
                suggestions={invItems.map(i => i.name)}
                placeholder="Search ingredients…"
                allowFreeEntry={false}
              />
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <label htmlFor="new-qty" className="sr-only">Quantity</label>
                  <input
                    id="new-qty"
                    type="number" min="0.001" step="0.001" inputMode="decimal"
                    placeholder="Quantity"
                    value={newQty}
                    onChange={e => setNewQty(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && addIngredient()}
                    className="w-full rounded-xl glass-card bg-transparent px-3 py-2.5
                      text-sm focus:outline-none focus:border-primary-main"
                  />
                </div>
                {newIngName && (() => {
                  const inv = invItems.find(i => i.name === newIngName)
                  const displayUnit = inv?.pack_unit ?? inv?.unit ?? ''
                  return <span className="text-xs text-ink-tertiary pb-2.5 shrink-0">{displayUnit}</span>
                })()}
                <Button variant="ghost" size="sm"
                  onClick={addIngredient}
                  disabled={!newIngName || !newQty || parseFloat(newQty) <= 0}>
                  + Add
                </Button>
              </div>
            </div>

            {/* Copy from another dish */}
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-1.5">
                Copy from another dish
              </p>
              <select
                style={{ colorScheme: 'dark' }}
                value={copySource}
                onChange={e => setCopySource(e.target.value)}
                aria-label="Copy recipe from another dish"
                className="w-full rounded-xl glass-card bg-transparent px-3 py-2.5
                  text-sm text-ink-secondary focus:outline-none focus:border-primary-main"
              >
                <option value="">Choose a dish to copy its recipe…</option>
                {copyItems.map(i => (
                  <option key={i.id} value={i.id}>{i.name}</option>
                ))}
              </select>
            </div>

            {/* Recipe template starter */}
            {draftLines.length === 0 && (
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-1.5">
                  Start from a template
                </p>
                <div className="flex gap-2">
                  {['shot', 'cocktail', 'mocktail'].map(t => (
                    <button key={t} onClick={() => setTemplateType(t)}
                      className="flex-1 px-3 py-2 rounded-xl glass-card bg-transparent
                        text-sm text-ink-secondary hover:bg-white/5 transition-colors capitalize">
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Live cost preview */}
            {draftLines.length > 0 && (
              <div className="p-4 rounded-xl bg-white/6 space-y-2">
                <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
                  Cost Preview
                </p>
                {draftCost ? (
                  <>
                    <div className="flex justify-between text-sm">
                      <span className="text-ink-secondary">Food cost</span>
                      <span className="tabular-nums font-semibold text-ink-primary">
                        KSh {draftCost.food_cost.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-ink-secondary">Gross margin</span>
                      <span className="tabular-nums font-semibold text-ink-primary">
                        KSh {draftCost.gross_margin.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                    {draftCost.pct !== null && (
                      <div className="flex justify-between text-sm items-center">
                        <span className="text-ink-secondary">Food cost %</span>
                        <span className={`tabular-nums font-bold ${marginClass(String(draftCost.pct))}`}>
                          {draftCost.pct.toFixed(1)}%
                        </span>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-xs text-ink-tertiary">
                    Add cost data to inventory items to see margin preview.
                  </p>
                )}
              </div>
            )}

            <Button
              variant="primary" size="lg" className="w-full"
              loading={recipeMut.isPending}
              disabled={draftLines.length === 0}
              onClick={() => recipeMut.mutate()}
            >
              Save Recipe
            </Button>
          </div>
        )}
      </Drawer>
      </ErrorBoundary>
    </div>
  )
}
