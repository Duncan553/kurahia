import { Input } from './Input'

/**
 * The M-Pesa code (or card slip) for a payment, captured where it is taken.
 *
 * Only the villa folio ever asked for one. The four screens where M-Pesa is
 * actually taken most — the waiter's tab, spa and water pay, the gate, and
 * check-in — recorded the payment with no code at all, even though every one
 * of those endpoints already accepts `mpesa_code`.
 *
 * The cost lands on somebody else's desk. The manager's M-Pesa reconciliation
 * lists each payment against the day's statement, and every row read
 * "no reference" — so ticking off KSh 74,750 across 7 payments meant matching
 * on the amount and a guess. The screen was not broken; the one field that
 * makes it usable was never filled in.
 *
 * Deliberately NOT required. A guest is standing there and the transaction
 * message can be slow; blocking the sale to wait for an SMS is worse than a
 * blank reference. The label says why it is wanted instead.
 */
export function PaymentRef({ method, value, onChange, className = '' }: {
  method: string
  value: string
  onChange: (v: string) => void
  className?: string
}) {
  if (method !== 'MPESA' && method !== 'CARD') return null
  const isMpesa = method === 'MPESA'
  return (
    <div className={className}>
      <label htmlFor="payment-ref"
             className="block text-[11px] uppercase tracking-wider text-ink-tertiary mb-1">
        {isMpesa ? 'M-Pesa code' : 'Card slip number'}
        <span className="text-ink-tertiary/70 normal-case tracking-normal"> — optional</span>
      </label>
      <Input
        id="payment-ref"
        value={value}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        placeholder={isMpesa ? 'e.g. SFF7XK2P9Q' : 'last 4 digits or slip no.'}
        autoCapitalize="characters"
        spellCheck={false}
      />
      <p className="text-[11px] text-ink-tertiary mt-1">
        {isMpesa
          ? 'Taken from the guest’s confirmation SMS. Without it this payment cannot be matched against the M-Pesa statement at close of day.'
          : 'Lets this payment be matched against the card settlement.'}
      </p>
    </div>
  )
}
