// The kitchen and bar boards.
//
// Guarded HERE rather than in shared_ui, because the shim is where this app's
// routes point and the rule is this app's to state.
//
// The API rule is a DEPARTMENT, not a rank: below manager, your department must
// equal the station (_queue_for_station in app/pos/queues.py). A waiter is
// Restaurant, so /kitchen/queue and /bar/queue both refuse them — and until now
// both boards opened anyway and sat there with an error where a queue belongs.
// The sweep found it for six roles across two boards: waiter, housekeeping,
// spa, front desk and gate lead on both, and each station lead on the other
// one's board.
//
// A rank cannot express this, so the predicate reads the department. A manager
// is above it either way, because a manager covers any post.
import { RequireRole } from '../components/AuthGate'
import {
  KitchenQueueScreen as SharedKitchen,
  BarQueueScreen as SharedBar,
} from '@shared/screens/StationQueues'

const worksAt = (station: string) =>
  (u: { role_level: number; department?: string | null }) =>
    u.role_level >= 5 || (u.department ?? '').toUpperCase() === station

export function KitchenQueueScreen() {
  return (
    <RequireRole minLevel={5} allow={worksAt('KITCHEN')}>
      <SharedKitchen />
    </RequireRole>
  )
}

export function BarQueueScreen() {
  return (
    <RequireRole minLevel={5} allow={worksAt('BAR')}>
      <SharedBar />
    </RequireRole>
  )
}
