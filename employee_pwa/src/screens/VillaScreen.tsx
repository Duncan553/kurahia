import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Skeleton, EmptyState, SearchInput, Button, useToastStore, ErrorBoundary } from '@shared'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'

interface VillaTab {
  id: string; reference: string | null; status: string
  opened_at: string; opened_by: string | null; balance: string
}

// Resource returned by /bookings/availability
interface VillaResource {
  id: string; name: string; resource_type: string
  base_price: string; capacity: number | null; available: boolean
}

const kes = (v: string | number) =>
  `KSh ${parseFloat(String(v)).toLocaleString('en-KE', { minimumFractionDigits: 0 })}`

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

const fadeIn = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0 } }
const stagger = { visible: { transition: { staggerChildren: 0.06 } } }

export default function VillaScreen() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const roleLevel = useAuthStore(s => s.user?.role_level ?? 0)
  const [searchQ, setSearchQ] = useState('')

  // Can this user create bookings? (level 3+ = front desk or manager)
  const canBook = roleLevel >= 3

  // Booking form state
  const [booking, setBooking] = useState<string | null>(null)  // resource_id being booked
  const [form, setForm] = useState({ guest_name: '', guest_phone: '', guests: '1', checkin: '', checkout: '' })

  const { data: tabs = [], isLoading } = useQuery<VillaTab[]>({
    queryKey: ['villa-tabs'],
    queryFn: () => api.get<VillaTab[]>('/tabs?tab_type=VILLA&status=OPEN').then(r => r.data),
    staleTime: 15_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })

  // Availability check for today forward (7 days window)
  const today = new Date().toISOString().slice(0, 10)
  const weekLater = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10)
  const { data: resources = [], isLoading: resLoading, error: resError } = useQuery<VillaResource[]>({
    queryKey: ['villa-availability', today],
    queryFn: () => api.get<VillaResource[]>(
      `/bookings/availability?resource_type=VILLA&from=${today}T00:00:00&to=${weekLater}T23:59:59`
    ).then(r => r.data),
    staleTime: 60_000,
    retry: false, // a 403 here is a permission fact, not a flaky network call — don't retry it
  })
  // /bookings/availability requires FRONT_DESK_LEVEL (3); housekeeping/villa staff
  // routed here by AppLayout are often level 1, so this legitimately 403s for them.
  // Without this check the empty-array fallback below claimed "nothing configured,"
  // which is wrong and sends people looking for a setup step that isn't the issue.
  const resForbidden = (resError as { response?: { status?: number } } | undefined)?.response?.status === 403

  // Create booking mutation
  const bookMut = useMutation({
    mutationFn: (resourceId: string) => {
      if (!form.guest_name.trim() || !form.guest_phone.trim()) throw new Error('Guest name and phone are required.')
      if (!form.checkin || !form.checkout) throw new Error('Check-in and check-out dates are required.')
      return api.post('/bookings', {
        resource_id: resourceId,
        guest_name: form.guest_name.trim(),
        guest_phone: form.guest_phone.trim(),
        number_of_guests: parseInt(form.guests) || 1,
        check_in_planned_utc: `${form.checkin}T14:00:00`,
        check_out_planned_utc: `${form.checkout}T11:00:00`,
        idempotency_key: crypto.randomUUID(),
      })
    },
    onSuccess: () => {
      setBooking(null)
      setForm({ guest_name: '', guest_phone: '', guests: '1', checkin: '', checkout: '' })
      addToast({ type: 'success', message: 'Villa booked successfully.' })
      qc.invalidateQueries({ queryKey: ['villa-availability'] })
      qc.invalidateQueries({ queryKey: ['villa-tabs'] })
    },
    onError: (e) => addToast({ type: 'error', message: e instanceof Error ? e.message : extractErr(e) }),
  })

  // Client-side filter by reference or "Villa Guest"
  const filteredTabs = searchQ
    ? tabs.filter(t => (t.reference ?? 'Villa Guest').toLowerCase().includes(searchQ.toLowerCase()))
    : tabs

  return (
    <div className="min-h-screen p-4 md:p-6">
      <ErrorBoundary level="tile">
      <motion.div className="max-w-3xl mx-auto space-y-6"
        initial="hidden" animate="visible" variants={stagger}>

      <motion.div variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}>
        <h1 className="text-2xl font-bold font-serif text-ink-primary">Villas</h1>
        <p className="text-xs text-amber-200/40 mt-0.5">Waterfront Country Club</p>
      </motion.div>

      {/* Villa cards with availability status */}
      {resLoading && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {[1,2,3].map(i => <Skeleton key={i} variant="row" className="h-40" />)}
        </div>
      )}

      {!resLoading && resources.length > 0 && (
        <motion.div variants={fadeIn} transition={{ duration: 0.35, ease: 'easeOut' }}
          className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {resources.map(v => (
            <div key={v.id} className={`glass-card rounded-2xl overflow-hidden ${
              !v.available ? 'opacity-60' : ''
            }`}>
              <div className={`h-24 flex items-center justify-center text-xs ${
                v.available ? 'bg-emerald-900/20 text-emerald-300/50' : 'bg-red-900/20 text-red-300/50'
              }`}>
                {v.name}
              </div>
              <div className="p-4">
                <div className="flex items-center justify-between mb-1">
                  <p className="font-semibold text-ink-primary text-sm">{v.name}</p>
                  <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                    v.available
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}>
                    {v.available ? 'Available' : 'Occupied'}
                  </span>
                </div>
                <p className="text-xs text-amber-200/60 tabular-nums">{kes(v.base_price)}/night</p>
                {v.capacity && (
                  <p className="text-[10px] text-amber-200/40">{v.capacity} guests max</p>
                )}
                {v.available && canBook && (
                  <button
                    onClick={() => setBooking(booking === v.id ? null : v.id)}
                    className="mt-2 w-full py-2 rounded-xl text-xs font-semibold
                      bg-primary-main text-white hover:bg-primary-main/90 transition-colors"
                  >
                    Book Villa
                  </button>
                )}
                {v.available && !canBook && (
                  <p className="mt-2 text-[10px] text-amber-200/40 italic">
                    Contact front desk to book
                  </p>
                )}
              </div>

              {/* Booking form (inline, below the card content) */}
              <AnimatePresence>
                {booking === v.id && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}
                    className="overflow-hidden border-t border-white/10"
                  >
                    <div className="p-4 space-y-2">
                      <input placeholder="Guest name" value={form.guest_name}
                        onChange={e => setForm(f => ({ ...f, guest_name: e.target.value }))}
                        className="w-full rounded-lg glass-card bg-transparent px-3 py-2
                          text-xs text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-primary-main" />
                      <input placeholder="Phone (e.g. 0712...)" value={form.guest_phone}
                        onChange={e => setForm(f => ({ ...f, guest_phone: e.target.value }))}
                        className="w-full rounded-lg glass-card bg-transparent px-3 py-2
                          text-xs text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-primary-main" />
                      <input type="number" min="1" placeholder="Guests" value={form.guests}
                        onChange={e => setForm(f => ({ ...f, guests: e.target.value }))}
                        className="w-full rounded-lg glass-card bg-transparent px-3 py-2
                          text-xs text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-primary-main" />
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="text-[10px] text-ink-tertiary">Check-in</label>
                          <input type="date" value={form.checkin}
                            onChange={e => setForm(f => ({ ...f, checkin: e.target.value }))}
                            className="w-full rounded-lg glass-card bg-transparent px-3 py-2
                              text-xs text-ink-primary focus:outline-none focus:border-primary-main" />
                        </div>
                        <div>
                          <label className="text-[10px] text-ink-tertiary">Check-out</label>
                          <input type="date" value={form.checkout}
                            onChange={e => setForm(f => ({ ...f, checkout: e.target.value }))}
                            className="w-full rounded-lg glass-card bg-transparent px-3 py-2
                              text-xs text-ink-primary focus:outline-none focus:border-primary-main" />
                        </div>
                      </div>
                      <p className="text-[10px] text-amber-200/40">
                        Guest must present valid ID at check-in.
                      </p>
                      <div className="flex gap-2">
                        <button onClick={() => setBooking(null)}
                          className="flex-1 py-2 rounded-lg text-xs font-semibold glass-card
                            text-ink-secondary hover:bg-white/5 transition-colors">
                          Cancel
                        </button>
                        <Button variant="primary" size="sm" className="flex-1"
                          loading={bookMut.isPending}
                          onClick={() => bookMut.mutate(v.id)}>
                          Confirm Booking
                        </Button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </motion.div>
      )}

      {/* Fallback if availability endpoint fails or returns empty — show static cards */}
      {!resLoading && resources.length === 0 && (
        <motion.div variants={fadeIn} transition={{ duration: 0.35, ease: 'easeOut' }}>
          <p className="text-sm text-ink-tertiary text-center py-4">
            {resForbidden
              ? "You don't have permission to view villa availability — front desk level or above needed. Ask your manager."
              : 'No villa resources configured yet. Ask the manager to set up villa resources.'}
          </p>
        </motion.div>
      )}

      <motion.h2 variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}
        className="text-lg font-bold font-serif text-ink-primary">Current Guests</motion.h2>

      <motion.div variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}>
        <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search guests..." label="Search guests" />
      </motion.div>

      <AnimatePresence>
        {searchQ && filteredTabs.length === 0 && !isLoading && (
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="text-sm text-amber-200/40 text-center py-8">
            No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu
          </motion.p>
        )}
      </AnimatePresence>

      {isLoading && <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} variant="row" />)}</div>}

      <AnimatePresence>
        {!isLoading && tabs.length === 0 && !searchQ && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}>
            <EmptyState
              icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                <path d="M6 20L20 8l14 12v16a2 2 0 01-2 2H8a2 2 0 01-2-2V20z"
                  stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <rect x="15" y="26" width="10" height="10" rx="1" stroke="currentColor" strokeWidth="1.5"/>
              </svg>}
              title="No villa guests currently checked in."
            />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="space-y-2">
        {filteredTabs.map(t => {
          const bal = parseFloat(t.balance)
          return (
            <motion.button key={t.id} onClick={() => navigate(`/pos/tabs/${t.id}`)}
              whileTap={{ scale: 0.98 }}
              className="w-full flex items-center justify-between p-4 rounded-2xl glass-card
                hover:bg-cream-alt transition-colors text-left">
              <div>
                <p className="font-semibold text-ink-primary">{t.reference ?? 'Villa Guest'}</p>
                <p className="text-xs text-amber-200/40 mt-0.5">
                  Checked in {new Date(t.opened_at).toLocaleDateString('en-KE')}
                  {t.opened_by ? ` · by ${t.opened_by}` : ''}
                </p>
              </div>
              <div className="text-right">
                <p className={`text-sm font-bold tabular-nums ${bal > 0 ? 'text-status-failed' : 'text-status-paid'}`}>
                  {kes(t.balance)}
                </p>
                <p className="text-[10px] text-amber-200/40">{bal > 0 ? 'outstanding' : 'settled'}</p>
              </div>
            </motion.button>
          )
        })}
      </div>
      </motion.div>
      </ErrorBoundary>
    </div>
  )
}
