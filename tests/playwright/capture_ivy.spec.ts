/**
 * capture_ivy.spec.ts — EVIDENCE CAPTURE for the non-technical explainer doc.
 *
 * Prime directive: NEVER screenshot blind. Every shot is preceded by an
 * assertion that a string unique to THAT screen is actually rendered, plus a
 * negative check that we are not sitting on a login / PIN screen. A failed
 * assertion is RECORDED in evidence.json (captured:false) and NO image is
 * saved — a missing screenshot is fine, a mislabelled one is not.
 *
 * Nothing here modifies app source. It reads, it clicks nothing destructive
 * beyond the one deliberate gate-issue + order flow that produces the money
 * and stock evidence.
 */
import { test, expect, Page, BrowserContext } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const API = 'http://localhost:5000'
const PASSWORD = process.env.SEED_PASSWORD ?? 'Kurahia1!'

/** app id -> origin + the sessionStorage key that app's zustand store persists under. */
const APPS = {
  employee: { base: 'http://localhost:5173', key: 'kurahia-auth' },
  owner:    { base: 'http://localhost:5174', key: 'kurahia-owner-auth' },
  station:  { base: 'http://localhost:5176', key: 'kurahia-auth' },
} as const
type AppId = keyof typeof APPS

const SHOTS = path.resolve(__dirname, '../../docs/ivy/shots')
const EVIDENCE = path.resolve(__dirname, '../../docs/ivy/evidence.json')
fs.mkdirSync(SHOTS, { recursive: true })

/* ─────────────────────────── auth (copied from flows_gate_lifecycle) ─────── */

const tokens = new Map<string, { access_token: string; refresh_token: string }>()

async function tokenFor(username: string) {
  if (tokens.has(username)) return tokens.get(username)!
  for (let attempt = 0; attempt < 8; attempt++) {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: PASSWORD }),
    })
    const body = await res.json() as any
    if (body.access_token) { tokens.set(username, body); return tokens.get(username)! }
    // /auth/login is 5-per-minute per IP. Several people from one machine trips
    // it — that is the limiter working. Wait it out.
    if (res.status !== 429) throw new Error(`login failed for ${username}: ${JSON.stringify(body)}`)
    await new Promise(r => setTimeout(r, 20_000))
  }
  throw new Error(`login for ${username} stayed rate-limited after backoff`)
}

