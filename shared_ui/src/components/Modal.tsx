import { useEffect, useId, useRef } from 'react'
import { useIsDesktop } from '../hooks/useIsDesktop'
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
  const isDesktop = useIsDesktop()
  const triggerRef = useRef<HTMLElement | null>(null)
  // Was the hardcoded string 'modal-title'. Every Modal on a page therefore
  // shared one id, so aria-labelledby could point at another modal's heading.
  const titleId = useId()

  // Store the element that opened the modal so we can restore focus on close
  useEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement as HTMLElement
    } else if (triggerRef.current) {
      triggerRef.current.focus()
      triggerRef.current = null
    }
  }, [open])

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

          {/* ONE dialog, positioned responsively.

              This used to be two sibling subtrees — a `md:hidden` bottom sheet
              and a `hidden md:flex` centred dialog — each rendering {children}.
              Both were always in the DOM, so every modal duplicated its whole
              contents: duplicate `id`s (a <label htmlFor> could bind to the
              hidden copy), two elements with role="dialog" aria-modal="true" at
              once, autoFocus on both, and any child effect running twice. It
              also made `getByRole` ambiguous for tests.

              The focus trap was attached to the mobile div only, which is
              display:none on desktop — so desktop had NO working focus trap. */}
          <div
            className={[
              'fixed inset-0 z-50 flex justify-center',
              'items-end md:items-center',   // sheet on phones, centred on desktop
              'md:p-6',
            ].join(' ')}
            onClick={preventClose ? undefined : onClose}
          >
            <motion.div
              key="modal-panel"
              ref={dialogRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
              // Variants follow the same breakpoint as the classes above, so the
              // panel never slides up from the bottom while centred (or vice versa).
              variants={isDesktop ? desktopVariants : mobileVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
              // The wrapper closes on click; the panel must not.
              onClick={(e) => e.stopPropagation()}
              className={[
                'bg-cream-card shadow-xl overflow-y-auto',
                'p-6 max-h-[90vh]',
                'w-full rounded-t-2xl',        // phone: full-width sheet
                `md:rounded-2xl ${SIZE[size]}`, // desktop: rounded card, size-capped
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
