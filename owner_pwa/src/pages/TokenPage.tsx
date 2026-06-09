/**
 * TokenPage — F-1 gate verification page.
 * Proves all design tokens render correctly before real components are built.
 * Remove once F-2 components are wired.
 */

interface Swatch {
  token: string;
  hex: string;
  bg: string;
  lightText: boolean;
}

interface Palette {
  name: string;
  swatches: Swatch[];
}

const PALETTES: Palette[] = [
  {
    name: 'System',
    swatches: [
      { token: '--color-sage-main',      hex: '#9CB39A', bg: 'bg-sage-main',      lightText: false },
      { token: '--color-sage-light',     hex: '#B8C8B0', bg: 'bg-sage-light',     lightText: false },
      { token: '--color-sage-dark',      hex: '#7A9374', bg: 'bg-sage-dark',      lightText: false },
      { token: '--color-cream-card',     hex: '#F2EBDD', bg: 'bg-cream-card',     lightText: false },
      { token: '--color-cream-alt',      hex: '#EBE2CE', bg: 'bg-cream-alt',      lightText: false },
      { token: '--color-ink-primary',    hex: '#2A2620', bg: 'bg-ink-primary',    lightText: true  },
      { token: '--color-ink-secondary',  hex: '#5C5147', bg: 'bg-ink-secondary',  lightText: true  },
      { token: '--color-ink-tertiary',   hex: '#8C7E6F', bg: 'bg-ink-tertiary',   lightText: false },
    ],
  },
  {
    name: 'Ticket',
    swatches: [
      { token: '--color-ticket-paper',   hex: '#EFE6D2', bg: 'bg-ticket-paper',   lightText: false },
      { token: '--color-ticket-alt',     hex: '#E5DAC1', bg: 'bg-ticket-alt',     lightText: false },
      { token: '--color-ticket-ink',     hex: '#1F1B14', bg: 'bg-ticket-ink',     lightText: true  },
      { token: '--color-stamp-red',      hex: '#9A3E32', bg: 'bg-stamp-red',      lightText: true  },
      { token: '--color-leaf-green',     hex: '#708A4F', bg: 'bg-leaf-green',     lightText: true  },
      { token: '--color-tea-brown',      hex: '#6B4A2E', bg: 'bg-tea-brown',      lightText: true  },
    ],
  },
  {
    name: 'Status',
    swatches: [
      { token: '--color-status-paid',    hex: '#4A7A4A', bg: 'bg-status-paid',    lightText: true  },
      { token: '--color-status-pending', hex: '#B88838', bg: 'bg-status-pending', lightText: false },
      { token: '--color-status-failed',  hex: '#A04438', bg: 'bg-status-failed',  lightText: true  },
      { token: '--color-status-neutral', hex: '#4A7889', bg: 'bg-status-neutral', lightText: true  },
    ],
  },
];

const TYPE_SCALE: { label: string; px: number; twClass: string }[] = [
  { label: '12px  · text-xs',   px: 12, twClass: 'text-xs'   },
  { label: '14px  · text-sm',   px: 14, twClass: 'text-sm'   },
  { label: '16px  · text-base', px: 16, twClass: 'text-base' },
  { label: '20px  · text-xl',   px: 20, twClass: 'text-xl'   },
  { label: '25px  · text-2xl',  px: 25, twClass: 'text-2xl'  },
  { label: '31px  · text-3xl',  px: 31, twClass: 'text-3xl'  },
  { label: '39px  · text-4xl',  px: 39, twClass: 'text-4xl'  },
  { label: '49px  · text-5xl',  px: 49, twClass: 'text-5xl'  },
];

const WEIGHTS: { label: string; tw: string }[] = [
  { label: '400 — Regular', tw: 'font-normal' },
  { label: '500 — Medium',  tw: 'font-medium' },
  { label: '700 — Bold',    tw: 'font-bold'   },
];

