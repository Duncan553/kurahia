import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence, useDragControls } from 'framer-motion'
import type { ReactNode } from 'react'

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

export interface DrawerProps {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  side?: 'bottom' | 'right'
}

// Snap points as fractions of viewport height (bottom drawer only)
const SNAP_POINTS = [0.4, 0.85, 1.0]

function BottomDrawer({ open, onClose, title, children }: Omit<DrawerProps, 'side'>) {
  const [snapIndex, setSnapIndex] = useState(1) // default: 85%
  const dragControls = useDragControls()
  const constraintsRef = useRef<HTMLDivElement>(null)
  const drawerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement as HTMLElement
    } else if (triggerRef.current) {
      triggerRef.current.focus()
      triggerRef.current = null
    }
  }, [open])

  useFocusTrap(drawerRef, open)

  useEffect(() => {
    if (!open) return
    function handleKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  const snapHeightVh = SNAP_POINTS[snapIndex] * 100

  function handleDragEnd(_: unknown, info: { offset: { y: number }; velocity: { y: number } }) {
    const { offset, velocity } = info
    // Swipe down fast or drag past 100px → close
    if (velocity.y > 500 || offset.y > 100) {
      if (snapIndex === 0) { onClose(); return }
      setSnapIndex((i) => Math.max(0, i - 1))
      return
    }
    // Swipe up → snap to next point
    if (velocity.y < -500 || offset.y < -80) {
      setSnapIndex((i) => Math.min(SNAP_POINTS.length - 1, i + 1))
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="drawer-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-ink-primary/40"
            onClick={onClose}
            aria-hidden="true"
          />
          <div ref={constraintsRef} className="fixed inset-0 z-50 pointer-events-none" aria-hidden="true" />
          <motion.div
            key="bottom-drawer"
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            drag="y"
            dragControls={dragControls}
            // Without this, framer-motion's dragListener defaults to TRUE, so a
            // pointerdown ANYWHERE in the drawer — including on its own buttons —
            // starts a drag. On release the element was left at a drag-derived y
            // instead of the animate target: one stationary click (zero movement)
            // moved it from translateY(120px) to translateY(931px), i.e. entirely
            // off-screen, which made approve/reject unreachable the moment you
            // pressed anything. Only the handle below starts a drag now.
            dragListener={false}
            dragConstraints={constraintsRef}
            dragElastic={0.1}
            onDragEnd={handleDragEnd}
            initial={{ y: '100%' }}
            // y: 0, NOT `${100 - snapHeightVh}vh`. This element is `fixed bottom-0`
            // with height = snapHeightVh, so it already sits flush with the
            // bottom; translating it down by the remaining viewport height
            // pushed it off-screen. At the 0.85 snap point that was 15vh = 120px
            // below the fold on an 800px viewport, permanently.
            animate={{ y: 0, transition: { type: 'spring', stiffness: 300, damping: 35 } }}
            exit={{ y: '100%', transition: { duration: 0.2, ease: 'easeIn' } }}
            className="fixed bottom-0 left-0 right-0 z-50 bg-cream-card rounded-t-2xl shadow-xl overflow-hidden flex flex-col"
            style={{ height: `${snapHeightVh}vh` }}
          >
            {/* Drag handle */}
            <div
              className="shrink-0 flex justify-center pt-3 pb-2 cursor-grab active:cursor-grabbing"
              onPointerDown={(e) => dragControls.start(e)}
            >
              <div className="w-10 h-1 rounded-full bg-ink-tertiary/40" aria-hidden="true" />
            </div>
            {/* flex-1 + min-h-0, NOT h-full: h-full made this as tall as the whole
                drawer while the drag handle sat above it, so the content
                overflowed by the handle's height and the last rows could not be
                scrolled into view (scrollHeight === clientHeight, canScroll false). */}
            <div className="px-6 pb-6 overflow-y-auto flex-1 min-h-0">
              {title && <h2 className="text-xl font-bold text-ink-primary mb-4">{title}</h2>}
              {children}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

function RightDrawer({ open, onClose, title, children }: Omit<DrawerProps, 'side'>) {
  const drawerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement as HTMLElement
    } else if (triggerRef.current) {
      triggerRef.current.focus()
      triggerRef.current = null
    }
  }, [open])

  useFocusTrap(drawerRef, open)

  useEffect(() => {
    if (!open) return
    function handleKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="right-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-ink-primary/40"
            onClick={onClose}
            aria-hidden="true"
          />
          <motion.div
            key="right-drawer"
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            initial={{ x: '100%' }}
            animate={{ x: 0, transition: { duration: 0.25, ease: 'easeOut' } }}
            exit={{ x: '100%', transition: { duration: 0.2, ease: 'easeIn' } }}
            className="fixed top-0 right-0 bottom-0 z-50 w-[400px] bg-cream-card shadow-xl overflow-y-auto p-6"
          >
            {title && <h2 className="text-xl font-bold text-ink-primary mb-4">{title}</h2>}
            {children}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

export function Drawer({ side = 'bottom', ...props }: DrawerProps) {
  return side === 'right' ? <RightDrawer {...props} /> : <BottomDrawer {...props} />
}
