/**
 * flows_owner_station.spec.ts — FUNCTIONAL flow tests for owner_pwa + station_pwa.
 *
 * This is NOT a layout sweep (ui_sweep.spec.ts already does that). Every test
 * here drives a real business flow end to end and then PROVES the result twice:
 *   1. in the UI (state visible after an action, and still there after reload)
 *   2. against the live API (the row actually changed in the database)
 *
 * Run:  npx playwright test flows_owner_station
 *
 * Servers are assumed already running:
 *   backend :5000   owner :5174   station :5176
 */
import { test, expect, Page, BrowserContext } from '@playwright/test'
import fs from 'fs'
import os from 'os'
import path from 'path'
import { execSync } from 'child_process'

const API      = 'http://localhost:5000'
const OWNER    = 'http://localhost:5174'
const STATION  = 'http://localhost:5176'
const PASSWORD = process.env.SEED_PASSWORD ?? 'Kurahia1!'
const REPO     = path.resolve(__dirname, '../..')

/* ═══════════════════════════════════════════════════════════════════════════
 * AUTH
 *
 * POST /auth/login is rate-limited to 5 per minute per IP (app/auth/routes.py).
 * A spec that logs in per-test blows that budget instantly and every later test
 * fails with a 429 that looks exactly like an app bug. So: log in AT MOST ONCE
 * per username for the whole run, cache the token on disk (survives parallel
 * workers, which are separate processes), and back off if we do get a 429.
 * ═══════════════════════════════════════════════════════════════════════════ */

const TOKEN_CACHE = path.join(os.tmpdir(), 'kurahia-flow-tokens.json')

type Tok = { access: string; refresh: string; at: number }

function readCache(): Record<string, Tok> {
  try { return JSON.parse(fs.readFileSync(TOKEN_CACHE, 'utf8')) } catch { return {} }
}
function writeCache(c: Record<string, Tok>) {
  try { fs.writeFileSync(TOKEN_CACHE, JSON.stringify(c)) } catch { /* best effort */ }
}
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

/** Log in through the real API. Cached for 15 min (access tokens live 30 min,
 *  and axios refreshes them in-page anyway via the 401 interceptor). */
async function apiLogin(username: string): Promise<Tok> {
  const cache = readCache()
  const hit = cache[username]
  if (hit && Date.now() - hit.at < 25 * 60_000) return hit

  for (let attempt = 0; attempt < 3; attempt++) {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: PASSWORD }),
    })
    if (res.status === 429) { await sleep(62_000); continue }   // rate limiter — wait the window out
    if (!res.ok) throw new Error(`login failed for ${username}: ${res.status} ${await res.text()}`)
    const body = await res.json() as { access_token: string; refresh_token: string }
    const fresh = { access: body.access_token, refresh: body.refresh_token, at: Date.now() }
    const c = readCache(); c[username] = fresh; writeCache(c)
    return fresh
  }
  throw new Error(`login for ${username} stayed rate-limited`)
}

function decodeJwt(token: string) {
  return JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString())
}

/** The two apps persist their auth store under DIFFERENT sessionStorage keys.
 *  Seeding the wrong one silently bounces every protected route to /login. */
const STORE_KEY: Record<'owner' | 'station', string> = {
  owner:   'kurahia-owner-auth',   // owner_pwa/src/stores/authStore.ts
  station: 'kurahia-auth',         // shared_ui/src/stores/authStore.ts
}

/** Put a valid zustand-persist payload in sessionStorage before the app boots. */
async function seedAuth(ctx: BrowserContext, app: 'owner' | 'station', username: string) {
  const { access, refresh } = await apiLogin(username)
  const claims = decodeJwt(access)
  const state = {
    state: {
      user: {
        id: claims.sub,
        username,
        role_level: claims.role_level ?? 0,
        department: claims.department ?? null,
      },
      accessToken: access,
      refreshToken: refresh,
      isAuthenticated: true,
      setupToken: null,
    },
    version: 0,
  }
  await ctx.addInitScript(
    ([key, value]) => window.sessionStorage.setItem(key as string, value as string),
    [STORE_KEY[app], JSON.stringify(state)] as const,
  )
}

/** Raw API call as a given user — used to PROVE persistence independent of the UI. */
async function api<T = any>(
  username: string, method: string, path: string, body?: unknown,
): Promise<{ status: number; data: T }> {
  const { access } = await apiLogin(username)
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${access}` },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  })
  const text = await res.text()
  let data: any = null
  try { data = JSON.parse(text) } catch { data = text }
  return { status: res.status, data }
}

/* ═══════════════════════════════════════════════════════════════════════════
 * SHARED PAGE HELPERS
 * ═══════════════════════════════════════════════════════════════════════════ */

/** Go to a route and wait until the data-fetching has actually settled.
 *  networkidle alone isn't enough — react-query fires after hydration. */
async function visit(page: Page, url: string, settleMs = 1200) {
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle').catch(() => { /* long-poll pages never idle */ })
  // Every protected screen renders an <h1> once its lazy chunk has mounted.
  // Waiting on that (instead of a bare timeout) removes the cold-dev-server
  // flake that made /settings look broken on the first run — the module graph
  // is compiled on demand and the first hit can take >2s.
  await page.locator('h1').first().waitFor({ state: 'visible', timeout: 20_000 }).catch(() => {})
  await page.waitForTimeout(settleMs)
}

/** Skeleton placeholders all carry .sk-pulse (shared_ui/src/components/Skeleton.tsx).
 *  Any still on screen after the data settled = a query that never resolved. */
async function assertNoStuckSkeletons(page: Page, where: string) {
  const n = await page.locator('.sk-pulse').count()
  expect(n, `${where}: ${n} skeleton placeholder(s) still rendered after data settled`).toBe(0)
}

/** Collect page console errors, minus the noise that isn't the app's fault. */
function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`))
  return errors
}
function realErrors(errs: string[]): string[] {
  return errs.filter(e =>
    !/Failed to load resource/.test(e) &&      // covered by explicit response assertions
    !/net::ERR_/.test(e) &&
    !/favicon/.test(e) &&
    !/Download the React DevTools/.test(e))
}

/** Toasts render twice (a desktop container and a mobile one) — always .first(). */
function toast(page: Page, text: string | RegExp) {
  return page.getByText(text).first()
}

/** Where the open [role=dialog] actually sits, and whether its scroll container
 *  can move. Used to prove a drawer is unreachable rather than merely below the
 *  fold — "below the fold" is fine, "cannot be scrolled to" is a bug. */
async function drawerGeometry(page: Page) {
  return page.evaluate(() => {
    const d = document.querySelector('[role="dialog"]') as HTMLElement | null
    if (!d) return { present: false, top: 0, bottom: 0, viewportH: window.innerHeight, transform: 'none', scrollH: 0, clientH: 0 }
    const r = d.getBoundingClientRect()
    const inner = d.querySelector('.overflow-y-auto') as HTMLElement | null
    return {
      present: true,
      top: Math.round(r.top),
      bottom: Math.round(r.bottom),
      viewportH: window.innerHeight,
      transform: getComputedStyle(d).transform,
      scrollH: inner?.scrollHeight ?? 0,
      clientH: inner?.clientHeight ?? 0,
    }
  })
}

