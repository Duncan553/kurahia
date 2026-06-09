import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
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

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

const router = createBrowserRouter([
  // Public
  { path: '/login',     element: <LoginScreen />   },
  { path: '/pin',       element: <PinEntryScreen /> },
  { path: '/pin/setup', element: <PinSetupScreen /> },

  // Protected — all inside AuthGate → AppLayout
  {
    element: <AuthGate />,
    children: [{
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

        // ── Water activities: waiver + safety check (any staff, nav filters by dept)
        { path: '/gate/waiver',           element: <WaiverScreen />       },
        { path: '/equipment/safety-check', element: <SafetyCheckScreen /> },

        // ── Gate / Front Desk (level 3+) ─────────────────────────
        {
          element: <RoleGate minLevel={3} />,
          children: [
            { path: '/gate/issue',         element: <WristbandScreen /> },
            { path: '/front-desk/checkin', element: <CheckInScreen />   },
          ],
        },

        // ── Manager (level 5+) ───────────────────────────────────
        {
          element: <RoleGate minLevel={5} />,
          children: [
            { path: '/manager',                    element: <ManagerScreen />         },
            { path: '/inventory/count',            element: <InventoryCountScreen />  },
            { path: '/inventory/purchase-request', element: <PurchaseRequestScreen /> },
            { path: '/inventory/quick-entry',      element: <QuickEntryScreen />      },
            { path: '/equipment/maintenance',      element: <MaintenanceLogScreen />  },
          ],
        },
      ],
    }],
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
