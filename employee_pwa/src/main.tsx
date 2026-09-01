import { StrictMode, lazy } from 'react'
import { useAuthStore } from './stores/authStore'

import { ErrorBoundary } from '@shared'
import { MotionConfig } from 'framer-motion'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { registerSW } from 'virtual:pwa-register'
import api from './lib/axios'
import './index.css'

// Service worker: auto-updates on new deploy (skipWaiting in sw.ts)
registerSW({ immediate: true })
import { ToastContainer } from '@shared'
import { AuthGate } from './components/AuthGate'
import AppLayout from './layouts/AppLayout'

// Auth
import LoginScreen       from './screens/LoginScreen'
import PinEntryScreen    from './screens/PinEntryScreen'
import PinSetupScreen    from './screens/PinSetupScreen'

// Universal — all staff
import ClockScreen         from './screens/ClockScreen'

// All staff — band lookup (level 1+)

// Gate / Front Desk (level 3+)

// Water activities (level 1, water dept) — nav filters by department

// Equipment maintenance (level 5+ manager)

// Manager (level 5+)

// Manager sub-screens (F-11)

// F-17: Department POS screens


// Kiosk (F-12/F-13/F-14) — outside AppLayout, inside AuthGate


// Route-level code splitting: everything beyond login/PIN/clock loads on demand.
// The SW precaches all chunks anyway, so offline still works.
const NotificationsScreen = lazy(() => import('./screens/NotificationsScreen'))
const ProfileScreen = lazy(() => import('./screens/ProfileScreen'))
const ConductScreen = lazy(() => import('./screens/ConductScreen'))
const SuggestionsScreen = lazy(() => import('./screens/SuggestionsScreen'))
const LeaveRequestScreen = lazy(() => import('./screens/LeaveRequestScreen'))
const AbsenceNoticeScreen = lazy(() => import('./screens/AbsenceNoticeScreen'))
const KioskLaunchScreen = lazy(() => import('./screens/kiosk/KioskLaunchScreen'))
const KioskMenuScreen = lazy(() => import('./screens/kiosk/KioskMenuScreen'))
const KioskWelcomeScreen = lazy(() => import('./screens/kiosk/KioskWelcomeScreen'))
const KioskWaiverScreen = lazy(() => import('./screens/kiosk/KioskWaiverScreen'))
const KioskFeedbackLaunchScreen = lazy(() => import('./screens/kiosk/KioskFeedbackLaunchScreen'))
const KioskFeedbackScreen = lazy(() => import('./screens/kiosk/KioskFeedbackScreen'))
const CalendarScreen = lazy(() => import('./screens/CalendarScreen'))
const DisputesScreen = lazy(() => import('./screens/DisputesScreen'))
const IncidentScreen = lazy(() => import('./screens/IncidentScreen'))
import RegisterScreen from './screens/RegisterScreen'

// ── HomeRedirect: landing page based on device mode ──
function HomeRedirect() {
  const user = useAuthStore((s) => s.user)
  const station = localStorage.getItem('kurahia:station_mode') === 'true'
  // Today's roster overrides the account's fixed department — same source
  // AppLayout uses, so a manager's reassignment for today is respected here
  // too, not just on subsequent navigation. See AppLayout.tsx.
  const { data: rosterToday } = useQuery<{ department: string | null }>({
    queryKey: ['roster', 'me'],
    queryFn: () => api.get('/hr/roster/me').then(r => r.data),
    staleTime: 5 * 60_000,
    enabled: !!user,
  })
  if (!user) return <Navigate to='/login' replace />
  const dept = (rosterToday?.department ?? user.department ?? '').toLowerCase() // DB names are Title-Case ("Kitchen"), so lowercase before matching
  const level = user.role_level ?? 0
  if (station && level < 5) {
    if (dept.includes('kitchen')) return <Navigate to='/pos/kitchen' replace />
    if (dept.includes('bar')) return <Navigate to='/pos/bar' replace />
    if (dept.includes('waiter') || dept.includes('front')) return <Navigate to='/pos/tabs' replace />
    if (dept.includes('gate')) return <Navigate to='/gate/hub' replace />
    return <Navigate to='/pos/tabs' replace />
  }
  return <Navigate to='/clock' replace />
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

const router = createBrowserRouter([
  // Public
  { path: '/register', element: <RegisterScreen /> },
  { path: '/login',     element: <LoginScreen />   },
  { path: '/pin',       element: <PinEntryScreen /> },
  { path: '/pin/setup', element: <PinSetupScreen /> },

  // Protected — all inside AuthGate
  {
    element: <AuthGate />,
    children: [
      // ── Kiosk routes (F-12/F-13/F-14) — no AppLayout chrome ────
      { path: '/kiosk/launch',              element: <KioskLaunchScreen />         },
      { path: '/kiosk/menu',                element: <KioskMenuScreen />           },
      { path: '/kiosk/welcome',             element: <KioskWelcomeScreen />        },
      { path: '/kiosk/waiver/:bookingId',   element: <KioskWaiverScreen />         },
      { path: '/kiosk/feedback/launch',     element: <KioskFeedbackLaunchScreen /> },
      { path: '/kiosk/feedback',            element: <KioskFeedbackScreen />       },

      // ── Staff routes — inside AppLayout ────────────────────────
      {
      element: <ErrorBoundary><AppLayout /></ErrorBoundary>,
      children: [
        { path: '/', element: <HomeRedirect /> },

        // ── Universal: all staff ──────────────────────────────────
        { path: '/clock',           element: <ClockScreen />         },
        { path: '/notifications',   element: <NotificationsScreen /> },
        { path: '/profile',         element: <ProfileScreen />       },
        { path: '/conduct',         element: <ConductScreen />       },
        { path: '/suggestions/new', element: <SuggestionsScreen />   },
        { path: '/leave',           element: <LeaveRequestScreen />  },
        { path: '/absence',         element: <AbsenceNoticeScreen /> },
        { path: '/calendar',        element: <CalendarScreen />      },
        { path: '/disputes',        element: <DisputesScreen />      },
        { path: '/incidents',       element: <IncidentScreen />      },

        // ── Everything else used to live here ─────────────────────
        // POS, the kitchen and bar queues, the gate hub, front-desk check-in,
        // the villa and housekeeping boards, inventory counts and the whole
        // /manager/* group — 31 routes, all of them ALSO in station_pwa.
        //
        // They are the POST'S tools, not the person's. A tablet bolted to the
        // bar is the bar's tool and belongs to whoever is standing at it; this
        // app is personal and follows one person around. Mixing them meant a
        // waiter's phone could open the manager's cash screen, and every screen
        // existed twice — which had already started to bite: five of the shared
        // screens had drifted, CheckInScreen by 198 lines, so there were two
        // different check-in flows depending on which app you opened.
        //
        // The employee app is now what it says: clock in, HR, your profile.

      ],    // end AppLayout children
      },    // end AppLayout route object
    ],      // end AuthGate children
  },

  { path: '*', element: <LoginScreen /> },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <ToastContainer />
      </QueryClientProvider>
    </MotionConfig>
  </StrictMode>,
)
