/**
 * station_notfound.spec.ts — an unknown address must say so, not ask for a login.
 *
 * The station catch-all used to be `{ path: '*', element: <StationLoginScreen /> }`
 * sitting OUTSIDE AuthGate, so any address the app didn't recognise rendered a
 * login screen — to people who were already signed in. A typo or a stale
 * bookmark read as "your session ended", sending staff to chase a sign-in
 * problem that didn't exist.
 *
 * It also made automated capture unsafe: a mistyped route returned a plausible
 * page instead of an error, which is how an earlier screenshot run produced
 * eight identical login screens filed under eight different dashboard names.
 *
 * Both halves are asserted, because fixing one by breaking the other would be
 * worse than the original bug:
 *   signed in  + unknown path -> "Page not found", still signed in
 *   signed out + unknown path -> /login, as before
 */
import { test, expect, Page, BrowserContext } from '@playwright/test'

const API = 'http://localhost:5000'
const STATION = 'http://localhost:5176'
const PASSWORD = process.env.SEED_PASSWORD ?? 'Kurahia1!'
const GATE = 'hassan.omondi'

let cached: any = null

async function tokenFor(username: string) {
  if (cached) return cached
  for (let attempt = 0; attempt < 6; attempt++) {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: PASSWORD }),
    })
    const body = await res.json() as any
    if (body.access_token) { cached = body; return cached }
    if (res.status !== 429) throw new Error(`login ${username}: ${JSON.stringify(body)}`)
    await new Promise(r => setTimeout(r, 20_000))
  }
  throw new Error('stayed rate limited')
}

async function signedInPage(browser: any): Promise<{ ctx: BrowserContext; page: Page }> {
  const t = await tokenFor(GATE)
  const claims = JSON.parse(Buffer.from(t.access_token.split('.')[1], 'base64').toString())
  const ctx: BrowserContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  await ctx.addInitScript(([k, v]: any) => sessionStorage.setItem(k, v), ['kurahia-auth',
    JSON.stringify({
      state: {
        user: { id: claims.sub, username: GATE, role_level: claims.role_level, department: claims.department },
        accessToken: t.access_token, refreshToken: t.refresh_token,
        isAuthenticated: true, setupToken: null,
      }, version: 0,
    })] as const)
  return { ctx, page: await ctx.newPage() }
}

test.describe.configure({ mode: 'serial' })
test.beforeAll(async () => { test.setTimeout(300_000); await tokenFor(GATE) })

// /gate/issue is the exact address that failed: it exists in employee_pwa but
// never existed here, so it fell straight through to the catch-all.
for (const path of ['/gate/issue', '/this/route/does/not/exist']) {
  test(`signed in, ${path} says not found instead of asking for a login`, async ({ browser }) => {
    test.setTimeout(60_000)
    const { ctx, page } = await signedInPage(browser)
    await page.goto(`${STATION}${path}`, { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})

    const text = (await page.locator('body').innerText()).replace(/\s+/g, ' ')

    expect(text, 'the not-found screen should name itself').toContain('Page not found')
    // The actual regression: a signed-in person being shown a login form.
    expect(text, 'must not show a login/PIN prompt to someone already signed in')
      .not.toMatch(/Enter your PIN|Enter PIN|Use password instead/i)
    // And it must not be a dead end — a fixed tablet has no browser back button.
    await expect(page.getByRole('button', { name: /go back/i })).toBeVisible()

    await ctx.close()
  })
}

test('signed out, an unknown address still goes to the login screen', async ({ browser }) => {
  test.setTimeout(60_000)
  // No token injected — this is a fresh tablet with nobody signed in.
  const ctx: BrowserContext = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  await page.goto(`${STATION}/this/route/does/not/exist`, { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle').catch(() => {})

  expect(page.url(), 'AuthGate must still send anonymous visitors to /login').toContain('/login')
  await ctx.close()
})
