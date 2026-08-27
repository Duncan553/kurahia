/**
 * flows_employee.spec.ts — FUNCTIONAL end-to-end flows through employee_pwa.
 *
 * This is not a route sweep (ui_sweep.spec.ts does layout). Every test here
 * drives a real job a real person does, as the role that would do it, and
 * proves the result twice: once in the UI, once against the API.
 *
 * Ground rules baked into this file, learned the hard way:
 *   1. Never claim an element is broken without proving it — proveUsable()
 *      scrolls it in, calls checkVisibility() (which walks the ancestor chain),
 *      measures the box, and hit-tests the centre point.
 *   2. WaiterTabDetailScreen renders BOTH panes into the DOM (desktop grid +
 *      `md:hidden` mobile copy), so every control there exists twice. .first()
 *      is the desktop copy, which is the visible one at 1280px. Matching both
 *      would be a strict-mode error, not an app bug.
 *   3. AuthGate bounces every non-/clock route back to /clock unless the user
 *      is CLOCKED IN. Seeding a token is not enough — ensureClockedIn() must
 *      run first or every flow "fails" for the wrong reason.
 *   4. POST /auth/login is rate limited to 5/minute per IP (app/auth/routes.py).
 *      Tokens are cached per username and 429 is retried with a backoff.
 *
 * Servers must already be running: backend :5000, employee_pwa :5173.
 *   npx playwright test flows_employee
 */
import { test, expect, Page, Locator, BrowserContext, Browser } from '@playwright/test'

const API = 'http://localhost:5000'
const APP = 'http://localhost:5173'
const PASSWORD = process.env.SEED_PASSWORD ?? 'Kurahia1!'

/* Findings collected as we go; printed as a summary at the end. */
const notes: string[] = []
const note = (s: string) => { notes.push(s); console.log('  · ' + s) }

/* ───────────────────────── API plumbing ───────────────────────── */

type Tok = { access: string; refresh: string; claims: any }
const tokens = new Map<string, Tok>()

function decodeJwt(t: string) {
  return JSON.parse(Buffer.from(t.split('.')[1], 'base64').toString())
}

/** Log in once per username and cache it. 429 (5 logins/min) is retried. */
async function login(username: string): Promise<Tok> {
  const hit = tokens.get(username)
  if (hit) return hit
  for (let attempt = 0; attempt < 6; attempt++) {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: PASSWORD }),
    })
    if (res.ok) {
      const b = await res.json()
      const tok = { access: b.access_token, refresh: b.refresh_token, claims: decodeJwt(b.access_token) }
      tokens.set(username, tok)
      return tok
    }
    if (res.status !== 429) throw new Error(`login ${username} → ${res.status} ${await res.text()}`)
    await new Promise(r => setTimeout(r, 13_000))   // ride out the per-minute window
  }
  throw new Error(`login ${username} — still rate limited after 6 tries`)
}

