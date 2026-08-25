import { Suspense, useEffect } from 'react'
import type { ReactElement } from 'react'
import { useLocation, useNavigate, NavLink, Outlet, Navigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { OfflineBanner, InstallPrompt } from '@shared'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'
import { kvGet, kvSet } from '../lib/idb'
import { loadFontSizePref } from '../lib/fontSizePref'
import PushPrompt from '../components/PushPrompt'
import IdleBrand from '../components/IdleBrand'
import type { Notification } from '../screens/NotificationsScreen'
import { isStationDevice, setStationMode } from '../lib/deviceMode'

// ── Icons (inline SVG — no library dependency) ─────────────────────────────

function ClockIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M10 6v4.5l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function ScheduleIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="3.5" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 1.5v4M13 1.5v4M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M7 12.5h2M12 12.5h2M7 15.5h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function BellIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2.5a6.5 6.5 0 00-6.5 6.5v3.5L2 14.5h16L16.5 12.5V9A6.5 6.5 0 0010 2.5z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M8.5 16a1.5 1.5 0 003 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function ProfileIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="7" r="3.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 18c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Band search: magnifier
function BandIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M13 13l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M6 8.5h5M8.5 6v5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Gate: wristband icon
function GateIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="2.5" y="4.5" width="15" height="11" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M2.5 10h5M12.5 10h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Check-in: calendar + check
function CheckInIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="3.5" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 1.5v4M13 1.5v4M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M7 13l2.5 2.5L14 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Waiver: document + pen
function WaiverIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="4" y="2" width="12" height="16" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 7h6M7 10.5h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M11.5 14.5l1.5-1.5L14.5 14.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Inventory: grid
function InventoryIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="2.5" y="2.5" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <rect x="11.5" y="2.5" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <rect x="2.5" y="11.5" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M11.5 14.5h6M14.5 11.5v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Restock: clipboard + arrow up
function RestockIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3.5" y="3.5" width="13" height="15" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M7.5 3.5V2.5a1 1 0 011-1h3a1 1 0 011 1v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 8.5v5.5M7.5 11L10 8.5l2.5 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Meals: utensils
function MealsIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2.5v4M6.5 3.5c0 3 1.5 4.5 3.5 4.5s3.5-1.5 3.5-4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 8v9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M5.5 13h9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Safety check: shield + checkmark
function SafetyIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2.5L3.5 5.5v4.5c0 4 2.5 7.5 6.5 8.5 4-1 6.5-4.5 6.5-8.5V5.5L10 2.5z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M7.5 10l2 2.5L13.5 8.5" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Maintenance: wrench
function MaintenanceIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M13.5 4a3.5 3.5 0 00-3.5 3.5c0 .5.1 1 .3 1.4L3.5 15.5a1.2 1.2 0 001.7 1.7l6.6-6.8c.4.2.9.3 1.4.3A3.5 3.5 0 0013.5 4z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M13.5 4v2.5h-2.5" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Manager: person + check badge
function ManagerIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 16v-1c0-2.5 3-4.5 7-4.5s7 2 7 4.5v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="10" cy="6.5" r="3.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M14 2.5l1.5 1.5L18 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}

// Waiter pad: notepad + pen stroke
function WaiterIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3.5" y="2" width="13" height="16" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M7 6h6M7 9h6M7 12h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M15 16.5l2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Kitchen: pot/flame
function KitchenIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3.5 9h13v6.5a2 2 0 01-2 2h-9a2 2 0 01-2-2V9z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M7.5 9V6.5c0-1.2.8-2 .8-3.5M12 9V6.5c0-1.2.8-2 .8-3.5"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M7.5 13.5h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Bar: cocktail glass
function BarIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M4.5 3.5l5.5 7.5 5.5-7.5H4.5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 11v5.5M6.5 16.5h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M6.5 7h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Spa/Gym: leaf
function SpaGymIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 17C10 17 3.5 13 3.5 8a6.5 6.5 0 0113 0C16.5 13 10 17 10 17z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 17V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Water: wave
function WaterIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M2 11c1.3-2.5 2.6-2.5 4 0s2.6 2.5 4 0 2.6-2.5 4 0 2.6 2.5 4 0"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 6.5c1.3-2.5 2.6-2.5 4 0s2.6 2.5 4 0 2.6-2.5 4 0 2.6 2.5 4 0"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 15.5c1.3-2.5 2.6-2.5 4 0s2.6 2.5 4 0 2.6-2.5 4 0 2.6 2.5 4 0"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Events: calendar + star
function EventsIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="3.5" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 1.5v4M13 1.5v4M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M10 11.5l1.2 2.4 2.6.4-1.9 1.8.5 2.6L10 17.2l-2.4 1.5.5-2.6-1.9-1.8 2.6-.4L10 11.5z"
      stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Villa: house
function VillaIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 9.5L10 3l7 6.5v8a1 1 0 01-1 1H4a1 1 0 01-1-1v-8z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <rect x="7.5" y="13" width="5" height="5.5" rx="0.5" stroke="currentColor" strokeWidth="1.5"/>
  </svg>
}

