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

  return (
    <div className="p-4 max-w-lg mx-auto space-y-4">
      <h1 className="text-xl font-bold font-serif text-ink-primary">Villa Guests</h1>

      <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search guests..." label="Search guests" />

      {searchQ && filteredTabs.length === 0 && !isLoading && (
        <p className="text-sm text-ink-tertiary text-center py-8">No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu</p>
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
              className="w-full flex items-center justify-between p-4 rounded-2xl glass-card glass-shine
                hover:bg-cream-alt transition-colors text-left">
              <div>
                <p className="font-semibold text-ink-primary">{t.reference ?? 'Villa Guest'}</p>
                <p className="text-xs text-ink-tertiary mt-0.5">
                  Checked in {new Date(t.opened_at).toLocaleDateString('en-KE')}
                  {t.opened_by ? ` · by ${t.opened_by}` : ''}
                </p>
              </div>
              <div className="text-right">
                <p className={`text-sm font-bold tabular-nums ${bal > 0 ? 'text-status-failed' : 'text-status-paid'}`}>
                  {kes(t.balance)}
                </p>
                <p className="text-[10px] text-ink-tertiary">{bal > 0 ? 'outstanding' : 'settled'}</p>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