/** Thin API caller used to CORROBORATE what the UI claims happened. */
async function api(method: string, path: string, username: string, body?: unknown) {
  const { access } = await login(username)
  const res = await fetch(API + path, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${access}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  let data: any = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  return { status: res.status, data }
}

/** AuthGate redirects any non-/clock route to /clock unless status === CLOCK_IN. */
async function ensureClockedIn(username: string) {
  const s = await api('GET', '/hr/clock-status', username)
  if (s.data?.status !== 'CLOCK_IN') await api('POST', '/hr/clock-in', username)
}

/**
 * A browser context already logged in as `username`.
 * The store shape must match shared_ui/src/stores/authStore.ts —
 * zustand `persist`, key 'kurahia-auth', sessionStorage. (owner_pwa uses a
 * different key; that is a different app.)
 * Service workers are blocked so a cached shell can never mask a real result.
 */
async function contextAs(browser: Browser, username: string): Promise<BrowserContext> {
  const { access, refresh, claims } = await login(username)
  const ctx = await browser.newContext({ serviceWorkers: 'block' })
  const state = {
    state: {
      user: { id: claims.sub, username, role_level: claims.role_level ?? 0, department: claims.department ?? null },
      accessToken: access, refreshToken: refresh, isAuthenticated: true, setupToken: null,
    },
    version: 0,
  }
  await ctx.addInitScript(
    ([k, v]) => window.sessionStorage.setItem(k as string, v as string),
    ['kurahia-auth', JSON.stringify(state)] as const,
  )
  return ctx
}

/** Opens a page as `username`, clocked in, with console errors captured. */
async function pageAs(browser: Browser, username: string) {
  await ensureClockedIn(username)
  const ctx = await contextAs(browser, username)
  const page = await ctx.newPage()
  const errors: string[] = []
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
  page.on('pageerror', e => errors.push(String(e)))
  return { ctx, page, errors }
}

/* ─────────────────── empirical visibility proof ─────────────────── */

/**
 * Proves a control is genuinely operable before we blame it for anything.
 * Below the fold is NOT hidden (we scroll it in). Inside overflow-x-auto is
 * NOT hidden (it scrolls). Only zero-size, ancestor-hidden, or actually
 * covered counts as broken.
 */
async function proveUsable(loc: Locator, label: string) {
  /*
   * RETRIES, deliberately.
   *
   * The first version measured once and failed four separate times in this
   * suite — every one of them blaming a control that was actually fine:
   *
   *   - scrollIntoViewIfNeeded() threw "element is not stable" / "not attached
   *     to the DOM", because these screens re-render whenever a query settles
   *   - checkVisibility({checkOpacity:true}) read a control mid-fade-in as
   *     HIDDEN; it was not hidden, it was arriving
   *   - elementFromPoint reported "covered" while a dropdown was still open
   *     over the field beneath it, which is what a dropdown is for
   *
   * A single measurement of an animated, re-rendering UI is a coin flip. So
   * this polls until the control is genuinely usable, and only reports a
   * failure if it never becomes usable. A real problem stays failing; a
   * transient one resolves — which is exactly the distinction the helper exists
   * to make.
   */
  let last: any = null
  await expect.poll(async () => {
    try {
      last = await loc.evaluate((el: HTMLElement) => {
        // Scroll and measure in ONE page-side call so the node cannot be
        // swapped between the two.
        el.scrollIntoView({ block: 'center', behavior: 'instant' as ScrollBehavior })
        const r = el.getBoundingClientRect()
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2
        const onScreen = cx >= 0 && cx <= innerWidth && cy >= 0 && cy <= innerHeight
        const hit = onScreen ? document.elementFromPoint(cx, cy) : null
        const own = !hit || hit === el || el.contains(hit) || hit.contains(el)
        return {
          visible: el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }),
          w: Math.round(r.width), h: Math.round(r.height), onScreen, own,
          blocker: own ? null : `<${hit!.tagName.toLowerCase()} class="${((hit as HTMLElement).className || '').toString().slice(0, 60)}">`,
          disabled: (el as HTMLButtonElement).disabled === true,
        }
      })
    } catch {
      // Detached mid-measure: a re-render, not a broken control. Try again.
      last = null
      return false
    }
    return last.visible && last.w > 0 && last.h > 0 && (!last.onScreen || last.own)
  }, {
    message: `${label} never became usable`,
    timeout: 15_000,
    intervals: [100, 200, 300, 500, 800],
  }).toBe(true)

  // Report WHY it never settled, using the last reading we managed to take.
  expect(last, `${label}: element never stayed attached long enough to measure`).not.toBeNull()
  expect(last.visible, `${label}: checkVisibility() said hidden`).toBe(true)
  expect(last.w > 0 && last.h > 0, `${label}: zero-sized ${last.w}x${last.h}`).toBe(true)
  if (last.onScreen) expect(last.own, `${label}: covered by ${last.blocker}`).toBe(true)
  return last
}

/** Toasts render into TWO containers (desktop + mobile); .first() is desktop. */
function toast(page: Page, text: string | RegExp) {
  return page.locator('[role="status"], [role="alert"]').filter({ hasText: text }).first()
}

const stamp = Date.now().toString().slice(-6)

/* Cross-test state — this file is serial on purpose: the waiter's order in
 * test 2 is the same order the kitchen finishes in test 3 and the manager
 * reconciles in test 7. That chain IS the system. */
const flow = {
  tabId: '',
  tabRef: `PW-${stamp}`,
  item: 'Club Sandwich',   // KITCHEN, KSh 1,200, in_stock: true
  price: 1200,
}

test.setTimeout(180_000)

/* ═══════════════ 1. CLOCK IN / CLOCK OUT — kevin.mutua (housekeeping, L1) ══
 *
 * Split in two on purpose:
 *   1a asserts the BUTTON does what its label says   → currently FAILS (bug)
 *   1b asserts the SCREEN reflects real server state → passes
 * so a broken button can't be confused with a broken screen.
 * ═══════════════════════════════════════════════════════════════════════════ */

/** Force a clock state through the API, bypassing the UI entirely. */
async function forceClock(username: string, want: 'CLOCK_IN' | 'CLOCK_OUT') {
  const s = await api('GET', '/hr/clock-status', username)
  if (s.data?.status !== want) await api('POST', want === 'CLOCK_IN' ? '/hr/clock-in' : '/hr/clock-out', username)
  expect((await api('GET', '/hr/clock-status', username)).data.status).toBe(want)
}

