import { useQuery } from '@tanstack/react-query'

/**
 * Is the M-Pesa prompt route switched on at this till?
 *
 * Asked BEFORE the button is drawn, never assumed. The socket is dormant
 * until the resort's own Daraja credentials are in the environment, and a
 * till that offers a prompt it cannot send records money that never moved.
 *
 * Takes the app's own axios instance rather than importing one, because the
 * three PWAs each carry their own (different base URL, different token store).
 */
export function useMpesaPrompt(api: { get: (u: string) => Promise<{ data: unknown }> }) {
  const { data } = useQuery<{ configured: boolean; message: string }>({
    queryKey: ['mpesa-status'],
    queryFn: () => api.get('/finance/mpesa/status').then(r => r.data as { configured: boolean; message: string }),
    // The answer changes when the resort activates the socket — once, not
    // hourly. Five minutes is already generous; a retry loop would not be.
    staleTime: 5 * 60_000,
    retry: false,
  })
  return { canPrompt: data?.configured === true, message: data?.message }
}
