/**
 * capture_proposal.spec.ts — the screenshot set for the client proposal.
 *
 * The last proposal carried FOUR images across twenty sections, for a client
 * who has never seen the system. Words cannot do that job: they have nothing
 * to compare the claims against. This captures one honest screen per claim,
 * in the order the proposal argues them — owner, then management, then the
 * floor, then the person's own phone, then the guest.
 *
 * Every shot asserts it is on the right screen before it saves. Run:
 *   npx playwright test tests/playwright/capture_proposal.spec.ts --project=chromium
 * then check the evidence log and that distinct md5s == number of images.
 */
import { test } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { appPage, makeCapturer, api, type Entry, type AppId } from './lib/capture'

const SHOTS = path.resolve(__dirname, '../../docs/proposal/shots')
const EVIDENCE = path.resolve(__dirname, '../../docs/proposal/evidence.json')

const evidence: Entry[] = []
const capture = makeCapturer(SHOTS, evidence)

const OWNER  = 'amara.wanjiku'     // owner L10
const MGR    = 'brian.mwangi'      // manager L5
const DESK   = 'grace.muthoni'     // front_desk L3
const GATE   = 'hassan.omondi'     // gate_lead L3
const CHEF   = 'cynthia.achieng'   // head_chef Kitchen L3
const BAR    = 'david.otieno'      // bar_lead L3
const WAITER = 'ivan.kipchoge'     // waiter Restaurant L1

/** One row per screenshot: who signs in, where they go, and what proves it. */
type Shot = {
  id: string; app: AppId; user: string; role: string; route: string
  markers: string[]; notes: string; fullPage?: boolean
}

const SHOT_LIST: Shot[] = [
  // ── The owner's chair ─────────────────────────────────────────────────────
  { id: '01_owner_dashboard', app: 'owner', user: OWNER, role: 'owner', route: '/dashboard',
    markers: ['today', 'occupancy', 'revenue'],
    notes: 'What the owner sees first: the day so far, without asking anyone.' },
  { id: '02_owner_menu_profit', app: 'owner', user: OWNER, role: 'owner', route: '/menu-profit',
    markers: ['margin', 'menu', 'profit'],
    notes: 'Margin per dish, derived from recorded purchases — not typed in.' },
  { id: '03_owner_audit', app: 'owner', user: OWNER, role: 'owner', route: '/audit',
    markers: ['audit', 'actor', 'action'],
    notes: 'The hash-chained log. Every price change and every refund has a name on it.' },
  { id: '04_owner_purchase_approvals', app: 'owner', user: OWNER, role: 'owner', route: '/purchase-approvals',
    markers: ['approval', 'budget', 'request'],
    notes: 'Spending authority: the owner sets the budget, the manager works inside it.' },
  { id: '05_owner_payroll', app: 'owner', user: OWNER, role: 'owner', route: '/payroll',
    markers: ['payroll', 'wage', 'hours'],
    notes: 'Wages computed from clock-ins, not from a notebook.' },
  { id: '06_owner_reconciliation', app: 'owner', user: OWNER, role: 'owner', route: '/reconciliation',
    markers: ['reconcil', 'cash', 'counted'],
    notes: 'What the till says against what was counted, per shift.' },

  // ── The manager runs the day ──────────────────────────────────────────────
  { id: '10_manager_hub', app: 'station', user: MGR, role: 'manager', route: '/manager',
    markers: ['front house', 'cash', 'staff'],
    notes: 'The manager hub. Every tool the day needs, one tap from here.' },
  { id: '11_manager_front_house', app: 'station', user: MGR, role: 'manager', route: '/manager/front-desk',
    markers: ['arriv', 'occupancy', 'depart'],
    notes: 'Arrivals, departures and occupancy for today.' },
  { id: '12_manager_cash', app: 'station', user: MGR, role: 'manager', route: '/manager/cash',
    markers: ['cash', 'float', 'shift'],
    notes: 'Cash position by till.' },
  { id: '13_manager_staff', app: 'station', user: MGR, role: 'manager', route: '/manager/staff',
    markers: ['staff', 'role', 'department'],
    notes: 'The staff file: roles, departments, and who may do what.' },
  { id: '14_manager_roster', app: 'station', user: MGR, role: 'manager', route: '/manager/roster',
    markers: ['roster', 'shift', 'week'],
    notes: 'The roster people are held to — and the one the wages are read from.' },
  { id: '15_manager_purchases', app: 'station', user: MGR, role: 'manager', route: '/manager/purchases',
    markers: ['budget', 'purchase', 'request'],
    notes: 'A spend request, with the arithmetic in the message when it exceeds budget.' },
  { id: '16_manager_suppliers', app: 'station', user: MGR, role: 'manager', route: '/manager/suppliers',
    markers: ['supplier', 'contact'],
    notes: 'Who the property buys from.' },
  { id: '17_manager_disputes', app: 'station', user: MGR, role: 'manager', route: '/manager/disputes',
    markers: ['dispute', 'resolved', 'open'],
    notes: 'Grievances, and the answer that goes back to the person who filed it.' },
  { id: '18_lost_found', app: 'station', user: MGR, role: 'manager', route: '/lost-found',
    markers: ['lost', 'claimed'],
    notes: 'What guests left behind. Front desk may look; a manager releases it.' },
  { id: '19_events', app: 'station', user: MGR, role: 'manager', route: '/events',
    markers: ['event', 'guests'],
    notes: 'A wedding or conference: staffing and the stock set aside for it.' },
  { id: '20_inventory_count', app: 'station', user: MGR, role: 'manager', route: '/inventory/count',
    markers: ['count', 'stock', 'item'],
    notes: 'A stock count in the unit the item is actually kept in.' },

  // ── The floor ─────────────────────────────────────────────────────────────
  { id: '30_gate_hub', app: 'station', user: GATE, role: 'gate lead', route: '/gate/hub',
    markers: ['band', 'gate', 'entry'],
    notes: 'The gate. One payment settles the entry fee and opens the wristband tab.' },
  { id: '31_front_desk_checkin', app: 'station', user: DESK, role: 'front desk', route: '/front-desk/checkin',
    markers: ['check', 'booking', 'arriv'],
    notes: 'Check-in. Confirm is refused until the deposit is recorded.' },
  { id: '32_front_desk_new_booking', app: 'station', user: DESK, role: 'front desk', route: '/front-desk/new-booking',
    markers: ['booking', 'villa', 'night'],
    notes: 'A new booking, priced from the villa rate card.' },
  { id: '33_pos_tabs', app: 'station', user: WAITER, role: 'waiter', route: '/pos/tabs',
    markers: ['tab', 'band', 'balance'],
    notes: 'Every bill belongs to a wristband or a room. No anonymous tables.' },
  { id: '34_pos_kitchen_order', app: 'station', user: WAITER, role: 'waiter', route: '/pos/kitchen',
    markers: ['kitchen', 'order', 'menu'],
    notes: 'Taking a food order. An unclassified item cannot be sold at all.' },
  { id: '35_chef_queue', app: 'station', user: CHEF, role: 'head chef', route: '/chef',
    markers: ['kitchen', 'ready', 'order'],
    notes: 'The kitchen queue. Stock is consumed when an item is marked ready.' },
  { id: '36_bar_queue', app: 'station', user: BAR, role: 'bar lead', route: '/bar',
    markers: ['bar', 'ready', 'order'],
    notes: 'The bar queue, same rule — the pour is what moves the stock.' },
  { id: '37_receipts', app: 'station', user: DESK, role: 'front desk', route: '/receipts',
    markers: ['receipt', 'total'],
    notes: 'The guest’s paper: what they had, what it cost, what VAT was charged.' },
  { id: '38_incidents', app: 'station', user: MGR, role: 'manager', route: '/incidents',
    markers: ['incident', 'report'],
    notes: 'Anything that goes wrong is written down where someone will see it.' },

  // ── The person's own phone ────────────────────────────────────────────────
  { id: '50_employee_clock', app: 'employee', user: WAITER, role: 'waiter', route: '/clock',
    markers: ['clock', 'shift'],
    notes: 'The employee app is the person’s own: clock in, HR, nothing else.' },
  { id: '51_employee_profile', app: 'employee', user: WAITER, role: 'waiter', route: '/profile',
    markers: ['profile', 'department'],
    notes: 'Their own record, and nobody else’s.' },
  { id: '52_employee_leave', app: 'employee', user: WAITER, role: 'waiter', route: '/leave',
    markers: ['leave', 'request', 'days'],
    notes: 'Leave requested here, decided by the manager, and the answer comes back.' },

  // ── The guest ─────────────────────────────────────────────────────────────
  { id: '60_kiosk_menu', app: 'employee', user: WAITER, role: 'kiosk', route: '/kiosk/menu',
    markers: ['menu', 'ksh'],
    notes: 'The kiosk a guest touches. No login screen, no staff tools.',
    // kioskMode is deliberately in-memory only, so a guest screen cannot be
    // reached by typing a URL — a member of staff hands the tablet over. Walk
    // the real hand-off instead of faking the flag.
    arrive: async (page, base) => {
      await page.goto(`${base}/kiosk/launch`, { waitUntil: 'domcontentloaded', timeout: 30_000 })
      await page.getByRole('button', { name: 'Activate Menu Kiosk' }).click({ timeout: 15_000 })
    } },
]

