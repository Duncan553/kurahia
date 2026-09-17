/**
 * PurchaseRecordScreen — record a completed purchase. THE way stock enters.
 *
 * POST /inventory/purchases has existed since Phase A and had no caller in any
 * of the three PWAs, so the only step that raises stock and teaches an
 * ingredient its cost could not be performed from the apps at all. That is why
 * 1 of 33 ingredients has a cost: exactly one purchase was ever recorded, and
 * it had to be done outside the UI.
 *
 * cost_per_unit is DERIVED here as a weighted average over existing stock
 * (app/inventory/purchases.py) — never typed in. So every margin, budget-burn
 * and food-cost figure downstream is waiting on this form.
 *
 * The receipt photo is mandatory server-side. That is deliberate: a purchase
 * without a receipt is an unverifiable cash outflow, which is the exact hole
 * this system exists to close.
 */
import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Input, Select, FormField, Button, useToastStore, ErrorBoundary, EmptyState } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'

interface InvItem {
  id: string; name: string; unit: string; cost_per_unit: string | null
  // How the item ARRIVES: 1 crate = 25 bottles. Null for anything bought in
  // its own unit — a kg of onions is a kg.
  purchase_pack_name: string | null; purchase_pack_size: string | null
}
interface Supplier { id: string; name: string; is_active: boolean }
interface RecentPurchase {
  id: string; item_name: string; unit: string; quantity: string; actual_cost: string
  supplier_name: string | null; recorded_at: string | null
  purchase_pack_name: string | null; purchase_pack_size: string | null
}
interface PurchaseReq {
  id: string; item_id: string; item_name?: string
  // The API sends `quantity`. This read `quantity_requested`, a field that never
  // arrives, so every request in the picker said "? requested".
  quantity: string; unit?: string | null; status: string
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error
  ?? 'Something went wrong. Try again.'

export default function PurchaseRecordScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  const [itemId,    setItemId]    = useState('')
  const [qty,       setQty]       = useState('')
  // Count what the supplier actually handed over. Six crates is six crates;
  // making a storeman multiply by 25 in his head at the delivery door is how
  // "6 crates" becomes 120 or 250 bottles and the count never reconciles again.
  const [inPacks,   setInPacks]   = useState(true)
  // Counting in packs is the default for EVERY line, and the choice does not
  // survive the item or the save. It used to: one delivery entered in bottles
  // left the toggle on bottles, so the next storeman's "4" crates of soda went
  // in as 4 bottles — right money, stock short by a factor of the pack size,
  // and nothing on the screen to say so. 96 bottles became 4 exactly this way.
  const [cost,      setCost]      = useState('')
  const [supplier,  setSupplier]  = useState('')
  const [reqId,     setReqId]     = useState('')
  const [receipt,   setReceipt]   = useState<File | null>(null)
  // One key per form fill. Regenerated on success so the next purchase is a
  // new write, but a double-tap on THIS one collapses to a single row.
  const [idemKey,   setIdemKey]   = useState(() => crypto.randomUUID())

  const { data: items = [], isLoading } = useQuery<InvItem[]>({
    queryKey: ['inv-items'],
    queryFn: () => api.get<InvItem[]>('/inventory/items').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })
  const { data: suppliers = [] } = useQuery<Supplier[]>({
    queryKey: ['suppliers'],
    queryFn: () => api.get<Supplier[]>('/suppliers').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 5 * 60_000,
  })
  // Approved requests are what a purchase usually settles. Picking one marks it
  // FULFILLED server-side, so the request list stops nagging.
  const { data: approved = [] } = useQuery<PurchaseReq[]>({
    queryKey: ['pr-approved'],
    queryFn: () => api.get<PurchaseReq[]>('/inventory/purchase-requests', { params: { status: 'APPROVED' } })
      .then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })

  const item = useMemo(() => items.find(i => i.id === itemId), [items, itemId])

  // What has just been received. On screen because a wrong quantity is only
  // ever noticed by the person who typed it, in the minute after typing it.
  const { data: recent = [] } = useQuery<RecentPurchase[]>({
    queryKey: ['recent-purchases'],
    queryFn: () => api.get<RecentPurchase[]>('/inventory/purchases', { params: { limit: 40 } })
      .then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 30_000,
  })

  const [fixing,  setFixing]  = useState<RecentPurchase | null>(null)
  const [fixQty,  setFixQty]  = useState('')
  const [fixPack, setFixPack] = useState(true)

