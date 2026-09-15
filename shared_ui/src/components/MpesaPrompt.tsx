import { useState } from 'react'
import { Button } from './Button'

/**
 * The M-Pesa prompt: the guest approves on their own phone.
 *
 * Two ways exist to take M-Pesa. The guest pushes to the paybill and reads a
 * code back to the till, or the till pushes a prompt to the guest's phone and
 * Safaricom confirms it back to us. The second is better on both sides of the
 * counter: nothing is typed in from a screen the till cannot see, and the
 * payment arrives already matched instead of waiting for the manager to tick
 * it off a statement.
 *
 * Three rules this component exists to hold, because the first version of the
 * prompt broke all three:
 *
 * 1. NEVER offer it when the socket is dormant. Offering it unconditionally
 *    created the Payment row, failed the charge, and left the bill reading
 *    SETTLED with no money behind it. `canPrompt` comes from
 *    GET /finance/mpesa/status, and the fallback sentence is shown instead.
 * 2. Check again at the tap, not only at render — the socket can be switched
 *    off while this screen sits open. That guard lives in the caller's
 *    mutation, where the payment row is created.
 * 3. Say what happens next. "Send prompt" means a phone lights up in the
 *    guest's hand; the copy says so, so nobody taps it twice.
 */
export function MpesaPrompt({ canPrompt, amount, sending, onSend }: {
  canPrompt: boolean
  /** What will be charged. Guards against sending a prompt for nothing. */
  amount: number
  sending: boolean
  onSend: (phone: string) => void
}) {
  const [phone, setPhone] = useState('')

  if (!canPrompt) {
    // Deliberately NOT the server's own message. /finance/mpesa/status answers
    // with a setup diagnostic — "Daraja socket dormant — missing env vars:
    // MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, ..." — and piping that
    // through put a list of environment variables on a gate attendant's
    // screen while a guest stood in front of them. The person at the till
    // needs the one sentence that tells them what to do instead; the env
    // vars are for whoever sets the server up, and that endpoint still
    // carries them for exactly that reader.
    return (
      <p className="text-[11px] text-ink-tertiary">
        Phone prompts are not switched on yet — ask the guest to pay the
        paybill and type their M-Pesa code below.
      </p>
    )
  }

  return (
    <div className="rounded-xl glass-surface p-3 space-y-2">
      <p className="text-[11px] uppercase tracking-wider text-ink-tertiary">
        Ask the guest to approve on their phone
      </p>
      <div className="flex gap-2">
        <input
          type="tel" inputMode="tel"
          aria-label="Guest phone number for the M-Pesa prompt"
          placeholder="07xx xxx xxx"
          value={phone}
          onChange={e => setPhone(e.target.value)}
          className="flex-1 min-w-0 rounded-xl glass-card bg-transparent px-3 py-2
            text-sm text-ink-primary focus:outline-none focus:border-primary-main"
        />
        <Button
          variant="primary" size="sm"
          loading={sending}
          disabled={!phone.trim() || !(amount > 0)}
          onClick={() => onSend(phone.trim())}
        >
          Send prompt
        </Button>
      </div>
      <p className="text-[11px] text-ink-tertiary">
        They enter their M-Pesa PIN and Safaricom confirms it back — nothing to
        type in afterwards.
      </p>
    </div>
  )
}
