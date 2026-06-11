// Single source of truth for notification tap-routing.
// Imported by BOTH NotificationsScreen (in-app taps) and src/sw.ts
// (push notificationclick) so the two can never drift apart.

export const ROUTE_MAP: Record<string, string> = {
  leave_request: '/schedule',
  shift: '/schedule',
  conduct_rule: '/conduct',
  conduct: '/conduct',
  clock_event: '/clock',
  order_ready: '/pos/tabs',
}

export function routeFor(type: string): string {
  return ROUTE_MAP[type.toLowerCase().replace(/\s+/g, '_')] ?? '/notifications'
}
