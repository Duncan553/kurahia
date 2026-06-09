import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { ToastContainer } from '@shared'
import { AuthGate } from './components/AuthGate'
import LoginScreen from './screens/LoginScreen'
import PinEntryScreen from './screens/PinEntryScreen'
import PinSetupScreen from './screens/PinSetupScreen'
import PlaceholderHome from './screens/PlaceholderHome'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

const router = createBrowserRouter([
  // Public
  { path: '/login',     element: <LoginScreen />    },
  { path: '/pin',       element: <PinEntryScreen />  },
  { path: '/pin/setup', element: <PinSetupScreen />  },

  // Protected — AuthGate redirects to /pin when not authenticated
  {
    element: <AuthGate />,
    children: [
      { path: '/', element: <PlaceholderHome /> },
      // F-7+ screens nest here with optional requireRole() wrappers
    ],
  },

  // Catch-all → login
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
