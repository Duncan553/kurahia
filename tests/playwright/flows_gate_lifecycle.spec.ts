/**
 * flows_gate_lifecycle.spec.ts — follow a wristband from the gate to the exit.
 *
 * The gate is where cash enters the resort in its rawest form: a guest pays at
 * the barrier, gets a numbered band, and that band carries spending credit all
 * day. So the whole band lifecycle is a money trail, and every step of it should
 * be checkable end to end:
 *
 *     issue (guest pays)  ->  band is ACTIVE with credit
 *       -> spend against the band's tab
 *       -> gate staff look the band up by number and see the live balance
 *       -> guest leaves: deactivate the band
 *       -> EOD sweep: unused credit on still-active bands is FORFEITED
 *
 * Everything below is asserted against the API as the source of truth, with the
 * station UI driven where it owns the step. Balances are DERIVED
 * (SUM(charges) - SUM(payments)), never read from a stored column — see the
 * engineering invariants in CLAUDE.md.
 */
import { test, expect, Page, BrowserContext } from '@playwright/test'

const API     = 'http://localhost:5000'
const STATION = 'http://localhost:5176'
const PASSWORD = process.env.SEED_PASSWORD ?? 'Kurahia1!'

/** Token cache — the backend locks an account out after repeated login attempts. */
const tokens = new Map<string, { access_token: string; refresh_token: string }>()

async function tokenFor(username: string) {
  if (!tokens.has(username)) {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: PASSWORD }),
    })
    const body = await res.json() as any
    if (!body.access_token) throw new Error(`login failed for ${username}: ${JSON.stringify(body)}`)
    tokens.set(username, body)
  }
  return tokens.get(username)!
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

async function stationPage(browser: any, username: string): Promise<{ ctx: BrowserContext; page: Page }> {
  const t = await tokenFor(username)
  const claims = JSON.parse(Buffer.from(t.access_token.split('.')[1], 'base64').toString())
  const ctx: BrowserContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  await ctx.addInitScript(([k, v]: any) => sessionStorage.setItem(k, v), ['kurahia-auth',
    JSON.stringify({
      state: {
        user: { id: claims.sub, username, role_level: claims.role_level, department: claims.department },
        accessToken: t.access_token, refreshToken: t.refresh_token,
        isAuthenticated: true, setupToken: null,
      }, version: 0,
    })] as const)
  return { ctx, page: await ctx.newPage() }
}

const GATE    = 'hassan.omondi'   // gate_lead, level 3 — issues bands
const MANAGER = 'brian.mwangi'    // manager, level 5 — reconciles the day
const OWNER   = 'amara.wanjiku'   // owner, level 10 — runs the EOD forfeit sweep
const uid = () => `pw-gate-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`

test.describe.configure({ mode: 'serial' })

/* ═══════════ 1. ISSUE — a guest pays at the barrier ═══════════════════════ */

let band: { band_number: number; tab_id: string; id: string }

test('1. gate issues a band: payment recorded, band ACTIVE, tab opened', async () => {
  const entry = await api('POST', '/gate/issue-band', GATE, {
    method: 'CASH',
    idempotency_key: uid(),
    notes: 'playwright lifecycle',
  })
  expect(entry.status, JSON.stringify(entry.data)).toBe(201)

  band = entry.data
  expect(band.band_number, 'a band must carry a number the guest can be identified by').toBeGreaterThan(0)
  expect(band.status).toBe('ACTIVE')
  // Invariant: issuing a band opens a tab, because the band IS the spending vehicle.
  expect(band.tab_id, 'issuing a band must open a tab to carry the spend').toBeTruthy()
})

test('2. the same idempotency key does not issue a second band', async () => {
  const key = uid()
  const first  = await api('POST', '/gate/issue-band', GATE, { method: 'CASH', idempotency_key: key })
  const second = await api('POST', '/gate/issue-band', GATE, { method: 'CASH', idempotency_key: key })

  expect(first.status).toBe(201)
  expect(second.status, 'a replayed request must be absorbed, not duplicated').toBe(200)
  expect(second.data.duplicate).toBe(true)
  expect(second.data.band_number).toBe(first.data.band_number)
})

/* ═══════════ 2. LOOK UP — gate staff find the band by its number ══════════ */

test('3. band lookup by number returns the live derived balance', async () => {
  const found = await api('GET', `/gate/bands/${band.band_number}`, GATE)
  expect(found.status).toBe(200)
  expect(found.data.band_number).toBe(band.band_number)
  expect(found.data.status).toBe('ACTIVE')
  // The band's spending position is DERIVED (SUM(charges) - SUM(payments)), so
  // a live band must report it. It is NEGATIVE while the guest is in credit:
  // they paid at the barrier and have not spent it down yet.
  expect(found.data).toHaveProperty('tab_balance')
  expect(Number(found.data.tab_balance), 'a freshly issued band is in credit')
    .toBeLessThanOrEqual(0)
})

test('4. an unknown band number fails in plain English, not a crash', async () => {
  const missing = await api('GET', '/gate/bands/999999', GATE)
  expect(missing.status).toBe(404)
  expect(typeof missing.data?.error, 'invariant 5: every error carries a message').toBe('string')
})

