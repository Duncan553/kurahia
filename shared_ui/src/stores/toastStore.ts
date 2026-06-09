import { create } from 'zustand'

export type ToastType = 'success' | 'error' | 'warning'

export interface Toast {
  id: string
  type: ToastType
  message: string
  actionLabel?: string
  onAction?: () => void
}

interface ToastStore {
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void
}

const DURATION: Record<ToastType, number> = {
  success: 3000,
  error:   5000,
  warning: 4000,
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],

  addToast(toast) {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    set((s) => ({ toasts: [...s.toasts, { ...toast, id }] }))
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, DURATION[toast.type])
  },

  removeToast(id) {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
  },
}))
