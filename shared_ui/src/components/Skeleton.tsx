// Shimmer uses CSS keyframes — the one allowed exception to Framer Motion.
// React 19 deduplicates <style> elements with the same precedence + content.
const SHIMMER_CSS = `
@keyframes skeleton-pulse {
  0%, 100% { opacity: 0.6; }
  50%       { opacity: 1.0; }
}
.sk-pulse {
  animation: skeleton-pulse 1.4s ease-in-out infinite;
  background-color: var(--color-cream-alt);
}
@media (prefers-reduced-motion: reduce) {
  .sk-pulse { animation: none; opacity: 0.7; }
}
`

export type SkeletonVariant = 'text' | 'heading' | 'card' | 'row' | 'avatar' | 'badge' | 'button'

export interface SkeletonProps {
  variant?: SkeletonVariant
  lines?: number   // text variant only: number of lines to simulate
  className?: string
}

// Shape classes per variant — match real content dimensions exactly
const SHAPE: Record<SkeletonVariant, string> = {
  text:    'h-4 w-full rounded',
  heading: 'h-7 w-3/4 rounded',
  card:    'h-48 w-full rounded-xl',
  row:     'h-12 w-full rounded-lg',
  avatar:  'h-10 w-10 rounded-full shrink-0',
  badge:   'h-6 w-20 rounded-full',
  button:  'h-11 w-32 rounded',
}

export function Skeleton({ variant = 'text', lines = 1, className = '' }: SkeletonProps) {
  if (variant === 'text' && lines > 1) {
    return (
      <>
        <style precedence="low">{SHIMMER_CSS}</style>
        <div className={`flex flex-col gap-2 ${className}`} aria-hidden="true">
          {Array.from({ length: lines }).map((_, i) => (
            // Last line shorter — mimics real text wrapping
            <div key={i} className={`sk-pulse rounded ${i === lines - 1 ? 'w-3/5' : 'w-full'} h-4`} />
          ))}
        </div>
      </>
    )
  }

  return (
    <>
      <style precedence="low">{SHIMMER_CSS}</style>
      <div
        className={`sk-pulse ${SHAPE[variant]} ${className}`}
        aria-hidden="true"
      />
    </>
  )
}
