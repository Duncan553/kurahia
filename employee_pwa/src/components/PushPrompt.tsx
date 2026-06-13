import { useState } from 'react'
import { Button, useToastStore } from '@shared'
import { pushSupported, enablePush } from '../lib/push'

// Quiet card under the install prompt — browser permission popup only
// fires on an explicit Enable tap. Renders nothing once decided.
export default function PushPrompt() {
  const addToast = useToastStore((s) => s.addToast)
  const [hidden, setHidden] = useState(
    () => !pushSupported() || Notification.permission !== 'default'
  )
  const [busy, setBusy] = useState(false)

  if (hidden) return null

  async function onEnable() {
    setBusy(true)
    try {
      const ok = await enablePush()
      if (ok) addToast({ type: 'success', message: 'Notifications enabled.' })
    } catch {
      addToast({ type: 'error', message: 'Could not enable notifications. Try again.' })
    }
    setHidden(true)
  }

  return (
    <div className="m-4 mb-0 p-4 rounded-2xl border border-cream-alt bg-cream-card
      flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-ink-primary">Get notified about shifts and approvals</p>
        <p className="text-xs text-ink-secondary mt-0.5">Even when the app is closed.</p>
      </div>
      <Button variant="ghost" size="sm" onClick={() => setHidden(true)}>Not now</Button>
      <Button variant="primary" size="sm" loading={busy} onClick={onEnable}>Enable</Button>
    </div>
  )
}
