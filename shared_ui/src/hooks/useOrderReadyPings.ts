import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { playReadyChime } from '../lib/audio'

export interface ReadyPing {
  id: string
  subject: string
  body: string
  reference_type: string
  reference_id: string | null
  created_at_utc?: string
}

/**
 * "Your order is ready" — the waiter's half of the kitchen conversation.
 *
 * The kitchen has always been told when an order arrives: the queue screen
 * polls, and a tone plays for anything new. The other direction was only half
 * built. Marking an item READY does write a notification to the waiter (see
 * _notify_waiter_ready in app/pos/orders.py), so the cook's "Waiter has been
 * notified." was true — but the waiter's end rendered it as a silent card on
 * ONE screen, the Tables list. A waiter is not standing at the Tables list;
 * they are at a table taking the next order, or at the till, or walking. Food
 * sat under the lamp while the only thing that knew was a tablet nobody was
 * looking at.
 *
 * So this lives in the app SHELL, not on a screen: the poll and the chime
 * follow the waiter wherever they are, which is the same reason the kitchen's
 * alert works.
 *
 * Polling, not a socket. A resort LAN with tablets that sleep, wake, and lose
 * the access point mid-shift punishes long-lived connections — a dropped
 * socket that nobody notices is worse than a poll that is a few seconds late,
 * because it fails silently and forever. Ten seconds is the compromise: fast
 * enough that a plate is collected hot, cheap enough that thirty tablets on
 * one router are not a problem. Web Push already fires alongside for a tablet
 * that is asleep.
 */
export function useOrderReadyPings(api: { get: (u: string) => Promise<{ data: unknown }> }) {
  const { data: pings = [] } = useQuery<ReadyPing[]>({
    queryKey: ['notifications', 'inbox'],
    queryFn: () => api.get('/notifications/inbox')
      .then(r => (Array.isArray(r.data) ? r.data as ReadyPing[] : [])),
    refetchInterval: 10_000,
    staleTime: 0,
    retry: false,
    select: (all) => all.filter(n => n.reference_type === 'order_ready'),
  })

  // Chime only for pings that were not there last time.
  //
  // Keyed on the ping id and seeded on the FIRST load, so opening the app with
  // three plates already waiting does not sound three times for news that is
  // not news — the same rule the kitchen queue uses.
  const seen = useRef<Set<string> | null>(null)
  useEffect(() => {
    const ids = new Set(pings.map(p => p.id))
    if (seen.current === null) { seen.current = ids; return }
    if (pings.some(p => !seen.current!.has(p.id))) playReadyChime()
    seen.current = ids
  }, [pings])

  return pings
}
