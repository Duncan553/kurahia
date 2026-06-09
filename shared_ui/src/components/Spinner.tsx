import { motion, useReducedMotion } from 'framer-motion'

export type SpinnerSize = 'sm' | 'md' | 'lg'
export type SpinnerColor = 'sage' | 'cream' | 'ink'

export interface SpinnerProps {
  size?: SpinnerSize
  color?: SpinnerColor
  label?: string
}

const SIZE_PX: Record<SpinnerSize, number> = { sm: 16, md: 24, lg: 32 }

const STROKE_COLOR: Record<SpinnerColor, string> = {
  sage:  'var(--color-sage-dark)',
  cream: 'var(--color-cream-card)',
  ink:   'var(--color-ink-primary)',
}

// Arc length tuned per size so the visible arc is ~75% of the circle
const ARC: Record<SpinnerSize, { dasharray: number; dashoffset: number }> = {
  sm: { dasharray: 37.7, dashoffset: 9   },  // r=6
  md: { dasharray: 56.5, dashoffset: 14  },  // r=9
  lg: { dasharray: 75.4, dashoffset: 19  },  // r=12
}

const RADIUS: Record<SpinnerSize, number> = { sm: 6, md: 9, lg: 12 }

export function Spinner({ size = 'md', color = 'sage', label = 'Loading…' }: SpinnerProps) {
  const reduced = useReducedMotion()
  const px = SIZE_PX[size]
  const r  = RADIUS[size]
  const { dasharray, dashoffset } = ARC[size]

  return (
    <motion.svg
      role="status"
      aria-label={label}
      width={px}
      height={px}
      viewBox={`0 0 ${px} ${px}`}
      fill="none"
      animate={reduced ? undefined : { rotate: 360 }}
      transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
    >
      <circle
        cx={px / 2}
        cy={px / 2}
        r={r}
        stroke={STROKE_COLOR[color]}
        strokeWidth="2"
        strokeDasharray={dasharray}
        strokeDashoffset={dashoffset}
        strokeLinecap="round"
      />
    </motion.svg>
  )
}
