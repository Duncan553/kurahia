import { useEffect, useState } from 'react'
import { kvGet, kvSet } from './idb'

export const FONT_SIZES = { S: '14px', M: '16px', L: '18px' } as const
export type FontSizeKey = keyof typeof FONT_SIZES
const IDB_KEY = 'font-size-pref'

export function applyFontSize(key: FontSizeKey) {
  document.documentElement.style.setProperty('--font-size-base', FONT_SIZES[key])
}

// Used in AppLayout to rehydrate the preference at every session start
export async function loadFontSizePref() {
  const saved = await kvGet<FontSizeKey>(IDB_KEY)
  if (saved && saved in FONT_SIZES) applyFontSize(saved)
}

// Used in ProfileScreen to show + change the active size
export function useFontSizePref() {
  const [size, setSize] = useState<FontSizeKey>('M')

  useEffect(() => {
    kvGet<FontSizeKey>(IDB_KEY).then(saved => {
      if (saved && saved in FONT_SIZES) setSize(saved)
    })
  }, [])

  async function changeSize(key: FontSizeKey) {
    setSize(key)
    applyFontSize(key)
    await kvSet(IDB_KEY, key)
  }

  return { size, changeSize }
}