/* ═══════════════════════════════════════════════════════════════════════════
 * 1. OWNER — /dashboard
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('OWNER · dashboard', () => {
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'owner', 'amara.wanjiku') })

  test('every tile resolves to real data — no stuck skeletons, no error tiles', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${OWNER}/dashboard`, 2500)

    // The screen rendered at all.
    await expect(page.getByRole('heading', { name: /Good (Morning|Afternoon|Evening), Director\./ })).toBeVisible()

    // No tile is stuck in its loading state.
    await assertNoStuckSkeletons(page, '/dashboard')

    // TileError renders the literal string "Couldn't load" — one per failed query.
    const failedTiles = await page.getByText("Couldn't load").count()
    expect(failedTiles, `/dashboard: ${failedTiles} tile(s) rendered the TileError state`).toBe(0)

    // Values are the REAL API values, not placeholders.
    const overview = (await api('amara.wanjiku', 'GET', '/dashboard/overview')).data
    const staff    = (await api('amara.wanjiku', 'GET', '/dashboard/staff')).data
    const alerts   = (await api('amara.wanjiku', 'GET', '/dashboard/alerts')).data

    // TileCard = <div><p>{title}</p>…</div>, so the title's parent is the tile.
    const activeGuests = page.getByText('Active Guests', { exact: true }).locator('..')
    await expect(activeGuests.getByText(String(overview.bookings.active), { exact: true })).toBeVisible()

    const staffTile = page.getByText('Staff On Duty', { exact: true }).locator('..')
    await expect(staffTile.getByText(String(staff.on_duty), { exact: true })).toBeVisible()

    const alertsTile = page.getByText('Judge Alerts', { exact: true }).locator('..')
    await expect(alertsTile.getByText(String(alerts.length), { exact: true })).toBeVisible()

    expect(realErrors(errs), `/dashboard console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('Resort Health tabs switch between overview and department scores', async ({ page }) => {
    await visit(page, `${OWNER}/dashboard`, 2000)

    await expect(page.getByText('Guest Satisfaction')).toBeVisible()
    await page.getByRole('button', { name: 'departments', exact: true }).click()

    // Either department cards or the honest empty line — but NOT the overview metrics.
    await expect(page.getByText('Guest Satisfaction')).toHaveCount(0)
    const feedback = (await api('amara.wanjiku', 'GET', '/dashboard/feedback')).data
    if ((feedback.by_department ?? []).length === 0) {
      await expect(page.getByText('No department data this period.')).toBeVisible()
    }

    await page.getByRole('button', { name: 'overview', exact: true }).click()
    await expect(page.getByText('Guest Satisfaction')).toBeVisible()
  })

  test('refresh control re-fires every tile query', async ({ page }) => {
    await visit(page, `${OWNER}/dashboard`, 2000)
    let refetches = 0
    page.on('request', r => { if (r.url().includes('/dashboard/overview')) refetches++ })
    await page.getByRole('button', { name: 'Refresh all tiles' }).click()
    await page.waitForTimeout(1500)
    expect(refetches, 'refresh button did not re-request /dashboard/overview').toBeGreaterThan(0)
    await assertNoStuckSkeletons(page, '/dashboard after refresh')
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 2. OWNER — /finance
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('OWNER · finance', () => {
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'owner', 'amara.wanjiku') })

  test('money renders and matches the API; period picker re-queries', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${OWNER}/finance`, 2000)

    await expect(page.getByRole('heading', { name: 'Finance' })).toBeVisible()
    await assertNoStuckSkeletons(page, '/finance')

    // Whatever period the screen actually settled on, the P&L must be labelled
    // with it and the API must agree — that part is read from the DOM so the
    // rest of the coverage still runs even while the picker is wrong.
    const selected = await page.locator('#finance-period').inputValue()
    const dash = (await api('amara.wanjiku', 'GET', `/finance/dashboard?period=${selected}`)).data
    expect(dash.revenue, 'finance dashboard API did not return a revenue block').toBeTruthy()
    await expect(page.getByText(`Profit & Loss — ${selected}`)).toBeVisible()

    await expect(page.getByText('Open shortfalls')).toBeVisible()
    const shortfallCard = page.getByText('Open shortfalls').locator('..')
    await expect(shortfallCard.getByText(String(dash.open_shortfalls), { exact: true })).toBeVisible()

    // Switching period must issue a new request for that period.
    const options = await page.locator('#finance-period option').allTextContents()
    const older = options[1]
    const req = page.waitForRequest(r => r.url().includes(`/finance/dashboard?period=${older}`), { timeout: 10_000 })
    await page.locator('#finance-period').selectOption(older)
    await req
    await expect(page.getByText(`Profit & Loss — ${older}`)).toBeVisible()

    /* ── APP BUG (timezone) ───────────────────────────────────────────────
     * PERIODS in FinanceScreen.tsx:44-48 builds each option with
     *     new Date(y, m - i, 1).toISOString().slice(0, 7)
     * `new Date(y, m, 1)` is LOCAL midnight; .toISOString() converts to UTC.
     * The resort runs in Africa/Nairobi (UTC+3), so local 2026-08-01T00:00+03
     * is 2026-07-31T21:00Z and the option renders as "2026-07".
     * Net effect: every option is one month late and the CURRENT month cannot
     * be selected at all. Asserted last so the checks above still run. */
    const localMonth =
      `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`
    expect(options,
      `APP BUG: the current month (${localMonth}) is missing from the finance period ` +
      `picker — FinanceScreen.tsx:44-48 shifts every option one month back in any ` +
      `UTC+ timezone. Options offered: ${options.join(', ')}`,
    ).toContain(localMonth)

    expect(realErrors(errs), `/finance console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('budget tab: month/year toggle and Set Budget form work', async ({ page }) => {
    await visit(page, `${OWNER}/finance`, 2000)
    await page.getByRole('tab', { name: 'Budget Burn' }).click()
    await page.waitForTimeout(1200)

    // Read the period the screen actually selected rather than computing it —
    // FinanceScreen's own list is timezone-shifted (see the APP BUG note in the
    // test above), and this test is about the toggle, not about that bug.
    const period = await page.locator('#finance-period').inputValue()
    const year   = period.slice(0, 4)

    // The Set Budget form must be populated from /auth/users/meta, not empty.
    const deptSelect = page.locator('select').filter({ hasText: 'Select department...' })
    await expect(deptSelect).toBeVisible()
    const optionCount = await deptSelect.locator('option').count()
    expect(optionCount, 'department dropdown has no departments loaded').toBeGreaterThan(1)

    // Yearly toggle must re-query /finance/budgets/status with a bare year.
    const req = page.waitForRequest(r => r.url().includes(`/finance/budgets/status?period=${year}`), { timeout: 10_000 })
    await page.getByRole('tab', { name: `Yearly (${year})` }).click()
    await req

    // And the department rows the API reports as budgeted must be on screen.
    const status = (await api('amara.wanjiku', 'GET', `/finance/budgets/status?period=${period}`)).data
    const budgeted = (status.budgets ?? status ?? []).filter((r: any) => parseFloat(r.budget) > 0)
    await page.getByRole('tab', { name: `Monthly (${period})` }).click()
    await page.waitForTimeout(800)
    for (const row of budgeted) {
      // filter({ visible: true }) is required: the Set Budget <select> at the top
      // of this tab contains an <option>Bar</option> etc. for every department,
      // and options inside a closed select are matched by getByText but are not
      // visible. .first() kept picking the option instead of the budget row.
      await expect(
        page.getByText(row.department, { exact: true }).filter({ visible: true }).first(),
      ).toBeVisible()
    }
    if (budgeted.length === 0) {
      await expect(page.getByText(/No budgets set for this/)).toBeVisible()
    }
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 3. OWNER — /reconciliation
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('OWNER · reconciliation', () => {
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'owner', 'amara.wanjiku') })

  test('balanced / imbalanced state computes and agrees with the API', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${OWNER}/reconciliation`, 2000)

    await expect(page.getByRole('heading', { name: 'Three-Way Reconciliation' })).toBeVisible()
    await assertNoStuckSkeletons(page, '/reconciliation')

    const today = await page.locator('#recon-date').inputValue()
    const recon = (await api('amara.wanjiku', 'GET', `/finance/reconciliation?date=${today}`)).data

    // The badge is the whole point of the screen — it must reflect the API verdict.
    await expect(page.getByText(recon.balanced ? 'Balanced' : 'Imbalanced', { exact: false }).first()).toBeVisible()

    // All three corners rendered with real numbers.
    await expect(page.getByText('Receipts', { exact: true })).toBeVisible()
    await expect(page.getByText('Cash Reconciliation', { exact: true })).toBeVisible()
    await expect(page.getByText('Stock Alerts', { exact: true })).toBeVisible()
    const stockCol = page.getByText('Stock Alerts', { exact: true }).locator('..')
    await expect(stockCol.getByText(String(recon.stock.open_alerts_count), { exact: true })).toBeVisible()

    expect(realErrors(errs), `/reconciliation console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('date picker re-queries reconciliation for the chosen day', async ({ page }) => {
    await visit(page, `${OWNER}/reconciliation`, 1500)
    const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10)
    const req = page.waitForRequest(r => r.url().includes(`/finance/reconciliation?date=${yesterday}`), { timeout: 10_000 })
    await page.locator('#recon-date').fill(yesterday)
    await req
    await page.waitForTimeout(1000)
    // Still a real verdict, not an error banner.
    await expect(page.getByText('Failed to load reconciliation. Select a date that has data.')).toHaveCount(0)
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 4. OWNER — /alerts  (acknowledge + persistence)
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('OWNER · alerts', () => {
  test.describe.configure({ mode: 'serial' })
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'owner', 'amara.wanjiku') })

  /* The seeded alerts were already acknowledged by an earlier run, so there is
   * nothing OPEN left to acknowledge. Rather than skip the flow (the whole point
   * of this screen), plant one OPEN alert as a fixture — same thing
   * scripts/seed_realistic.py does. No application source is touched. */
  test.beforeAll(async () => {
    const open = (await api('amara.wanjiku', 'GET', '/judge/alerts?status=open')).data
    if (Array.isArray(open) && open.length > 0) return
    execSync(
      `python3 -c "
from app import create_app
from app.extensions import db
from app.models.judge_alert import JudgeAlert, AlertStatus, AlertSeverity
app = create_app()
with app.app_context():
    db.session.add(JudgeAlert(
        alert_type='VARIANCE', severity=AlertSeverity.HIGH.value,
        description='PLAYWRIGHT FIXTURE — open alert for the acknowledge flow test.',
        status=AlertStatus.OPEN.value))
    db.session.commit()
"`,
      { cwd: REPO, stdio: 'pipe' },
    )
  })

  test('acknowledging an alert changes state, toasts, and survives a reload', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${OWNER}/alerts`, 1500)

    await expect(page.getByRole('heading', { name: 'Judge Alerts' })).toBeVisible()

    const openBefore = (await api('amara.wanjiku', 'GET', '/judge/alerts?status=open')).data
    expect(openBefore.length, 'fixture did not create an OPEN alert').toBeGreaterThan(0)
    const target = openBefore[0]

    // The card for that alert must be on screen with an Ack button.
    await expect(page.getByText(target.description.slice(0, 40), { exact: false }).first()).toBeVisible()
    // exact:true is load-bearing. Accessible-name matching is a SUBSTRING match
    // by default, so { name: 'Ack' } also matches the "Acknowledged" filter tab,
    // which sits earlier in the DOM — .first() then clicked the tab, the list
    // silently swapped to the acknowledged view, and no modal ever opened. That
    // looked exactly like "the Ack button is a no-op". It isn't.
    await page.getByRole('button', { name: 'Ack', exact: true }).first().click()

    // Confirmation modal, then commit.
    const modal = page.getByRole('dialog')
    await expect(modal).toBeVisible()
    await expect(modal.getByText('This cannot be undone.')).toBeVisible()
    await modal.getByRole('button', { name: 'Acknowledge', exact: true }).click()

    await expect(toast(page, 'Alert acknowledged.')).toBeVisible({ timeout: 10_000 })

    // Proof 1 — the database row changed.
    await expect.poll(async () => {
      const one = (await api('amara.wanjiku', 'GET', '/judge/alerts?status=all')).data
        .find((a: any) => a.id === target.id)
      return one?.status
    }, { timeout: 10_000 }).toBe('ACKNOWLEDGED')

    // Proof 2 — it survives a full reload and shows in the Acknowledged view.
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1500)
    await page.getByRole('button', { name: 'Acknowledged', exact: true }).click()
    await page.waitForTimeout(1200)
    const card = page.getByText(target.description.slice(0, 40), { exact: false }).first()
    await expect(card).toBeVisible()
    await expect(page.getByText('Done', { exact: true }).first()).toBeVisible()

    // And it is gone from the Open view.
    await page.getByRole('button', { name: 'Open', exact: true }).click()
    await page.waitForTimeout(1200)
    await expect(page.getByText(target.description.slice(0, 40), { exact: false })).toHaveCount(0)

    expect(realErrors(errs), `/alerts console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('search filters the alert list and reports an empty result honestly', async ({ page }) => {
    await visit(page, `${OWNER}/alerts`, 1500)
    await page.getByRole('button', { name: 'All', exact: true }).click()
    await page.waitForTimeout(1000)

    const all = (await api('amara.wanjiku', 'GET', '/judge/alerts?status=all')).data
    test.skip(all.length === 0, 'no alerts at all in seed data — nothing to search')

    await page.getByLabel('Search alerts').fill('zzz-no-such-alert-zzz')
    await expect(page.getByText(/No results for/)).toBeVisible()

    // A term that does match brings the row back.
    const word = String(all[0].description).split(' ')[0]
    await page.getByLabel('Search alerts').fill(word)
    await page.waitForTimeout(400)
    await expect(page.getByText(/No results for/)).toHaveCount(0)
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 5. OWNER — /staff
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('OWNER · staff', () => {
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'owner', 'amara.wanjiku') })

  test('list loads every account and the Active/All filter changes the result set', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${OWNER}/staff`, 2000)

    await expect(page.getByRole('heading', { name: 'Staff' })).toBeVisible()
    await assertNoStuckSkeletons(page, '/staff')

    const users  = (await api('amara.wanjiku', 'GET', '/auth/users')).data as any[]
    const active = users.filter(u => u.is_active)
    expect(users.length, 'no users returned by /auth/users').toBeGreaterThan(0)

    // Default tab is Active — a known active username must be visible.
    await expect(page.getByText(active[0].username, { exact: false }).first()).toBeVisible()

    // Switching to All must not shrink the list.
    await page.getByRole('tab', { name: 'All', exact: true }).click()
    await page.waitForTimeout(800)
    for (const u of users.slice(0, 5)) {
      await expect(page.getByText(u.username, { exact: false }).first()).toBeVisible()
    }

    // If any account is inactive, prove the Active filter actually excludes it.
    const inactive = users.find(u => !u.is_active)
    if (inactive) {
      await page.getByRole('tab', { name: 'Active', exact: true }).click()
      await page.waitForTimeout(800)
      await expect(page.getByText(inactive.username, { exact: true })).toHaveCount(0)
    }

    expect(realErrors(errs), `/staff console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('tapping a staff row opens the detail drawer with that account', async ({ page }) => {
    await visit(page, `${OWNER}/staff`, 2000)
    const users = (await api('amara.wanjiku', 'GET', '/auth/users')).data as any[]
    const target = users.filter(u => u.is_active)[0]

    await page.getByText(target.username, { exact: false }).first().click()
    const drawer = page.getByRole('dialog')
    await expect(drawer).toBeVisible()
    await expect(drawer.getByText(target.username, { exact: false }).first()).toBeVisible()
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 6. OWNER — /purchase-approvals  (decide + persistence)
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('OWNER · purchase approvals', () => {
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'owner', 'amara.wanjiku') })

  test('rejecting a pending request persists across reload and in the API', async ({ page }) => {
    const errs = collectConsoleErrors(page)

    const before = (await api('amara.wanjiku', 'GET', '/inventory/purchase-requests')).data as any[]
    const actionable = before.filter(r => r.status === 'PENDING' || r.status === 'PROPOSED')
    test.skip(actionable.length === 0,
      'seed data has no PENDING/PROPOSED purchase request left to decide on')
    const target = actionable[0]

    await visit(page, `${OWNER}/purchase-approvals`, 1800)
    await expect(page.getByRole('heading', { name: 'Purchase Approvals' })).toBeVisible()
    await assertNoStuckSkeletons(page, '/purchase-approvals')

    // Open the drawer for that request.
    await page.getByText(target.item_name, { exact: true }).first().click()
    const drawer = page.getByRole('dialog')
    await expect(drawer).toBeVisible()
    await expect(drawer.getByText(target.requested_by, { exact: false })).toBeVisible()

    /* ── APP BUG (bottom drawer flies off-screen on any press) ────────────
     * Reject is two-step on purpose: "Reject" reveals "Yes, reject".
     * The first press also destroys the drawer. Measured here rather than
     * asserted through a click timeout, so the failure names the real cause.
     *
     * shared_ui/src/components/Drawer.tsx:104-119 — the motion.div carries
     * drag="y" AND a dragControls, but never sets dragListener={false}.
     * framer-motion's dragListener defaults to true, so EVERY pointerdown on
     * the drawer (its own buttons included) opens a drag gesture on top of the
     * intended drag-handle path at line 123. On pointerup the element is left
     * at a drag-derived y instead of snapping back to the animate target. */
    const geoBefore = await drawerGeometry(page)
    await drawer.getByRole('button', { name: 'Reject', exact: true }).click()
    await expect(drawer.getByText('Confirm rejection?')).toBeVisible()
    await page.waitForTimeout(1200)   // let any spring settle
    const geoAfter = await drawerGeometry(page)

    expect(geoAfter.top,
      `APP BUG: pressing a control inside the bottom Drawer throws the whole ` +
      `drawer off-screen. Before the press it sat at y ${geoBefore.top}..${geoBefore.bottom} ` +
      `(viewport 0..${geoBefore.viewportH}); after a single stationary press it is at ` +
      `y ${geoAfter.top}..${geoAfter.bottom} — transform ${geoAfter.transform}. ` +
      `Its scroll container reports scrollHeight ${geoAfter.scrollH} === clientHeight ` +
      `${geoAfter.clientH}, so nothing can scroll it back. "Yes, reject" is unreachable ` +
      `and the approve/reject flow cannot be completed. Root cause: ` +
      `shared_ui/src/components/Drawer.tsx:109-113 (drag="y" with the default ` +
      `dragListener={true}).`,
    ).toBeLessThan(geoBefore.viewportH)

    await drawer.getByRole('button', { name: 'Yes, reject' }).click()

    await expect(toast(page, 'Purchase rejected.')).toBeVisible({ timeout: 10_000 })

    // Proof 1 — the API row moved to REJECTED.
    await expect.poll(async () => {
      const after = (await api('amara.wanjiku', 'GET', '/inventory/purchase-requests')).data as any[]
      return after.find(r => r.id === target.id)?.status
    }, { timeout: 10_000 }).toBe('REJECTED')

    // Proof 2 — after a reload it is in Rejected, not Pending.
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1800)
    await page.getByRole('tab', { name: 'Rejected' }).click()
    await page.waitForTimeout(800)
    await expect(page.getByText(target.item_name, { exact: true }).first()).toBeVisible()

    await page.getByRole('tab', { name: /^Pending/ }).click()
    await page.waitForTimeout(800)
    await expect(page.getByText(target.item_name, { exact: true })).toHaveCount(0)

    expect(realErrors(errs), `/purchase-approvals console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('search filter queries the backend and reports empty results in plain English', async ({ page }) => {
    await visit(page, `${OWNER}/purchase-approvals`, 1800)
    await page.getByRole('tab', { name: 'All', exact: true }).click()

    const req = page.waitForRequest(r => r.url().includes('/inventory/purchase-requests?q='), { timeout: 10_000 })
    await page.getByLabel('Search requests').fill('zzzz-nothing-matches')
    await req
    await page.waitForTimeout(800)
    await expect(page.getByText(/No results for/)).toBeVisible()
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 7. OWNER — payroll / bookings / feedback / settings
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('OWNER · remaining screens', () => {
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'owner', 'amara.wanjiku') })

  test('/payroll lists every employee the API returns', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${OWNER}/payroll`, 2000)

    await expect(page.getByRole('heading', { name: 'Payroll Draft' })).toBeVisible()
    await assertNoStuckSkeletons(page, '/payroll')
    await expect(page.getByText('Failed to load payroll data.')).toHaveCount(0)

    const period = new Date().toISOString().slice(0, 7)
    const payroll = (await api('amara.wanjiku', 'GET', `/finance/payroll?period=${period}`)).data
    if ((payroll.employees ?? []).length === 0) {
      await expect(page.getByText('No active employees with profiles yet.')).toBeVisible()
    } else {
      for (const e of payroll.employees.slice(0, 4)) {
        await expect(page.getByText(e.employee_name, { exact: false }).first()).toBeVisible()
      }
      // Export CSV only appears when there is something to export.
      await expect(page.getByRole('button', { name: 'Export CSV' })).toBeVisible()
    }
    expect(realErrors(errs), `/payroll console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('/bookings loads real bookings; status tabs, date filter and search all work', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${OWNER}/bookings`, 2000)

    await expect(page.getByRole('heading', { name: 'Bookings' })).toBeVisible()
    await assertNoStuckSkeletons(page, '/bookings')

    const bookings = (await api('amara.wanjiku', 'GET', '/bookings?limit=50')).data as any[]
    expect(Array.isArray(bookings), '/bookings did not return a list').toBe(true)

    // The screen opens on the CHECKED_IN tab (BookingsScreen.tsx:231), not on an
    // unfiltered list — comparing it against the raw /bookings response was the
    // spec's own mistake. Switch to All first, then the whole set must be there.
    const tabs = await page.getByRole('tab').all()
    expect(tabs.length, 'no status tabs rendered on /bookings').toBeGreaterThan(1)
    const allReq = page.waitForRequest(r => /\/bookings\?/.test(r.url()), { timeout: 10_000 })
    await page.getByRole('tab', { name: 'All', exact: true }).click()
    await allReq
    await page.waitForTimeout(1200)
    if (bookings.length > 0) {
      await expect(page.getByText(bookings[0].guest_name, { exact: false }).first()).toBeVisible()
    }

    // Another status tab must re-query the backend with that filter.
    const req = page.waitForRequest(r => /\/bookings\?/.test(r.url()), { timeout: 10_000 })
    await page.getByRole('tab', { name: 'Confirmed', exact: true }).click()
    await req

    // Search with a term nothing matches must say so, not blank out silently.
    await page.getByLabel('Search bookings').fill('zzzz-no-guest')
    await page.waitForTimeout(1200)
    await expect(page.getByText(/No results for/)).toBeVisible()

    expect(realErrors(errs), `/bookings console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('/feedback shows the real rating and both tabs render', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${OWNER}/feedback`, 2000)

    await expect(page.getByRole('heading', { name: 'Guest Feedback' })).toBeVisible()
    await assertNoStuckSkeletons(page, '/feedback')

    const fb = (await api('amara.wanjiku', 'GET', '/feedback')).data
    const avg = fb.average_score ? parseFloat(fb.average_score).toFixed(1) : null
    if (avg) await expect(page.getByText(avg, { exact: true }).first()).toBeVisible()
    await expect(page.getByText(String(fb.count), { exact: true }).first()).toBeVisible()

    // The two tabs are labelled "Recent" and "By Staff" (CSS uppercases them,
    // the accessible name is title case). { name: 'staff', exact: true } matched
    // nothing at all.
    await page.getByRole('button', { name: 'By Staff', exact: true }).click()
    await page.waitForTimeout(1200)
    // The staff tab loads /hr/profiles — the picker must actually be populated.
    const profiles = (await api('amara.wanjiku', 'GET', '/hr/profiles')).data as any[]
    if (profiles.length > 0) {
      const selects = page.locator('select')
      if (await selects.count() > 0) {
        expect(await selects.first().locator('option').count()).toBeGreaterThan(1)
      }
    }

    expect(realErrors(errs), `/feedback console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('/settings tabs each load their own data', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${OWNER}/settings`, 2000)

    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()

    const depts = (await api('amara.wanjiku', 'GET', '/admin/departments')).data as any[]
    const roles = (await api('amara.wanjiku', 'GET', '/admin/roles')).data as any[]

    // Departments tab is the default.
    await expect(page.getByText(depts[0].name, { exact: false }).first()).toBeVisible()

    // Walk every tab; each must render without throwing and without a stuck skeleton.
    for (const t of await page.getByRole('tab').all()) {
      const label = (await t.textContent())?.trim() ?? ''
      await t.click()
      await page.waitForTimeout(1200)
      await assertNoStuckSkeletons(page, `/settings → ${label}`)
      const body = await page.locator('body').innerText()
      expect(body.length, `/settings → ${label} rendered nothing`).toBeGreaterThan(50)
    }

    // Roles tab content is real.
    await page.getByRole('tab', { name: /Roles/i }).click()
    await page.waitForTimeout(1000)
    await expect(page.getByText(roles[0].name, { exact: false }).first()).toBeVisible()

    expect(realErrors(errs), `/settings console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 8. OWNER — negative: a manager must not get in
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('OWNER · access control', () => {
  test('a level-5 manager is bounced off every owner route', async ({ context, page }) => {
    await seedAuth(context, 'owner', 'brian.mwangi')   // manager, level 5

    for (const route of ['/dashboard', '/finance', '/staff', '/purchase-approvals', '/settings']) {
      await page.goto(`${OWNER}${route}`, { waitUntil: 'domcontentloaded' })
      // Wait for the redirect instead of sampling the URL after a fixed 900ms.
      // On a cold Vite dev server the first route takes seconds to compile and
      // mount, so the old fixed wait read the URL before AuthGate had rendered
      // at all — it reported "manager reached /dashboard" against a blank page.
      // The bounce is real; only the sampling was wrong.
      await page.waitForURL(/\/login/, { timeout: 20_000 }).catch(() => {})
      expect(page.url(), `manager reached ${route} instead of /login`).toContain('/login')
    }
    // And the login screen is what he actually sees, not a blank shell.
    await expect(page.locator('#login-username')).toBeVisible()
  })

  test('owner API endpoints reject a manager token with a plain-English message', async () => {
    const res = await api('brian.mwangi', 'GET', '/judge/alerts?status=open')
    expect(res.status, 'manager was allowed to read judge alerts').toBe(403)
    expect(typeof res.data?.error, 'error response carried no plain-English message').toBe('string')
    expect(res.data.error.length).toBeGreaterThan(5)
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 9. STATION — full POS flow
 *    open tab → add items → send → kitchen receive/ready → bar receive/ready
 *    → serve → pay → close.
 *
 * Run as brian.mwangi (manager, level 5): the backend lets manager+ operate any
 * prep station (_can_operate_station in app/pos/orders.py), which is what makes
 * one browser able to walk the whole chain. Every POS write is also gated by
 * @require_clocked_in, so we clock in over the API first — the real app does
 * this inside PIN login (StationLoginScreen.tsx), which we bypass by seeding.
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('STATION · POS end to end', () => {
  test.describe.configure({ mode: 'serial' })
  const REF = `PW-${Date.now().toString().slice(-6)}`
  const KITCHEN_ITEM = 'Chips'
  const BAR_ITEM     = 'Tusker Beer'

  test.beforeAll(async () => {
    // @require_clocked_in gates /orders, /order-items/*, /tabs/*/payments…
    await api('brian.mwangi', 'POST', '/hr/clock-in', {})
  })
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'station', 'brian.mwangi') })

  test('open a tab, order food + drink, cook it, serve it, take payment, close it', async ({ page }) => {
    test.setTimeout(180_000)
    const errs = collectConsoleErrors(page)

    /* ── 1. Open a new table ─────────────────────────────────────────────── */
    await visit(page, `${STATION}/pos/tabs`, 1800)
    await expect(page.getByRole('heading', { name: /Tables$/ })).toBeVisible()

    await page.getByRole('button', { name: '+ New Table' }).click()
    const newTableModal = page.getByRole('dialog')
    await expect(newTableModal).toBeVisible()
    await newTableModal.getByPlaceholder('e.g. Table 7, Beach Bar 3').fill(REF)
    await newTableModal.getByRole('button', { name: 'Open Table' }).click()

    // The app navigates straight into the tab detail on success.
    await page.waitForURL(/\/pos\/tabs\/[0-9a-f-]{36}/, { timeout: 15_000 })
    const tabId = page.url().split('/').pop()!
    expect(tabId, 'no tab id in the URL after opening a table').toMatch(/^[0-9a-f-]{36}$/)

    /* ── 2. Add one kitchen item and one bar item ────────────────────────── */
    // A brand-new tab shows the "how would you like to start?" prompt first.
    await page.getByRole('button', { name: /Straight to Order/ }).click()
    await page.waitForTimeout(1200)

    await page.getByRole('button', { name: `Add ${KITCHEN_ITEM} to order` }).click()
    await page.getByRole('button', { name: `Add ${BAR_ITEM} to order` }).click()

    // The order pane must reflect the draft before we send it.
    await expect(page.getByText('New Order')).toBeVisible()
    await expect(page.getByRole('button', { name: /^Send Order/ })).toBeVisible()
    await page.getByRole('button', { name: /^Send Order/ }).click()
    await expect(toast(page, 'Order sent to kitchen / bar.')).toBeVisible({ timeout: 15_000 })

    // Proof: the order really exists on the tab.
    const tabAfterOrder = (await api('brian.mwangi', 'GET', `/tabs/${tabId}`)).data
    const orderItems = (tabAfterOrder.orders ?? []).flatMap((o: any) => o.items)
    expect(orderItems.length, 'sending the order created no order items').toBe(2)
    expect(orderItems.every((i: any) => i.status === 'PENDING')).toBe(true)
    expect(parseFloat(tabAfterOrder.balance), 'tab balance did not rise after ordering').toBeGreaterThan(0)

    /* ── 3. Kitchen board: PENDING → RECEIVED → READY ────────────────────── */
    await visit(page, `${STATION}/pos/kitchen`, 1800)
    await expect(page.getByRole('heading', { name: 'Kitchen Station' })).toBeVisible()

    const kitchenTicket = page.locator('.glass-card').filter({ hasText: REF }).first()
    await expect(kitchenTicket, 'the new order never appeared on the kitchen board').toBeVisible({ timeout: 15_000 })
    await expect(kitchenTicket.getByText(KITCHEN_ITEM)).toBeVisible()

    await kitchenTicket.getByRole('button', { name: 'Start Cooking' }).click()
    await expect.poll(async () => {
      const t = (await api('brian.mwangi', 'GET', `/tabs/${tabId}`)).data
      return t.orders.flatMap((o: any) => o.items).find((i: any) => i.name === KITCHEN_ITEM)?.status
    }, { timeout: 15_000 }).toBe('RECEIVED')

    await expect(kitchenTicket.getByRole('button', { name: 'Ready for Pickup' })).toBeVisible({ timeout: 15_000 })
    await kitchenTicket.getByRole('button', { name: 'Ready for Pickup' }).click()
    await expect(toast(page, 'Waiter has been notified.')).toBeVisible({ timeout: 15_000 })
    await expect.poll(async () => {
      const t = (await api('brian.mwangi', 'GET', `/tabs/${tabId}`)).data
      return t.orders.flatMap((o: any) => o.items).find((i: any) => i.name === KITCHEN_ITEM)?.status
    }, { timeout: 15_000 }).toBe('READY')

    // A READY item drops off the prep queue — that's the board's contract.
    await expect.poll(async () => {
      const q = (await api('brian.mwangi', 'GET', '/kitchen/queue')).data as any[]
      return q.some(i => i.tab_reference === REF)
    }, { timeout: 15_000 }).toBe(false)

    /* ── 4. Bar board: same transitions, different wording ───────────────── */
    await visit(page, `${STATION}/pos/bar`, 1800)
    await expect(page.getByRole('heading', { name: 'Bar Station' })).toBeVisible()
    const barTicket = page.locator('.glass-card').filter({ hasText: REF }).first()
    await expect(barTicket, 'the new order never appeared on the bar board').toBeVisible({ timeout: 15_000 })

    await barTicket.getByRole('button', { name: 'Start Mixing' }).click()
    await expect(barTicket.getByRole('button', { name: 'Ready for Pickup' })).toBeVisible({ timeout: 15_000 })
    await barTicket.getByRole('button', { name: 'Ready for Pickup' }).click()
    await expect.poll(async () => {
      const t = (await api('brian.mwangi', 'GET', `/tabs/${tabId}`)).data
      return t.orders.flatMap((o: any) => o.items).find((i: any) => i.name === BAR_ITEM)?.status
    }, { timeout: 15_000 }).toBe('READY')

    /* ── 5. Waiter serves both items ─────────────────────────────────────── */
    await visit(page, `${STATION}/pos/tabs/${tabId}`, 2000)
    const servedButtons = page.getByRole('button', { name: /Served/ })
    await expect(servedButtons.first()).toBeVisible({ timeout: 15_000 })
    // Click until none are left — the list re-renders after each mutation.
    for (let i = 0; i < 4; i++) {
      if (await servedButtons.count() === 0) break
      await servedButtons.first().click()
      await page.waitForTimeout(1200)
    }
    await expect.poll(async () => {
      const t = (await api('brian.mwangi', 'GET', `/tabs/${tabId}`)).data
      return t.orders.flatMap((o: any) => o.items).every((i: any) => i.status === 'SERVED')
    }, { timeout: 20_000 }).toBe(true)

    /* ── 6. Take the payment ─────────────────────────────────────────────── */
    const owed = parseFloat((await api('brian.mwangi', 'GET', `/tabs/${tabId}`)).data.balance)
    expect(owed, 'nothing owed before payment — the charges never landed').toBeGreaterThan(0)

    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    await expect(page.getByText('Record Payment', { exact: true }).first()).toBeVisible()
    await page.getByRole('button', { name: 'Cash', exact: true }).click()
    // The amount field auto-fills with the exact balance; assert that, don't retype it.
    const amount = page.getByPlaceholder('Amount (KSh)')
    await expect(amount).toHaveValue(String(owed))
    await page.getByRole('button', { name: 'Record Payment' }).click()
    await expect(toast(page, 'Payment recorded.')).toBeVisible({ timeout: 15_000 })

    await expect.poll(async () => {
      const t = (await api('brian.mwangi', 'GET', `/tabs/${tabId}`)).data
      return parseFloat(t.balance)
    }, { timeout: 15_000 }).toBe(0)

    /* ── 7. Close the table ──────────────────────────────────────────────── */
    await expect(page.getByRole('button', { name: /Close Table/ })).toBeVisible({ timeout: 15_000 })
    await page.getByRole('button', { name: /Close Table/ }).click()
    await expect(toast(page, 'Table closed.')).toBeVisible({ timeout: 15_000 })
    await page.waitForURL(/\/pos\/tabs$/, { timeout: 15_000 })

    // Proof: closed in the database, and gone from the open-tables board.
    await expect.poll(async () => {
      return (await api('brian.mwangi', 'GET', `/tabs/${tabId}`)).data.status
    }, { timeout: 15_000 }).toBe('CLOSED')
    await page.waitForTimeout(1500)
    await expect(page.getByText(REF, { exact: true })).toHaveCount(0)

    expect(realErrors(errs), `POS flow console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('an unknown wristband number produces a plain-English error, not a crash', async ({ page }) => {
    await visit(page, `${STATION}/pos/tabs`, 1800)
    await page.getByLabel('Wristband number').fill('999999')
    await page.getByRole('button', { name: 'Open Band' }).click()
    // Backend 404 → toast, and we stay on the tabs screen.
    await expect(toast(page, /not found|No wristband|Band/i)).toBeVisible({ timeout: 10_000 })
    expect(page.url()).toContain('/pos/tabs')
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 10. STATION — gate: issue a wristband, then look it up
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('STATION · gate', () => {
  test.describe.configure({ mode: 'serial' })
  let issuedBand: number | null = null

  test.beforeAll(async () => { await api('hassan.omondi', 'POST', '/hr/clock-in', {}) })
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'station', 'hassan.omondi') })

  test('/gate/hub issues a wristband and the stats update', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${STATION}/gate/hub`, 1800)

    await expect(page.getByRole('heading', { name: 'Gate' })).toBeVisible()
    const statsBefore = (await api('hassan.omondi', 'GET', '/gate/today-stats')).data

    await page.getByRole('button', { name: 'Issue wristband' }).click()
    const modal = page.getByRole('dialog')
    await expect(modal).toBeVisible()
    await expect(modal.getByText(/Payment cannot be reversed/)).toBeVisible()
    await modal.getByRole('button', { name: 'Confirm' }).click()

    await expect(toast(page, /Band #\d+ issued/)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/Last issued: #\d+/)).toBeVisible()

    // Proof: a new active band exists and the day's counter moved.
    const bands = (await api('hassan.omondi', 'GET', '/gate/active-bands')).data as any[]
    expect(bands.length, 'no active band after issuing one').toBeGreaterThan(0)
    issuedBand = bands.map(b => b.band_number).sort((a, b) => b - a)[0]

    await expect.poll(async () => {
      return (await api('hassan.omondi', 'GET', '/gate/today-stats')).data.issued_today
    }, { timeout: 10_000 }).toBe((statsBefore.issued_today ?? 0) + 1)

    expect(realErrors(errs), `/gate/hub console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('/gate/band-lookup finds the band that was just issued', async ({ page }) => {
    test.skip(issuedBand === null, 'no band was issued by the previous test')
    await visit(page, `${STATION}/gate/band-lookup`, 1200)

    await expect(page.getByRole('heading', { name: 'Band Lookup' })).toBeVisible()
    await page.getByPlaceholder('Band number…').fill(String(issuedBand))
    await page.getByRole('button', { name: 'Search' }).click()

    await expect(page.getByText(`Band #${issuedBand}`)).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('Active', { exact: false }).first()).toBeVisible()
    await expect(page.getByText('Issued by')).toBeVisible()

    // Cross-check against the API so we know it's the real record.
    const band = (await api('hassan.omondi', 'GET', `/gate/bands/${issuedBand}`)).data
    expect(band.status).toBe('ACTIVE')
  })

  test('/gate/band-lookup on a missing number shows a plain-English not-found', async ({ page }) => {
    await visit(page, `${STATION}/gate/band-lookup`, 1200)
    await page.getByPlaceholder('Band number…').fill('987654')
    await page.getByRole('button', { name: 'Search' }).click()
    await expect(page.getByText('Band #987654 not found for today.')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('Check the number is correct or try a different date.')).toBeVisible()
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 11. STATION — front desk check-in
 *
 * Seed data has no arrivals today, so this test creates a real booking through
 * the Villa screen (the app's own booking flow) and then tries to check it in.
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('STATION · front desk', () => {
  test.describe.configure({ mode: 'serial' })
  const GUEST = `PW Guest ${Date.now().toString().slice(-5)}`
  let bookingId: string | null = null

  test.beforeAll(async () => { await api('grace.muthoni', 'POST', '/hr/clock-in', {}) })
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'station', 'grace.muthoni') })

  test('/villa creates a real booking for today', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${STATION}/villa`, 2000)

    // Availability drives the villa list — if it 403s or is empty, say so plainly.
    const today = new Date().toISOString().slice(0, 10)
    const week  = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10)
    const avail = await api('grace.muthoni', 'GET',
      `/bookings/availability?resource_type=VILLA&from=${today}T00:00:00&to=${week}T23:59:59`)
    test.skip(avail.status !== 200 || !Array.isArray(avail.data) || avail.data.length === 0,
      `no villa availability for this user (status ${avail.status}) — cannot create a booking`)

    /* The booking form is NOT a dialog — "Book Villa" expands an inline panel
     * inside the villa card (VillaScreen.tsx:145 setBooking, :161-216 the
     * panel). The spec's getByRole('dialog') could never have matched, which
     * is why this read as "the villa screen won't open a booking form". */
    const bookButtons = page.getByRole('button', { name: 'Book Villa' })
    expect(await bookButtons.count(), 'no bookable villa rendered').toBeGreaterThan(0)
    await bookButtons.first().click()
    await expect(page.getByPlaceholder('Guest name')).toBeVisible({ timeout: 10_000 })

    await page.getByPlaceholder('Guest name').fill(GUEST)
    await page.getByPlaceholder('Phone (e.g. 0712...)').fill('0712345678')
    // exact:true — the villa screen's own "Search guests..." box also contains
    // the substring "guests", so the loose match hit two inputs.
    await page.getByPlaceholder('Guests', { exact: true }).fill('2')
    const dateInputs = page.locator('input[type="date"]')
    await dateInputs.nth(0).fill(today)
    await dateInputs.nth(1).fill(new Date(Date.now() + 86_400_000).toISOString().slice(0, 10))

    await page.getByRole('button', { name: 'Confirm Booking' }).click()
    await expect(toast(page, /Villa booked successfully/i)).toBeVisible({ timeout: 15_000 })

    // Proof: the booking is in the database.
    const list = (await api('grace.muthoni', 'GET', '/bookings?limit=50')).data as any[]
    const made = list.find(b => b.guest_name === GUEST)
    expect(made, 'booking form reported success but no booking exists').toBeTruthy()
    bookingId = made.id

    expect(realErrors(errs), `/villa console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })

  test('/front-desk/checkin lists today\'s arrivals and the check-in button acts on them', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${STATION}/front-desk/checkin`, 2000)

    await expect(page.getByRole('heading', { name: 'Front Desk' })).toBeVisible()
    await assertNoStuckSkeletons(page, '/front-desk/checkin')

    const today = (await api('grace.muthoni', 'GET', '/front-desk/today')).data
    const arrivals = today.arrivals ?? []

    // Occupancy tab must always reflect the API.
    await page.getByRole('button', { name: /occupancy/i }).click()
    await page.waitForTimeout(800)
    for (const o of (today.occupancy ?? []).slice(0, 3)) {
      await expect(page.getByText(o.guest_name, { exact: false }).first()).toBeVisible()
    }

    await page.getByRole('button', { name: /arrivals/i }).click()
    await page.waitForTimeout(800)

    if (arrivals.length === 0) {
      await expect(page.getByText('No arrivals today.')).toBeVisible()
      test.skip(true, 'no arrivals today in seed data — check-in flow not reachable')
    }

    const target = arrivals.find((a: any) => a.guest_name === GUEST) ?? arrivals[0]
    await expect(page.getByText(target.guest_name, { exact: false }).first()).toBeVisible()

    /* The front desk is a three-step counter, not one button.

       A villa booking taken through the app lands HELD. It cannot become
       CHECKED_IN directly — VALID_BOOKING_TRANSITIONS (app/models/booking.py)
       allows HELD only to CONFIRMED, and confirming is refused until the
       deposit is recorded (app/bookings/core.py:183).

       This test used to click "Check In" on a HELD row and assert the refusal,
       as a standing report of a dead end: at the time NO screen in any PWA
       called confirm or recorded a deposit, so such a booking could never be
       checked in from the UI. Both now exist on this screen, so the sequence is
       driven for real and any step regressing fails here. */
    const statusOf = async (id: string) =>
      ((await api('grace.muthoni', 'GET', '/bookings?limit=50')).data as any[])
        .find(b => b.id === id)?.status

    // The row is the innermost element that carries BOTH the guest's name and
    // an action. Filtering on the name alone and taking .last() lands on a leaf
    // node inside the row — below the buttons — and then reports them missing.
    const row = page.locator('div')
      .filter({ hasText: target.guest_name })
      .filter({ has: page.getByRole('button', { name: /^(Confirm|Check In)$/ }) })
      .last()

    if (target.status === 'HELD') {
      // The dead-end guard: a HELD row MUST offer a way forward, not only the
      // one action the backend is guaranteed to refuse.
      await expect(row.getByRole('button', { name: /^Confirm$/ }),
        'a HELD arrival offers no way forward — the front-desk dead end is back',
      ).toBeVisible()

      // The deposit has to exist before confirm will pass. Recorded through the
      // same endpoint the row's own deposit control posts to.
      if (parseFloat(target.deposit_required ?? '0') > parseFloat(target.deposit_paid ?? '0')) {
        const dep = await api('grace.muthoni', 'POST', '/booking-payments', {
          booking_id: target.booking_id, purpose: 'DEPOSIT', method: 'CASH',
          amount: target.deposit_required, idempotency_key: crypto.randomUUID(),
        })
        expect([200, 201], `recording the deposit failed: ${JSON.stringify(dep.data)}`)
          .toContain(dep.status)
        await page.reload()
        await page.getByRole('button', { name: /arrivals/i }).click()
        await page.waitForTimeout(800)
      }

      await row.getByRole('button', { name: /^Confirm$/ }).first().click()
      await expect.poll(() => statusOf(target.booking_id), { timeout: 15_000 })
        .toBe('CONFIRMED')
    }

    // CONFIRMED — now, and only now, the row offers check-in.
    const checkIn = row.getByRole('button', { name: /^Check In$/ })
    await expect(checkIn, 'a CONFIRMED arrival must offer Check In').toBeVisible({ timeout: 15_000 })
    await checkIn.first().click()

    await expect.poll(() => statusOf(target.booking_id), { timeout: 20_000 }).toBe('CHECKED_IN')

    /* There is no GET /bookings/<id> route (app/bookings/core.py registers only
       GET "", /availability and /today). An earlier version fetched it, got a
       Flask 404 HTML page, read .status off a string and quietly took the
       "refused" branch for the wrong reason. Read the row out of the list. */
    const after = ((await api('grace.muthoni', 'GET', '/bookings?limit=50')).data as any[])
      .find(b => b.id === target.booking_id)
    expect(after, 'the arrival booking vanished from /bookings').toBeTruthy()
    expect(after.tab_id ?? after.tab, 'checked in but no villa tab was opened').toBeTruthy()

    expect(realErrors(errs), `/front-desk/checkin console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })
})

/* ═══════════════════════════════════════════════════════════════════════════
 * 12. STATION — incidents / housekeeping / safety check
 * ═══════════════════════════════════════════════════════════════════════════ */

test.describe('STATION · incidents', () => {
  test.beforeAll(async () => { await api('brian.mwangi', 'POST', '/hr/clock-in', {}) })
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'station', 'brian.mwangi') })

  test('an empty form is refused in plain English, a filled one persists', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${STATION}/incidents`, 1500)

    await expect(page.getByRole('heading', { name: 'Log Incident' })).toBeVisible()

    // Negative case first: submit with nothing filled.
    await page.getByRole('button', { name: 'Submit Incident Report' }).click()
    await expect(toast(page, 'Location and description are required.')).toBeVisible({ timeout: 10_000 })

    // Now a real submission.
    const marker = `PW incident ${Date.now().toString().slice(-6)}`
    await page.getByRole('button', { name: 'High', exact: true }).click()
    await page.getByPlaceholder('e.g. Pool area, Jet ski dock, Villa 6').fill('Pool area')
    await page.getByPlaceholder('Describe what happened clearly and factually.').fill(marker)
    await page.getByRole('button', { name: 'Submit Incident Report' }).click()
    await expect(toast(page, 'Incident logged.')).toBeVisible({ timeout: 10_000 })

    // Proof 1 — the API has it.
    await expect.poll(async () => {
      const list = (await api('brian.mwangi', 'GET', '/incidents?limit=50')).data as any[]
      return list.some(i => i.description === marker && i.severity === 'HIGH')
    }, { timeout: 10_000 }).toBe(true)

    // Proof 2 — it survives a reload in the history list (manager+ sees history).
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    await expect(page.getByText(marker, { exact: false }).first()).toBeVisible({ timeout: 10_000 })

    // Proof 3 — the form cleared itself, so the next report starts blank.
    await expect(page.getByPlaceholder('e.g. Pool area, Jet ski dock, Villa 6')).toHaveValue('')

    expect(realErrors(errs), `/incidents console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })
})

test.describe('STATION · housekeeping', () => {
  test.beforeAll(async () => { await api('brian.mwangi', 'POST', '/hr/clock-in', {}) })
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'station', 'brian.mwangi') })

  test('board loads every villa and a state change persists', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${STATION}/housekeeping`, 2000)

    await expect(page.getByRole('heading', { name: 'Housekeeping' })).toBeVisible()
    await assertNoStuckSkeletons(page, '/housekeeping')

    const records = (await api('brian.mwangi', 'GET', '/housekeeping/status')).data as any[]
    expect(records.length, '/housekeeping/status returned nothing').toBeGreaterThan(0)
    for (const r of records.slice(0, 4)) {
      await expect(page.getByText(r.resource_name, { exact: true }).first()).toBeVisible()
    }

    // Find a record we can legally advance. CLEAN → INSPECTED is manager-only.
    const inspectable = records.find(r => r.id && r.status === 'CLEAN')
    if (!inspectable) {
      // Not a bug — just no record sitting in the state this control acts on.
      test.skip(true, 'no CLEAN cleaning record to inspect — cannot exercise the transition')
    }

    await page.getByText(inspectable!.resource_name, { exact: true }).first().click()
    const inspectBtn = page.getByRole('button', { name: /Inspect & Approve/ })
    await expect(inspectBtn).toBeVisible({ timeout: 10_000 })
    await inspectBtn.click()

    await expect.poll(async () => {
      const after = (await api('brian.mwangi', 'GET', '/housekeeping/status')).data as any[]
      return after.find(r => r.id === inspectable!.id)?.status
    }, { timeout: 15_000 }).toBe('INSPECTED')

    // And it survives a reload.
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    const card = page.getByText(inspectable!.resource_name, { exact: true }).first().locator('../..')
    await expect(card.getByText(/Inspected/i).first()).toBeVisible({ timeout: 10_000 })

    expect(realErrors(errs), `/housekeeping console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })
})

