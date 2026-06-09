import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { ToastContainer } from '@shared'
import { AuthGate, RoleGate } from './components/AuthGate'
import AppLayout from './layouts/AppLayout'
import LoginScreen from './screens/LoginScreen'
import PinEntryScreen from './screens/PinEntryScreen'
import PinSetupScreen from './screens/PinSetupScreen'
import ClockScreen from './screens/ClockScreen'
import ScheduleScreen from './screens/ScheduleScreen'
import NotificationsScreen from './screens/NotificationsScreen'
import ProfileScreen from './screens/ProfileScreen'
import ConductScreen from './screens/ConductScreen'
import SuggestionsScreen from './screens/SuggestionsScreen'
import GateScreen from './screens/GateScreen'
import ManagerScreen from './screens/ManagerScreen'
import WristbandScreen from './screens/WristbandScreen'
import CheckInScreen from './screens/CheckInScreen'
import WaiverScreen from './screens/WaiverScreen'

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
        // Root redirects to primary action
        { path: '/',                element: <Navigate to="/clock" replace /> },

        // Universal screens (F-7)
        { path: '/clock',           element: <ClockScreen />         },
        { path: '/schedule',        element: <ScheduleScreen />      },
        { path: '/notifications',   element: <NotificationsScreen /> },
        { path: '/profile',         element: <ProfileScreen />       },
        { path: '/conduct',         element: <ConductScreen />       },
        { path: '/suggestions/new', element: <SuggestionsScreen />   },

        // F-8: Front desk screens (level 3+)
        {
          element: <RoleGate minLevel={3} />,
          children: [
            { path: '/gate',               element: <GateScreen />      },
            { path: '/gate/issue',         element: <WristbandScreen /> },
            { path: '/front-desk/checkin', element: <CheckInScreen />   },
          ],
        },

        // F-8: Waiver (level 1+ — any staff)
        { path: '/gate/waiver', element: <WaiverScreen /> },

        // Manager screens (level 5+)
        {
          element: <RoleGate minLevel={5} />,
          children: [{ path: '/manager', element: <ManagerScreen /> }],
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
