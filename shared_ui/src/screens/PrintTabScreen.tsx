/**
 * The paper a guest walks away with.
 *
 * Two documents, one layout, decided by what is still owed:
 *   BILL    — money outstanding. "Please pay", no payment lines yet.
 *   RECEIPT — settled. Proof of payment, with what was paid and how.
 *
 * Sized for an 80mm thermal roll (the printer a resort till actually has), but
 * it is ordinary HTML, so an A4 sheet or a PDF "printer" works the same. The
 * backend's A4 PDF at GET /reports/receipt/:tab_id still exists for the office
 * copy; it is front-desk-only and closed-tabs-only, which is why it could never
 * be the thing a waiter hands over at the table.
 */
import { useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/axios'

interface Tab {
  id: string; reference: string | null; status: string; balance: string | null
  service_view?: boolean
  opened_at?: string; opened_by?: string | null; tab_type?: string
  charges: { id: string; description: string; amount: string }[]
  payments: { id: string; method: string; amount: string; created_at?: string; received_by?: string | null }[]
}

const money = (v: string | number) =>
  Number(v).toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function PrintTabScreen() {
  const { tabId } = useParams()
  const navigate = useNavigate()
  // The print dialog is modal: it freezes the page under it. Opening the
  // printer automatically is right when a till taps "Print" (?print=1) and
  // wrong when someone opens the link to look at it — including any tool
  // driving the browser, which simply hangs there.
  const [params] = useSearchParams()
  const autoPrint = params.get('print') === '1'

  const { data: tab, isLoading, error } = useQuery<Tab>({
    queryKey: ['print-tab', tabId],
    queryFn: () => api.get<Tab>(`/tabs/${tabId}`).then(r => r.data),
    enabled: !!tabId,
  })

  // Print as soon as the numbers are on the page. The small delay lets the
  // browser lay the text out first — print too early and the dialog captures a
  // half-rendered page.
  useEffect(() => {
    if (!tab || !autoPrint) return
    const t = setTimeout(() => window.print(), 500)
    return () => clearTimeout(t)
  }, [tab, autoPrint])

  if (isLoading) return <p style={{ padding: 24, fontFamily: 'monospace' }}>Loading the bill…</p>
  if (error || !tab) return (
    <div style={{ padding: 24, fontFamily: 'monospace' }}>
      <p>That bill could not be opened. It may belong to another till.</p>
      <button onClick={() => navigate(-1)}>← Back</button>
    </div>
  )

  const total = tab.charges.reduce((s, c) => s + Number(c.amount), 0)
  const paid = tab.payments.reduce((s, p) => s + Number(p.amount), 0)
  const balance = tab.balance === null ? total - paid : Number(tab.balance)
  const settled = balance <= 0
  const isBand = tab.tab_type === 'BAND'
  const now = new Date()

  return (
    <>
      <style>{`
        /* 80mm roll. The browser's own margins are the enemy on a thermal
           printer — @page takes them to nothing and the receipt keeps its own. */
        @page { size: 80mm auto; margin: 0; }
        @media print {
          body { background: #fff !important; }
          .no-print { display: none !important; }
          .receipt { box-shadow: none !important; margin: 0 !important; }
        }
        .receipt {
          width: 76mm; margin: 12px auto; padding: 4mm 3mm;
          background: #fff; color: #000;
          font-family: "Courier New", ui-monospace, monospace; font-size: 11px; line-height: 1.45;
        }
        .receipt h1 { font-size: 15px; letter-spacing: 2px; margin: 0; text-align: center; }
        .receipt .sub { text-align: center; font-size: 10px; margin: 2px 0 8px; }
        .receipt .kind { text-align: center; font-weight: bold; letter-spacing: 3px;
                         border-top: 1px dashed #000; border-bottom: 1px dashed #000;
                         padding: 3px 0; margin: 8px 0; }
        .receipt .row { display: flex; justify-content: space-between; gap: 8px; }
        .receipt .row span:last-child { white-space: nowrap; }
        .receipt .items { border-top: 1px dashed #000; margin-top: 6px; padding-top: 6px; }
        .receipt .total { border-top: 1px solid #000; margin-top: 6px; padding-top: 6px; font-weight: bold; }
        .receipt .foot { text-align: center; margin-top: 10px; border-top: 1px dashed #000; padding-top: 6px; font-size: 10px; }
      `}</style>

      <div className="no-print" style={{ textAlign: 'center', padding: '10px', fontFamily: 'sans-serif' }}>
        <button onClick={() => window.print()} style={{ padding: '10px 18px', marginRight: 8 }}>Print again</button>
        <button onClick={() => navigate(-1)} style={{ padding: '10px 18px' }}>← Back to the till</button>
      </div>

      <div className="receipt">
        <h1>WATERFRONT JUJA</h1>
        <p className="sub">Juja Farm, Kiambu<br />Tel 0712 000 000</p>

        <div className="kind">{settled ? 'RECEIPT' : 'BILL'}</div>

        <div className="row"><span>{tab.reference ?? 'Walk-in'}</span><span>#{tab.id.slice(0, 8)}</span></div>
        <div className="row"><span>{now.toLocaleDateString('en-KE')}</span><span>{now.toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })}</span></div>
        {tab.opened_by && <div className="row"><span>Served by</span><span>{tab.opened_by}</span></div>}

        <div className="items">
          {tab.charges.length === 0 && <p>Nothing has been charged yet.</p>}
          {tab.charges.map(c => (
            <div className="row" key={c.id}>
              <span>{c.description}</span>
              <span>{money(c.amount)}</span>
            </div>
          ))}
        </div>

        <div className="row total"><span>TOTAL</span><span>KSh {money(total)}</span></div>

        {/* On a wristband the money was paid at the gate before anything was
            bought, so it is not a "payment" at the bottom of the bill — it is
            credit coming OFF the total. A guest looking at 3,500 of jet ski
            must see the 3,000 they already handed over, and the 500 they still
            owe, on the same piece of paper. */}
        {tab.payments.length > 0 && (
          <div className="items">
            {/* How the bill was handled, not just that it was: the method, the
                time and the person who took it. A guest querying a charge next
                week, and the manager checking a till, are asking the same
                question of this line. */}
            {tab.payments.map(p => (
              <div key={p.id}>
                <div className="row">
                  <span>{isBand ? 'Less — wristband credit' : `Paid — ${p.method}`}</span>
                  <span>−{money(p.amount)}</span>
                </div>
                {(p.created_at || p.received_by) && (
                  <div className="row" style={{ fontSize: 9, opacity: 0.75 }}>
                    <span>
                      {p.created_at ? new Date(p.created_at).toLocaleString('en-KE',
                        { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
                      {isBand ? ` · ${p.method}` : ''}
                    </span>
                    <span>{p.received_by ?? ''}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="row total">
          <span>{settled ? (isBand ? 'COVERED BY THE BAND' : 'PAID IN FULL') : 'STILL TO PAY'}</span>
          <span>KSh {money(settled ? paid : balance)}</span>
        </div>

        {/* A band that has not spent everything is walking around with money on
            it. Say so on the paper — the guest can spend it or lose it. */}
        {isBand && balance < 0 && (
          <div className="row"><span>Credit still on the band</span><span>KSh {money(-balance)}</span></div>
        )}

        <div className="foot">
          {settled
            ? <>Asante sana — karibu tena.</>
            : <>Not yet paid. Settle at the till or at front desk.</>}
          <br />Prices include VAT where it applies.
        </div>
      </div>
    </>
  )
}