test.describe('STATION · safety check', () => {
  test.beforeAll(async () => { await api('brian.mwangi', 'POST', '/hr/clock-in', {}) })
  test.beforeEach(async ({ context }) => { await seedAuth(context, 'station', 'brian.mwangi') })

  test('equipment list drives the checklist; empty inventory is stated plainly', async ({ page }) => {
    const errs = collectConsoleErrors(page)
    await visit(page, `${STATION}/equipment/safety-check`, 2000)

    await expect(page.getByRole('heading', { name: 'Safety Check' })).toBeVisible()
    await assertNoStuckSkeletons(page, '/equipment/safety-check')

    const equipment = (await api('brian.mwangi', 'GET', '/equipment')).data as any[]

    if (equipment.length === 0) {
      // Not a bug: the resort has no equipment rows. The screen must SAY that.
      await expect(page.getByText('No equipment configured for water activities.')).toBeVisible()
      expect(realErrors(errs)).toEqual([])
      test.skip(true, 'no equipment seeded — safety-check submission is not reachable')
    }

    // With equipment present, selecting one must load its checklist template.
    await page.getByText(equipment[0].name, { exact: false }).first().click()
    await page.waitForTimeout(1500)
    const noTemplate = await page.getByText('No checklist template configured for this equipment type.').count()
    if (noTemplate > 0) {
      test.skip(true, `no checklist template for ${equipment[0].equipment_type} — submission not reachable`)
    }
    await expect(page.getByRole('heading', { name: equipment[0].name })).toBeVisible()

    expect(realErrors(errs), `/equipment/safety-check console errors: ${realErrors(errs).join(' | ')}`).toEqual([])
  })
})
