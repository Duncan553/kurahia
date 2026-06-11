import { StrictMode } from 'react'
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
import ScheduleScreen      from './screens/ScheduleScreen'
import NotificationsScreen from './screens/NotificationsScreen'
import ProfileScreen       from './screens/ProfileScreen'
import ConductScreen       from './screens/ConductScreen'
import SuggestionsScreen   from './screens/SuggestionsScreen'
import LeaveRequestScreen  from './screens/LeaveRequestScreen'
import AbsenceNoticeScreen from './screens/AbsenceNoticeScreen'

// All staff — band lookup (level 1+)
import BandLookupScreen  from './screens/BandLookupScreen'

// Gate / Front Desk (level 3+)
import WristbandScreen from './screens/WristbandScreen'
import CheckInScreen   from './screens/CheckInScreen'

// Water activities (level 1, water dept) — nav filters by department
import WaiverScreen        from './screens/WaiverScreen'
import SafetyCheckScreen   from './screens/SafetyCheckScreen'

// Equipment maintenance (level 5+ manager)
import MaintenanceLogScreen from './screens/MaintenanceLogScreen'

// Manager (level 5+)
import ManagerScreen          from './screens/ManagerScreen'
import InventoryCountScreen   from './screens/InventoryCountScreen'
import PurchaseRequestScreen  from './screens/PurchaseRequestScreen'
import QuickEntryScreen       from './screens/QuickEntryScreen'

// Manager sub-screens (F-11)
import StaffAccountsScreen  from './screens/StaffAccountsScreen'
import CashReconScreen      from './screens/CashReconScreen'
import LeaveApprovalScreen  from './screens/LeaveApprovalScreen'
import ShiftScreen          from './screens/ShiftScreen'
import AttendanceScreen     from './screens/AttendanceScreen'
import PurchaseReqScreen    from './screens/PurchaseReqScreen'
import FrontDeskScreen      from './screens/FrontDeskScreen'

// F-17: Department POS screens
import WaiterTabsScreen       from './screens/WaiterTabsScreen'
import WaiterTabDetailScreen  from './screens/WaiterTabDetailScreen'
import { KitchenQueueScreen, BarQueueScreen } from './screens/StationQueues'
import ServicePayScreen       from './screens/ServicePayScreen'
import VillaScreen            from './screens/VillaScreen'

// Kiosk (F-12/F-13/F-14) — outside AppLayout, inside AuthGate
import KioskLaunchScreen         from './screens/kiosk/KioskLaunchScreen'
import KioskMenuScreen           from './screens/kiosk/KioskMenuScreen'
import KioskWelcomeScreen        from './screens/kiosk/KioskWelcomeScreen'
import KioskWaiverScreen         from './screens/kiosk/KioskWaiverScreen'
import KioskFeedbackLaunchScreen from './screens/kiosk/KioskFeedbackLaunchScreen'
import KioskFeedbackScreen       from './screens/kiosk/KioskFeedbackScreen'

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
      element: <AppLayout />,
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
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <ToastContainer />
    </QueryClientProvider>
  </StrictMode>,
)