test('1a. clock: the button must call the endpoint its label promises', async ({ browser }) => {
  await forceClock('kevin.mutua', 'CLOCK_IN')
  const ctx = await contextAs(browser, 'kevin.mutua')
  const page = await ctx.newPage()

  // Watch what the button actually sends. This is the airtight proof — no
  // guessing from rendered text, no timing races.
  const sent: string[] = []
  page.on('request', r => { if (/\/hr\/clock-(in|out)$/.test(r.url()) && r.method() === 'POST') sent.push(new URL(r.url()).pathname) })

  await page.goto(`${APP}/clock`, { waitUntil: 'networkidle' })

  const clockOut = page.getByRole('button', { name: 'Clock out', exact: true })
  await expect(clockOut, 'a clocked-in user must be offered Clock out').toBeVisible()
  await proveUsable(clockOut, 'clock-out button')
  await clockOut.click()
  await page.waitForTimeout(2500)

  expect(sent, 'tapping "Clock out" while clocked in must POST /hr/clock-out')
    .toEqual(['/hr/clock-out'])
  expect((await api('GET', '/hr/clock-status', 'kevin.mutua')).data.status,
    'after tapping Clock out the server must say CLOCK_OUT').toBe('CLOCK_OUT')

  // Same button, other direction.
  await forceClock('kevin.mutua', 'CLOCK_OUT')
  sent.length = 0
  await page.reload({ waitUntil: 'networkidle' })
  const clockIn = page.getByRole('button', { name: 'Clock in', exact: true })
  await expect(clockIn).toBeVisible()
  await clockIn.click()
  await page.waitForTimeout(2500)
  expect(sent, 'tapping "Clock in" while clocked out must POST /hr/clock-in')
    .toEqual(['/hr/clock-in'])

  await ctx.close()
})

test('1b. clock: the screen renders real server state and survives a reload', async ({ browser }) => {
  const ctx = await contextAs(browser, 'kevin.mutua')
  const page = await ctx.newPage()

  await forceClock('kevin.mutua', 'CLOCK_OUT')
  await page.goto(`${APP}/clock`, { waitUntil: 'networkidle' })
  await expect(page.getByRole('button', { name: 'Clock in', exact: true })).toBeVisible()
  await expect(page.getByText('Off Duty')).toBeVisible()

  await forceClock('kevin.mutua', 'CLOCK_IN')
  await page.reload({ waitUntil: 'networkidle' })
  await expect(page.getByRole('button', { name: 'Clock out', exact: true })).toBeVisible()
  await expect(page.getByText(/On duty:/)).toBeVisible()
  await expect(page.getByText(/^\d{2}:\d{2}$/).first(), 'start time must be filled in').toBeVisible()

  note('clock screen: renders server state correctly and persists across reload (the BUTTON is the broken part — see 1a)')
  await ctx.close()
})

/* ═══════════════ 2-4. WAITER → KITCHEN → PAYMENT (one continuous shift) ════
 * Tests in a file run in declaration order in a single worker, and 3/4 skip
 * themselves if 2 never produced a tab — so one break reads as one break.
 * ═══════════════════════════════════════════════════════════════════════════ */

/* ═══════════════ 2. WAITER TAKES AN ORDER — joyce.wambua (waiter, L1) ══════ */

