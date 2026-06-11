// One IndexedDB for all offline state. Version bumps when stores are added:
//   v1: clock-queue (F-7)
//   v2: + pwa-state (F-17 — install-prompt dismissal, key/value)
// Every open() in the app MUST go through here — an open() with an older
// version number than the DB's current version throws VersionError.

const DB_NAME = 'kurahia-offline'
const DB_VERSION = 2

export const STORE_CLOCK_QUEUE = 'clock-queue'
export const STORE_PWA_STATE = 'pwa-state'

export function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      for (const store of [STORE_CLOCK_QUEUE, STORE_PWA_STATE]) {
        if (!req.result.objectStoreNames.contains(store)) {
          req.result.createObjectStore(store, store === STORE_CLOCK_QUEUE ? { autoIncrement: true } : undefined)
        }
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

// Key/value helpers on the pwa-state store
export async function kvGet<T>(key: string): Promise<T | undefined> {
  const db = await openDB()
  return new Promise((res, rej) => {
    const req = db.transaction(STORE_PWA_STATE, 'readonly').objectStore(STORE_PWA_STATE).get(key)
    req.onsuccess = () => res(req.result as T | undefined)
    req.onerror = () => rej(req.error)
  })
}

export async function kvSet(key: string, value: unknown): Promise<void> {
  const db = await openDB()
  return new Promise((res, rej) => {
    const tx = db.transaction(STORE_PWA_STATE, 'readwrite')
    tx.objectStore(STORE_PWA_STATE).put(value, key)
    tx.oncomplete = () => res()
    tx.onerror = () => rej(tx.error)
  })
}
