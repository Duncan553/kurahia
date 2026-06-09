import type { HTMLAttributes } from 'react'

interface LogoProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg'
  variant?: 'light' | 'dark'
}

const sizes = {
  sm: { mark: 20, title: 'text-xl', sub: 'text-[10px]' },
  md: { mark: 28, title: 'text-3xl', sub: 'text-xs' },
  lg: { mark: 36, title: 'text-4xl', sub: 'text-sm' },
}

// Placeholder wordmark — swap Logo.tsx contents when real brand assets arrive.
export function Logo({ size = 'md', variant = 'dark', className = '', ...props }: LogoProps) {
  const s = sizes[size]
  const textColor   = variant === 'light' ? 'text-cream-card' : 'text-ink-primary'
  const subColor    = variant === 'light' ? 'text-cream-card/60' : 'text-ink-tertiary'
  const strokeColor = variant === 'light' ? 'currentColor' : 'currentColor'

  return (
    <div className={`flex flex-col items-center gap-1 ${textColor} ${className}`} {...props}>
      {/* Botanical leaf mark — simple inline SVG, replace with real logo SVG later */}
      <svg
        width={s.mark} height={s.mark}
        viewBox="0 0 40 40" fill="none" aria-hidden="true"
        className={variant === 'light' ? 'text-cream-card/50' : 'text-sage-dark/60'}
      >
        <path
          d="M20 36C20 36 8 28 8 18a12 12 0 0124 0c0 10-12 18-12 18z"
          stroke={strokeColor} strokeWidth="1.5" fill="none"
        />
        <path d="M20 36V18" stroke={strokeColor} strokeWidth="1.5" strokeLinecap="round" />
        <path
          d="M14 22c2-2 4-3 6-4M26 22c-2-2-4-3-6-4"
          stroke={strokeColor} strokeWidth="1.2" strokeLinecap="round"
        />
      </svg>

      <span className={`font-bold font-serif tracking-wide ${s.title}`}>
        Kurahia
      </span>
      <span className={`tracking-widest uppercase ${s.sub} ${subColor}`}>
        Waterfront Resort
      </span>
    </div>
  )
}
