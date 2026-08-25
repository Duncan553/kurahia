import { create } from 'zustand'

interface KioskState {
  kioskMode: boolean
  kioskUser: string | null   // username of staff who activated — used for PIN exit
  activateKiosk: (username: string) => void
  deactivateKiosk: () => void
}

export const useKioskStore = create<KioskState>((set) => ({
  kioskMode: false,
  kioskUser: null,
  activateKiosk: (username) => set({ kioskMode: true, kioskUser: username }),
  deactivateKiosk: () => set({ kioskMode: false, kioskUser: null }),
}))