async function api(method: string, path: string, username: string, body?: unknown) {
  const { access_token } = await tokenFor(username)
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${access_token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  let data: any = null
  try { data = await res.json() } catch { /* some endpoints return no body */ }
  return { status: res.status, data }
}

/** Same idea as stationPage(), but parameterised by app so it works on 5173/5174/5176. */
async function appPage(browser: any, app: AppId, username: string): Promise<{ ctx: BrowserContext; page: Page }> {
  const t = await tokenFor(username)
  const claims = JSON.parse(Buffer.from(t.access_token.split('.')[1], 'base64').toString())
  const ctx: BrowserContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  // addInitScript runs on every document of this context, so the store is
  // hydrated BEFORE React mounts and AuthGate can't bounce us to /login.
  await ctx.addInitScript(([k, v]: any) => sessionStorage.setItem(k, v), [APPS[app].key,
    JSON.stringify({
      state: {
        user: { id: claims.sub, username, role_level: claims.role_level, department: claims.department },
        accessToken: t.access_token, refreshToken: t.refresh_token,
        isAuthenticated: true, setupToken: null,
      }, version: 0,
    })] as const)
  return { ctx, page: await ctx.newPage() }
}

/* ─────────────────────────── evidence plumbing ───────────────────────────── */

type Entry = {
  id: string; app: string; route: string; user: string; role: string
  captured: boolean
  assert_used: string
  heading_seen?: string
  visible_numbers?: string[]
  failure?: string
  notes?: string
}
const evidence: Entry[] = []
const flows: Record<string, any> = {}

/** Text that only ever appears on a login / PIN screen — the blind-shot tripwire. */
const LOGIN_MARKERS = [
  'Enter your PIN to start your shift', // station_pwa StationLoginScreen
  'Welcome Back',                       // employee_pwa LoginScreen
  'Enter your username',                // employee_pwa LoginScreen
  'e.g. wachira',                       // owner/employee PinEntryScreen
]

/** Pull real currency / number strings out of the rendered text. Never invent. */
function numbersFrom(text: string): string[] {
  const out = new Set<string>()
  for (const m of text.matchAll(/KSh\s?-?[\d,]+(?:\.\d+)?/g)) out.add(m[0].replace(/\s+/g, ' ').trim())
  for (const m of text.matchAll(/\b\d[\d,]*(?:\.\d+)?\s?(?:%|kg|litre|litres|items?|bands?|guests?|pending|unmatched)\b/gi)) out.add(m[0].trim())
  return [...out].slice(0, 14)
}

/** First non-empty line of the rendered body — a decent proxy for "what screen am I on". */
function headingFrom(text: string): string {
  return text.split('\n').map(s => s.trim()).filter(Boolean).slice(0, 6).join(' | ').slice(0, 200)
}

/**
 * Navigate, WAIT for a marker unique to the target screen, verify we're not on
 * a login screen, then and only then save the image.
 */
async function capture(opts: {
  page: Page; app: AppId; id: string; route: string; user: string; role: string
  /** any ONE of these strings appearing in rendered text proves we're on the right screen */
  markers: string[]
  notes?: string
}) {
  const { page, app, id, route, user, role, markers } = opts
  const entry: Entry = {
    id, app: `${app}_pwa`, route, user, role,
    captured: false,
    assert_used: `rendered text contains one of: ${markers.map(m => `"${m}"`).join(' | ')}`,
    notes: opts.notes,
  }

  try {
    await page.goto(`${APPS[app].base}${route}`, { waitUntil: 'domcontentloaded', timeout: 30_000 })
    // TanStack Query re-renders when the fetch lands; wait for the network to
    // go quiet rather than sleeping a fixed amount, then poll for the marker.
    await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {})

    // Case-insensitive: several screens render their section labels in CSS
    // uppercase but the DOM text varies. The strings are still unique per screen.
    let text = ''
    let hit: string | undefined
    const deadline = Date.now() + 20_000
    do {
      text = await page.locator('body').innerText().catch(() => '')
      const hay = text.toLowerCase()
      hit = markers.find(m => hay.includes(m.toLowerCase()))
      if (hit) break
      await page.waitForTimeout(500)
    } while (Date.now() < deadline)

    entry.heading_seen = headingFrom(text)
    entry.visible_numbers = numbersFrom(text)

    const url = page.url()
    const pathname = new URL(url).pathname
    const onLogin = /\/login|\/pin(\/|$)/.test(pathname)
    const loginText = LOGIN_MARKERS.find(m => text.includes(m))

    // These are SPAs: the router picks the screen off the path, so a pathname
    // that no longer equals the requested route means we were redirected and
    // whatever rendered is NOT the screen we asked for.
    if (pathname !== route) {
      entry.failure = `redirected: asked for ${route}, ended on ${pathname}. No image saved.`
      evidence.push(entry); return
    }

    if (onLogin || loginText) {
      entry.failure = `landed on an auth screen (url=${url}${loginText ? `, marker="${loginText}"` : ''}) — NOT the requested screen, no image saved`
      evidence.push(entry); return
    }
    // RoleGate renders this instead of the screen when the account's level is
    // below the route's minLevel. A real product behaviour, worth naming exactly.
    if (!hit && text.includes('Access restricted')) {
      entry.failure = `RoleGate blocked this account: the screen rendered "Access restricted — You don't have permission to view this page." instead of the requested content. No image saved.`
      evidence.push(entry); return
    }
    if (!hit) {
      entry.failure = `none of the expected markers rendered within 20s (final url=${url}). No image saved.`
      evidence.push(entry); return
    }

    await page.screenshot({ path: path.join(SHOTS, `${id}.jpg`), type: 'jpeg', quality: 62 })
    entry.captured = true
    entry.assert_used = `matched "${hit}"`
    evidence.push(entry)
  } catch (err: any) {
    entry.failure = `exception: ${String(err?.message ?? err).slice(0, 300)}`
    evidence.push(entry)
  }
}