// Calendar: monthly calendar
function CalendarIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="4" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 2v4M13 2v4M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="7.5" cy="12.5" r="1" fill="currentColor" />
    <circle cx="10" cy="12.5" r="1" fill="currentColor" />
    <circle cx="12.5" cy="12.5" r="1" fill="currentColor" />
    <circle cx="7.5" cy="15.5" r="1" fill="currentColor" />
  </svg>
}
// Disputes: shield + exclamation
function DisputesIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2.5L3.5 5.5v4.5c0 4 2.5 7.5 6.5 8.5 4-1 6.5-4.5 6.5-8.5V5.5L10 2.5z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 8v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="10" cy="13.5" r="0.75" fill="currentColor" />
  </svg>
}
// Performance: bar chart
function PerformanceIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="11" width="3" height="6" rx="0.5" stroke="currentColor" strokeWidth="1.5" />
    <rect x="8.5" y="7" width="3" height="10" rx="0.5" stroke="currentColor" strokeWidth="1.5" />
    <rect x="14" y="3" width="3" height="14" rx="0.5" stroke="currentColor" strokeWidth="1.5" />
  </svg>
}
// Housekeeping: sparkle
function HousekeepingIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2l1.2 2.4L14 5l-2 2 .5 3L10 8.5 7.5 10l.5-3-2-2 2.8-.6L10 2z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 11v7M7 14h6" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}

function IncidentIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 3L2 17h16L10 3z" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 9v4M10 14.5v.5" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round"/>
  </svg>
}

// ── Department helper ──────────────────────────────────────────────────────────

function deptIs(dept: string | null, ...keywords: string[]): boolean {
  if (!dept) return false
  const d = dept.toLowerCase()
  return keywords.some((k) => d.includes(k))
}

// ── Nav item definition ─────────────────────────────────────────────────────

interface NavItem {
  id: string
  path: string
  label: string
  Icon: () => ReactElement
  badge?: boolean
  // mode: 'personal' = phone HR app, 'station' = shared work tablet, 'both' = always
  mode: 'personal' | 'station' | 'both'
  visible: (level: number, dept: string | null) => boolean
}

