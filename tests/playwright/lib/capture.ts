/**
 * capture.ts — the screenshot harness, extracted so more than one spec can use
 * it without a second copy drifting out of step.
 *
 * Prime directive, unchanged from capture_ivy.spec.ts: NEVER screenshot blind.
 * Every shot is preceded by an assertion that a string unique to THAT screen
 * really rendered, plus a negative check that we are not sitting on a login or
 * PIN screen. A failed assertion is RECORDED and NO image is saved.
 *
 * This exists because an earlier run produced 8 byte-identical login
 * screenshots filed under 8 different dashboard names. A missing screenshot is
 * fine. A mislabelled one is a lie in a document a client will read.
 */
import { Page, BrowserContext } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const API = 'http://localhost:5000'
const PASSWORD = process.env.SEED_PASSWORD ?? 'Kurahia1!'

/** app id -> origin + the sessionStorage key that app's zustand store persists under. */
// All three apps persist into the SAME key, because they share one store.
// The owner app used to keep a second, near-identical store under
// 'kurahia-owner-auth'; that copy is gone (see owner_pwa/src/stores/authStore.ts)
// but the capture harness still wrote the old key — so every owner screenshot
// was silently redirected to /login and saved nothing. Another rule that lived
// in two places with one of them stale.
export const APPS = {
  // Ports are overridable because 5173 is Vite's default and another project
  // on this machine claims it — a capture run once "failed" four screens that
  // were actually a different product's router refusing /clock.
  employee: { base: process.env.EMPLOYEE_BASE ?? 'http://localhost:5173', key: 'kurahia-auth' },
  owner:    { base: 'http://localhost:5174', key: 'kurahia-auth' },
  station:  { base: 'http://localhost:5176', key: 'kurahia-auth' },
} as const
export type AppId = keyof typeof APPS

const tokens = new Map<string, { access_token: string; refresh_token: string }>()

export async function tokenFor(username: string) {
  if (tokens.has(username)) return tokens.get(username)!
  for (let attempt = 0; attempt < 8; attempt++) {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: PASSWORD }),
    })
    const body = await res.json() as any
    if (body.access_token) { tokens.set(username, body); return tokens.get(username)! }
    // /auth/login is 5-per-minute per IP. Several people from one machine trips
    // it — that is the limiter working, not a fault. Wait it out.
    if (res.status !== 429) throw new Error(`login failed for ${username}: ${JSON.stringify(body)}`)
    await new Promise(r => setTimeout(r, 20_000))
  }
  throw new Error(`login for ${username} stayed rate-limited after backoff`)
}