test.describe.configure({ mode: 'serial' })

test('capture the proposal screenshot set', async ({ browser }) => {
  test.setTimeout(20 * 60 * 1000)

  // employee_pwa's AuthGate sends anyone not clocked in to /clock, which would
  // redirect three of the shots below and save nothing.
  await api('POST', '/hr/clock-in', WAITER).catch(() => {})

  const contexts = new Map<string, { ctx: any; page: any }>()
  const keyFor = (app: AppId, user: string) => `${app}:${user}`

  for (const shot of SHOT_LIST) {
    const key = keyFor(shot.app, shot.user)
    if (!contexts.has(key)) {
      // A login that fails must cost us ONE screenshot, not the whole run.
      // The first attempt died on hassan.omondi and threw away 29 other shots
      // — including ones that had already been proven on screen.
      try {
        contexts.set(key, await appPage(browser, shot.app, shot.user))
      } catch (err: any) {
        evidence.push({
          id: shot.id, app: `${shot.app}_pwa`, route: shot.route,
          user: shot.user, role: shot.role, captured: false,
          assert_used: 'never reached — sign-in failed',
          failure: `could not sign in as ${shot.user}: ${String(err?.message ?? err).slice(0, 200)}`,
          notes: shot.notes,
        })
        continue
      }
    }
    const { page } = contexts.get(key)!
    await capture({ page, ...shot })
  }

  for (const { ctx } of contexts.values()) await ctx.close()

  fs.mkdirSync(path.dirname(EVIDENCE), { recursive: true })
  fs.writeFileSync(EVIDENCE, JSON.stringify(evidence, null, 2))

  const ok = evidence.filter(e => e.captured)
  console.log(`\nCAPTURED ${ok.length}/${evidence.length}`)
  for (const e of evidence) {
    if (!e.captured) console.log(`  MISS ${e.id.padEnd(28)} ${e.failure}`)
  }
})