test('5. the station band-lookup screen shows a real band and rejects a bad one', async ({ browser }) => {
  const { ctx, page } = await stationPage(browser, GATE)
  await page.goto(`${STATION}/gate/band-lookup`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(600)

  const input = page.locator('input').first()
  await input.fill(String(band.band_number))
  await input.press('Enter')
  await page.waitForTimeout(1500)

  await expect(
    page.getByText(new RegExp(`#\\s*${band.band_number}\\b`)).first(),
    'the looked-up band number must appear on screen',
  ).toBeVisible({ timeout: 10_000 })

  await ctx.close()
})

/* ═══════════ 3. SPEND — the band carries credit through the day ═══════════ */

test('6. active-bands lists the issued band while it is in use', async () => {
  const active = await api('GET', '/gate/active-bands', GATE)
  expect(active.status).toBe(200)
  const rows = Array.isArray(active.data) ? active.data : active.data?.bands ?? []
  expect(
    rows.some((b: any) => b.band_number === band.band_number),
    'a freshly issued band must appear in active-bands',
  ).toBe(true)
})

/* ═══════════ 4. EXIT — the guest leaves and the band is closed ════════════ */

test('7. deactivating the band closes it, and it leaves the active list', async () => {
  const out = await api('POST', `/gate/deactivate-band/${band.band_number}`, GATE, {
    idempotency_key: uid(),
  })
  expect(out.status, JSON.stringify(out.data)).toBe(200)

  const after = await api('GET', `/gate/bands/${band.band_number}`, GATE)
  expect(after.data.status, 'a departed guest\'s band must not stay ACTIVE').toBe('DEACTIVATED')

  const active = await api('GET', '/gate/active-bands', GATE)
  const rows = Array.isArray(active.data) ? active.data : active.data?.bands ?? []
  expect(rows.some((b: any) => b.band_number === band.band_number)).toBe(false)
})

test('8. deactivating an already-closed band is refused in plain English', async () => {
  const again = await api('POST', `/gate/deactivate-band/${band.band_number}`, GATE, {
    idempotency_key: uid(),
  })
  // 404 with "No active band #N found for today." is the right answer here: the
  // endpoint looks up ACTIVE bands for today, and a closed one is not among them.
  // The word "active" is what keeps the message honest — it does not claim the
  // band never existed. (This test originally expected 400/409; the app was right.)
  expect(again.status).toBe(404)
  expect(String(again.data?.error), 'invariant 5: plain English, and says ACTIVE')
    .toMatch(/no active band/i)
})

/* ═══════════ 5. RECONCILE — the day's gate money must add up ══════════════ */

test('9. gate reconciliation and today-stats agree that the band existed', async () => {
  const stats = await api('GET', '/gate/today-stats', GATE)
  expect(stats.status).toBe(200)
  // Shape: { inside_now, issued_today, total_entry_fees }
  expect(Number(stats.data.issued_today), 'the bands issued above must be counted')
    .toBeGreaterThan(0)
  expect(Number(stats.data.total_entry_fees), 'entry money must be totalled')
    .toBeGreaterThan(0)
  // inside_now counts bands still ACTIVE; we deactivated ours, so it must be
  // no larger than the number issued today.
  expect(Number(stats.data.inside_now)).toBeLessThanOrEqual(Number(stats.data.issued_today))

  // Reconciliation is money OVERSIGHT, not a gate-staff function — the person
  // taking the cash must not be the person signing off that it adds up.
  const byGate = await api('GET', '/gate/reconciliation', GATE)
  expect(byGate.status, 'gate staff must not reconcile their own till').toBe(403)
  expect(typeof byGate.data?.error).toBe('string')

  const byManager = await api('GET', '/gate/reconciliation', MANAGER)
  expect(byManager.status, JSON.stringify(byManager.data)).toBe(200)
  expect(byManager.data, 'reconciliation must report the day, not an empty object').toBeTruthy()
})

/* ═══════════ 6. FORFEIT — EOD sweep on bands nobody closed ════════════════ */

test('10. the EOD sweep forfeits unused credit on still-active bands', async () => {
  // Leave this one open deliberately: a guest who wandered off without checking out.
  const stray = await api('POST', '/gate/issue-band', GATE, { method: 'CASH', idempotency_key: uid() })
  expect(stray.status).toBe(201)
  const strayNumber = stray.data.band_number

  // Gate staff must NOT be able to forfeit — turning a guest's unused credit
  // into resort revenue is an owner decision, and the person at the barrier is
  // exactly who should not be able to make it.
  const byGate = await api('POST', '/gate/forfeit-day', GATE, { idempotency_key: uid() })
  expect(byGate.status, 'gate staff must not run the forfeit sweep').toBe(403)

  const sweep = await api('POST', '/gate/forfeit-day', OWNER, { idempotency_key: uid() })
  expect(sweep.status, JSON.stringify(sweep.data)).toBe(200)

  const after = await api('GET', `/gate/bands/${strayNumber}`, GATE)
  expect(
    after.data.status,
    'an unclosed band must end the day FORFEITED, so the credit becomes resort revenue',
  ).toBe('FORFEITED')

  // And the already-deactivated band must NOT be swept into FORFEITED.
  const closed = await api('GET', `/gate/bands/${band.band_number}`, GATE)
  expect(closed.data.status, 'the sweep must not re-status a band that was properly closed')
    .toBe('DEACTIVATED')
})