test('2. waiter: open a tab, add a menu item, send it to the kitchen', async ({ browser }) => {
  const { ctx, page } = await pageAs(browser, 'joyce.wambua')

  await page.goto(`${APP}/pos/tabs`, { waitUntil: 'networkidle' })
  expect(page.url(), 'AuthGate must not bounce a clocked-in waiter').toContain('/pos/tabs')

  // ── open a new table ──
  const newTable = page.getByRole('button', { name: '+ New Table' })
  await proveUsable(newTable, '+ New Table')
  await newTable.click()
  await page.getByPlaceholder('e.g. Table 7, Beach Bar 3').fill(flow.tabRef)
  await page.getByRole('button', { name: 'Open Table' }).click()

  await page.waitForURL(/\/pos\/tabs\/[0-9a-f-]{36}$/, { timeout: 15_000 })
  flow.tabId = page.url().split('/').pop()!

  // A brand-new tab asks how to start. Take the "Straight to Order" branch.
  const straight = page.getByRole('button', { name: /Straight to Order/ })
  await expect(straight).toBeVisible()
  await proveUsable(straight, 'Straight to Order')
  await straight.click()

  // ── add the item (both panes are in the DOM; .first() is the desktop one) ──
  const addItem = page.getByRole('button', { name: `Add ${flow.item} to order` }).first()
  await expect(addItem).toBeVisible({ timeout: 15_000 })
  await proveUsable(addItem, `menu tile "${flow.item}"`)
  await addItem.click()

  // Draft shows before sending
  const send = page.getByRole('button', { name: /Send Order/ }).first()
  await expect(send).toBeVisible()
  await proveUsable(send, 'Send Order')
  await send.click()
  await expect(toast(page, 'Order sent to kitchen / bar.')).toBeVisible()

  // ── it must now exist on the tab, and survive a reload ──
  const line = page.getByText(new RegExp(`${flow.item}`)).first()
  await expect(line).toBeVisible()
  await page.reload({ waitUntil: 'networkidle' })
  await expect(page.getByText(new RegExp(flow.item)).first()).toBeVisible({ timeout: 15_000 })

  // Cosmetic check worth recording: quantity comes back as Decimal("1.00").
  const qtyText = await page.getByText(new RegExp(`\\S+×\\s*${flow.item}`)).first().innerText()
  if (/1\.00\s*×/.test(qtyText)) note(`COSMETIC: order line renders "${qtyText.trim()}" — raw Decimal quantity ("1.00×" not "1×")`)

  // ── corroborate against the API ──
  const t = await api('GET', `/tabs/${flow.tabId}`, 'joyce.wambua')
  expect(t.status).toBe(200)
  const items = t.data.orders.flatMap((o: any) => o.items)
  expect(items.map((i: any) => i.name)).toContain(flow.item)
  expect(items.find((i: any) => i.name === flow.item).status).toBe('PENDING')
  expect(parseFloat(t.data.balance), 'sending the order must charge the tab').toBe(flow.price)

  note(`waiter order: tab "${flow.tabRef}" opened, ${flow.item} sent, balance KSh ${t.data.balance}`)
  await ctx.close()
})

/* ═══════════════ 3. KITCHEN — cynthia.achieng (head_chef, L3, Kitchen) ═════ */

test('3. kitchen: the order arrives, is received, and is marked ready', async ({ browser }) => {
  test.skip(!flow.tabId, 'test 2 did not produce a tab — nothing to cook')
  const { ctx, page } = await pageAs(browser, 'cynthia.achieng')

  await page.goto(`${APP}/pos/kitchen`, { waitUntil: 'networkidle' })
  await expect(page.getByRole('heading', { name: 'Kitchen Station' })).toBeVisible()

  // The queue is shared with real seed traffic — find OUR ticket by tab reference.
  const ticket = page.locator('.glass-card').filter({ hasText: flow.tabRef }).first()
  await expect(ticket, 'the waiter order must reach the kitchen queue').toBeVisible({ timeout: 20_000 })
  await expect(ticket).toContainText(flow.item)

  // ── PENDING → RECEIVED ──
  const start = ticket.getByRole('button', { name: 'Start Cooking' })
  await proveUsable(start, 'Start Cooking')
  await start.click()
  await expect(ticket.getByRole('button', { name: 'Ready for Pickup' })).toBeVisible({ timeout: 15_000 })

  let items = (await api('GET', `/tabs/${flow.tabId}`, 'cynthia.achieng')).data.orders.flatMap((o: any) => o.items)
  expect(items[0].status).toBe('RECEIVED')

  // ── RECEIVED → READY ──
  const ready = ticket.getByRole('button', { name: 'Ready for Pickup' })
  await proveUsable(ready, 'Ready for Pickup')
  await ready.click()
  await expect(toast(page, 'Waiter has been notified.')).toBeVisible()

  items = (await api('GET', `/tabs/${flow.tabId}`, 'cynthia.achieng')).data.orders.flatMap((o: any) => o.items)
  expect(items[0].status).toBe('READY')

  // A READY item leaves the active queue (queues.py filters PENDING/RECEIVED).
  const q = await api('GET', '/kitchen/queue', 'cynthia.achieng')
  expect(q.data.some((i: any) => i.tab_reference === flow.tabRef)).toBe(false)

  note('kitchen: ticket received → ready, waiter notified, item leaves the active queue')
  await ctx.close()
})

/* ═══════════════ 4. PAYMENT — joyce.wambua ═════════════════════════════════ */

