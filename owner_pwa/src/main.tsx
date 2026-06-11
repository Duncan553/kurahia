import { StrictMode } from 'react'
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
import FinanceScreen          from './screens/FinanceScreen'
import AlertsScreen           from './screens/AlertsScreen'
import PayrollDraftScreen     from './screens/PayrollDraftScreen'
import ReconciliationScreen   from './screens/ReconciliationScreen'
import StaffScreen            from './screens/StaffScreen'
import BookingsScreen         from './screens/BookingsScreen'
import SettingsScreen         from './screens/SettingsScreen'

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
      element: <AppLayout />,
      children: [
        { path: '/',          element: <DashboardScreen /> },
        { path: '/dashboard', element: <DashboardScreen /> },
        { path: '/finance',          element: <FinanceScreen />        },
        { path: '/alerts',           element: <AlertsScreen />         },
        { path: '/payroll',          element: <PayrollDraftScreen />   },
        { path: '/reconciliation',   element: <ReconciliationScreen /> },
        { path: '/staff',            element: <StaffScreen />          },
        { path: '/bookings',  element: <BookingsScreen />  },
        { path: '/settings',  element: <SettingsScreen />  },
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
