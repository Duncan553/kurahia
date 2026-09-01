// Single source of truth for notification tap-routing.
// Imported by BOTH NotificationsScreen (in-app taps) and src/sw.ts
// (push notificationclick) so the two can never drift apart.
//
// Every destination here must be a route THIS app still serves. Three of them
// were not: leave_request and shift pointed at /schedule, and order_ready at
// /pos/tabs — all station screens now. Tapping one of those notifications
// would have bounced off the catch-all onto the login screen, which reads as
// "the app logged me out" rather than "that screen moved".
//
// Anything without an entry falls through to /notifications, where the person
// can at least read the message. That is the right default for the ones
// removed below: an order being ready is the tablet's business, and a shift
// change is something to read, not a screen this app has.
export const ROUTE_MAP: Record<string, string> = {
  leave_request: '/leave',      // their own request, not the manager's approval queue
  conduct_rule:  '/conduct',
  conduct:       '/conduct',
  clock_event:   '/clock',
}

export function routeFor(type: string): string {
  return ROUTE_MAP[type.toLowerCase().replace(/\s+/g, '_')] ?? '/notifications'
}