test('4. payment: bad amount is refused in plain English, good amount clears the balance', async ({ browser }) => {
  test.skip(!flow.tabId, 'test 2 did not produce a tab — nothing to pay for')
  const { ctx, page } = await pageAs(browser, 'joyce.wambua')
  await page.goto(`${APP}/pos/tabs/${flow.tabId}`, { waitUntil: 'networkidle' })

  // The waiter marks the ready item served first — that's the real sequence.
  const served = page.getByRole('button', { name: /Served/ }).first()
  await expect(served).toBeVisible({ timeout: 15_000 })
  await proveUsable(served, 'Served')
  await served.click()

  const amount = page.getByPlaceholder('Amount (KSh)').first()
  await expect(amount).toBeVisible()

  // ── NEGATIVE: a nonsense amount must produce a readable message ──
  await amount.fill('-50')
  await page.getByRole('button', { name: 'Record Payment' }).first().click()
  const err = toast(page, /positive number/i)
  await expect(err, 'a bad amount must surface the backend plain-English error').toBeVisible()
  note(`bad payment input → "${(await err.innerText()).replace(/\s+/g, ' ').trim()}"`)
  expect(parseFloat((await api('GET', `/tabs/${flow.tabId}`, 'joyce.wambua')).data.balance)).toBe(flow.price)

  // ── POSITIVE: exact cash ──
  await amount.fill(String(flow.price))
  const pay = page.getByRole('button', { name: 'Record Payment' }).first()
  await proveUsable(pay, 'Record Payment')
  await pay.click()
  await expect(toast(page, 'Payment recorded.')).toBeVisible()

  // Balance in the UI drops to zero and the payment is listed.
  await expect(page.getByText('Balance due').first()).toBeVisible()
  await expect(page.locator('text=CASH').first()).toBeVisible({ timeout: 10_000 })

  const t = await api('GET', `/tabs/${flow.tabId}`, 'joyce.wambua')
  expect(parseFloat(t.data.balance), 'balance must drop to zero').toBe(0)
  expect(t.data.payments.length).toBe(1)
  expect(t.data.payments[0].method).toBe('CASH')

  // Closing the table is only offered once every item is resolved — check it works.
  const close = page.getByRole('button', { name: /Close Table/ }).first()
  await expect(close).toBeVisible({ timeout: 10_000 })
  await proveUsable(close, 'Close Table')
  await close.click()
  await expect(toast(page, 'Table closed.')).toBeVisible()
  await page.waitForURL(/\/pos\/tabs$/)
  expect((await api('GET', `/tabs/${flow.tabId}`, 'joyce.wambua')).data.status).toBe('CLOSED')

  note(`payment: KSh ${flow.price} cash recorded, balance → 0, table closed`)
  await ctx.close()
})

/* ═══════════════ 5. LEAVE REQUEST — kevin.mutua ════════════════════════════ */

test('5. leave: inverted dates are refused, a valid request is submitted and listed', async ({ browser }) => {
  const { ctx, page } = await pageAs(browser, 'kevin.mutua')
  await page.goto(`${APP}/leave`, { waitUntil: 'networkidle' })

  const today = new Date()
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  const start = iso(new Date(today.getTime() + 3 * 864e5))
  const end = iso(new Date(today.getTime() + 4 * 864e5))
  const reason = `Playwright leave ${stamp}`

  const before = (await api('GET', '/hr/leave-requests', 'kevin.mutua')).data.length

  // ── NEGATIVE: end before start ──
  await page.locator('input[type="date"]').first().fill(start)
  await page.locator('input[type="date"]').nth(1).fill(iso(today))
  await page.getByRole('button', { name: 'Submit Request' }).click()
  await expect(page.getByText('End date must be after start date.')).toBeVisible()
  expect((await api('GET', '/hr/leave-requests', 'kevin.mutua')).data.length,
    'an invalid form must not reach the server').toBe(before)
  note('leave: inverted dates blocked with "End date must be after start date."')

  // ── POSITIVE ──
  await page.getByRole('button', { name: 'Sick Leave' }).click()
  await page.locator('input[type="date"]').first().fill(start)
  await page.locator('input[type="date"]').nth(1).fill(end)
  await page.getByPlaceholder(/Family event/).fill(reason)
  const submit = page.getByRole('button', { name: 'Submit Request' })
  await proveUsable(submit, 'Submit Request')
  await submit.click()
  await expect(toast(page, 'Leave request submitted.')).toBeVisible()

  await expect(page.getByText(reason)).toBeVisible({ timeout: 10_000 })
  await page.reload({ waitUntil: 'networkidle' })
  await expect(page.getByText(reason), 'the request must survive a reload').toBeVisible({ timeout: 15_000 })

  const after = (await api('GET', '/hr/leave-requests', 'kevin.mutua')).data
  const mine = after.find((r: any) => r.reason === reason)
  expect(mine, 'the request must exist server-side').toBeTruthy()
  expect(mine.leave_type).toBe('SICK')
  expect(mine.status).toBe('PENDING')

  note(`leave: SICK ${start}→${end} submitted, listed in "My requests", PENDING on the server`)
  await ctx.close()
})

