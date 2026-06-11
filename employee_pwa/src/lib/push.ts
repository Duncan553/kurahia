// Web Push subscribe flow. Called only after the user taps Enable —
// never ambush the browser permission popup.
import api from './axios'

// applicationServerKey must be a Uint8Array, not the base64url string
function urlB64ToUint8Array(base64: string): Uint8Array {
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

export function pushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

// Returns true when subscribed and registered with the backend.
export async function enablePush(): Promise<boolean> {
  const { data: cfg } = await api.get<{ configured: boolean; public_key?: string }>(
    '/notifications/push-config'
  )
  if (!cfg.configured || !cfg.public_key) return false // socket dormant — server has no VAPID keys

  if ((await Notification.requestPermission()) !== 'granted') return false

  const reg = await navigator.serviceWorker.ready
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToUint8Array(cfg.public_key).buffer as ArrayBuffer,
    }))

  await api.post('/notifications/push-subscribe', sub.toJSON())
  return true
}
