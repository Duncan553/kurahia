import { StrictMode, lazy } from 'react'
import { ErrorBoundary } from '@shared'
import { MotionConfig } from 'framer-motion'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { registerSW } from 'virtual:pwa-register'
import './index.css'

// Service worker: auto-updates on new deploy (skipWaiting in sw.ts)
registerSW({ immediate: true })
import { ToastContainer } from '@shared'
import { AuthGate, RoleGate } from './components/AuthGate'
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
const ScheduleScreen = lazy(() => import('./screens/ScheduleScreen'))
const NotificationsScreen = lazy(() => import('./screens/NotificationsScreen'))
const ProfileScreen = lazy(() => import('./screens/ProfileScreen'))
const ConductScreen = lazy(() => import('./screens/ConductScreen'))
const SuggestionsScreen = lazy(() => import('./screens/SuggestionsScreen'))
const LeaveRequestScreen = lazy(() => import('./screens/LeaveRequestScreen'))
const AbsenceNoticeScreen = lazy(() => import('./screens/AbsenceNoticeScreen'))
const BandLookupScreen = lazy(() => import('./screens/BandLookupScreen'))
const WristbandScreen = lazy(() => import('./screens/WristbandScreen'))
const CheckInScreen = lazy(() => import('./screens/CheckInScreen'))
const WaiverScreen = lazy(() => import('./screens/WaiverScreen'))
const SafetyCheckScreen = lazy(() => import('./screens/SafetyCheckScreen'))
const MaintenanceLogScreen = lazy(() => import('./screens/MaintenanceLogScreen'))
const ManagerScreen = lazy(() => import('./screens/ManagerScreen'))
const InventoryCountScreen = lazy(() => import('./screens/InventoryCountScreen'))
const PurchaseRequestScreen = lazy(() => import('./screens/PurchaseRequestScreen'))
const QuickEntryScreen = lazy(() => import('./screens/QuickEntryScreen'))
const StaffAccountsScreen = lazy(() => import('./screens/StaffAccountsScreen'))
const MenuManageScreen = lazy(() => import('./screens/MenuManageScreen'))
const CashReconScreen = lazy(() => import('./screens/CashReconScreen'))
const LeaveApprovalScreen = lazy(() => import('./screens/LeaveApprovalScreen'))
const ShiftScreen = lazy(() => import('./screens/ShiftScreen'))
const AttendanceScreen = lazy(() => import('./screens/AttendanceScreen'))
const PurchaseReqScreen = lazy(() => import('./screens/PurchaseReqScreen'))
const FrontDeskScreen = lazy(() => import('./screens/FrontDeskScreen'))
const WaiterTabsScreen = lazy(() => import('./screens/WaiterTabsScreen'))
const WaiterTabDetailScreen = lazy(() => import('./screens/WaiterTabDetailScreen'))
const ServicePayScreen = lazy(() => import('./screens/ServicePayScreen'))
const VillaScreen = lazy(() => import('./screens/VillaScreen'))
const KioskLaunchScreen = lazy(() => import('./screens/kiosk/KioskLaunchScreen'))
const KioskMenuScreen = lazy(() => import('./screens/kiosk/KioskMenuScreen'))
const KioskWelcomeScreen = lazy(() => import('./screens/kiosk/KioskWelcomeScreen'))
const KioskWaiverScreen = lazy(() => import('./screens/kiosk/KioskWaiverScreen'))
const KioskFeedbackLaunchScreen = lazy(() => import('./screens/kiosk/KioskFeedbackLaunchScreen'))
const KioskFeedbackScreen = lazy(() => import('./screens/kiosk/KioskFeedbackScreen'))
const KitchenQueueScreen = lazy(() => import('./screens/StationQueues').then(m => ({ default: m.KitchenQueueScreen })))
const BarQueueScreen = lazy(() => import('./screens/StationQueues').then(m => ({ default: m.BarQueueScreen })))
const GateHubScreen = lazy(() => import('./screens/GateHubScreen'))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

const router = createBrowserRouter([
  // Public
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
        { path: '/', element: <Navigate to="/clock" replace /> },

        // ── Universal: all staff ──────────────────────────────────
        { path: '/clock',           element: <ClockScreen />         },
        { path: '/schedule',        element: <ScheduleScreen />      },
        { path: '/notifications',   element: <NotificationsScreen /> },
        { path: '/profile',         element: <ProfileScreen />       },
        { path: '/conduct',         element: <ConductScreen />       },
        { path: '/suggestions/new', element: <SuggestionsScreen />   },
        { path: '/leave',           element: <LeaveRequestScreen />  },
        { path: '/absence',         element: <AbsenceNoticeScreen /> },

        // ── Band lookup: all staff (level 1+) ────────────────────
        { path: '/gate/band-lookup', element: <BandLookupScreen /> },

        // ── Water activities: waiver + safety check + payment
        { path: '/gate/waiver',            element: <WaiverScreen />       },
        { path: '/equipment/safety-check', element: <SafetyCheckScreen />  },
        { path: '/pos/water-pay',          element: <ServicePayScreen />    },

        // ── POS: waiter tables + tab detail (level 1+, dept-filtered in nav)
        { path: '/pos/tabs',     element: <WaiterTabsScreen />      },
        { path: '/pos/tabs/:id', element: <WaiterTabDetailScreen /> },

        // ── POS: kitchen + bar queues (dept-filtered in nav)
        { path: '/pos/kitchen', element: <KitchenQueueScreen /> },
        { path: '/pos/bar',     element: <BarQueueScreen />     },

        // ── POS: spa / gym service payment (dept-filtered in nav)
        { path: '/pos/spa', element: <ServicePayScreen /> },

        // ── Villa: villa staff + front desk (level 3-4 or villa dept)
        { path: '/villa', element: <VillaScreen /> },

        // ── Gate / Front Desk (level 3+) ─────────────────────────
        {
          element: <RoleGate minLevel={3} />,
          children: [
            { path: '/gate/hub',           element: <GateHubScreen />   },
            // /gate/issue kept as a direct deep-link for managers navigating
            // back to the standalone issue screen (e.g. from ManagerScreen).
            // GateHubScreen (/gate/hub) is the primary gate-staff landing.
            { path: '/gate/issue',         element: <WristbandScreen /> },
            { path: '/front-desk/checkin', element: <CheckInScreen />   },
          ],
        },

        // ── Staff meals: any staff (level 1+) ───────────────────
        { path: '/inventory/quick-entry', element: <QuickEntryScreen /> },

        // ── Manager (level 5+) ───────────────────────────────────
        {
          element: <RoleGate minLevel={5} />,
          children: [
            { path: '/manager',                    element: <ManagerScreen />         },
            { path: '/inventory/count',            element: <InventoryCountScreen />  },
            { path: '/inventory/purchase-request', element: <PurchaseRequestScreen /> },
            { path: '/equipment/maintenance',      element: <MaintenanceLogScreen />  },
            // F-11: Manager sub-screens
            { path: '/manager/staff',      element: <StaffAccountsScreen /> },
            { path: '/manager/menu',       element: <MenuManageScreen />    },
            { path: '/manager/cash',       element: <CashReconScreen />     },
            { path: '/manager/leave',      element: <LeaveApprovalScreen /> },
            { path: '/manager/shifts',     element: <ShiftScreen />         },
            { path: '/manager/attendance', element: <AttendanceScreen />    },
            { path: '/manager/purchases',  element: <PurchaseReqScreen />   },
            { path: '/manager/front-desk', element: <FrontDeskScreen />     },
          ],
        },
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