/* ═══════════════ 6. INCIDENT REPORT — kevin.mutua files, brian sees it ═════ */

test('6. incident: empty form is refused, a real report persists and reaches the manager', async ({ browser }) => {
  const { ctx, page } = await pageAs(browser, 'kevin.mutua')
  await page.goto(`${APP}/incidents`, { waitUntil: 'networkidle' })

  const submit = page.getByRole('button', { name: 'Submit Incident Report' })
  await proveUsable(submit, 'Submit Incident Report')

  // ── NEGATIVE: nothing filled in ──
  await submit.click()
  await expect(toast(page, 'Location and description are required.')).toBeVisible()
  note('incident: empty form blocked with "Location and description are required."')

  // ── POSITIVE ──
  const desc = `Playwright incident ${stamp} — guest slipped near the pool steps.`
  await page.getByRole('button', { name: 'High' }).click()
  await page.getByPlaceholder(/Pool area, Jet ski dock/).fill('Pool deck')
  await page.getByPlaceholder(/Describe what happened/).fill(desc)
  await submit.click()
  await expect(toast(page, 'Incident logged.')).toBeVisible()

  // A level-1 reporter has no history list by design (IncidentScreen gates it
  // at level 5), so persistence is proved on the server and in the manager UI.
  const list = (await api('GET', '/incidents?limit=50', 'brian.mwangi')).data
  const mine = list.find((i: any) => i.description === desc)
  expect(mine, 'the incident must exist server-side').toBeTruthy()
  expect(mine.severity).toBe('HIGH')
  expect(mine.location).toBe('Pool deck')
  expect(mine.reported_by).toBe('kevin.mutua')
  await ctx.close()

  // Manager view: it shows up, and Acknowledge works.
  const mgr = await pageAs(browser, 'brian.mwangi')
  await mgr.page.goto(`${APP}/incidents`, { waitUntil: 'networkidle' })
  const card = mgr.page.locator('.glass-card').filter({ hasText: desc }).first()
  await expect(card, 'the manager must see the reported incident').toBeVisible({ timeout: 15_000 })
  await expect(card).toContainText('Needs attention')

  const ack = card.getByRole('button', { name: 'Acknowledge' })
  await proveUsable(ack, 'Acknowledge')
  await ack.click()
  await expect(toast(mgr.page, 'Incident acknowledged.')).toBeVisible()
  const after = (await api('GET', '/incidents?limit=50', 'brian.mwangi')).data.find((i: any) => i.description === desc)
  expect(after.actioned).toBe(true)
  expect(after.actioned_by).toBe('brian.mwangi')

  note('incident: filed by housekeeping (HIGH), visible to manager, Acknowledge writes through')
  await mgr.ctx.close()
})

/* ═══════════════ 7. MANAGER SCREENS — brian.mwangi (manager, L5) ═══════════ */

test('7a. manager/roster: loads real staff and the Set action writes through', async ({ browser }) => {
  const { ctx, page } = await pageAs(browser, 'brian.mwangi')
  await page.goto(`${APP}/manager/roster`, { waitUntil: 'networkidle' })

  await expect(page.getByRole('heading', { name: "Today's Roster" })).toBeVisible()
  // Real data, not a placeholder: every active seeded user has a row.
  const users = (await api('GET', '/auth/users', 'brian.mwangi')).data.filter((u: any) => u.is_active)
  const rows = page.locator('.glass-card').filter({ has: page.locator('select') })
  await expect(rows.first()).toBeVisible({ timeout: 15_000 })
  expect(await rows.count(), 'one roster row per active user').toBe(users.length)

  // ── the action: move a waiter to the Kitchen for today ──
  const row = page.locator('.glass-card').filter({ hasText: 'ivan.kipchoge' }).first()
  await expect(row).toBeVisible()
  const select = row.locator('select')
  await proveUsable(select, 'roster department select')

  // Pick a department Ivan is NOT already on today.
  //
  // This test used to hardcode 'Kitchen'. Roster postings persist for the whole
  // day, so the first run assigned Ivan to Kitchen and every later run then
  // re-selected the department he was already on — at which point
  // `pending === rostered.department_id` and the app CORRECTLY disables Set to
  // stop a no-op write. That looked like "the button is broken"; it was the
  // test not being idempotent against persistent state.
  const currentLabel = (await select.locator('option:checked').textContent())?.trim() ?? ''
  const target = (await select.locator('option').allTextContents())
    .map(t => t.trim())
    .find(t => t && !t.includes('(home)') && t !== currentLabel)
  expect(target, 'need at least one department Ivan is not already posted to').toBeTruthy()
  await select.selectOption({ label: target! })

  const set = row.getByRole('button', { name: 'Set' })
  await proveUsable(set, 'roster Set button')
  expect(await set.isDisabled(), 'Set must enable once a DIFFERENT department is chosen').toBe(false)
  await set.click()

  await expect(row.getByText(new RegExp(`on ${target} today`)),
    'the row must reflect the new posting').toBeVisible({ timeout: 15_000 })
  const roster = (await api('GET', '/hr/roster', 'brian.mwangi')).data
  const ivan = users.find((u: any) => u.username === 'ivan.kipchoge')
  expect(roster.some((r: any) => r.user_id === ivan.id && r.department === target)).toBe(true)

  note(`manager/roster: ${users.length} staff rows from /auth/users; Set posted /hr/roster and the UI updated`)
  await ctx.close()
})

