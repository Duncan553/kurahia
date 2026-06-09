/**
 * TokenPage — F-1 through F-4 gate verification page.
 * Proves design tokens, primitives, containers, and feedback components render correctly.
 * Remove once F-4 gate is signed off.
 */
import { useState } from 'react'
import { Button, Input, Select, Toggle, Card, Modal, Drawer, ToastContainer, useToastStore,
  StatusBadge, Skeleton, Spinner, EmptyState } from '@shared'
import type { StatusValue } from '@shared'

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
      { token: '--color-primary-main',      hex: '#9CB39A', bg: 'bg-primary-main',      lightText: false },
      { token: '--color-primary-light',     hex: '#B8C8B0', bg: 'bg-primary-light',     lightText: false },
      { token: '--color-primary-dark',      hex: '#7A9374', bg: 'bg-primary-dark',      lightText: false },
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

const TYPE_SCALE: { label: string; twClass: string }[] = [
  { label: '12px  · text-xs',   twClass: 'text-xs'   },
  { label: '14px  · text-sm',   twClass: 'text-sm'   },
  { label: '16px  · text-base', twClass: 'text-base' },
  { label: '20px  · text-xl',   twClass: 'text-xl'   },
  { label: '25px  · text-2xl',  twClass: 'text-2xl'  },
  { label: '31px  · text-3xl',  twClass: 'text-3xl'  },
  { label: '39px  · text-4xl',  twClass: 'text-4xl'  },
  { label: '49px  · text-5xl',  twClass: 'text-5xl'  },
];

const WEIGHTS: { label: string; tw: string }[] = [
  { label: '400 — Regular', tw: 'font-normal' },
  { label: '500 — Medium',  tw: 'font-medium' },
  { label: '700 — Bold',    tw: 'font-bold'   },
];

const DEPT_OPTIONS = [
  { value: 'kitchen', label: 'Kitchen' },
  { value: 'bar',     label: 'Bar'     },
  { value: 'gate',    label: 'Gate'    },
  { value: 'hr',      label: 'HR'      },
]

