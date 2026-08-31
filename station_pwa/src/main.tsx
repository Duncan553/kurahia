import { StrictMode } from 'react'
import { ErrorBoundary, ToastContainer } from '@shared'
import { MotionConfig } from 'framer-motion'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'

import { AuthGate } from './components/AuthGate'
import AppLayout, { StationHome } from './layouts/AppLayout'

import StationLoginScreen from './screens/StationLoginScreen'
import { KitchenQueueScreen, BarQueueScreen } from './screens/StationQueues'
import WaiterTabsScreen from './screens/WaiterTabsScreen'
import WaiterTabDetailScreen from './screens/WaiterTabDetailScreen'
import CustomerMenuScreen from './screens/CustomerMenuScreen'
import ServicePayScreen from './screens/ServicePayScreen'
import WaiverScreen from './screens/WaiverScreen'
import SafetyCheckScreen from './screens/SafetyCheckScreen'
import VillaScreen from './screens/VillaScreen'
import HousekeepingScreen from './screens/HousekeepingScreen'
import GateHubScreen from './screens/GateHubScreen'
import CheckInScreen from './screens/CheckInScreen'
import BandLookupScreen from './screens/BandLookupScreen'
import IncidentScreen from './screens/IncidentScreen'
import NotFoundScreen from './screens/NotFoundScreen'

// ── Work that used to live on the employee's personal phone ──────────
// Managing, costing a menu, counting stock, reconciling cash and opening a
// staff account are all WORK, so they belong at the post like every other
// job — not in the app whose only business is clock-in, HR and personal
// profile. Gated by role, not by department: a manager works everywhere.
// Events and Calendar are the deliberate exception to the split: they exist in
// BOTH apps. What is on today is something you check on your own phone before
// you leave the house, and again at the post while you work it.
import EventsScreen from './screens/EventsScreen'
import CalendarScreen from './screens/CalendarScreen'

import ManagerScreen from './screens/ManagerScreen'
// ManagerScreen's own action tiles already pointed at all of these. Moving that
// screen here without them left six tiles navigating to routes this app did not
// have — including Leave and Cash, which are core to the job.
import LeaveApprovalScreen from './screens/LeaveApprovalScreen'
import ShiftScreen from './screens/ShiftScreen'
import AttendanceScreen from './screens/AttendanceScreen'
import RosterScreen from './screens/RosterScreen'

// New: the two manager duties that had no screen anywhere. Recording a purchase
// is the only step that raises stock and derives cost_per_unit.
import PurchaseRecordScreen from './screens/PurchaseRecordScreen'
import SuppliersScreen from './screens/SuppliersScreen'
import ResourcesScreen from './screens/ResourcesScreen'
import ReconcileScreen from './screens/ReconcileScreen'
// The guest's bill for the whole stay. GET /receipts/:tab_id was built in
// Phase A and never called, so a guest checking out saw a total and no lines.
import FolioScreen from './screens/FolioScreen'
// Front desk taking a guest in. POST /bookings always allowed FRONT_DESK_LEVEL;
// the only screen calling it was gated to villa/housekeeping staff.
import NewBookingScreen from './screens/NewBookingScreen'
import HeadChefScreen from './screens/HeadChefScreen'
import ProposeBudgetScreen from './screens/ProposeBudgetScreen'
import InventoryCountScreen from './screens/InventoryCountScreen'
import MenuManageScreen from './screens/MenuManageScreen'
import CashReconScreen from './screens/CashReconScreen'
import StaffAccountsScreen from './screens/StaffAccountsScreen'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

const router = createBrowserRouter([
  { path: '/login', element: <StationLoginScreen /> },
  {
    element: <AuthGate />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, path: '/', element: <StationHome /> },
          { path: '/pos/tabs', element: <WaiterTabsScreen /> },
          { path: '/pos/tabs/:id', element: <WaiterTabDetailScreen /> },
          { path: '/pos/menu/:tabId?', element: <CustomerMenuScreen /> },
          { path: '/pos/kitchen', element: <KitchenQueueScreen /> },
          { path: '/pos/bar', element: <BarQueueScreen /> },
          { path: '/pos/spa', element: <ServicePayScreen /> },
          { path: '/pos/water-pay', element: <ServicePayScreen /> },
          { path: '/gate/waiver', element: <WaiverScreen /> },
          { path: '/equipment/safety-check', element: <SafetyCheckScreen /> },
          { path: '/villa', element: <VillaScreen /> },
          { path: '/housekeeping', element: <HousekeepingScreen /> },
          { path: '/gate/hub', element: <GateHubScreen /> },
          { path: '/front-desk/checkin', element: <CheckInScreen /> },
          { path: '/gate/band-lookup', element: <BandLookupScreen /> },
          { path: '/incidents', element: <IncidentScreen /> },

          // ── Work moved off the employee phone ──────────────────────
          // Paths kept identical to the ones employee_pwa used, so every
          // existing link, notification route and deep link still resolves.
          { path: '/events',            element: <EventsScreen />         },
          { path: '/calendar',          element: <CalendarScreen />       },
          { path: '/manager',           element: <ManagerScreen />        },
          { path: '/manager/purchases', element: <ProposeBudgetScreen /> },
          { path: '/manager/menu',      element: <MenuManageScreen />     },
          { path: '/chef',              element: <HeadChefScreen />       },
          { path: '/inventory/count',   element: <InventoryCountScreen /> },
          // One path only. A /finance/cash-recon alias existed briefly so the
          // nav tile and the Manage tile could each have their own URL — two
          // addresses for one screen is how a fix lands on half of them.
          { path: '/manager/cash',      element: <CashReconScreen />      },
          { path: '/manager/leave',     element: <LeaveApprovalScreen />  },
          { path: '/manager/shifts',    element: <ShiftScreen />          },
          { path: '/manager/attendance',element: <AttendanceScreen />     },
          // Was FrontDeskScreen: 381 lines reading GET /front-desk/today and
          // writing nothing — a read-only subset of CheckInScreen, which shows
          // the same day AND can confirm, check in, check out and take deposits.
          // Two screens, one endpoint, one titled Front Desk; the weaker one is
          // gone and the path now lands on the one that can actually do the job.
          { path: '/manager/front-desk',element: <CheckInScreen />        },
          { path: '/manager/roster',    element: <RosterScreen />         },
          { path: '/manager/receive',   element: <PurchaseRecordScreen /> },
          { path: '/manager/suppliers', element: <SuppliersScreen />      },
          { path: '/manager/resources', element: <ResourcesScreen />      },
          { path: '/manager/reconcile', element: <ReconcileScreen />      },
          // Level 3+: front desk needs this at check-out, waiters when closing a table.
          { path: '/folio/:tabId',      element: <FolioScreen />          },
          { path: '/front-desk/new-booking', element: <NewBookingScreen /> },
          { path: '/manager/staff',     element: <StaffAccountsScreen />  },
          // Unknown address, but signed in: say so. This lives INSIDE AuthGate
          // and AppLayout on purpose — AuthGate still sends anyone not signed in
          // to /login, so the only people who reach this are the ones who
          // mistyped or followed a stale link. It used to render the login
          // screen from outside the gate, which told signed-in staff they had
          // been signed out.
          { path: '*', element: <NotFoundScreen /> },
        ],
      },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <QueryClientProvider client={queryClient}>
        <ErrorBoundary level="screen">
          <RouterProvider router={router} />
        </ErrorBoundary>
        <ToastContainer />
      </QueryClientProvider>
    </MotionConfig>
  </StrictMode>,
)
