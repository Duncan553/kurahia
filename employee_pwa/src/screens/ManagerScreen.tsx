import { useNavigate } from 'react-router-dom'
import { RequireRole } from '../components/AuthGate'

interface Tile {
  label: string
  description: string
  path: string
  Icon: () => React.ReactElement
}

function FrontDeskIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <rect x="3" y="8" width="22" height="15" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M9 8V6a5 5 0 0110 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M14 15v-3M12 15h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function AttendanceIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <circle cx="14" cy="10" r="5" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M5 24c0-5 4-8 9-8s9 3 9 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M19 16l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
function ShiftIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <rect x="4" y="5" width="20" height="19" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M9 3v4M19 3v4M4 12h20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M9 17h4M9 20.5h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function LeaveIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <rect x="4" y="5" width="20" height="19" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M9 3v4M19 3v4M4 12h20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M9 17l3 3 7-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
function CashIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <rect x="3" y="8" width="22" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <circle cx="14" cy="15" r="3" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M7 15h0M21 15h0" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
  </svg>
}
function PurchaseIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <path d="M4 5h3l2.5 11h12l2.5-8H9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="12" cy="21" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <circle cx="19" cy="21" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
  </svg>
}

const TILES: Tile[] = [
  {
    label: 'Front Desk',
    description: 'Arrivals, departures, occupancy',
    path: '/manager/front-desk',
    Icon: FrontDeskIcon,
  },
  {
    label: 'Attendance',
    description: "Today's roster + week summary",
    path: '/manager/attendance',
    Icon: AttendanceIcon,
  },
  {
    label: 'Shifts',
    description: 'Schedule and cancel shifts',
    path: '/manager/shifts',
    Icon: ShiftIcon,
  },
  {
    label: 'Leave',
    description: 'Approve or reject leave requests',
    path: '/manager/leave',
    Icon: LeaveIcon,
  },
  {
    label: 'Cash',
    description: 'Reconcile staff cash handovers',
    path: '/manager/cash',
    Icon: CashIcon,
  },
  {
    label: 'Purchases',
    description: 'Review and propose budgets',
    path: '/manager/purchases',
    Icon: PurchaseIcon,
  },
]

export default function ManagerScreen() {
  const navigate = useNavigate()

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 max-w-lg mx-auto space-y-4">

        <div>
          <h1 className="text-xl font-bold text-ink-primary">Manager</h1>
          <p className="text-sm text-ink-tertiary">Daily operations hub</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {TILES.map(({ label, description, path, Icon }) => (
            <button
              key={path}
              onClick={() => navigate(path)}
              className="flex flex-col items-start gap-3 p-4 rounded-2xl border border-cream-alt
                bg-cream-card hover:bg-cream-alt/40 active:bg-cream-alt/60 transition-colors text-left
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
            >
              <span className="text-primary-dark">
                <Icon />
              </span>
              <div>
                <p className="text-sm font-semibold text-ink-primary">{label}</p>
                <p className="text-xs text-ink-tertiary mt-0.5 leading-snug">{description}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </RequireRole>
  )
}