export async function api(method: string, p: string, username: string, body?: unknown) {
  const { access_token } = await tokenFor(username)
  const res = await fetch(`${API}${p}`, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${access_token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  let data: any = null
  try { data = await res.json() } catch { /* some endpoints return no body */ }
  return { status: res.status, data }
}

/** A browser context already signed in as `username`, for whichever app. */
export async function appPage(
  browser: any, app: AppId, username: string,
  viewport = { width: 1440, height: 900 },
): Promise<{ ctx: BrowserContext; page: Page }> {
  const t = await tokenFor(username)
  const claims = JSON.parse(Buffer.from(t.access_token.split('.')[1], 'base64').toString())
  const ctx: BrowserContext = await browser.newContext({ viewport, deviceScaleFactor: 2 })
  // addInitScript runs on every document of this context, so the store is
  // hydrated BEFORE React mounts and AuthGate cannot bounce us to /login.
  await ctx.addInitScript(([k, v]: any) => sessionStorage.setItem(k, v), [APPS[app].key,
    JSON.stringify({
      state: {
        user: {
          id: claims.sub, username,
          role_level: claims.role_level, department: claims.department,
          can_count_stock: claims.can_count_stock,
        },
        accessToken: t.access_token, refreshToken: t.refresh_token,
        isAuthenticated: true, setupToken: null,
      }, version: 0,
    })] as const)
  return { ctx, page: await ctx.newPage() }
}

export type Entry = {
  id: string; app: string; route: string; user: string; role: string
  captured: boolean
  assert_used: string
  heading_seen?: string
  visible_numbers?: string[]
  failure?: string
  notes?: string
  /** How much the screen actually rendered, and whether it rendered NOTHING.
      A plate of an empty state is a true picture of a screen with no data in
      it — fine for a test, useless in a document that has to show a client
      what the thing does. Measured rather than eyeballed, because two earlier
      guesses at "is this plate any good" (file size, then visible currency)
      both lied: the kiosk menu is 96% flat background and reads beautifully. */
  text_chars?: number
  empty_state?: string
}

/**
 * Text that only appears when a screen has CRASHED into its error boundary.
 *
 * A picture of a crash nearly went into the client proposal. The marker for
 * that plate was the word "dispute", which matched the nav item beside the
 * wreckage, so the capture believed it was on the right screen — and it was,
 * technically. The screen was just broken.
 *
 * (That particular crash turned out to be a dev server holding a module from
 * before StatusBadge learned the dispute statuses — our own tooling, not the
 * product. Which is exactly why this has to be caught automatically: a crash
 * is worth knowing about whoever caused it.)
 */
const CRASH_MARKERS = [
  'Something went wrong',
  'The screen hit an unexpected error',
  'Your data is safe',
]

/** Text that only ever appears on a login / PIN screen — the blind-shot tripwire. */
const LOGIN_MARKERS = [
  'Enter your PIN to start your shift',
  'Welcome Back',
  'Enter your username',
  'e.g. wachira',
]

/** Pull real currency / number strings out of the rendered text. Never invent. */
function numbersFrom(text: string): string[] {
  const out = new Set<string>()
  for (const m of text.matchAll(/KSh\s?-?[\d,]+(?:\.\d+)?/g)) out.add(m[0].replace(/\s+/g, ' ').trim())
  for (const m of text.matchAll(/\b\d[\d,]*(?:\.\d+)?\s?(?:%|kg|litre|litres|items?|bands?|guests?|pending|unmatched)\b/gi)) out.add(m[0].trim())
  return [...out].slice(0, 14)
}

/** The words this app uses when a screen has nothing in it. */
const EMPTY_STATES = [
  'nothing yet', 'no requests', 'no pending', 'nothing to show', 'none yet',
  'no items', 'no results', 'no bookings', 'no alerts', 'no incidents',
  'no suggestions', 'no disputes', 'nothing here', 'all clear', 'all healthy',
  'no staff', 'no shifts', 'no entries', 'empty',
]

function headingFrom(text: string): string {
  return text.split('\n').map(s => s.trim()).filter(Boolean).slice(0, 6).join(' | ').slice(0, 200)
}

export function makeCapturer(shotsDir: string, evidence: Entry[]) {
  fs.mkdirSync(shotsDir, { recursive: true })

  return async function capture(opts: {
    page: Page; app: AppId; id: string; route: string; user: string; role: string
    /** any ONE of these strings appearing in rendered text proves the right screen */
    markers: string[]
    notes?: string
    /**
     * How to GET to the screen, when a URL is not enough. The kiosk is the case
     * this exists for: a guest screen is reached by a member of staff handing
     * the tablet over, and kioskMode lives in memory only, so navigating
     * straight to /kiosk/menu correctly bounces back to the clock. Default is a
     * plain goto. Whatever this does, the route and marker assertions below
     * still have to pass, so a flow that goes wrong still saves nothing.
     */
    arrive?: (page: Page, base: string) => Promise<void>
    /** run after the screen is proven, before the shot — e.g. open a drawer */
    then?: (page: Page) => Promise<void>
    /** capture the whole scrollable page instead of just the viewport */
    fullPage?: boolean
  }) {
    const { page, app, id, route, user, role, markers } = opts
    const entry: Entry = {
      id, app: `${app}_pwa`, route, user, role,
      captured: false,
      assert_used: `rendered text contains one of: ${markers.map(m => `"${m}"`).join(' | ')}`,
      notes: opts.notes,
    }

    try {
      if (opts.arrive) {
        await opts.arrive(page, APPS[app].base)
      } else {
        await page.goto(`${APPS[app].base}${route}`, { waitUntil: 'domcontentloaded', timeout: 30_000 })
      }
      await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {})

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
      entry.text_chars = text.replace(/\s+/g, ' ').trim().length
      entry.empty_state = EMPTY_STATES.find(m => text.toLowerCase().includes(m))

      const url = page.url()
      const pathname = new URL(url).pathname
      const loginText = LOGIN_MARKERS.find(m => text.includes(m))

      if (pathname !== route) {
        entry.failure = `redirected: asked for ${route}, ended on ${pathname}. No image saved.`
        evidence.push(entry); return
      }
      if (/\/login|\/pin(\/|$)/.test(pathname) || loginText) {
        entry.failure = `landed on an auth screen (url=${url}) — NOT the requested screen, no image saved`
        evidence.push(entry); return
      }
      if (!hit && text.includes('Access restricted')) {
        entry.failure = `RoleGate blocked this account — "Access restricted" rendered instead of the screen. No image saved.`
        evidence.push(entry); return
      }
      if (!hit) {
        entry.failure = `none of the expected markers rendered within 20s (final url=${url}). No image saved.`
        evidence.push(entry); return
      }
      // Checked AFTER the marker, because a crashed screen still carries its
      // nav — which is where the marker was matching.
      const crash = CRASH_MARKERS.find(m => text.includes(m))
      if (crash) {
        entry.failure = `the screen crashed into its error boundary ("${crash}"). No image saved.`
        evidence.push(entry); return
      }

      // Framer-motion fades every screen in. Shooting during the fade produces
      // the washed-out half-transparent images that made the last set unusable.
      await page.waitForTimeout(900)

      if (opts.then) {
        await opts.then(page)
        await page.waitForTimeout(700)
        // Re-measure: `then` is what puts content on screens that are a bare
        // form until somebody uses them. Band Lookup read 104 characters and
        // "still empty" long after the fix, because the tape measure ran
        // before the hook did.
        const after = await page.locator('body').innerText().catch(() => '')
        entry.text_chars = after.replace(/\s+/g, ' ').trim().length
        entry.visible_numbers = numbersFrom(after)
        entry.empty_state = EMPTY_STATES.find(m => after.toLowerCase().includes(m))
      }

      await page.screenshot({
        path: path.join(shotsDir, `${id}.jpg`),
        type: 'jpeg', quality: 78, fullPage: opts.fullPage ?? false,
      })
      entry.captured = true
      entry.assert_used = `matched "${hit}"`
      evidence.push(entry)
    } catch (err: any) {
      entry.failure = `exception: ${String(err?.message ?? err).slice(0, 300)}`
      evidence.push(entry)
    }
  }
}