const NAV_ITEMS: NavItem[] = [
  // ── Personal phone: HR + clock-in ───────────────────────────────────────────
  {
    id: 'clock',
    path: '/clock',
    label: 'Clock',
    Icon: ClockIcon,
    mode: 'personal',
    visible: () => true,
  },
  {
    id: 'alerts',
    path: '/notifications',
    label: 'Alerts',
    Icon: BellIcon,
    badge: true,
    mode: 'personal',
    visible: () => true,
  },
  {
    id: 'profile',
    path: '/profile',
    label: 'Profile',
    Icon: ProfileIcon,
    mode: 'personal',
    visible: (level) => level < 5,
  },
  {
    id: 'schedule',
    path: '/schedule',
    label: 'Schedule',
    Icon: ScheduleIcon,
    mode: 'personal',
    visible: (level) => level >= 5,
  },
  {
    id: 'calendar',
    path: '/calendar',
    label: 'Calendar',
    Icon: CalendarIcon,
    mode: 'personal',
    visible: () => true,
  },
  {
    id: 'incidents',
    path: '/incidents',
    label: 'Incident',
    Icon: IncidentIcon,
    mode: 'personal',
    visible: () => true,
  },

  // ── Station tablet: work dashboards ─────────────────────────────────────────
  {
    id: 'waiter',
    path: '/pos/tabs',
    label: 'Tables',
    Icon: WaiterIcon,
    mode: 'station',
    visible: (_l, dept) => deptIs(dept, 'waiter', 'restaurant', 'food', 'beverage', 'f&b', 'front-of-house'),
  },
  {
    id: 'kitchen',
    path: '/pos/kitchen',
    label: 'Kitchen',
    Icon: KitchenIcon,
    mode: 'station',
    visible: (_l, dept) => deptIs(dept, 'kitchen'),
  },
  {
    id: 'bar',
    path: '/pos/bar',
    label: 'Bar',
    Icon: BarIcon,
    mode: 'station',
    visible: (_l, dept) => deptIs(dept, 'bar'),
  },
  {
    id: 'spa-gym',
    path: '/pos/spa',
    label: 'Services',
    Icon: SpaGymIcon,
    mode: 'station',
    visible: (_l, dept) => deptIs(dept, 'spa', 'gym', 'wellness', 'massage', 'beauty', 'fitness'),
  },
  {
    id: 'waiver',
    path: '/gate/waiver',
    label: 'Waiver',
    Icon: WaiverIcon,
    mode: 'station',
    visible: (_l, dept) => deptIs(dept, 'water', 'activit', 'aqua'),
  },
  {
    id: 'safety-check',
    path: '/equipment/safety-check',
    label: 'Safety',
    Icon: SafetyIcon,
    mode: 'station',
    visible: (_l, dept) => deptIs(dept, 'water', 'activit', 'aqua'),
  },
  {
    id: 'water-pay',
    path: '/pos/water-pay',
    label: 'Payment',
    Icon: WaterIcon,
    mode: 'station',
    visible: (_l, dept) => deptIs(dept, 'water', 'activit', 'aqua'),
  },
  {
    id: 'villa',
    path: '/villa',
    label: 'Villa',
    Icon: VillaIcon,
    mode: 'station',
    visible: (level, dept) =>
      deptIs(dept, 'villa', 'housekeep') ||
      (level >= 3 && level <= 4 && !deptIs(dept, 'kitchen', 'bar')),
  },
  {
    id: 'housekeeping',
    path: '/housekeeping',
    label: 'Cleaning',
    Icon: HousekeepingIcon,
    mode: 'station',
    visible: (_l, dept) => deptIs(dept, 'villa', 'housekeep'),
  },
  {
    id: 'gate-hub',
    path: '/gate/hub',
    label: 'Gate',
    Icon: GateIcon,
    mode: 'station',
    visible: (level, dept) => level >= 3 && level <= 4 && !deptIs(dept, 'kitchen', 'bar'),
  },
  {
    id: 'checkin',
    path: '/front-desk/checkin',
    label: 'Check-In',
    Icon: CheckInIcon,
    mode: 'station',
    visible: (level, dept) => level >= 3 && level <= 4 && !deptIs(dept, 'kitchen', 'bar'),
  },
  {
    id: 'band-lookup',
    path: '/gate/band-lookup',
    label: 'Band',
    Icon: BandIcon,
    mode: 'station',
    visible: (level, dept) => level >= 3 && level < 5 && !deptIs(dept, 'kitchen', 'bar'),
  },
  {
    id: 'events',
    path: '/events',
    label: 'Events',
    Icon: EventsIcon,
    mode: 'station',
    visible: (level) => level >= 3,
  },

  // ── Manager: both modes (managers carry their tablet everywhere) ─────────────
  {
    id: 'inventory',
    path: '/inventory/count',
    label: 'Inventory',
    Icon: InventoryIcon,
    mode: 'both',
    visible: (level) => level >= 5,
  },
  {
    id: 'restock',
    path: '/inventory/purchase-request',
    label: 'Restock',
    Icon: RestockIcon,
    mode: 'both',
    visible: (level) => level >= 5,
  },
  {
    id: 'meals',
    path: '/inventory/quick-entry',
    label: 'Meals',
    Icon: MealsIcon,
    mode: 'both',
    visible: (level) => level >= 5,
  },
  {
    id: 'maintenance',
    path: '/equipment/maintenance',
    label: 'Service',
    Icon: MaintenanceIcon,
    mode: 'both',
    visible: (level) => level >= 5,
  },
  {
    id: 'disputes',
    path: '/disputes',
    label: 'Disputes',
    Icon: DisputesIcon,
    mode: 'both',
    visible: (level) => level >= 5,
  },
  {
    id: 'performance',
    path: '/performance',
    label: 'Performance',
    Icon: PerformanceIcon,
    mode: 'both',
    visible: (level) => level >= 5,
  },
  {
    id: 'manager',
    path: '/manager',
    label: 'Manager',
    Icon: ManagerIcon,
    mode: 'both',
    visible: (level) => level >= 5,
  },
]

// ── Page transition ─────────────────────────────────────────────────────────

const pageVariants = {
  initial: { opacity: 0, x: 20 },
  animate: { opacity: 1,  x: 0  },
  exit:    { opacity: 0,        },
}

