// IndexedDB offline queue for clock events.
// Token storage taught us localStorage is off-limits → IndexedDB for any offline state.

import { openDB, STORE_CLOCK_QUEUE as STORE } from './idb'

export type ClockEventType = 'CLOCK_IN' | 'CLOCK_OUT'

interface QueuedEvent {
  type: ClockEventType
  queued_at: string  // ISO
}

export async function enqueueClockEvent(type: ClockEventType): Promise<void> {
  const db = await openDB()
  const tx = db.transaction(STORE, 'readwrite')
  tx.objectStore(STORE).add({ type, queued_at: new Date().toISOString() } satisfies QueuedEvent)
}

// Calls `sync` for each queued event in order. Stops on first failure.
// Returns number successfully synced.
export async function drainClockQueue(
  sync: (type: ClockEventType) => Promise<void>
): Promise<number> {
  const db = await openDB()
  const items = await new Promise<{ key: IDBValidKey; value: QueuedEvent }[]>((res, rej) => {
    const tx = db.transaction(STORE, 'readonly')
    const out: { key: IDBValidKey; value: QueuedEvent }[] = []
    const req = tx.objectStore(STORE).openCursor()
    req.onsuccess = () => {
      const cur = req.result
      if (cur) { out.push({ key: cur.key, value: cur.value as QueuedEvent }); cur.continue() }
      else res(out)
    }
    req.onerror = () => rej(req.error)
  })
  let synced = 0
  for (const item of items) {
    try {
      await sync(item.value.type)
      const del = db.transaction(STORE, 'readwrite')
      del.objectStore(STORE).delete(item.key)
      synced++
    } catch {
      break  // leave rest in queue for next reconnect
    }
  }
  return synced
}