test('7b. manager/staff: loads real accounts and search filters them', async ({ browser }) => {
  const { ctx, page } = await pageAs(browser, 'brian.mwangi')
  await page.goto(`${APP}/manager/staff`, { waitUntil: 'networkidle' })

  await expect(page.getByRole('heading', { name: 'Staff Accounts' })).toBeVisible()
  await expect(page.getByText('joyce.wambua').first()).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('cynthia.achieng').first()).toBeVisible()

  const search = page.getByPlaceholder('Search staff...')
  await proveUsable(search, 'staff search')
  await search.fill('kevin')
  await expect(page.getByText('kevin.mutua').first()).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('joyce.wambua'), 'search must actually filter the list').toHaveCount(0, { timeout: 15_000 })

  note('manager/staff: real accounts listed, server-side search (?q=) filters correctly')
  await ctx.close()
})

test('7c. manager/cash: pulls the waiter\'s pending cash and reconciles it', async ({ browser }) => {
  // Record fresh cash for Joyce rather than relying on test 4's.
  //
  // "Pending" means unreconciled, so once an earlier RUN of this test
  // reconciled her float there was nothing left and every later run failed —
  // the same non-idempotency that made the roster test blame a working button.
  // A test that depends on its own previous run passing is a test that only
  // works once.
  {
    const ref = `cash-${Date.now()}`
    const tab = await api('POST', '/tabs', 'joyce.wambua', { reference: ref, idempotency_key: ref })
    if (tab.status === 201) {
      await api('POST', `/tabs/${tab.data.id}/payments`, 'joyce.wambua',
        { amount: '1200', method: 'CASH', idempotency_key: `pay-${ref}` })
    }
  }

  // The screen must be opened AFTER the cash exists — it reads its figures once
  // on load, so creating the payment later would leave the UI showing a stale
  // total that no longer matches the API.
  const { ctx, page } = await pageAs(browser, 'brian.mwangi')
  await page.goto(`${APP}/manager/cash`, { waitUntil: 'networkidle' })

  await expect(page.getByRole('heading', { name: 'Cash Reconciliation' })).toBeVisible()

  const picker = page.getByRole('button', { name: /Choose a staff member/ })
  await proveUsable(picker, 'staff picker')
  await picker.click()
  const joyce = page.getByRole('button', { name: 'Joyce Wambua', exact: true })
  await expect(joyce, 'seeded HR profiles must populate the picker').toBeVisible({ timeout: 15_000 })
  await joyce.click()

  // There must now be pending cash against Joyce.
  const expectedApi = (await api('GET', `/finance/cash/pending?staff_id=${(await api('GET', '/hr/profiles', 'brian.mwangi')).data.find((p: any) => p.full_name === 'Joyce Wambua').user_id}`, 'brian.mwangi')).data
  expect(expectedApi.payment_count, 'the cash from test 4 must show as pending').toBeGreaterThan(0)

  await expect(page.getByText(/Expected cash from Joyce Wambua/)).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(`KSh ${parseFloat(expectedApi.expected_total).toLocaleString('en-KE', { minimumFractionDigits: 2 })}`)).toBeVisible()

  // ── the action: count exactly what's expected and reconcile ──
  // Wait for the staff dropdown to actually be gone first. It legitimately
  // covers the field below it while open — that is what a dropdown does — so
  // measuring the input before it closes reports "covered" for a control that
  // is fine. The app closes it on select; the test just has to let it.
  // The cash field only EXISTS once a staff member is chosen, so waiting for it
  // is the natural signal that the selection landed and the dropdown closed.
  //
  // Two earlier attempts here were wrong, and both blamed the app: measuring the
  // input while the list was still open reported it "covered" (a dropdown
  // covering the field beneath it is what a dropdown does), and asserting the
  // option list reached zero could never pass because another button on the
  // page shares those classes. Probed directly in a browser: after selection
  // the list returns to baseline and elementFromPoint on the input returns the
  // input. The screen was fine both times.
  const actual = page.getByPlaceholder('0.00')
  await expect(actual, 'the cash field appears once a staff member is chosen')
    .toBeVisible({ timeout: 10_000 })
  await proveUsable(actual, 'actual cash input')
  await actual.fill(expectedApi.expected_total)
  await expect(page.getByText('Balanced')).toBeVisible()

  const reconcile = page.getByRole('button', { name: 'Reconcile' })
  await proveUsable(reconcile, 'Reconcile')
  // Assert on what the SERVER did, not on the wording of a confirmation panel.
  //
  // The panel text is assembled from several JSX expressions, so matching it is
  // brittle in a way that has nothing to do with whether the money reconciled.
  // Watching the response proves the actual outcome — and when this was written
  // it showed 201 with payments_swept 1 and status BALANCED while the text
  // matcher was still failing. The screen was right; the assertion was not.
  const [reconcileResp] = await Promise.all([
    page.waitForResponse(r =>
      r.request().method() === 'POST' && r.url().includes('/finance/cash'), { timeout: 20_000 }),
    reconcile.click(),
  ])
  expect(reconcileResp.status(), 'reconcile must be accepted').toBe(201)
  const swept = await reconcileResp.json()
  expect(swept.status, 'counting exactly the expected cash must balance').toBe('BALANCED')
  expect(swept.payments_swept, 'the pending payments must be swept in').toBeGreaterThan(0)
  const after = (await api('GET', `/finance/cash/pending?staff_id=${expectedApi.staff_id}`, 'brian.mwangi')).data
  expect(after.payment_count, 'reconciling must clear the pending cash').toBe(0)

  note(`manager/cash: KSh ${expectedApi.expected_total} over ${expectedApi.payment_count} payment(s) reconciled BALANCED; pending cleared`)
  await ctx.close()
})