/* ─────────────────────────── users ───────────────────────────────────────── */

const GATE   = 'hassan.omondi'     // gate_lead L3
// The brief named peter.mwendwa as the waiter, but that account rejects the
// seed password (see flows.account_findings) — it is the ONLY active user with
// no `.archived` twin, i.e. created through the app rather than the seed, so it
// carries a password nobody recorded. ivan.kipchoge (waiter, Restaurant, L1) is
// the stand-in: same role tier, same story for the document.
const WAITER = 'ivan.kipchoge'     // waiter Restaurant L1
const BAR    = 'david.otieno'      // bar_lead L3
const CHEF   = 'cynthia.achieng'   // head_chef Kitchen L3
const SPA    = 'esther.kamau'      // spa_attendant L2
const WATER  = 'francis.njoroge'   // water_lead L2
const MGR    = 'brian.mwangi'      // manager L5
const OWNER  = 'amara.wanjiku'     // owner L10

const ALL = [GATE, WAITER, BAR, CHEF, SPA, WATER, MGR, OWNER]
/** employee_pwa's AuthGate bounces anyone not CLOCK_IN to /clock — so clock them in. */
const EMPLOYEE_APP_USERS = [MGR, CHEF, WAITER]

const uid = () => `ivy-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
const num = (v: any) => Number(v ?? 0)

test.describe.configure({ mode: 'serial' })

test.beforeAll(async () => {
  test.setTimeout(600_000)

  // Record, don't hide: peter.mwendwa is an active seeded-looking account whose
  // password is not the seed password. Probed once so the finding is evidence,
  // not a claim. One attempt only — repeated failures lock the account.
  const probe = await fetch(`${API}/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'peter.mwendwa', password: PASSWORD }),
  })
  flows.account_findings = {
    'peter.mwendwa': {
      login_status: probe.status,
      response: await probe.json().catch(() => null),
      note: 'Active, role_level 1 (waiter). Rejects the seed password and is the only active user with no ".archived" twin — created through the app, not the seed script. Substituted ivan.kipchoge for the waiter screens.',
    },
  }

  for (const who of ALL) await tokenFor(who)
  for (const who of EMPLOYEE_APP_USERS) {
    const r = await api('POST', '/hr/clock-in', who, { idempotency_key: uid() })
    flows.clock_in = flows.clock_in ?? {}
    flows.clock_in[who] = { status: r.status, event: r.data?.event_type ?? r.data?.error ?? null }
  }
})

test.afterAll(async () => {
  fs.writeFileSync(EVIDENCE, JSON.stringify({
    captured_at_utc: new Date().toISOString(),
    summary: {
      attempted: evidence.length,
      captured: evidence.filter(e => e.captured).length,
      failed: evidence.filter(e => !e.captured).length,
    },
    flows,
    screens: evidence,
  }, null, 2))
})

/* ═══════════ FLOWS — the real money + stock evidence ══════════════════════ */

let band: { band_number: number; tab_id: string; id: string } | null = null

