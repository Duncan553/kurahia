import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Skeleton, EmptyState, SearchInput } from '@shared'
import api from '../lib/axios'

interface VillaTab {
  id: string; reference: string | null; status: string
  opened_at: string; opened_by: string | null; balance: string
}

const kes = (v: string) =>
  `KSh ${parseFloat(v).toLocaleString('en-KE', { minimumFractionDigits: 0 })}`

export default function VillaScreen() {
  const navigate = useNavigate()
  const [searchQ, setSearchQ] = useState('')

  const { data: tabs = [], isLoading } = useQuery<VillaTab[]>({
    queryKey: ['villa-tabs'],
    queryFn: () => api.get<VillaTab[]>('/tabs?tab_type=VILLA&status=OPEN').then(r => r.data),
    staleTime: 15_000,
    refetchOnWindowFocus: true,
  })

  // Client-side filter by reference or "Villa Guest"
  const filteredTabs = searchQ
    ? tabs.filter(t => (t.reference ?? 'Villa Guest').toLowerCase().includes(searchQ.toLowerCase()))
    : tabs

  const VILLAS = [
    { name: 'Villa 1', price: 100000, sqft: '8,000 ft²', img: '/images/villas/villa-1.jpg' },
    { name: 'Villa 2', price: 100000, sqft: '120 ft²', img: '/images/villas/villa-2.jpg' },
    { name: 'Villa 4', price: 120000, sqft: '120 ft²', img: '/images/villas/villa-4.jpg' },
    { name: 'Villa 6', price: 140000, sqft: '8,000 ft²', img: '/images/villas/villa-6.jpg' },
    { name: 'Villa 14', price: 65000, sqft: '1,200 ft²', img: '/images/villas/villa-14.jpg' },
    { name: 'Villa 15', price: 65000, sqft: '1,200 ft²', img: '/images/villas/villa-15.jpg' },
  ]

  return (
    <div className="min-h-screen p-4 md:p-6">
      <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold font-serif text-white">Villas</h1>
        <p className="text-xs text-amber-200/40 mt-0.5">Waterfront Country Club · 8 adults/night</p>
      </div>

      {/* Real villa cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {VILLAS.map(v => (
          <div key={v.name} className="rounded-2xl overflow-hidden border border-amber-200/10"
            style={{ background: 'rgba(45, 31, 21, 0.7)', backdropFilter: 'blur(12px)' }}>
            <div className="h-24 bg-amber-900/30 flex items-center justify-center text-amber-200/30 text-xs">
              📷 {v.name}
            </div>
            <div className="p-3">
              <p className="font-semibold text-white text-sm">{v.name}</p>
              <p className="text-xs text-amber-200/60 tabular-nums">KSh {v.price.toLocaleString()}/night</p>
              <p className="text-[10px] text-amber-200/40">{v.sqft} · 8 adults</p>
            </div>
          </div>
        ))}
      </div>

      <h2 className="text-lg font-bold font-serif text-white">Current Guests</h2>

      <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search guests..." label="Search guests" />

      {searchQ && filteredTabs.length === 0 && !isLoading && (
        <p className="text-sm text-amber-200/40 text-center py-8">No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu</p>
      )}

      {isLoading && <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} variant="row" />)}</div>}

      {!isLoading && tabs.length === 0 && !searchQ && (
        <EmptyState
          icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <path d="M6 20L20 8l14 12v16a2 2 0 01-2 2H8a2 2 0 01-2-2V20z"
              stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
            <rect x="15" y="26" width="10" height="10" rx="1" stroke="currentColor" strokeWidth="1.5"/>
          </svg>}
          title="No villa guests currently checked in."
        />
      )}

      <div className="space-y-2">
        {filteredTabs.map(t => {
          const bal = parseFloat(t.balance)
          return (
            <button key={t.id} onClick={() => navigate(`/pos/tabs/${t.id}`)}
              className="w-full flex items-center justify-between p-4 rounded-2xl border border-amber-200/10
                hover:bg-cream-alt transition-colors text-left">
              <div>
                <p className="font-semibold text-white">{t.reference ?? 'Villa Guest'}</p>
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
            </button>
          )
        })}
      </div>
      </div>
    </div>
  )
}