export default function TokenPage() {
  return (
    <div className="min-h-screen bg-cream-card font-sans text-ink-primary p-8">
      <header className="mb-12 border-b border-ink-tertiary pb-6">
        <p className="text-sm tracking-wide text-ink-secondary uppercase mb-1">
          Kurahia · Phase F-1 Gate
        </p>
        <h1 className="text-4xl font-bold">Design Token Reference</h1>
        <p className="text-base text-ink-secondary mt-2">
          All 18 colour swatches · 8 type sizes · 3 weights · tabular-nums demo
        </p>
      </header>

      {/* ── Colour palettes ───────────────────────────────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          Colour Tokens
        </h2>
        {PALETTES.map((palette) => (
          <div key={palette.name} className="mb-8">
            <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-3">
              {palette.name} Palette
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {palette.swatches.map((s) => (
                <div
                  key={s.token}
                  className={`${s.bg} rounded-lg p-4 h-24 flex flex-col justify-end`}
                >
                  <p
                    className={`text-xs font-mono font-medium leading-tight ${
                      s.lightText ? 'text-cream-card' : 'text-ink-primary'
                    }`}
                  >
                    {s.token.replace('--color-', '')}
                  </p>
                  <p
                    className={`text-xs font-mono tabular-nums ${
                      s.lightText ? 'text-cream-alt' : 'text-ink-secondary'
                    }`}
                  >
                    {s.hex}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      {/* ── Type scale — Inter (sans) ─────────────────────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          Type Scale — Inter (font-sans)
        </h2>
        <div className="space-y-6">
          {TYPE_SCALE.map(({ label, twClass }) => (
            <div key={label} className="border-b border-cream-alt pb-4">
              <p className="text-xs tracking-widest uppercase text-ink-tertiary mb-2 font-mono">
                {label}
              </p>
              <div className="space-y-1">
                {WEIGHTS.map(({ label: wLabel, tw }) => (
                  <p
                    key={wLabel}
                    className={`${twClass} ${tw} font-sans text-ink-primary leading-tight`}
                  >
                    {wLabel} — The quick brown fox
                  </p>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Type scale — Cormorant Garamond (serif) ───────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          Type Scale — Cormorant Garamond (font-serif)
        </h2>
        <div className="space-y-6">
          {TYPE_SCALE.map(({ label, twClass }) => (
            <div key={label} className="border-b border-cream-alt pb-4">
              <p className="text-xs tracking-widest uppercase text-ink-tertiary mb-2 font-mono font-sans">
                {label}
              </p>
              <div className="space-y-1">
                {WEIGHTS.map(({ label: wLabel, tw }) => (
                  <p
                    key={wLabel}
                    className={`${twClass} ${tw} font-serif text-ink-primary leading-tight`}
                  >
                    {wLabel} — The quick brown fox
                  </p>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Tabular-nums demo ────────────────────────────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          tabular-nums Demo
        </h2>
        <div className="bg-cream-alt rounded-lg p-6 space-y-4">
          <div>
            <p className="text-xs tracking-widest uppercase text-ink-tertiary mb-2 font-mono">
              Inter (font-sans)
            </p>
            <p className="text-2xl font-medium font-sans tabular-nums text-ink-primary">
              1,234,567.89
            </p>
            <p className="text-xl font-normal font-sans tabular-nums text-ink-secondary">
              KES 1,234,567.89
            </p>
          </div>
          <div>
            <p className="text-xs tracking-widest uppercase text-ink-tertiary mb-2 font-mono">
              Cormorant Garamond (font-serif)
            </p>
            <p className="text-2xl font-medium font-serif tabular-nums text-ink-primary">
              1,234,567.89
            </p>
            <p className="text-xl font-normal font-serif tabular-nums text-ink-secondary">
              KES 1,234,567.89
            </p>
          </div>
        </div>
      </section>

      {/* ── Responsive breakpoint probe ──────────────────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          Responsive Breakpoints
        </h2>
        <div className="rounded-lg overflow-hidden border border-cream-alt text-sm font-mono">
          <div className="bg-ink-primary text-cream-card p-3 block sm:hidden">
            &lt; 640px — base (no prefix)
          </div>
          <div className="hidden sm:block md:hidden bg-sage-dark text-cream-card p-3">
            640px–767px — sm:
          </div>
          <div className="hidden md:block lg:hidden bg-sage-main text-ink-primary p-3">
            768px–1023px — md:
          </div>
          <div className="hidden lg:block xl:hidden bg-sage-light text-ink-primary p-3">
            1024px–1279px — lg:
          </div>
          <div className="hidden xl:block bg-cream-card text-ink-primary p-3">
            ≥ 1280px — xl:
          </div>
        </div>
      </section>

      <footer className="text-xs text-ink-tertiary pt-6 border-t border-cream-alt">
        F-1 token page · Remove before F-2 ships
      </footer>
    </div>
  );
}