// ── AppLayout ───────────────────────────────────────────────────────────────

export default function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const roleLevel = user?.role_level ?? 0
  const stationMode = isStationDevice()

  // Today's station roster overrides the employee's fixed home department —
  // a manager can put someone on a different station for a shift (e.g. a
  // waiter covering Front Desk today) without touching their account. Falls
  // back to the account's own department when nobody explicitly rostered
  // them today (the ordinary case). Same cache key everywhere it's read.
  const { data: rosterToday } = useQuery<{ department: string | null }>({
    queryKey: ['roster', 'me'],
    queryFn: () => api.get('/hr/roster/me').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const department = rosterToday?.department ?? user?.department ?? null

  const visibleItems = NAV_ITEMS.filter((item) => {
    if (item.mode === 'both') return item.visible(roleLevel, department)
    if (stationMode) return item.mode === 'station' && item.visible(roleLevel, department)
    return item.mode === 'personal' && item.visible(roleLevel, department)
  })

  // Shares the same TanStack cache key as NotificationsScreen → no extra network request
  const { data: inbox } = useQuery<Notification[]>({
    queryKey: ['notifications', 'inbox'],
    queryFn: () => api.get<Notification[]>('/notifications/inbox').then((r) => r.data),
    staleTime: 30_000,
  })
  const badgeCount = inbox?.length ?? 0

  // Shares the same TanStack cache key as AuthGate/ClockScreen — free read, no
  // extra request. Needed below to break a redirect loop with AuthGate.
  const { data: clockStatus } = useQuery<{ status: string }>({
    queryKey: ['clock-status'],
    queryFn: () => api.get('/hr/clock-status').then((r) => r.data),
  })

  function signOut() { clearAuth(); navigate('/pin') }

  function toggleStationMode() {
    setStationMode(!stationMode)
    // Reload so all routing/nav recalculates from scratch
    window.location.replace('/clock')
  }

  // Apply saved font-size preference from IDB at session start
  useEffect(() => { void loadFontSizePref() }, [])

  // Station tablets skip clock on login — go straight to their work screen.
  // On personal phones (default) this never fires: the employee always lands on Clock.
  // Must stay BELOW every hook (early return above a hook breaks React rule #310).
  //
  // The clockStatus==='CLOCK_IN' check is load-bearing, not decorative: AuthGate
  // (components/AuthGate.tsx) forces anyone who ISN'T clocked in onto /clock,
  // from any route. Before this check, this block redirected AWAY from /clock
  // unconditionally whenever station-mode+department matched — including the
  // exact moment AuthGate had just forced them there because they still needed
  // to clock in. The two rules fought forever: AuthGate → /clock, this block →
  // department screen, AuthGate → /clock again. A station-mode employee could
  // never actually reach the clock-in button. Now this only fires for someone
  // who's already clocked in and merely landed on /clock (e.g. a stale link).
  if (stationMode && location.pathname === '/clock' && roleLevel < 5 && clockStatus?.status === 'CLOCK_IN') {
    if (deptIs(department, 'kitchen'))                                  return <Navigate to="/pos/kitchen" replace />
    if (deptIs(department, 'bar'))                                      return <Navigate to="/pos/bar" replace />
    if (deptIs(department, 'front-of-house', 'waiter', 'restaurant'))  return <Navigate to="/pos/tabs" replace />
    if (deptIs(department, 'spa', 'gym', 'wellness'))                   return <Navigate to="/pos/spa" replace />
    if (deptIs(department, 'water', 'activit', 'aqua'))                 return <Navigate to="/gate/waiver" replace />
    if (deptIs(department, 'villa', 'housekeep'))                       return <Navigate to="/villa" replace />
    if (deptIs(department, 'gate', 'entry', 'secur'))                   return <Navigate to="/gate/hub" replace />
  }

  return (
    <div className="h-screen flex">
      <IdleBrand />
      <OfflineBanner />

      {/* ── Left Nav Rail (sm+) ─────────────────────────────────── */}
      <aside className="hidden sm:flex flex-col w-16 lg:w-52 shrink-0 border-r border-white/5"
        style={{ background: 'rgba(30, 16, 12, 0.95)', backdropFilter: 'blur(20px)' }}>

        {/* Logo */}
        <div className="h-14 flex items-center justify-center lg:justify-start lg:px-4 border-b border-white/5">
          <span className="text-ink-primary font-bold font-serif text-lg">
            <span className="hidden lg:block">Kurahia</span>
            <span className="lg:hidden">K</span>
          </span>
        </div>

        {/* Nav items */}
        <nav className="flex-1 py-2 space-y-0.5 overflow-y-auto" aria-label="Main navigation">
          {visibleItems.map(({ id, path, label, Icon, badge }) => (
            <NavLink key={id} to={path} end={path === '/clock'}
              className={({ isActive }) => [
                'flex items-center gap-3 px-3 lg:px-4 py-2.5 mx-1 rounded-lg transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main',
                isActive
                  ? 'bg-primary-main/10 text-[#ffb59f]'
                  : 'text-ink-tertiary hover:text-ink-primary hover:bg-white/5',
              ].join(' ')}
            >
              <span className="relative shrink-0">
                <Icon />
                {badge && badgeCount > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[14px] h-3.5 rounded-full
                    bg-status-failed text-white text-[8px] font-bold flex items-center justify-center px-0.5">
                    {badgeCount > 9 ? '9+' : badgeCount}
                  </span>
                )}
              </span>
              <span className="hidden lg:block text-sm font-medium truncate">{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div className="p-2 border-t border-white/5 space-y-1">
          {/* Station mode toggle — managers only, lets them convert any device to a work tablet */}
          {roleLevel >= 5 && (
            <button onClick={toggleStationMode}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg
                text-[10px] font-medium transition-colors
                text-ink-tertiary hover:text-ink-secondary hover:bg-white/5">
              <span className={`w-5 h-3 rounded-full border transition-colors ${stationMode ? 'bg-primary-main border-primary-main' : 'border-white/20'}`} />
              <span className="hidden lg:block">{stationMode ? 'Station mode' : 'Personal mode'}</span>
            </button>
          )}
          <div className="flex items-center gap-2 px-2">
            <div className="w-8 h-8 rounded-full bg-primary-main/20 border border-primary-main/20
              flex items-center justify-center text-primary-main text-xs font-bold shrink-0">
              {user?.username?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div className="hidden lg:block flex-1 min-w-0">
              <p className="text-xs font-medium text-ink-primary truncate">{user?.username}</p>
              <button onClick={signOut} className="text-[10px] text-status-failed/50 hover:text-status-failed">
                Sign out
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main content area ──────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Mobile top bar (sm: hidden since sidebar has logo) */}
        <header className="sm:hidden h-14 shrink-0 flex items-center justify-between px-4 border-b border-white/5"
          style={{ background: 'rgba(30, 16, 12, 0.9)' }}>
          <span className="text-lg font-bold font-serif text-ink-primary">Kurahia</span>
          <button onClick={signOut}
            className="w-8 h-8 rounded-full bg-primary-main/20 flex items-center justify-center
              text-primary-main text-sm font-bold" aria-label="Sign out">
            {user?.username?.[0]?.toUpperCase() ?? '?'}
          </button>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          {location.pathname === '/clock' && (
            <>
              <InstallPrompt kvGet={kvGet} kvSet={kvSet} />
              <PushPrompt />
            </>
          )}
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="min-h-full"
            >
              <Suspense fallback={
                <div className="flex items-center justify-center py-24">
                  <div className="w-7 h-7 rounded-full border-2 border-primary-main border-t-transparent animate-spin" />
                </div>
              }>
                <Outlet />
              </Suspense>
            </motion.div>
          </AnimatePresence>
        </main>

        {/* Mobile bottom nav (sm: hidden since sidebar replaces it) */}
        <nav className="sm:hidden shrink-0 flex border-t border-white/5"
          style={{ background: 'rgba(30, 16, 12, 0.95)' }}
          aria-label="Main navigation">
          {visibleItems.slice(0, 5).map(({ id, path, label, Icon, badge }) => (
            <NavLink key={id} to={path} end={path === '/clock'}
              className={({ isActive }) => [
                'flex-1 flex flex-col items-center justify-center gap-0.5 py-2',
                'min-h-[56px] relative transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main focus-visible:ring-inset',
                isActive ? 'text-primary-main' : 'text-ink-tertiary hover:text-ink-primary',
              ].join(' ')}
            >
              <span className="relative">
                <Icon />
                {badge && badgeCount > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[16px] h-4 rounded-full
                    bg-status-failed text-white text-[10px] font-bold flex items-center justify-center px-1">
                    {badgeCount > 9 ? '9+' : badgeCount}
                  </span>
                )}
              </span>
              <span className="text-[10px] font-medium leading-none">{label}</span>
            </NavLink>
          ))}
        </nav>

      </div>
    </div>
  )
}