test('flow A: gate issues a real band, then a real order is charged to its tab', async () => {
  test.setTimeout(180_000)

  /* --- 1. issue the band (guest pays at the barrier) --- */
  const issued = await api('POST', '/gate/issue-band', GATE, {
    method: 'CASH', idempotency_key: uid(), notes: 'ivy evidence capture',
  })
  flows.gate = { issue_status: issued.status, issue_response: issued.data }
  expect(issued.status, JSON.stringify(issued.data)).toBe(201)
  band = issued.data

  const stats = await api('GET', '/gate/today-stats', GATE)
  flows.gate.today_stats = stats.data
  const lookup = await api('GET', `/gate/bands/${band!.band_number}`, GATE)
  flows.gate.band_lookup = lookup.data
  flows.gate.band_number = band!.band_number
  flows.gate.tab_id = band!.tab_id

  /* --- 2. tab balance BEFORE any spend --- */
  const before = await api('GET', `/tabs/${band!.tab_id}`, WAITER)
  flows.tab = { get_status: before.status, balance_before: before.data?.balance ?? before.data?.total_due ?? null, raw_before: before.data }

  /* --- 3. pick the menu item whose recipe consumes a known inventory item --- */
  const menu = await api('GET', '/menu/items', WAITER)
  const menuRows: any[] = Array.isArray(menu.data) ? menu.data : menu.data?.items ?? []
  const dish = menuRows.find(m => m.name === 'Grilled Tilapia') ?? menuRows.find(m => m.prep_station === 'KITCHEN')
  flows.inventory = { menu_item: dish ? { id: dish.id, name: dish.name, price: dish.price } : null }

  const recipe = dish ? await api('GET', `/menu/items/${dish.id}/recipe`, MGR) : null
  const lines: any[] = recipe ? (Array.isArray(recipe.data) ? recipe.data : recipe.data?.lines ?? []) : []
  flows.inventory.recipe = lines.map(l => ({ item: l.inventory_item_name, qty: l.quantity, unit: l.unit, id: l.inventory_item_id }))

  const tracked = lines[0]
  const itemsBefore = await api('GET', '/inventory/items', MGR)
  const rowsBefore: any[] = Array.isArray(itemsBefore.data) ? itemsBefore.data : itemsBefore.data?.items ?? []
  const beforeRow = rowsBefore.find(r => r.id === tracked?.inventory_item_id)
  flows.inventory.tracked_item = beforeRow ? { id: beforeRow.id, name: beforeRow.name, unit: beforeRow.unit } : null
  flows.inventory.stock_before = beforeRow?.current_stock ?? null

  /* --- 4. order it onto the band's tab, send it, chef marks READY (deduction point) --- */
  const order = await api('POST', '/orders', WAITER, {
    tab_id: band!.tab_id, idempotency_key: uid(),
    items: [{ menu_item_id: dish.id, quantity: 1 }],
  })
  flows.tab.order_status = order.status
  flows.tab.order_response = order.data

  if (order.status === 201) {
    const sent = await api('POST', `/orders/${order.data.id}/send`, WAITER, { idempotency_key: uid() })
    flows.tab.send_status = sent.status

    // Match on order_id: /kitchen/queue rows carry {order_id, order_item_id},
    // and POST /orders does not return per-item ids, so keying off the order is
    // the only reliable join.
    const q = await api('GET', '/kitchen/queue', CHEF)
    const qRows: any[] = Array.isArray(q.data) ? q.data : q.data?.items ?? []
    const mine = qRows.find(r => r.order_id === order.data.id)
    const oiId = mine?.order_item_id

    if (oiId) {
      // stock is deducted by consume_order_item(), which fires on /ready
      const recv  = await api('POST', `/order-items/${oiId}/receive`, CHEF, { idempotency_key: uid() })
      const ready = await api('POST', `/order-items/${oiId}/ready`, CHEF, { idempotency_key: uid() })
      const serve = await api('POST', `/order-items/${oiId}/serve`, WAITER, { idempotency_key: uid() })
      flows.tab.kitchen = { receive: recv.status, ready: ready.status, serve: serve.status, order_item_id: oiId }
    } else {
      flows.tab.kitchen = { error: 'order item not found on the kitchen queue', queue_size: qRows.length }
    }
  }

  /* --- 5. tab balance AFTER, stock AFTER, and the movement ledger --- */
  const after = await api('GET', `/tabs/${band!.tab_id}`, WAITER)
  flows.tab.balance_after = after.data?.balance ?? after.data?.total_due ?? null
  flows.tab.raw_after = after.data

  const itemsAfter = await api('GET', '/inventory/items', MGR)
  const rowsAfter: any[] = Array.isArray(itemsAfter.data) ? itemsAfter.data : itemsAfter.data?.items ?? []
  flows.inventory.stock_after = rowsAfter.find(r => r.id === tracked?.inventory_item_id)?.current_stock ?? null

  const mv = await api('GET', `/inventory/movements?item_id=${tracked?.inventory_item_id}&limit=8`, MGR)
  const mvRows: any[] = Array.isArray(mv.data) ? mv.data : mv.data?.movements ?? mv.data?.items ?? []
  flows.inventory.movements_status = mv.status
  flows.inventory.movements = mvRows.slice(0, 8)
})

