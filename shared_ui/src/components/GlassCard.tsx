import type { ReactNode } from 'react'

export type GlassIntensity = 'high' | 'medium' | 'low'

export interface GlassCardProps {
  intensity?: GlassIntensity
  children: ReactNode
  className?: string
}

const INTENSITY_MAP: Record<GlassIntensity, string> = {
  high: 'backdrop-blur-[20px] saturate-[160%] bg-white/[0.06] border-white/[0.08] shadow-[0_8px_32px_rgba(0,0,0,0.3),inset_0_1px_0_rgba(255,255,255,0.12)]',
  medium: 'backdrop-blur-[16px] saturate-[150%] bg-white/[0.04] border-white/[0.06] shadow-[0_4px_20px_rgba(0,0,0,0.25),inset_0_1px_0_rgba(255,255,255,0.04)]',
  low: 'backdrop-blur-[12px] saturate-[140%] bg-white/[0.05] border-white/[0.06] shadow-[0_2px_12px_rgba(0,0,0,0.2)]',
}

export function GlassCard({ intensity = 'high', children, className = '' }: GlassCardProps) {
  return (
    <div className={['rounded-2xl border transition-all', INTENSITY_MAP[intensity], className].join(' ')}>
      {children}
    </div>
  )
}
