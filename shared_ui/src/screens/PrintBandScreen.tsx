/**
 * The wristband slip printed at the gate.
 *
 * The band number is the guest's account for the day: every till charges
 * against it, and at the gate on the way out it is closed and whatever credit
 * is left is forfeited. Until now that number lived only on a screen — the
 * guest walked in with nothing in their hand, and the gate had to remember or
 * write it down.
 *
 * What is on the paper:
 *   · the number, big enough to read across a counter
 *   · a Code 39 barcode of the same number, so a KSh 3,000 USB scanner can type
 *     it into Band Lookup instead of someone keying four digits wet-handed
 *   · what was loaded, when, and by whom
 *   · the terms, in the words a guest can argue with
 *
 * "Killed once used" is not a property of the paper: the band is closed with
 * Close Band on the lookup screen (POST /gate/deactivate-band/:n), and a
 * DEACTIVATED or FORFEITED band is refused by every till. This slip is what
 * makes that possible at the gate — scan, see, close.
 */
import { useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/axios'
import { code39 } from '../lib/code39'

interface Band {
  band_number: number
  issue_date: string
  issued_at: string
  issued_by: string | null
  status: string
  tab_balance: string
  paid_in?: string
  spent?: string
  tab_id: string
}

const money = (v: number) =>
  v.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function PrintBandScreen() {
  const { bandNumber } = useParams()
  const navigate = useNavigate()
  // The print dialog is modal: it freezes the page under it. Opening the
  // printer automatically is right when a till taps "Print" (?print=1) and
  // wrong when someone opens the link to look at it — including any tool
  // driving the browser, which simply hangs there.
  const [params] = useSearchParams()
  const autoPrint = params.get('print') === '1'

  const { data: band, isLoading, error } = useQuery<Band>({
    queryKey: ['print-band', bandNumber],
    queryFn: () => api.get<Band>(`/gate/bands/${bandNumber}`).then(r => r.data),
    enabled: !!bandNumber,
  })

  useEffect(() => {
    if (!band || !autoPrint) return
    const t = setTimeout(() => window.print(), 500)
    return () => clearTimeout(t)
  }, [band, autoPrint])

  if (isLoading) return <p style={{ padding: 24, fontFamily: 'monospace' }}>Loading band…</p>
  if (error || !band) return (
    <div style={{ padding: 24, fontFamily: 'monospace' }}>
      <p>No band with that number was issued today.</p>
      <button onClick={() => navigate(-1)}>← Back</button>
    </div>
  )

  // tab_balance is charges minus payments: the entry fee is a payment, so a
  // fresh band sits at −3,000 and that minus sign IS the credit.
  // Three numbers, and they must always add up on the paper:
  //   paid in (the KSh 3,000 entry fee, plus any top-up)
  // − spent   (everything charged to the band today)
  // = credit left, or what is owed at the gate on the way out.
  const bal    = Number(band.tab_balance)       // charges − payments
  const paidIn = Number(band.paid_in ?? 0)
  const spent  = Number(band.spent ?? 0)
  const credit = bal < 0 ? -bal : 0
  const owed   = bal > 0 ? bal : 0
  const bars = code39(String(band.band_number))
  const issued = new Date(band.issued_at)

  return (
    <>
      <style>{`
        @page { size: 80mm auto; margin: 0; }
        @media print {
          body { background: #fff !important; }
          .no-print { display: none !important; }
          .slip { box-shadow: none !important; margin: 0 !important; }
        }
        .slip {
          width: 76mm; margin: 12px auto; padding: 4mm 3mm;
          background: #fff; color: #000;
          font-family: "Courier New", ui-monospace, monospace; font-size: 11px; line-height: 1.45;
          text-align: center;
        }
        .slip h1 { font-size: 14px; letter-spacing: 2px; margin: 0; }
        .slip .num { font-size: 56px; font-weight: bold; line-height: 1; margin: 6px 0 2px; letter-spacing: 2px; }
        .slip .bars { display: flex; align-items: flex-end; justify-content: center; height: 46px; margin: 6px 0 2px; }
        .slip .row { display: flex; justify-content: space-between; text-align: left; gap: 8px; }
        .slip .box { border-top: 1px dashed #000; border-bottom: 1px dashed #000; padding: 4px 0; margin: 8px 0; }
        .slip .terms { text-align: left; font-size: 10px; margin-top: 8px; border-top: 1px dashed #000; padding-top: 6px; }
      `}</style>

      <div className="no-print" style={{ textAlign: 'center', padding: '10px', fontFamily: 'sans-serif' }}>
        <button onClick={() => window.print()} style={{ padding: '10px 18px', marginRight: 8 }}>Print again</button>
        <button onClick={() => navigate(-1)} style={{ padding: '10px 18px' }}>← Back to the gate</button>
      </div>

      <div className="slip">
        <h1>WATERFRONT JUJA</h1>
        <p style={{ margin: '2px 0 0', fontSize: 10 }}>DAY PASS · WRISTBAND</p>

        <div className="num">{band.band_number}</div>

        {/* Code 39: bars and spaces, narrow 2px / wide 6px. */}
        <div className="bars" aria-label={`Barcode for band ${band.band_number}`}>
          {bars.map((b, i) => (
            <div key={i} style={{
              width: b.wide ? 6 : 2,
              height: '100%',
              background: b.bar ? '#000' : 'transparent',
            }} />
          ))}
        </div>
        <p style={{ margin: 0, fontSize: 10, letterSpacing: 3 }}>*{band.band_number}*</p>

        {/* One line, and it must be true on a reprint as well as at issue.
            "Loaded" was printing the credit REMAINING under a label that means
            the entry fee — a band that had spent its 3,000 said "Loaded 0.00".
            The gate API returns the balance, not the fee, so print the balance
            and name it correctly. */}
        <div className="box">
          <div className="row"><span>Paid in</span><span>KSh {money(paidIn)}</span></div>
          <div className="row"><span>Spent</span><span>− KSh {money(spent)}</span></div>
          {owed > 0
            ? <div className="row" style={{ fontWeight: 'bold' }}>
                <span>Owing at the gate</span><span>KSh {money(owed)}</span>
              </div>
            : <div className="row" style={{ fontWeight: 'bold' }}>
                <span>Credit left</span><span>KSh {money(credit)}</span>
              </div>}
          <div className="row"><span>Status</span><span>{band.status}</span></div>
        </div>

        <div className="row"><span>{issued.toLocaleDateString('en-KE')}</span><span>{issued.toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })}</span></div>
        {band.issued_by && <div className="row"><span>Issued by</span><span>{band.issued_by}</span></div>}

        <div className="terms">
          One person, one band. Not transferable.<br />
          Buy anything on the property with this number — food, drinks, the boat,
          the spa — it comes off the credit.<br />
          Hand it in at the gate on your way out. Unspent credit is not refunded.<br />
          Lost band? Report it at the gate at once — it is closed on the spot.
        </div>
      </div>
    </>
  )
}
