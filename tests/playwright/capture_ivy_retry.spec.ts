/**
 * capture_ivy_retry.spec.ts — recapture the five screens the first Ivy run missed.
 *
 * The first pass reported /manager, /clock, /schedule, /performance and
 * /inventory/count as "none of the expected markers rendered". That is a claim
 * about a marker, not about a screen, and the two are easy to confuse — the
 * whole reason this document exists is that an earlier run mistook a login page
 * for eight different dashboards.
 *
 * Reading the source shows real content on all five (ManagerScreen renders
 * "Budget Burn" and "Low Stock"; ScheduleScreen renders "No shift scheduled").
 * So this pass waits for the app shell rather than for guessed heading text,
 * then dumps whatever the page actually says. If a screen really is broken the
 * dump will show it; if it renders, we get the screenshot the document needs.
 */
import { test, expect, Page, BrowserContext } from '@playwright/test'
import fs from 'fs'

const API = 'http://localhost:5000'
const EMPLOYEE = 'http://localhost:5173'
const PASSWORD = process.env.SEED_PASSWORD ?? 'Kurahia1!'
const SHOTS = 'docs/ivy/shots'

const tokens = new Map<string, any>()

async function tokenFor(username: string) {
  if (tokens.has(username)) return tokens.get(username)
  for (let attempt = 0; attempt < 6; attempt++) {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: PASSWORD }),
    })
    const body = await res.json() as any
    if (body.access_token) { tokens.set(username, body); return body }
    if (res.status !== 429) throw new Error(`login ${username}: ${JSON.stringify(body)}`)
    await new Promise(r => setTimeout(r, 20_000))
  }
  throw new Error(`${username} stayed rate limited`)
}

async function pageAs(browser: any, username: string): Promise<{ ctx: BrowserContext; page: Page }> {
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

const TARGETS = [
  { id: 'manager-home',      route: '/manager',         user: 'brian.mwangi' },
  { id: 'staff-clock',       route: '/clock',           user: 'ivan.kipchoge' },
  { id: 'staff-schedule',    route: '/schedule',        user: 'ivan.kipchoge' },
  { id: 'staff-performance', route: '/performance',     user: 'ivan.kipchoge' },
  { id: 'inv-count-chef',    route: '/inventory/count', user: 'cynthia.achieng' },
]

test.describe.configure({ mode: 'serial' })
test.beforeAll(async () => {
  test.setTimeout(300_000)
  for (const u of ['brian.mwangi', 'ivan.kipchoge', 'cynthia.achieng']) await tokenFor(u)
})

const report: any[] = []

for (const t of TARGETS) {
  test(`recapture ${t.id}`, async ({ browser }) => {
    test.setTimeout(90_000)
    const { ctx, page } = await pageAs(browser, t.user)

    await page.goto(`${EMPLOYEE}${t.route}`, { waitUntil: 'domcontentloaded' })

    // Wait for the app shell, not for guessed copy: if we are on a screen at all,
    // the nav is mounted. Then let the data queries settle.
    await page.waitForLoadState('networkidle').catch(() => {})
    await page.locator('body').waitFor({ state: 'visible' })
    await page.waitForTimeout(2500)

    const url = page.url()
    const text = (await page.locator('body').innerText()).replace(/\s+/g, ' ').trim()
    // The one check that matters — did we get bounced to a login wall?
    const bounced = /Enter your PIN|Enter PIN|Sign in|Username/i.test(text) && text.length < 400

    report.push({ id: t.id, route: t.route, user: t.user, url, bounced,
                  chars: text.length, sample: text.slice(0, 220) })

    if (!bounced) {
      fs.mkdirSync(SHOTS, { recursive: true })
      await page.screenshot({ path: `${SHOTS}/${t.id}.jpg`, type: 'jpeg', quality: 62 })
    }
    await ctx.close()
    expect(bounced, `${t.id} bounced to an auth wall: ${text.slice(0, 120)}`).toBe(false)
  })
}

test.afterAll(async () => {
  fs.writeFileSync('docs/ivy/retry_report.json', JSON.stringify(report, null, 1))
  for (const r of report) console.log(`${r.id.padEnd(18)} bounced=${r.bounced} chars=${r.chars} :: ${r.sample.slice(0, 90)}`)
})
