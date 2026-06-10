import { motion } from 'framer-motion'

const HERO_URL =
  'https://waterfrontcountryclub.com/wp-content/uploads/2025/08/DJI_0669-scaled.jpg'

interface ScreenHeroProps {
  title: string
  subtitle?: string
}

export default function ScreenHero({ title, subtitle }: ScreenHeroProps) {
  return (
    <motion.div
      className="screen-hero-torn relative w-full h-44 shrink-0"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
    >
      <img
        src={HERO_URL}
        alt=""
        aria-hidden="true"
        className="absolute inset-0 w-full h-full object-cover object-center"
      />
      {/* Terracotta overlay — same tint as login */}
      <div className="absolute inset-0 bg-primary-dark/45" />
      {/* Title block — bottom-left, serif editorial */}
      <div className="absolute bottom-9 left-5">
        {subtitle && (
          <p className="text-[9px] tracking-[0.3em] uppercase text-white/55 font-medium mb-1">
            {subtitle}
          </p>
        )}
        <h1
          className="font-serif text-[2.6rem] font-bold tracking-tight text-white leading-[0.88]"
          style={{ textShadow: '0 2px 16px rgba(0,0,0,0.45)' }}
        >
          {title}
        </h1>
      </div>
    </motion.div>
  )
}
