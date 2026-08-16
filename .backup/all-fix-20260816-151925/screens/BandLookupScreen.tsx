import { useState } from 'react'
import { useToastStore } from '@shared'
import api from '../lib/axios'

interface BandResult {
  id: string
  band_number: number
  issue_date: string
  status: string
  tab_id: string
  tab_balance: string
  issued_by: string | null
  issued_at: string
  notes: string | null
}

function StatusDot({ status }: { status: string }) {
  const s = status.toUpperCase()
  if (s === 'ACTIVE')    return <span className="inline-block w-2 h-2 rounded-full bg-status-paid mr-1.5" />
  if (s === 'FORFEITED') return <span className="inline-block w-2 h-2 rounded-full bg-status-failed mr-1.5" />
  return <span className="inline-block w-2 h-2 rounded-full bg-status-pending mr-1.5" />
}

export default function BandLookupScreen() {
  const addToast = useToastStore((s) => s.addToast)
  const [input,   setInput]   = useState('')
  const [loading, setLoading] = useState(false)
  const [result,  setResult]  = useState<BandResult | null>(null)
  const [notFound, setNotFound] = useState(false)

  async function lookup() {
    const num = parseInt(input.trim(), 10)
    if (!num || num <= 0) {
      addToast({ type: 'error', message: 'Enter a valid band number.' })
      return
    }
    setLoading(true)
    setResult(null)
    setNotFound(false)
    try {
      const r = await api.get<BandResult>(`/gate/bands/${num}`)
      setResult(r.data)
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 404) {
        setNotFound(true)
      } else {
        const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
          ?? 'Lookup failed. Check connection.'
        addToast({ type: 'error', message: msg })
      }
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') lookup()
  }

  async function deactivate() {
    if (!result) return
    setLoading(true)
    try {
      const r = await api.post<BandResult>(`/gate/deactivate-band/${result.band_number}`)
      setResult(r.data)
      addToast({ type: 'success', message: `Band #${result.band_number} deactivated.` })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Could not deactivate the band.'
      addToast({ type: 'error', message: msg })
    } finally {
      setLoading(false)
    }
  }

  const balance = result ? parseFloat(result.tab_balance) : 0

  return (
    <div className="p-4 max-w-3xl mx-auto space-y-5">

      <div>
        <h1 className="text-2xl font-bold text-[#f9dcd5] font-serif">Band Lookup</h1>
        <p className="text-xs text-ink-tertiary mt-0.5">Search wristbands by number</p>
      </div>

      {/* ── Search ───────────────────────────────────────────────── */}
      <div className="flex gap-2">
        <input
          type="number"
          min="1"
          inputMode="numeric"
          placeholder="Band number…"
          value={input}
          onChange={(e) => { setInput(e.target.value); setResult(null); setNotFound(false) }}
          onKeyDown={handleKey}
          className="flex-1 rounded-xl glass-card bg-transparent px-4 py-3
            text-lg font-semibold tabular-nums text-[#f9dcd5]
            focus:outline-none focus:border-[#fa5c29] focus:ring-2 focus:ring-primary-dark/20"
        />
        <button
          onClick={lookup}
          disabled={loading || !input.trim()}
          className={[
            'px-5 py-3 rounded-xl bg-[#fa5c29] text-white font-semibold text-sm',
            'hover:bg-[#af3000] transition-all shrink-0',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
          ].join(' ')}
        >
          {loading ? (
            <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
              <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          ) : 'Search'}
        </button>
      </div>

      {/* ── Not found ────────────────────────────────────────────── */}
      {notFound && (
        <div className="rounded-xl bg-status-failed/5 border border-status-failed/20 p-4 text-center">
          <p className="text-sm font-medium text-status-failed">
            Band #{input} not found for today.
          </p>
          <p className="text-xs text-ink-tertiary mt-1">
            Check the number is correct or try a different date.
          </p>
        </div>
      )}

      {/* ── Result ───────────────────────────────────────────────── */}
      {result && (
        <div className="rounded-2xl glass-card bg-transparent shadow-sm overflow-hidden">

          {/* Header */}
          <div className="bg-[#fa5c29]/10 px-5 py-4 flex items-center justify-between">
            <div>
              <p className="text-2xl font-bold tabular-nums text-[#f9dcd5]">
                Band #{result.band_number}
              </p>
              <p className="text-xs text-ink-tertiary mt-0.5 flex items-center">
                <StatusDot status={result.status} />
                {result.status.charAt(0) + result.status.slice(1).toLowerCase()}
                {' · '}
                {result.issue_date}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-ink-tertiary mb-0.5">Tab balance</p>
              <p className={[
                'text-2xl font-bold tabular-nums',
                balance > 0 ? 'text-status-failed' : 'text-status-paid',
              ].join(' ')}>
                KES {balance.toLocaleString()}
              </p>
            </div>
          </div>

          {/* Details */}
          <div className="px-5 py-4 space-y-2.5">
            {[
              { label: 'Tab ID',     value: result.tab_id },
              { label: 'Issued by',  value: result.issued_by ?? '—' },
              { label: 'Issued at',  value: new Date(result.issued_at).toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' }) },
              ...(result.notes ? [{ label: 'Notes', value: result.notes }] : []),
            ].map(({ label, value }) => (
              <div key={label} className="flex justify-between text-sm">
                <span className="text-ink-tertiary">{label}</span>
                <span className="text-[#f9dcd5] font-medium truncate max-w-[55%] text-right">{value}</span>
              </div>
            ))}
          </div>

          {balance > 0 && (
            <div className="px-5 py-4 border-t border-white/10 bg-status-failed/5">
              <p className="text-xs text-status-failed font-medium">
                Outstanding balance — guest must settle before leaving.
              </p>
            </div>
          )}

          {/* Guest leaving — close the band. Backend refuses if balance > 0. */}
          {result.status.toUpperCase() === 'ACTIVE' && (
            <div className="px-5 py-3 border-t border-white/10">
              <button
                onClick={deactivate}
                disabled={loading}
                className="w-full py-3 rounded-xl text-sm font-semibold border border-status-failed/40
                  text-status-failed hover:bg-status-failed/5 disabled:opacity-50 transition-colors">
                Deactivate Band — guest leaving
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
