import { useEffect, useState } from 'react'
import { Button } from './Button'

// Chrome fires beforeinstallprompt when the app qualifies for install.
// We stash the event and show a polite card instead of an ambush popup.
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
}

const DISMISS_KEY = 'install-dismissed-at'
const COOLDOWN_MS = 7 * 24 * 3600 * 1000 // 7 days

export interface InstallPromptProps {
  // Storage injected by the app (IndexedDB — no localStorage anywhere)
  kvGet: (key: string) => Promise<unknown>
  kvSet: (key: string, value: unknown) => Promise<void>
}

export function InstallPrompt({ kvGet, kvSet }: InstallPromptProps) {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [eligible, setEligible] = useState(false)

  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault()
      setDeferred(e as BeforeInstallPromptEvent)
    }
    window.addEventListener('beforeinstallprompt', onPrompt)
    // Eligible only if not dismissed within the last 7 days
    kvGet(DISMISS_KEY).then((ts) => {
      if (typeof ts !== 'number' || Date.now() - ts > COOLDOWN_MS) setEligible(true)
    })
    return () => window.removeEventListener('beforeinstallprompt', onPrompt)
  }, [kvGet])

  if (!deferred || !eligible) return null

  return (
    <div className="m-4 mb-0 p-4 rounded-2xl border border-cream-alt bg-cream-card
      flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-ink-primary">Add Kurahia to your home screen</p>
        <p className="text-xs text-ink-tertiary mt-0.5">Faster access, works like a real app.</p>
      </div>
      <Button variant="ghost" size="sm"
        onClick={() => { void kvSet(DISMISS_KEY, Date.now()); setEligible(false) }}>
        Not now
      </Button>
      <Button variant="primary" size="sm"
        onClick={() => { void deferred.prompt(); setDeferred(null) }}>
        Install
      </Button>
    </div>
  )
}