  const fixPackSize = fixing?.purchase_pack_size ? parseFloat(fixing.purchase_pack_size) : 0
  const fixStockQty = (() => {
    const q = parseFloat(fixQty)
    if (!q || q <= 0) return null
    return fixPack && fixPackSize > 0 ? q * fixPackSize : q
  })()

  const fix = useMutation({
    mutationFn: () => api.post(`/inventory/purchases/${fixing!.id}/correct-quantity`, {
      quantity: String(fixStockQty), reason: 'keyed wrong at the delivery door',
    }).then(r => r.data),
    onSuccess: (d: { message: string }) => {
      addToast({ type: 'success', message: d.message })
      setFixing(null); setFixQty('')
      qc.invalidateQueries({ queryKey: ['recent-purchases'] })
      qc.invalidateQueries({ queryKey: ['inv-items'] })
      qc.invalidateQueries({ queryKey: ['mgr-inventory'] })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  // Unit cost is what actually lands on the ingredient. Showing it live means
  // a fat-fingered total is caught here rather than three months into a margin
  // report that quietly reads wrong.
  // The pack, if this item has one, and whether we are currently counting in it.
  const pack     = useMemo(() => {
    const n = item?.purchase_pack_name, sz = parseFloat(item?.purchase_pack_size ?? '')
    return n && sz > 0 ? { name: n, size: sz } : null
  }, [item])
  const usingPack = !!pack && inPacks

  // What actually goes on the shelf: 6 crates → 150 bottles.
  const stockQty = useMemo(() => {
    const q = parseFloat(qty)
    if (!q || q <= 0) return null
    return usingPack ? q * pack!.size : q
  }, [qty, usingPack, pack])

  const unitCost = useMemo(() => {
    const c = parseFloat(cost)
    if (!stockQty || isNaN(c)) return null
    return c / stockQty
  }, [stockQty, cost])

  const save = useMutation({
    mutationFn: async () => {
      if (!receipt) throw new Error('Add a photo of the receipt — every purchase needs one.')
      const form = new FormData()
      form.append('file', receipt)
      const { data: up } = await api.post<{ path: string }>('/uploads/receipt', form)
      return api.post('/inventory/purchases', {
        item_id: itemId,
        // Always stored in the item's own unit — the ledger holds one language.
        quantity: String(stockQty ?? qty),
        actual_cost: cost,
        supplier_name: supplier.trim() || null,
        purchase_request_id: reqId || null,
        receipt_photo_path: up.path,
        idempotency_key: idemKey,
      })
    },
    onSuccess: () => {
      addToast({ type: 'success',
        message: `Purchase recorded. ${item?.name ?? 'Stock'} is up by `
          + `${stockQty ?? qty} ${item?.unit ?? ''}`
          + (usingPack ? ` (${qty} ${pack!.name}${parseFloat(qty) === 1 ? '' : 's'}).` : '.') })
      setItemId(''); setQty(''); setCost(''); setSupplier(''); setReqId(''); setReceipt(null)
      setInPacks(true)
      setIdemKey(crypto.randomUUID())
      qc.invalidateQueries({ queryKey: ['inv-items'] })
      qc.invalidateQueries({ queryKey: ['pr-approved'] })
      qc.invalidateQueries({ queryKey: ['mgr-inventory'] })
    },
    onError: (e) => addToast({ type: 'error', message: e instanceof Error ? e.message : extractErr(e) }),
  })

  const ready = !!itemId && !!qty && parseFloat(qty) > 0 && cost !== '' && !!receipt

  return (
    <RequireRole minLevel={5}>
      <ErrorBoundary level="tile">
        <div className="p-4 md:p-6 max-w-3xl mx-auto">
          <header className="mb-6">
            <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Stock in</p>
            <h1 className="text-3xl md:text-4xl font-bold font-serif text-ink-primary">Record a Purchase</h1>
            <p className="text-sm text-ink-secondary mt-1">
              What you bought, what it cost, and the receipt. This is what teaches an
              ingredient its price — every margin in the system comes from here.
            </p>
          </header>

          {isLoading ? (
            <div className="py-16 flex justify-center">
              <div className="w-7 h-7 rounded-full border-2 border-primary-main border-t-transparent animate-spin" />
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={
                <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <rect x="7" y="12" width="26" height="21" rx="2" stroke="currentColor" strokeWidth="1.5"/>
                  <path d="M7 18h26M15 12V8M25 12V8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              }
              title="No stock items yet"
              description="Create inventory items first, then record what you buy against them." />
          ) : (
            <form
              onSubmit={e => { e.preventDefault(); save.mutate() }}
              className="glass-card rounded-2xl p-5 flex flex-col gap-4"
            >
              {approved.length > 0 && (
                <FormField label="Settling an approved request?" htmlFor="pr">
                  <Select id="pr" value={reqId}
                    onChange={e => {
                      const v = e.target.value
                      setReqId(v)
                      // Pre-select the item the request was for — the common case
                      const pr = approved.find(p => p.id === v)
                      if (pr?.item_id) setItemId(pr.item_id)
                    }}
                    options={[
                      { value: '', label: 'Not against a request' },
                      ...approved.map(p => ({
                        value: p.id,
                        label: `${p.item_name ?? 'Item'} — ${Number(p.quantity)} ${p.unit ?? ''} requested`,
                      })),
                    ]}
                  />
                </FormField>
              )}

              <FormField label="What did you buy?" htmlFor="item" required>
                <Select id="item" required value={itemId}
                  onChange={e => { setItemId(e.target.value); setInPacks(true) }}
                  options={[
                    { value: '', label: 'Pick a stock item…' },
                    ...items.map(i => ({
                      value: i.id,
                      label: `${i.name} (${i.unit})${i.cost_per_unit ? '' : ' — no cost yet'}`,
                    })),
                  ]}
                />
              </FormField>

              <div className="grid grid-cols-2 gap-3">
                <FormField
                  label={`Quantity${item ? ` (${usingPack ? pack!.name + 's' : item.unit})` : ''}`}
                  htmlFor="qty" required>
                  <Input id="qty" required type="number" min="0" step="0.001" inputMode="decimal"
                    placeholder="0" value={qty} onChange={e => setQty(e.target.value)} />
                  {pack && (
                    <div className="flex gap-1 mt-1.5">
                      {[[true, `${pack.name}s`], [false, `${item!.unit}s`]].map(([v, label]) => (
                        <button key={String(v)} type="button"
                          onClick={() => setInPacks(v as boolean)}
                          className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-colors ${
                            inPacks === v
                              ? 'bg-primary-main text-white border-primary-main'
                              : 'border-white/15 text-ink-tertiary hover:text-ink-secondary'
                          }`}>
                          {label as string}
                        </button>
                      ))}
                      <span className="self-center text-[11px] text-ink-tertiary ml-1">
                        1 {pack.name} = {pack.size} {item!.unit}
                        {usingPack && stockQty ? ` → ${stockQty} ${item!.unit}` : ''}
                      </span>
                    </div>
                  )}
                </FormField>
                <FormField label="Total paid (KSh)" htmlFor="cost" required>
                  <Input id="cost" required type="number" min="0" step="0.01" inputMode="decimal"
                    placeholder="0.00" value={cost} onChange={e => setCost(e.target.value)} />
                </FormField>
              </div>

              {/* The number that actually lands on the ingredient. */}
              {unitCost !== null && item && (
                <div className="rounded-xl glass-surface px-4 py-3 flex items-baseline justify-between">
                  <span className="text-xs text-ink-tertiary">Works out at</span>
                  <span className="text-sm font-semibold text-ink-primary tabular-nums">
                    KSh {unitCost.toLocaleString(undefined, { maximumFractionDigits: 2 })} per {item.unit}
                    {item.cost_per_unit && (
                      <span className="text-ink-tertiary font-normal">
                        {' '}· was {parseFloat(item.cost_per_unit).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </span>
                    )}
                  </span>
                </div>
              )}

              <FormField label="Supplier" htmlFor="supplier">
                <Input id="supplier" list="supplier-names" placeholder="Who you bought from"
                  value={supplier} onChange={e => setSupplier(e.target.value)} />
                <datalist id="supplier-names">
                  {suppliers.filter(s => s.is_active).map(s => <option key={s.id} value={s.name} />)}
                </datalist>
              </FormField>

              {/* Server rejects a purchase with no receipt (400). Asking here, with
                  the reason, beats bouncing them off the backend's error. */}
              <div className="flex items-center gap-3">
                {receipt ? (
                  <img src={URL.createObjectURL(receipt)} alt=""
                    className="w-16 h-16 rounded-xl object-cover shrink-0" />
                ) : (
                  <div className="w-16 h-16 rounded-xl glass-surface shrink-0 flex items-center
                    justify-center text-[10px] text-ink-tertiary text-center px-1">
                    Receipt
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <label htmlFor="receipt"
                    className="inline-block px-3 py-2 rounded-xl glass-card text-xs font-semibold
                      cursor-pointer hover:border-primary-main">
                    {receipt ? 'Change photo' : 'Photograph the receipt'}
                  </label>
                  <input id="receipt" type="file" accept="image/*" capture="environment"
                    className="sr-only"
                    onChange={e => setReceipt(e.target.files?.[0] ?? null)} />
                  <p className="mt-1 text-[10px] text-ink-tertiary truncate">
                    {receipt ? receipt.name : 'Required — a purchase without a receipt cannot be checked.'}
                  </p>
                </div>
              </div>

              <Button type="submit" disabled={!ready} loading={save.isPending}>
                Record purchase
              </Button>
            </form>
          )}

          {/* ── What was just received ─────────────────────────────────── */}
          {recent.length > 0 && (
            <section className="mt-8">
              <h2 className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-2">
                Just received — check the quantity before you walk away
              </h2>
              <ul className="space-y-2">
                {recent.map(p => (
                  <li key={p.id} className="rounded-xl glass-card px-4 py-3">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-sm font-medium text-ink-primary">{p.item_name}</span>
                      <span className="text-sm tabular-nums text-ink-secondary">
                        {parseFloat(p.quantity).toLocaleString()} {p.unit}
                        {p.purchase_pack_size && parseFloat(p.purchase_pack_size) > 0 && (
                          <span className="text-ink-tertiary">
                            {' '}= {(parseFloat(p.quantity) / parseFloat(p.purchase_pack_size))
                                    .toLocaleString(undefined, { maximumFractionDigits: 2 })} {p.purchase_pack_name}s
                          </span>
                        )}
                      </span>
                    </div>
                    <div className="flex items-baseline justify-between gap-3 mt-0.5">
                      <span className="text-[11px] text-ink-tertiary">
                        {p.supplier_name ?? 'no supplier'} · KSh {parseFloat(p.actual_cost).toLocaleString()}
                      </span>
                      <button type="button"
                        onClick={() => { setFixing(p); setFixQty(''); setFixPack(!!p.purchase_pack_size) }}
                        className="text-[11px] font-semibold text-ink-tertiary hover:text-ink-primary">
                        Wrong quantity?
                      </button>
                    </div>

                    {fixing?.id === p.id && (
                      <div className="mt-3 border-t border-white/10 pt-3 space-y-2">
                        <p className="text-[11px] text-ink-tertiary">
                          How much actually arrived? The money and the receipt stay as they are.
                        </p>
                        <div className="flex gap-2">
                          <Input type="number" min="0" step="0.001" inputMode="decimal"
                            placeholder={p.purchase_pack_size && fixPack ? `e.g. 6 ${p.purchase_pack_name}s` : `e.g. 150 ${p.unit}`}
                            value={fixQty} onChange={e => setFixQty(e.target.value)} />
                          {p.purchase_pack_size && (
                            <div className="flex gap-1 shrink-0 items-center">
                              {[[true, `${p.purchase_pack_name}s`], [false, `${p.unit}s`]].map(([v, label]) => (
                                <button key={String(v)} type="button"
                                  onClick={() => setFixPack(v as boolean)}
                                  className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-colors ${
                                    fixPack === v
                                      ? 'bg-primary-main text-white border-primary-main'
                                      : 'border-white/15 text-ink-tertiary'
                                  }`}>
                                  {label as string}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                        {fixStockQty !== null && (
                          <p className="text-[11px] text-ink-secondary">
                            Sets stock to <strong>{fixStockQty.toLocaleString()} {p.unit}</strong>
                            {' '}(was {parseFloat(p.quantity).toLocaleString()}).
                          </p>
                        )}
                        <div className="flex gap-2">
                          <Button size="sm" onClick={() => fix.mutate()}
                            disabled={!fixStockQty} loading={fix.isPending}>
                            Correct it
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setFixing(null)}>
                            Cancel
                          </Button>
                        </div>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </ErrorBoundary>
    </RequireRole>
  )
}