export default function TokenPage() {
  const [inputVal, setInputVal]   = useState('')
  const [dept, setDept]           = useState('')
  const [toggle1, setToggle1]     = useState(false)
  const [toggle2, setToggle2]     = useState(true)
  const [loading, setLoading]     = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false)
  const addToast = useToastStore((s) => s.addToast)

  function simulateLoad() {
    setLoading(true)
    setTimeout(() => setLoading(false), 2000)
  }

  return (
    <div className="min-h-screen bg-cream-card font-sans text-ink-primary p-8">
      <ToastContainer />

      <header className="mb-12 border-b border-ink-tertiary pb-6">
        <p className="text-sm tracking-wide text-ink-secondary uppercase mb-1">
          Kurahia · Phase F-1/F-2/F-3 Gate
        </p>
        <h1 className="text-4xl font-bold">Design Token + Component Reference</h1>
        <p className="text-base text-ink-secondary mt-2">
          18 colour swatches · 8 type sizes · 3 weights · 8 components
        </p>
      </header>

      {/* ── Component Primitives ───────────────────────────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          Component Primitives
        </h2>

        {/* Button */}
        <div className="mb-8">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">Button</h3>
          <div className="flex flex-wrap gap-3 mb-3">
            <Button variant="primary"   size="sm">Primary sm</Button>
            <Button variant="primary"   size="md">Primary md</Button>
            <Button variant="primary"   size="lg">Primary lg</Button>
          </div>
          <div className="flex flex-wrap gap-3 mb-3">
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button disabled>Disabled</Button>
            <Button loading={loading} onClick={simulateLoad}>
              {loading ? 'Saving…' : 'Loading demo (click)'}
            </Button>
          </div>
        </div>

        {/* Input */}
        <div className="mb-8 max-w-sm space-y-4">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">Input</h3>
          <Input
            label="Guest name"
            placeholder="Enter name…"
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            maxLength={30}
          />
          <Input
            label="Password"
            type="password"
            error="Must be at least 8 characters"
          />
          <Input
            label="Phone"
            type="tel"
            disabled
            placeholder="+254 712 345 678"
          />
        </div>

        {/* Select */}
        <div className="mb-8 max-w-sm space-y-4">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">Select</h3>
          <Select
            label="Department"
            options={DEPT_OPTIONS}
            value={dept}
            onChange={(e) => setDept(e.target.value)}
          />
          <Select
            label="Department (error)"
            options={DEPT_OPTIONS}
            error="Please select a department"
          />
        </div>

        {/* Toggle */}
        <div className="mb-8 space-y-4">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">Toggle</h3>
          <Toggle
            checked={toggle1}
            onChange={setToggle1}
            label="Wi-Fi clock-in required"
          />
          <Toggle
            checked={toggle2}
            onChange={setToggle2}
            label="Notifications enabled"
          />
          <Toggle
            checked={false}
            onChange={() => {}}
            label="Disabled toggle"
            disabled
          />
        </div>
      </section>

      {/* ── Containers ───────────────────────────────────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          Containers
        </h2>

        {/* Card */}
        <div className="mb-8">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">Card</h3>
          <div className="flex flex-wrap gap-4">
            <Card padding="sm" shadow="none" border>
              <p className="text-sm text-ink-secondary">Border · no shadow · sm padding</p>
            </Card>
            <Card padding="md" shadow="sm">
              <p className="text-sm text-ink-secondary">Shadow sm · md padding</p>
            </Card>
            <Card padding="md" shadow="md" tappable onClick={() => addToast({ type: 'success', message: 'Card tapped!' })}>
              <p className="text-sm font-medium text-ink-primary">Tappable · shadow md</p>
              <p className="text-xs text-ink-tertiary mt-1">Hover lifts · tap scales · click fires toast</p>
            </Card>
            <Card padding="md" shadow="sm" selected>
              <p className="text-sm font-medium text-ink-primary">Selected state</p>
              <p className="text-xs text-ink-tertiary mt-1">primary-light bg · primary-dark border</p>
            </Card>
          </div>
        </div>

        {/* Modal */}
        <div className="mb-8">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">Modal</h3>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setModalOpen(true)}>Open Modal</Button>
          </div>
          <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Example Modal" size="md">
            <p className="text-base text-ink-secondary mb-4">
              Mobile: slides from bottom. Desktop: fades + scales from center. Escape closes.
              Focus is trapped inside — Tab cycles through the buttons below only.
            </p>
            <div className="flex gap-3 justify-end">
              <Button variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
              <Button variant="primary" onClick={() => { setModalOpen(false); addToast({ type: 'success', message: 'Action confirmed' }) }}>Confirm</Button>
            </div>
          </Modal>
        </div>

        {/* Drawer */}
        <div className="mb-8">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">Drawer</h3>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setDrawerOpen(true)}>Bottom Drawer</Button>
            <Button variant="secondary" onClick={() => setRightDrawerOpen(true)}>Right Drawer</Button>
          </div>
          <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Bottom Drawer" side="bottom">
            <p className="text-base text-ink-secondary mb-4">
              Drag the handle to snap between 40% / 85% / 100% height. Swipe down to dismiss.
            </p>
            <Button variant="primary" onClick={() => { setDrawerOpen(false); addToast({ type: 'warning', message: 'Drawer closed via button' }) }}>
              Close
            </Button>
          </Drawer>
          <Drawer open={rightDrawerOpen} onClose={() => setRightDrawerOpen(false)} title="Right Drawer" side="right">
            <p className="text-base text-ink-secondary mb-4">
              400px wide. Slides from right. Backdrop closes on click. Escape also closes.
            </p>
            <Button variant="primary" onClick={() => { setRightDrawerOpen(false); addToast({ type: 'success', message: 'Right drawer closed' }) }}>
              Close
            </Button>
          </Drawer>
        </div>

        {/* Toast */}
        <div className="mb-8">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">Toast</h3>
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" onClick={() => addToast({ type: 'success', message: 'Record saved successfully' })}>Success toast</Button>
            <Button variant="danger"  onClick={() => addToast({ type: 'error',   message: 'Failed to save — try again', actionLabel: 'Retry', onAction: () => {} })}>Error + retry</Button>
            <Button variant="ghost"  onClick={() => addToast({ type: 'warning', message: 'Session expires in 5 minutes' })}>Warning toast</Button>
          </div>
        </div>
      </section>

      {/* ── Feedback Components ──────────────────────────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          Feedback Components
        </h2>

        {/* StatusBadge — all 12 */}
        <div className="mb-8">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">StatusBadge — all 12 variants</h3>
          <div className="flex flex-wrap gap-3 mb-3">
            {(['paid','active','confirmed','checked-in','pending','held','failed','info','checked-out','inactive','cancelled','no-show'] as StatusValue[]).map((s) => (
              <StatusBadge key={s} status={s} />
            ))}
          </div>
          <div className="flex flex-wrap gap-3">
            {(['paid','pending','failed','inactive'] as StatusValue[]).map((s) => (
              <StatusBadge key={s} status={s} size="sm" variant="pill" />
            ))}
            <span className="text-xs text-ink-tertiary self-center">↑ sm + pill</span>
          </div>
        </div>

        {/* Skeleton */}
        <div className="mb-8 space-y-3 max-w-sm">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">Skeleton</h3>
          <Skeleton variant="heading" />
          <Skeleton variant="text" lines={3} />
          <div className="flex items-center gap-3">
            <Skeleton variant="avatar" />
            <div className="flex-1 space-y-2">
              <Skeleton variant="text" />
              <Skeleton variant="badge" />
            </div>
          </div>
          <Skeleton variant="row" />
          <Skeleton variant="button" />
          <Skeleton variant="card" />
        </div>

        {/* Spinner */}
        <div className="mb-8">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary mb-4">Spinner</h3>
          <div className="flex items-center gap-6 flex-wrap">
            <Spinner size="sm" color="sage" label="Loading small" />
            <Spinner size="md" color="sage" label="Loading medium" />
            <Spinner size="lg" color="sage" label="Loading large" />
            <div className="bg-ink-primary rounded-lg p-3 flex gap-4">
              <Spinner size="sm" color="cream" label="Light sm" />
              <Spinner size="md" color="cream" label="Light md" />
              <Spinner size="lg" color="cream" label="Light lg" />
            </div>
          </div>
        </div>

        {/* EmptyState */}
        <div className="mb-8 border border-cream-alt rounded-xl overflow-hidden">
          <h3 className="text-sm tracking-widest uppercase text-ink-tertiary p-4 border-b border-cream-alt">EmptyState</h3>
          <EmptyState
            icon={
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
                <rect x="8" y="14" width="32" height="24" rx="4" stroke="currentColor" strokeWidth="2" />
                <path d="M16 14V10a8 8 0 0116 0v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                <path d="M20 26h8M24 22v8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            }
            title="No orders yet today."
            description="Orders placed at the POS will appear here in real time."
            actionLabel="Refresh"
            onAction={() => addToast({ type: 'success', message: 'Refreshed' })}
          />
        </div>
      </section>

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
                <div key={s.token}>
                  <div className={`${s.bg} rounded-lg h-16 mb-2`} />
                  <p className="text-xs font-mono font-medium text-ink-primary leading-tight">
                    {s.token.replace('--color-', '')}
                  </p>
                  <p className="text-xs font-mono tabular-nums text-ink-tertiary">
                    {s.hex}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      {/* ── Type scale — Inter ────────────────────────────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          Type Scale — Inter (font-sans)
        </h2>
        <div className="space-y-6">
          {TYPE_SCALE.map(({ label, twClass }) => (
            <div key={label} className="border-b border-cream-alt pb-4">
              <p className="text-xs tracking-widest uppercase text-ink-tertiary mb-2 font-mono">{label}</p>
              <div className="space-y-1">
                {WEIGHTS.map(({ label: wLabel, tw }) => (
                  <p key={wLabel} className={`${twClass} ${tw} font-sans text-ink-primary leading-tight`}>
                    {wLabel} — The quick brown fox
                  </p>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Type scale — Cormorant Garamond ──────────────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          Type Scale — Cormorant Garamond (font-serif)
        </h2>
        <div className="space-y-6">
          {TYPE_SCALE.map(({ label, twClass }) => (
            <div key={label} className="border-b border-cream-alt pb-4">
              <p className="text-xs tracking-widest uppercase text-ink-tertiary mb-2 font-mono font-sans">{label}</p>
              <div className="space-y-1">
                {WEIGHTS.map(({ label: wLabel, tw }) => (
                  <p key={wLabel} className={`${twClass} ${tw} font-serif text-ink-primary leading-tight`}>
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
            <p className="text-xs tracking-widest uppercase text-ink-tertiary mb-2 font-mono">Inter (font-sans)</p>
            <p className="text-2xl font-medium font-sans tabular-nums text-ink-primary">1,234,567.89</p>
            <p className="text-xl font-normal font-sans tabular-nums text-ink-secondary">KES 1,234,567.89</p>
          </div>
          <div>
            <p className="text-xs tracking-widest uppercase text-ink-tertiary mb-2 font-mono">Cormorant Garamond (font-serif)</p>
            <p className="text-2xl font-medium font-serif tabular-nums text-ink-primary">1,234,567.89</p>
            <p className="text-xl font-normal font-serif tabular-nums text-ink-secondary">KES 1,234,567.89</p>
          </div>
        </div>
      </section>

      {/* ── Responsive breakpoint probe ──────────────────────── */}
      <section className="mb-14">
        <h2 className="text-2xl font-bold mb-6 tracking-wide uppercase text-ink-secondary">
          Responsive Breakpoints
        </h2>
        <div className="rounded-lg overflow-hidden border border-cream-alt text-sm font-mono">
          <div className="bg-ink-primary text-cream-card p-3 block sm:hidden">&lt; 640px — base</div>
          <div className="hidden sm:block md:hidden bg-primary-dark text-cream-card p-3">640px–767px — sm:</div>
          <div className="hidden md:block lg:hidden bg-primary-main text-ink-primary p-3">768px–1023px — md:</div>
          <div className="hidden lg:block xl:hidden bg-primary-light text-ink-primary p-3">1024px–1279px — lg:</div>
          <div className="hidden xl:block bg-cream-card text-ink-primary p-3">≥ 1280px — xl:</div>
        </div>
      </section>

      <footer className="text-xs text-ink-tertiary pt-6 border-t border-cream-alt">
        F-1/F-2 token + component gate · Remove before F-3 ships
      </footer>
    </div>
  );
}
