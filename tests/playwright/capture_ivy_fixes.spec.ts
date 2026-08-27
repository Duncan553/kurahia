/**
 * capture_ivy_fixes.spec.ts — photograph the two screens this session repaired,
 * so the Ivy Document shows the fix rather than only describing it.
 *
 *   station /gate/issue  -> "Page not found" instead of a login screen
 *   employee /notifications -> now names itself
 *
 * Same rule as the rest of the capture: assert the screen is what it claims to
 * be BEFORE saving an image. A picture of the wrong screen is worse than none.
 */
import { test, expect, Page, BrowserContext } from '@playwright/test'
import fs from 'fs'

const API = 'http://localhost:5000'
const PASSWORD = process.env.SEED_PASSWORD ?? 'Kurahia1!'
const SHOTS = 'docs/ivy/shots'

const tokens = new Map<string, any>()
async function tokenFor(username: string) {
  if (tokens.has(username)) return tokens.get(username)
  for (let i = 0; i < 6; i++) {
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

test.describe.configure({ mode: 'serial' })
test.beforeAll(async () => {
  test.setTimeout(300_000)
  for (const u of ['hassan.omondi', 'ivan.kipchoge']) await tokenFor(u)
})

test('station not-found screen', async ({ browser }) => {
  test.setTimeout(60_000)
  const { ctx, page } = await pageAs(browser, 'hassan.omondi')
  await page.goto('http://localhost:5176/gate/issue', { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle').catch(() => {})
  await expect(page.getByText('Page not found')).toBeVisible()
  fs.mkdirSync(SHOTS, { recursive: true })
  await page.screenshot({ path: `${SHOTS}/station-not-found.jpg`, type: 'jpeg', quality: 62 })
  await ctx.close()
})

test('notifications screen now names itself', async ({ browser }) => {
  test.setTimeout(60_000)
  const { ctx, page } = await pageAs(browser, 'ivan.kipchoge')
  await page.goto('http://localhost:5173/notifications', { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle').catch(() => {})
  // Only meaningful when the inbox has rows — the empty state has always had a
  // title. If it is empty, say so rather than saving a picture of nothing.
  const heading = page.getByRole('heading', { name: 'Notifications' })
  const empty = page.getByText(/all caught up/i)
  if (await empty.isVisible().catch(() => false)) {
    test.skip(true, 'inbox empty — the heading only applies to the populated list')
  }
  await expect(heading).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/staff-notifications.jpg`, type: 'jpeg', quality: 62 })
  await ctx.close()
})
