import { useFontSizePref, type FontSizeKey } from '../lib/fontSizePref'

export default function SettingsScreen() {
  const { size: fontSize, changeSize: changeFontSize } = useFontSizePref()

  return (
    <div className="p-4 max-w-md mx-auto space-y-6">
      <h1 className="text-xl font-bold text-ink-primary">Settings</h1>

      <section>
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
          Text Size
        </p>
        <div className="flex gap-2" role="group" aria-label="Text size">
          {(['S', 'M', 'L'] as FontSizeKey[]).map(key => (
            <button
              key={key}
              onClick={() => void changeFontSize(key)}
              aria-pressed={fontSize === key}
              className={[
                'flex-1 py-2 min-h-[44px] rounded-xl border text-sm font-semibold transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                fontSize === key
                  ? 'bg-ink-primary text-cream-card border-ink-primary'
                  : 'border-cream-alt text-ink-secondary hover:bg-cream-alt',
              ].join(' ')}
            >
              {key}
            </button>
          ))}
        </div>
        <p className="text-xs text-ink-secondary mt-2 px-1">
          Saved automatically. Applies to all text in the app.
        </p>
      </section>
    </div>
  )
}
