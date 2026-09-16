// The manager's inbox for what staff sent up.
//
// This was a bare re-export, and the route had no guard, so a waiter typing
// /manager/suggestions got the manager's screen: GET /suggestions answered
// 403 and the screen rendered "Nothing yet". An empty inbox and a refused one
// look identical, and the wrong one of those is reassuring.
//
// GET /suggestions is MANAGER_LEVEL (app/suggestions/core.py). The screen says
// so now, in words, instead of showing a silence it did not earn.
import SuggestionsScreen from '@shared/screens/SuggestionsScreen'
import { RequireRole } from '../components/AuthGate'

export default function SuggestionsInboxScreen() {
  return (
    <RequireRole minLevel={5}>
      <SuggestionsScreen />
    </RequireRole>
  )
}
