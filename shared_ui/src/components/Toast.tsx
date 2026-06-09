import { motion, AnimatePresence } from 'framer-motion'
import { useToastStore } from '../stores/toastStore'
import type { Toast as ToastItem } from '../stores/toastStore'

// Icon per toast type
function ToastIcon({ type }: { type: ToastItem['type'] }) {
  if (type === 'success') return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <circle cx="9" cy="9" r="8" stroke="#4A7A4A" strokeWidth="1.5" />
      <path d="M5.5 9l2.5 2.5L12.5 6" stroke="#4A7A4A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
  if (type === 'error') return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <circle cx="9" cy="9" r="8" stroke="#A04438" strokeWidth="1.5" />
      <path d="M9 5.5v4M9 12h.01" stroke="#A04438" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M9 2L1.5 15.5h15L9 2z" stroke="#B88838" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M9 7v4M9 13h.01" stroke="#B88838" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

const BORDER: Record<ToastItem['type'], string> = {
  success: 'border-l-4 border-status-paid',
  error:   'border-l-4 border-status-failed',
  warning: 'border-l-4 border-status-pending',
}

function ToastCard({ toast }: { toast: ToastItem }) {
  const removeToast = useToastStore((s) => s.removeToast)
  return (
    <motion.div
      layout
      key={toast.id}
      // Spring enter from the right (desktop) / bottom (mobile handled by container position)
      initial={{ opacity: 0, x: 40 }}
      animate={{ opacity: 1, x: 0, transition: { type: 'spring', stiffness: 350, damping: 30 } }}
      exit={{ opacity: 0, x: 40, transition: { duration: 0.2, ease: 'easeOut' } }}
      role={toast.type === 'error' ? 'alert' : 'status'}
      aria-live={toast.type === 'error' ? 'assertive' : 'polite'}
      className={[
        'flex items-start gap-3 bg-cream-card rounded-xl shadow-md p-4 min-w-[260px] max-w-[360px]',
        BORDER[toast.type],
      ].join(' ')}
    >
      <ToastIcon type={toast.type} />
      <p className="flex-1 text-sm text-ink-primary">{toast.message}</p>
      <div className="flex items-center gap-2 shrink-0">
        {toast.actionLabel && toast.onAction && (
          <button
            onClick={() => { toast.onAction?.(); removeToast(toast.id) }}
            className="text-sm font-medium text-sage-dark hover:underline"
          >
            {toast.actionLabel}
          </button>
        )}
        <button
          onClick={() => removeToast(toast.id)}
          aria-label="Dismiss"
          className="text-ink-tertiary hover:text-ink-primary transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </div>
    </motion.div>
  )
}

// Mount this once at the app root — it renders wherever the toasts should live.
// Desktop: top-right. Mobile: above bottom nav (bottom-20).
export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)
  return (
    <>
      {/* Desktop: top-4 right-4 */}
      <div className="hidden md:flex fixed top-4 right-4 z-[60] flex-col gap-2 items-end pointer-events-none">
        <AnimatePresence mode="popLayout">
          {toasts.map((t) => (
            <div key={t.id} className="pointer-events-auto">
              <ToastCard toast={t} />
            </div>
          ))}
        </AnimatePresence>
      </div>

      {/* Mobile: bottom-20 (clears the bottom nav bar) */}
      <div className="md:hidden fixed bottom-20 left-4 right-4 z-[60] flex flex-col gap-2 pointer-events-none">
        <AnimatePresence mode="popLayout">
          {toasts.map((t) => (
            <div key={t.id} className="pointer-events-auto">
              <ToastCard toast={t} />
            </div>
          ))}
        </AnimatePresence>
      </div>
    </>
  )
}