/* ═══════════ ACT 1 — the gate (station_pwa) ══════════════════════════════ */

test('act 1: gate screens', async ({ browser }) => {
  test.setTimeout(240_000)
  const { ctx, page } = await appPage(browser, 'station', GATE)
  const common = { page, app: 'station' as AppId, user: GATE, role: 'gate_lead (L3)' }

  await capture({ ...common, id: 'gate-hub', route: '/gate/hub', markers: ['Issue Band'] })
  // /gate/issue is NOT a route in station_pwa's router (it exists only in
  // employee_pwa). Attempted anyway so the finding is on record.
  await capture({ ...common, id: 'gate-issue', route: '/gate/issue', markers: ['Issue Wristband', 'Wristband'],
    notes: 'station_pwa/src/main.tsx has no /gate/issue route — expected to fall through to the * catch-all' })
  await capture({ ...common, id: 'gate-band-lookup', route: '/gate/band-lookup', markers: ['Band Lookup'] })
  await capture({ ...common, id: 'gate-waiver', route: '/gate/waiver', markers: ['Record Waiver'] })

  await ctx.close()
})

/* ═══════════ ACT 2 — spending against the band (station_pwa) ═════════════ */

test('act 2: POS screens', async ({ browser }) => {
  test.setTimeout(300_000)

  {
    const { ctx, page } = await appPage(browser, 'station', WAITER)
    const common = { page, app: 'station' as AppId, user: WAITER, role: 'waiter Restaurant (L1)' }
    await capture({ ...common, id: 'pos-tabs', route: '/pos/tabs', markers: ['Current Service', 'Assign New Table'] })
    if (band) {
      await capture({ ...common, id: 'pos-tab-detail', route: `/pos/tabs/${band.tab_id}`,
        markers: [`Band #${band.band_number}`, 'CHARGES', 'PAYMENTS'],
        notes: `tab opened by wristband #${band.band_number} — the "one bill per wristband" screen` })
    }
    await ctx.close()
  }
  {
    const { ctx, page } = await appPage(browser, 'station', BAR)
    await capture({ page, app: 'station', id: 'pos-bar', route: '/pos/bar', user: BAR, role: 'bar_lead (L3)', markers: ['Bar Station'] })
    await ctx.close()
  }
  {
    const { ctx, page } = await appPage(browser, 'station', CHEF)
    await capture({ page, app: 'station', id: 'pos-kitchen', route: '/pos/kitchen', user: CHEF, role: 'head_chef Kitchen (L3)', markers: ['Kitchen Station'] })
    await ctx.close()
  }
  {
    const { ctx, page } = await appPage(browser, 'station', SPA)
    await capture({ page, app: 'station', id: 'pos-spa', route: '/pos/spa', user: SPA, role: 'spa_attendant (L2)', markers: ['Sell · View Stock · Request Restock'] })
    await ctx.close()
  }
  {
    const { ctx, page } = await appPage(browser, 'station', WATER)
    await capture({ page, app: 'station', id: 'pos-water-pay', route: '/pos/water-pay', user: WATER, role: 'water_lead (L2)', markers: ['Sell · View Stock · Request Restock'] })
    await ctx.close()
  }
})

