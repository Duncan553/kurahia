import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { ToastContainer } from '@shared'
import { AuthGate, RoleGate } from './components/AuthGate'
import AppLayout from './layouts/AppLayout'
import LoginScreen from './screens/LoginScreen'
import PinEntryScreen from './screens/PinEntryScreen'
import PinSetupScreen from './screens/PinSetupScreen'
import HomeScreen from './screens/HomeScreen'
import OrdersScreen from './screens/OrdersScreen'
import NotificationsScreen from './screens/NotificationsScreen'
import ProfileScreen from './screens/ProfileScreen'
import GateScreen from './screens/GateScreen'
import ManagerScreen from './screens/ManagerScreen'

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
        { path: '/',              element: <HomeScreen />          },
        { path: '/orders',        element: <OrdersScreen />        },
        { path: '/notifications', element: <NotificationsScreen /> },
        { path: '/profile',       element: <ProfileScreen />       },
        // Gate tab — level 3+
        {
          element: <RoleGate minLevel={3} />,
          children: [{ path: '/gate', element: <GateScreen /> }],
        },
        // Manager tab — level 5+
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
