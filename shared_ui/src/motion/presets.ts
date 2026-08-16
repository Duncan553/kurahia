import type { Variants } from 'framer-motion'

export const slideUp: Variants = {
  hidden: { y: 20, opacity: 0 },
  visible: { y: 0, opacity: 1, transition: { duration: 0.25, ease: [0.16, 1, 0.3, 1] } },
  exit: { y: 20, opacity: 0, transition: { duration: 0.2, ease: 'easeIn' } },
}

export const fadeScale: Variants = {
  hidden: { scale: 0.95, opacity: 0 },
  visible: { scale: 1, opacity: 1, transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] } },
  exit: { scale: 0.95, opacity: 0, transition: { duration: 0.2, ease: 'easeIn' } },
}

export const slideFromRight: Variants = {
  hidden: { x: '100%', opacity: 0 },
  visible: { x: 0, opacity: 1, transition: { duration: 0.25, ease: [0.16, 1, 0.3, 1] } },
  exit: { x: '100%', opacity: 0, transition: { duration: 0.2, ease: 'easeIn' } },
}