/* ═══════════ ACT 3 — inventory (employee_pwa) ════════════════════════════ */

test('act 3: inventory screens', async ({ browser }) => {
  test.setTimeout(300_000)

  {
    const { ctx, page } = await appPage(browser, 'employee', CHEF)
    const common = { page, app: 'employee' as AppId, user: CHEF, role: 'head_chef Kitchen (L3)' }
    await capture({ ...common, id: 'inv-quick-entry', route: '/inventory/quick-entry', markers: ['Quick Entry'] })
    // /inventory/count sits behind RoleGate minLevel=5 — a head chef (L3) is
    // blocked. Attempted as the chef on purpose to record that.
    await capture({ ...common, id: 'inv-count-as-chef', route: '/inventory/count', markers: ['Live stock metrics and recent movements', 'Inventory Overview'],
      notes: 'employee_pwa routes /inventory/count under RoleGate minLevel={5}; head_chef is L3' })
    await capture({ ...common, id: 'chef-dashboard', route: '/chef', markers: ['Chef Dashboard'] })
    await ctx.close()
  }
  {
    const { ctx, page } = await appPage(browser, 'employee', MGR)
    const common = { page, app: 'employee' as AppId, user: MGR, role: 'manager (L5)' }
    await capture({ ...common, id: 'inv-count', route: '/inventory/count', markers: ['Live stock metrics and recent movements', 'Inventory Overview'],
      notes: 'same route as inv-count-as-chef, but with a level-5 account' })
    await capture({ ...common, id: 'inv-purchase-request', route: '/inventory/purchase-request', markers: ['Purchase Request'] })
    await capture({ ...common, id: 'manager-purchases', route: '/manager/purchases', markers: ['Purchase Requests'] })
    await capture({ ...common, id: 'manager-menu', route: '/manager/menu', markers: ['Menu & Services', 'Menu &amp; Services'] })
    await ctx.close()
  }
})

/* ═══════════ ACT 4 — manager dashboards (employee_pwa) ═══════════════════ */

test('act 4: manager dashboards', async ({ browser }) => {
  test.setTimeout(300_000)
  const { ctx, page } = await appPage(browser, 'employee', MGR)
  const common = { page, app: 'employee' as AppId, user: MGR, role: 'manager (L5)' }

  await capture({ ...common, id: 'manager-home',       route: '/manager',            markers: ['STOCK BY DEPARTMENT', 'BUDGET BURN', 'STOCK BEHAVIOR'] })
  await capture({ ...common, id: 'manager-cash',       route: '/manager/cash',       markers: ['Cash Reconciliation'] })
  await capture({ ...common, id: 'manager-staff',      route: '/manager/staff',      markers: ['Staff Accounts'] })
  await capture({ ...common, id: 'manager-attendance', route: '/manager/attendance', markers: ['Attendance'] })
  await capture({ ...common, id: 'manager-shifts',     route: '/manager/shifts',     markers: ['Shifts'] })
  await capture({ ...common, id: 'manager-roster',     route: '/manager/roster',     markers: ["Today's Roster"] })
  await capture({ ...common, id: 'manager-leave',      route: '/manager/leave',      markers: ['Leave Requests'] })
  await capture({ ...common, id: 'manager-front-desk', route: '/manager/front-desk', markers: ['Front Desk'] })

  await ctx.close()
})

/* ═══════════ ACT 5 — owner dashboards (owner_pwa) ════════════════════════ */