/* ═══════════════ 8. NEGATIVE — a level-1 waiter must be blocked ════════════ */

test('8a. RBAC: a level-1 waiter is blocked from every /manager/* screen', async ({ browser }) => {
  const { ctx, page } = await pageAs(browser, 'joyce.wambua')
  expect((await login('joyce.wambua')).claims.role_level).toBe(1)

  for (const route of ['/manager', '/manager/roster', '/manager/staff', '/manager/cash', '/manager/leave', '/performance']) {
    await page.goto(APP + route, { waitUntil: 'networkidle' })
    await expect(page.getByText('Access restricted'), `${route} must be gated`).toBeVisible({ timeout: 15_000 })
    // and none of the manager content leaked through
    await expect(page.getByRole('heading', { name: "Today's Roster" })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Staff Accounts' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Cash Reconciliation' })).toHaveCount(0)
  }

  // Defense in depth: the API refuses her too, not just the router.
  expect((await api('GET', '/hr/profiles', 'joyce.wambua')).status).toBe(403)
  expect((await api('GET', '/kitchen/queue', 'joyce.wambua')).status).toBe(403)

  note('RBAC: level-1 waiter blocked at the router AND at the API (403 on /hr/profiles, /kitchen/queue)')
  await ctx.close()
})

test('8b. BUG: the "Access restricted" screen has no explanation and no way back', async ({ browser }) => {
  // RoleGate (employee_pwa/src/components/AuthGate.tsx:36-41) passes
  //   message=… and action={{label,onClick}}
  // to <EmptyState>, whose props are description / actionLabel+onAction and
  // which also requires `icon`. Wrong prop names render nothing, so a blocked
  // user gets a bare title and is stranded. This test asserts the INTENDED
  // behaviour, so a failure here IS the bug.
  const { ctx, page } = await pageAs(browser, 'joyce.wambua')
  await page.goto(`${APP}/manager/roster`, { waitUntil: 'networkidle' })
  await expect(page.getByText('Access restricted')).toBeVisible()

  await expect(page.getByText("You don't have permission to view this page."),
    'RoleGate passes `message` but EmptyState reads `description` — the explanation never renders').toBeVisible()
  await expect(page.getByRole('button', { name: 'Go back' }),
    'RoleGate passes `action={{label,onClick}}` but EmptyState reads actionLabel/onAction — the escape hatch never renders').toBeVisible()

  await ctx.close()
})

test.afterAll(() => {
  console.log('\n═══ flows_employee summary ═══')
  for (const n of notes) console.log('  ✔ ' + n)
})
