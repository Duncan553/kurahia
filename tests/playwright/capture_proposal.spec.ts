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
const SPA    = 'esther.kamau'      // spa_attendant L2
const WATER  = 'francis.njoroge'   // water_lead L2

/** One row per screenshot: who signs in, where they go, and what proves it. */
type Shot = {
  id: string; app: AppId; user: string; role: string; route: string
  markers: string[]; notes: string; fullPage?: boolean
}

const SHOT_LIST: Shot[] = [
  // ══ The owner's chair ═══════════════════════════════════════════════════
  { id: '01_owner_dashboard', app: 'owner', user: OWNER, role: 'owner', route: '/dashboard',
    markers: ['revenue', 'occupancy'], notes: 'The state of the whole property on one page.' },
  { id: '02_owner_alerts', app: 'owner', user: OWNER, role: 'owner', route: '/alerts',
    markers: ['alert'], notes: 'What the system noticed on its own.' },
  { id: '03_owner_finance', app: 'owner', user: OWNER, role: 'owner', route: '/finance',
    markers: ['revenue', 'expense', 'profit'], notes: 'Revenue, expenses, profit, budgets. Refused to a manager.' },
  { id: '04_owner_purchase_approvals', app: 'owner', user: OWNER, role: 'owner', route: '/purchase-approvals',
    markers: ['approval', 'request', 'budget'], notes: 'Spending beyond a manager\u2019s delegated budget waits here.' },
  { id: '05_owner_reconciliation', app: 'owner', user: OWNER, role: 'owner', route: '/reconciliation',
    markers: ['reconcil', 'cash', 'counted'], notes: 'Receipts, cash and stock checked against each other.' },
  { id: '06_owner_payroll', app: 'owner', user: OWNER, role: 'owner', route: '/payroll',
    markers: ['payroll', 'wage', 'hours'], notes: 'Built from clock records, not from memory.' },
  { id: '07_owner_staff', app: 'owner', user: OWNER, role: 'owner', route: '/staff',
    markers: ['staff', 'role'], notes: 'Who works here, what they reach, and the switch that ends it.' },
  { id: '08_owner_bookings', app: 'owner', user: OWNER, role: 'owner', route: '/bookings',
    markers: ['booking', 'arriv'], notes: 'The villa book: who is in, who is coming, who owes a deposit.' },
  { id: '09_owner_menu_profit', app: 'owner', user: OWNER, role: 'owner', route: '/menu-profit',
    markers: ['margin', 'profit', 'menu'], notes: 'The menu sorted by what it earns, not by what sells.' },
  { id: '10_owner_feedback', app: 'owner', user: OWNER, role: 'owner', route: '/feedback',
    markers: ['feedback', 'rating', 'guest'], notes: 'What guests said, attached to the department and person.' },
  { id: '11_owner_suggestions', app: 'owner', user: OWNER, role: 'owner', route: '/suggestions',
    markers: ['suggestion', 'staff'], notes: 'What staff sent up \u2014 including notes marked for the owner alone.' },
  { id: '12_owner_disputes', app: 'owner', user: OWNER, role: 'owner', route: '/disputes',
    markers: ['dispute'], notes: 'Grievances that reached the owner.' },
  { id: '13_owner_audit', app: 'owner', user: OWNER, role: 'owner', route: '/audit',
    markers: ['audit', 'action'], notes: 'Every write, hash-chained. Editing history breaks the chain.' },
  { id: '14_owner_settings', app: 'owner', user: OWNER, role: 'owner', route: '/settings',
    markers: ['setting', 'role', 'threshold'], notes: 'Roles, thresholds and the staff network \u2014 yours to set.' },

  // ══ The manager's day ═══════════════════════════════════════════════════
  { id: '20_manager_hub', app: 'station', user: MGR, role: 'manager', route: '/manager',
    markers: ['stock', 'budget'], notes: 'Every tool the day needs, badged with what is outstanding.' },
  { id: '21_manager_front_house', app: 'station', user: MGR, role: 'manager', route: '/manager/front-desk',
    markers: ['arriv', 'occupancy'], notes: 'Arrivals, departures, occupancy and the cleaning board.' },
  { id: '22_manager_cash', app: 'station', user: MGR, role: 'manager', route: '/manager/cash',
    markers: ['cash', 'expected'], notes: 'A person\u2019s cash in against what the system says they took.' },
  { id: '23_manager_reconcile', app: 'station', user: MGR, role: 'manager', route: '/manager/reconcile',
    markers: ['reconcil', 'payment'], notes: 'Matching payments to the statement.' },
  { id: '24_manager_staff', app: 'station', user: MGR, role: 'manager', route: '/manager/staff',
    markers: ['staff', 'role'], notes: 'Accounts, roles and departments.' },
  { id: '25_manager_roster', app: 'station', user: MGR, role: 'manager', route: '/manager/roster',
    markers: ['roster', 'shift'], notes: 'Who is on which post today.' },
  { id: '26_manager_shifts', app: 'station', user: MGR, role: 'manager', route: '/manager/shifts',
    markers: ['shift', 'schedul'], notes: 'Scheduling ahead.' },
  { id: '27_manager_attendance', app: 'station', user: MGR, role: 'manager', route: '/manager/attendance',
    markers: ['attendance', 'clock'], notes: 'Who actually clocked in, against who was rostered.' },
  { id: '28_manager_leave', app: 'station', user: MGR, role: 'manager', route: '/manager/leave',
    markers: ['leave', 'request'], notes: 'Time off approved with the request in front of you.' },
  { id: '29_manager_purchases', app: 'station', user: MGR, role: 'manager', route: '/manager/purchases',
    markers: ['budget', 'purchase', 'request'], notes: 'A costed request, with the arithmetic when it exceeds budget.' },
  { id: '30_manager_receive', app: 'station', user: MGR, role: 'manager', route: '/manager/receive',
    markers: ['receive', 'purchase', 'deliver'], notes: 'A delivery recorded against a supplier, with the receipt photo.' },
  { id: '31_manager_suppliers', app: 'station', user: MGR, role: 'manager', route: '/manager/suppliers',
    markers: ['supplier'], notes: 'Who the property buys from.' },
  { id: '32_manager_menu', app: 'station', user: CHEF, role: 'head chef', route: '/manager/menu',
    markers: ['menu', 'price', 'recipe'], notes: 'The head chef prices the food and says how each dish draws on stock.' },
  { id: '33_inventory_count', app: 'station', user: MGR, role: 'manager', route: '/inventory/count',
    markers: ['stock', 'count'], notes: 'A count in the unit the item is kept in. A count can never add stock.' },
  { id: '34_manager_resources', app: 'station', user: MGR, role: 'manager', route: '/manager/resources',
    markers: ['villa', 'resource', 'capacity'], notes: 'The villas: what each sleeps, its rate, whether it is in service.' },
  { id: '35_manager_suggestions', app: 'station', user: MGR, role: 'manager', route: '/manager/suggestions',
    markers: ['suggestion'], notes: 'What staff sent up. Owner-only notes never appear here.' },
  { id: '36_manager_disputes', app: 'station', user: MGR, role: 'manager', route: '/manager/disputes',
    markers: ['dispute'], notes: 'A grievance, and the answer that goes back to whoever raised it.' },
  { id: '37_lost_found', app: 'station', user: MGR, role: 'manager', route: '/lost-found',
    markers: ['lost', 'claim'], notes: 'Front desk may look in the box; a manager releases it.' },
  { id: '38_events', app: 'station', user: MGR, role: 'manager', route: '/events',
    markers: ['event', 'guest'], notes: 'A wedding or conference: staffing and the stock set aside for it.' },
  { id: '39_calendar', app: 'station', user: MGR, role: 'manager', route: '/calendar',
    markers: ['calendar', 'september', 'month'], notes: 'Peak days and holidays the whole property can see.' },

  // ══ The floor ═══════════════════════════════════════════════════════════
  { id: '50_gate_hub', app: 'station', user: GATE, role: 'gate lead', route: '/gate/hub',
    markers: ['band', 'gate'], notes: 'The entry fee becomes credit on the band, not a fee that disappears.' },
  { id: '51_gate_band_lookup', app: 'station', user: GATE, role: 'gate lead', route: '/gate/band-lookup',
    markers: ['band', 'look'], notes: '\u201cHow much has this guest got left?\u201d, answered by band number.',
    // A bare search box is a true picture of a screen nobody has used, and it
    // shows a client nothing. USE it: the answer is the feature.
    then: async page => {
      await page.getByPlaceholder(/band number/i).fill('1')
      await page.getByRole('button', { name: /search/i }).click()
      await page.waitForTimeout(1200)
    } },
  { id: '52_gate_waiver', app: 'station', user: WATER, role: 'water lead', route: '/gate/waiver',
    markers: ['waiver', 'sign'], notes: 'A signed waiver recorded against the guest\u2019s band or booking.' },
  { id: '53_front_desk_checkin', app: 'station', user: DESK, role: 'front desk', route: '/front-desk/checkin',
    markers: ['check', 'arriv'], notes: 'Confirm is refused until the deposit is recorded.' },
  { id: '54_front_desk_new_booking', app: 'station', user: DESK, role: 'front desk', route: '/front-desk/new-booking',
    markers: ['booking', 'villa'], notes: 'A booking priced from the villa rate card.' },
  { id: '55_villa_folio', app: 'station', user: DESK, role: 'front desk', route: '/villa',
    markers: ['villa', 'folio', 'room'], notes: 'The room\u2019s whole bill. A villa is settled here and nowhere else.' },
  { id: '56_receipts', app: 'station', user: DESK, role: 'front desk', route: '/receipts',
    markers: ['receipt'], notes: 'Every bill raised today, whatever till raised it.' },
  { id: '57_pos_tabs', app: 'station', user: WAITER, role: 'waiter', route: '/pos/tabs',
    markers: ['tab', 'table'], notes: 'Every bill belongs to a wristband or a room.' },
  { id: '58_kitchen_board', app: 'station', user: CHEF, role: 'head chef', route: '/pos/kitchen',
    markers: ['kitchen'], notes: 'The kitchen queue. Stock moves when an item is marked ready.' },
  { id: '59_bar_board', app: 'station', user: BAR, role: 'bar lead', route: '/pos/bar',
    markers: ['bar'], notes: 'The bar queue, same rule \u2014 the pour moves the stock.' },
  { id: '60_chef_dashboard', app: 'station', user: CHEF, role: 'head chef', route: '/chef',
    markers: ['kitchen', 'chef'], notes: 'The head chef\u2019s own board: recipes, stock and the queue.' },
  { id: '61_pos_spa', app: 'station', user: SPA, role: 'spa attendant', route: '/pos/spa',
    markers: ['spa', 'service'], notes: 'The spa sells its own list \u2014 no food, no bar.' },
  { id: '62_pos_water', app: 'station', user: WATER, role: 'water lead', route: '/pos/water-pay',
    markers: ['water', 'jet', 'boat', 'activit'], notes: 'Water activities, refused without a signed waiver.' },
  { id: '63_safety_check', app: 'station', user: WATER, role: 'water lead', route: '/equipment/safety-check',
    markers: ['safety', 'equipment', 'check'], notes: 'Safety checks recorded against the boat or jet ski.' },
  { id: '64_incidents', app: 'station', user: MGR, role: 'manager', route: '/incidents',
    markers: ['incident'], notes: 'Filed from any post, in front of management immediately.' },

  // ══ The person's own phone ══════════════════════════════════════════════
  { id: '70_employee_clock', app: 'employee', user: WAITER, role: 'waiter', route: '/clock',
    markers: ['clock', 'shift'], notes: 'Clock in \u2014 only from the resort\u2019s own network.' },
  { id: '71_employee_profile', app: 'employee', user: WAITER, role: 'waiter', route: '/profile',
    markers: ['profile'], notes: 'Their own record, and nobody else\u2019s.' },
  { id: '72_employee_leave', app: 'employee', user: WAITER, role: 'waiter', route: '/leave',
    markers: ['leave', 'request'], notes: 'Leave requested here, decided by the manager, answered back.' },
  { id: '73_employee_absence', app: 'employee', user: WAITER, role: 'waiter', route: '/absence',
    markers: ['absence', 'not coming', 'report'], notes: '\u201cI am not coming in today\u201d \u2014 openable off duty, which it once was not.' },
  { id: '74_employee_calendar', app: 'employee', user: WAITER, role: 'waiter', route: '/calendar',
    markers: ['calendar', 'september'], notes: 'The shifts they are on, and the property\u2019s marked days.' },
  { id: '75_employee_notifications', app: 'employee', user: WAITER, role: 'waiter', route: '/notifications',
    markers: ['notification', 'inbox', 'nothing'], notes: 'Their inbox \u2014 where an answered grievance now lands.' },
  { id: '76_employee_conduct', app: 'employee', user: WAITER, role: 'waiter', route: '/conduct',
    markers: ['conduct', 'rule', 'sign'], notes: 'Rules by version, with their signature against each.' },
  { id: '77_employee_disputes', app: 'employee', user: WAITER, role: 'waiter', route: '/disputes',
    markers: ['dispute'], notes: 'A formal route to raise something \u2014 and the reply.' },
  { id: '78_employee_incidents', app: 'employee', user: WAITER, role: 'waiter', route: '/incidents',
    markers: ['incident'], notes: 'Any member of staff can file one from their own phone.' },

  // ══ The guest ═══════════════════════════════════════════════════════════
  { id: '90_kiosk_menu', app: 'employee', user: WAITER, role: 'kiosk', route: '/kiosk/menu',
    markers: ['menu', 'ksh'],
    notes: 'The kiosk a guest touches. No login screen, no staff tools.',
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
