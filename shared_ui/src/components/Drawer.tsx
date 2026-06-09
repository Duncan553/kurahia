import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence, useDragControls } from 'framer-motion'
import type { ReactNode } from 'react'

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
            role="dialog"
            aria-modal="true"
            drag="y"
            dragControls={dragControls}
            dragConstraints={constraintsRef}
            dragElastic={0.1}
            onDragEnd={handleDragEnd}
            initial={{ y: '100%' }}
            animate={{ y: `${100 - snapHeightVh}vh`, transition: { type: 'spring', stiffness: 300, damping: 35 } }}
            exit={{ y: '100%', transition: { duration: 0.2, ease: 'easeIn' } }}
            className="fixed bottom-0 left-0 right-0 z-50 bg-cream-card rounded-t-2xl shadow-xl overflow-hidden"
            style={{ height: `${snapHeightVh}vh` }}
          >
            {/* Drag handle */}
            <div
              className="flex justify-center pt-3 pb-2 cursor-grab active:cursor-grabbing"
              onPointerDown={(e) => dragControls.start(e)}
            >
              <div className="w-10 h-1 rounded-full bg-ink-tertiary/40" aria-hidden="true" />
            </div>
            <div className="px-6 pb-6 overflow-y-auto h-full">
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
