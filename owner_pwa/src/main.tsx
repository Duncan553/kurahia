import { StrictMode, lazy } from 'react'
import { ErrorBoundary } from '@shared'
import { MotionConfig } from 'framer-motion'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { registerSW } from 'virtual:pwa-register'
import './index.css'

// Service worker: auto-updates on new deploy (skipWaiting in sw.ts)
registerSW({ immediate: true })
import { ToastContainer } from '@shared'
import { AuthGate } from './components/AuthGate'
import AppLayout from './layouts/AppLayout'
import LoginScreen from './screens/LoginScreen'
import PinEntryScreen from './screens/PinEntryScreen'
import PinSetupScreen from './screens/PinSetupScreen'
import DashboardScreen       from './screens/DashboardScreen'


// Code splitting: dashboard is the landing screen, the rest load on demand
const FinanceScreen            = lazy(() => import('./screens/FinanceScreen'))
const AlertsScreen             = lazy(() => import('./screens/AlertsScreen'))
const PayrollDraftScreen       = lazy(() => import('./screens/PayrollDraftScreen'))
const ReconciliationScreen     = lazy(() => import('./screens/ReconciliationScreen'))
const StaffScreen              = lazy(() => import('./screens/StaffScreen'))
const BookingsScreen           = lazy(() => import('./screens/BookingsScreen'))
const SettingsScreen           = lazy(() => import('./screens/SettingsScreen'))
const PurchaseApprovalsScreen  = lazy(() => import('./screens/PurchaseApprovalsScreen'))
const FeedbackScreen           = lazy(() => import('./screens/FeedbackScreen'))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

const router = createBrowserRouter([
  // Public
  { path: '/login',     element: <LoginScreen />   },
  { path: '/pin',       element: <PinEntryScreen /> },
  { path: '/pin/setup', element: <PinSetupScreen /> },

  // Protected — all sit inside AuthGate → AppLayout
  {
    element: <AuthGate />,
    children: [{
      element: <ErrorBoundary><AppLayout /></ErrorBoundary>,
      children: [
        { path: '/',          element: <DashboardScreen /> },
        { path: '/dashboard', element: <DashboardScreen /> },
        { path: '/finance',          element: <FinanceScreen />        },
        { path: '/alerts',           element: <AlertsScreen />         },
        { path: '/payroll',          element: <PayrollDraftScreen />   },
        { path: '/reconciliation',   element: <ReconciliationScreen /> },
        { path: '/staff',            element: <StaffScreen />          },
        { path: '/bookings',              element: <BookingsScreen />            },
        { path: '/settings',              element: <SettingsScreen />            },
        { path: '/purchase-approvals',    element: <PurchaseApprovalsScreen />  },
        { path: '/feedback',               element: <FeedbackScreen />           },
      ],
    }],
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
