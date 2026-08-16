const STORAGE_KEY = 'kurahia:station_mode'

/** Read URL param on first load, persist to localStorage. Self-healing. */
export function initDeviceMode(): void {
  const params = new URLSearchParams(window.location.search)
  const mode = params.get('mode')
  if (mode === 'station') localStorage.setItem(STORAGE_KEY, 'true')
  if (mode === 'personal') localStorage.removeItem(STORAGE_KEY)
  if (mode) {
    const url = new URL(window.location.href)
    url.searchParams.delete('mode')
    window.history.replaceState({}, '', url)
  }
}

export function isStationDevice(): boolean {
  return localStorage.getItem(STORAGE_KEY) === 'true'
}

export function setStationMode(enabled: boolean): void {
  if (enabled) localStorage.setItem(STORAGE_KEY, 'true')
  else localStorage.removeItem(STORAGE_KEY)
}
