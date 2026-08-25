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
        ],
      },
    ],
  },
  { path: '*', element: <StationLoginScreen /> },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <QueryClientProvider client={queryClient}>
        <ErrorBoundary level="page">
          <RouterProvider router={router} />
        </ErrorBoundary>
        <ToastContainer />
      </QueryClientProvider>
    </MotionConfig>
  </StrictMode>,
)