test('act 5: owner dashboards', async ({ browser }) => {
  test.setTimeout(400_000)
  const { ctx, page } = await appPage(browser, 'owner', OWNER)
  const common = { page, app: 'owner' as AppId, user: OWNER, role: 'owner (L10)' }

  await capture({ ...common, id: 'owner-dashboard',          route: '/dashboard',          markers: ['Resort Health'] })
  await capture({ ...common, id: 'owner-finance',            route: '/finance',            markers: ['Revenue, expenses, reconciliation summaries', 'PROFIT & LOSS'] })
  await capture({ ...common, id: 'owner-reconciliation',     route: '/reconciliation',     markers: ['Three-Way Reconciliation'] })
  await capture({ ...common, id: 'owner-audit',              route: '/audit',              markers: ['Audit Trail'] })
  await capture({ ...common, id: 'owner-menu-profit',        route: '/menu-profit',        markers: ['Menu Profit'] })
  await capture({ ...common, id: 'owner-alerts',             route: '/alerts',             markers: ['Judge Alerts'] })
  await capture({ ...common, id: 'owner-payroll',            route: '/payroll',            markers: ['Payroll Draft'] })
  await capture({ ...common, id: 'owner-purchase-approvals', route: '/purchase-approvals', markers: ['Purchase Approvals'] })
  await capture({ ...common, id: 'owner-staff',              route: '/staff',              markers: ['Employee accounts, roles, departments'] })
  await capture({ ...common, id: 'owner-bookings',           route: '/bookings',           markers: ['Villa & event bookings, deposits, check-in'] })
  await capture({ ...common, id: 'owner-feedback',           route: '/feedback',           markers: ['Reviews and ratings from guests', 'OVERALL RATING'] })
  await capture({ ...common, id: 'owner-settings',           route: '/settings',           markers: ['Business day, system configuration', 'Judge Baselines'] })

  await ctx.close()
})

/* ═══════════ ACT 6 — staff-facing (employee_pwa) ═════════════════════════ */

test('act 6: staff-facing screens', async ({ browser }) => {
  test.setTimeout(240_000)
  const { ctx, page } = await appPage(browser, 'employee', WAITER)
  const common = { page, app: 'employee' as AppId, user: WAITER, role: 'waiter Restaurant (L1)' }

  await capture({ ...common, id: 'staff-clock',         route: '/clock',         markers: ['SHIFT STATUS', 'CLOCK OUT', 'CLOCK IN'] })
  // NotificationsScreen renders NO heading once it has rows — just the list.
  // So there is no static marker: assert on the real subject line the API says
  // this user has, and fall back to the empty-state text when the inbox is bare.
  const inbox = await api('GET', '/notifications/inbox', WAITER)
  const inboxRows: any[] = Array.isArray(inbox.data) ? inbox.data : inbox.data?.items ?? []
  const inboxMarkers = inboxRows.length
    ? [inboxRows[0].subject].filter(Boolean)
    : ["You're all caught up"]
  await capture({ ...common, id: 'staff-notifications', route: '/notifications', markers: inboxMarkers,
    notes: `inbox has ${inboxRows.length} row(s); this screen renders no title when populated, so the assertion is the real subject line from GET /notifications/inbox` })
  // /performance and /schedule are behind RoleGate minLevel={5} in
  // employee_pwa/src/main.tsx — a level-1 waiter cannot reach either.
  await capture({ ...common, id: 'staff-performance', route: '/performance', markers: ['Guest Rating', 'Punctuality'],
    notes: 'RoleGate minLevel={5}; a waiter is L1' })
  await capture({ ...common, id: 'staff-schedule', route: '/schedule', markers: ['Monday', 'No shift scheduled'],
    notes: 'RoleGate minLevel={5}; a waiter is L1' })

  // The two above are recorded as failures because the REQUESTED screen never
  // rendered. But the block itself is real product behaviour worth a picture,
  // so capture it once under an id that says exactly what it is — asserted on
  // the block's own text, not mislabelled as the screen behind it.
  await capture({ ...common, id: 'access-restricted-l1', route: '/performance',
    markers: ['Access restricted'],
    notes: 'What a level-1 account actually sees at a manager-only route. This is the RoleGate block, NOT the Performance screen.' })

  await ctx.close()
})
