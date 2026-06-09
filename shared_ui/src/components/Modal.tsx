import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { ReactNode } from 'react'

export type ModalSize = 'sm' | 'md' | 'lg' | 'full'

export interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  size?: ModalSize
  preventClose?: boolean
}

const SIZE: Record<ModalSize, string> = {
  sm:   'max-w-sm',
  md:   'max-w-md',
  lg:   'max-w-lg',
  full: 'max-w-none w-full',
}

// All focusable element types that can receive tab focus
const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'textarea:not([disabled])',
  'input:not([disabled])', 'select:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(',')

function useFocusTrap(ref: React.RefObject<HTMLElement | null>, active: boolean) {
  useEffect(() => {
    if (!active || !ref.current) return
    const el = ref.current
    const focusable = Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE))
    if (focusable.length === 0) return
    focusable[0].focus()

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Tab') return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus() }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    el.addEventListener('keydown', handleKeyDown)
    return () => el.removeEventListener('keydown', handleKeyDown)
  }, [active, ref])
}

// Mobile: slides up from bottom. Desktop: fades + scales from center.
const mobileVariants = {
  hidden:  { y: '100%', opacity: 0 },
  visible: { y: 0,      opacity: 1, transition: { duration: 0.2, ease: 'easeOut' as const } },
  exit:    { y: '100%', opacity: 0, transition: { duration: 0.2, ease: 'easeIn'  as const } },
}
const desktopVariants = {
  hidden:  { scale: 0.95, opacity: 0 },
  visible: { scale: 1,    opacity: 1, transition: { duration: 0.2, ease: 'easeOut' as const } },
  exit:    { scale: 0.95, opacity: 0, transition: { duration: 0.2, ease: 'easeIn'  as const } },
}

export function Modal({ open, onClose, title, children, size = 'md', preventClose = false }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleId = 'modal-title'

  useFocusTrap(dialogRef, open)

  // Escape key to close
  useEffect(() => {
    if (!open || preventClose) return
    function handleKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, preventClose, onClose])

  // Lock body scroll while open
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-ink-primary/40 backdrop-blur-sm"
            onClick={preventClose ? undefined : onClose}
            aria-hidden="true"
          />

          {/* Mobile: bottom sheet */}
          <motion.div
            key="modal-mobile"
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            variants={mobileVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            className={[
              'fixed bottom-0 left-0 right-0 z-50',
              'bg-cream-card rounded-t-2xl shadow-xl',
              'p-6 max-h-[90vh] overflow-y-auto',
              'md:hidden',
            ].join(' ')}
          >
            <h2 id={titleId} className="text-xl font-bold text-ink-primary mb-4">{title}</h2>
            {children}
          </motion.div>

          {/* Desktop: centered modal */}
          <div className="hidden md:flex fixed inset-0 z-50 items-center justify-center p-6">
            <motion.div
              key="modal-desktop"
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
              variants={desktopVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
              className={[
                'bg-cream-card rounded-2xl shadow-xl',
                'p-6 w-full overflow-y-auto max-h-[90vh]',
                SIZE[size],
              ].join(' ')}
            >
              <h2 id={titleId} className="text-xl font-bold text-ink-primary mb-4">{title}</h2>
              {children}
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  )
}
