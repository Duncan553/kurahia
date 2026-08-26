/**
 * ui_sweep.spec.ts — exhaustive responsive + usability sweep of all 3 PWAs.
 *
 * This is NOT a functional test suite (that's resort_simulation.spec.ts). It
 * answers one question per screen, at three viewport sizes:
 *
 *   "Can a human actually USE this screen at this size?"
 *
 * Which decomposes into the four failure modes worth catching automatically:
 *
 *   1. HIDDEN CONTROLS   — a button that is off-screen, zero-sized, or covered
 *                          by something else, so it cannot be tapped.
 *   2. TRAPPED CONTENT   — content taller than its container where nothing in
 *                          the ancestor chain can scroll: it is unreachable.
 *   3. SIDEWAYS SCROLL   — the page scrolls horizontally, which on a phone
 *                          means the layout is broken.
 *   4. TINY TAP TARGETS  — controls under ~44px on touch viewports.
 *
 * Plus console errors, which catch the screens that render but are quietly
 * throwing.
 *
 * Run against live dev servers:
 *   backend :5000   employee :5173   owner :5174   station :5176
 */
import { test, expect, Page, BrowserContext } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const API      = 'http://localhost:5000'
const EMPLOYEE = 'http://localhost:5173'
const OWNER    = 'http://localhost:5174'
const STATION  = 'http://localhost:5176'
const PASSWORD = process.env.SEED_PASSWORD ?? 'Kurahia1!'

const OUT = path.resolve(__dirname, 'sweep-results')
fs.mkdirSync(OUT, { recursive: true })

/** The three sizes that matter: a phone, a tablet (the resort's actual station
 *  hardware), and a desktop browser for the owner. */
const VIEWPORTS = [
  { name: 'phone',   width: 390,  height: 844,  touch: true  },
  { name: 'tablet',  width: 820,  height: 1180, touch: true  },
  { name: 'desktop', width: 1440, height: 900,  touch: false },
]

type Finding = {
  app: string; route: string; viewport: string
  kind: string; detail: string
}
const findings: Finding[] = []
function record(f: Finding) { findings.push(f) }

/* ─────────────────────────────────────────────────────────────────────────
 * Auth: log in through the real API, then seed the store the app reads.
 *
 * Why not drive the login form? Because we test the login screens explicitly
 * below, and re-typing credentials for ~85 route visits would triple the
 * runtime without testing anything new. The store shape here must match
 * shared_ui/src/stores/authStore.ts — key 'kurahia-auth', sessionStorage.
 * ──────────────────────────────────────────────────────────────────────── */
async function apiLogin(username: string) {
  const res = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password: PASSWORD }),
  })
  if (!res.ok) throw new Error(`login failed for ${username}: ${res.status}`)
  return res.json() as Promise<{ access_token: string; refresh_token: string }>
}

function decodeJwt(token: string) {
  return JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString())
}

/** owner_pwa keeps its own store under a DIFFERENT key — seeding 'kurahia-auth'
 *  for it silently bounced all 10 owner routes back to /login on the first run. */
const STORE_KEY: Record<string, string> = {
  employee: 'kurahia-auth',
  station:  'kurahia-auth',
  owner:    'kurahia-owner-auth',
}

async function seedAuth(ctx: BrowserContext, app: string, username: string) {
  const { access_token, refresh_token } = await apiLogin(username)
  const claims = decodeJwt(access_token)
  const state = {
    state: {
      user: {
        id: claims.sub,
        username,
        role_level: claims.role_level ?? 0,
        department: claims.department ?? null,
      },
      accessToken: access_token,
      refreshToken: refresh_token,
      isAuthenticated: true,
      setupToken: null,
    },
    version: 0,
  }
  await ctx.addInitScript(
    ([key, value]) => window.sessionStorage.setItem(key as string, value as string),
    [STORE_KEY[app], JSON.stringify(state)] as const
  )
}

/* ─────────────────────────────────────────────────────────────────────────
 * The audit itself. Runs entirely in the page so it can read live layout.
 * ──────────────────────────────────────────────────────────────────────── */
async function auditPage(page: Page, app: string, route: string, vp: typeof VIEWPORTS[0]) {
  const result = await page.evaluate((minTap: number) => {
    const out: { kind: string; detail: string }[] = []
    const vw = window.innerWidth
    const vh = window.innerHeight

    // ── 3. SIDEWAYS SCROLL ────────────────────────────────────────────────
    // A 1px tolerance absorbs sub-pixel rounding on scaled viewports.
    const de = document.documentElement
    if (de.scrollWidth > de.clientWidth + 1) {
      // Name the widest offender — "the page overflows" alone isn't actionable.
      let worst = { tag: '', width: 0, cls: '' }
      for (const el of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
        const r = el.getBoundingClientRect()
        if (r.width > 0 && r.right > vw + 1 && r.right - vw > worst.width) {
          worst = {
            tag: el.tagName.toLowerCase(),
            width: Math.round(r.right - vw),
            cls: (el.className || '').toString().slice(0, 80),
          }
        }
      }
      out.push({
        kind: 'SIDEWAYS_SCROLL',
        detail: `page scrolls horizontally (${de.scrollWidth}px content in ${de.clientWidth}px viewport)` +
                (worst.tag ? ` — widest overhang: <${worst.tag} class="${worst.cls}"> +${worst.width}px` : ''),
      })
    }

    // ── 1. HIDDEN CONTROLS ────────────────────────────────────────────────
    const controls = Array.from(document.querySelectorAll<HTMLElement>(
      'button, a[href], input, select, textarea, [role="button"], [tabindex]:not([tabindex="-1"])'
    ))
    for (const el of controls) {
      // checkVisibility() walks the ANCESTOR chain. Reading getComputedStyle on
      // the element alone is wrong and was this sweep's biggest false-positive
      // source: a responsive sidebar is `hidden md:flex`, so on a phone the
      // <aside> is display:none while each <a> inside still computes display:flex
      // and a 0x0 box. Those links are correctly hidden, not broken.
      if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue
      if (el.hasAttribute('disabled') || el.getAttribute('aria-hidden') === 'true') continue
      if (el.closest('[inert], [aria-hidden="true"]')) continue

      const r = el.getBoundingClientRect()
      const label = (el.textContent || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.tagName)
        .trim().replace(/\s+/g, ' ').slice(0, 45)

      // Zero-sized but not display:none — laid out, yet un-clickable.
      if (r.width === 0 || r.height === 0) {
        out.push({ kind: 'HIDDEN_CONTROL', detail: `"${label}" has zero size (${Math.round(r.width)}x${Math.round(r.height)})` })
        continue
      }

      // Horizontally off-screen — but only a real problem if NOTHING can scroll
      // it into view. The owner's mobile nav is deliberately `overflow-x-auto`
      // with fixed-width items; its later tabs start off-screen and the user
      // swipes to them. Flagging those as hidden was a false positive.
      if (r.right < 0 || r.left > vw) {
        let scrollableX = false
        let a: HTMLElement | null = el.parentElement
        while (a && a !== document.body) {
          const ox = getComputedStyle(a).overflowX
          if ((ox === 'auto' || ox === 'scroll') && a.scrollWidth > a.clientWidth) { scrollableX = true; break }
          a = a.parentElement
        }
        if (!scrollableX) {
          out.push({ kind: 'HIDDEN_CONTROL', detail: `"${label}" is off-screen horizontally (x ${Math.round(r.left)}..${Math.round(r.right)}, viewport 0..${vw}) with no scrollable ancestor` })
        }
        continue
      }

      // Covered by another element: hit-test the centre. Ignore when the hit
      // element is inside or contains ours (own children legitimately cover it).
      // Only meaningful when the centre is ACTUALLY on screen. Clamping it into
      // the viewport (the first version of this check) probed a point that was
      // not on the element at all, so anything below the fold reported itself as
      // "covered by the bottom nav" — 45 false positives in one run.
      const cx = r.left + r.width / 2
      const cy = r.top + r.height / 2
      if (cx >= 0 && cx <= vw && cy >= 0 && cy <= vh) {
        const hit = document.elementFromPoint(cx, cy)
        if (hit && hit !== el && !el.contains(hit) && !hit.contains(el)) {
          const blocker = (hit as HTMLElement)
          out.push({
            kind: 'COVERED_CONTROL',
            detail: `"${label}" is covered by <${blocker.tagName.toLowerCase()} class="${(blocker.className||'').toString().slice(0,60)}">`,
          })
          continue
        }
      }

      // ── 4. TINY TAP TARGETS (touch viewports only) ──────────────────────
      if (minTap > 0 && (r.width < minTap || r.height < minTap)) {
        out.push({
          kind: 'TINY_TAP_TARGET',
          detail: `"${label}" is ${Math.round(r.width)}x${Math.round(r.height)}px (min ${minTap})`,
        })
      }
    }

    // ── 2. TRAPPED CONTENT ────────────────────────────────────────────────
    // Content taller than its box, where neither it nor any ancestor scrolls.
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
      if (el.scrollHeight <= el.clientHeight + 4) continue
      if (el.clientHeight === 0) continue
      if (!el.checkVisibility({ checkVisibilityCSS: true })) continue  // same ancestor rule as above
      let node: HTMLElement | null = el
      let scrollable = false
      while (node && node !== document.body) {
        const oy = getComputedStyle(node).overflowY
        if (oy === 'auto' || oy === 'scroll') { scrollable = true; break }
        node = node.parentElement
      }
      const bodyScrolls = de.scrollHeight > de.clientHeight
      if (!scrollable && !bodyScrolls) {
        out.push({
          kind: 'TRAPPED_CONTENT',
          detail: `<${el.tagName.toLowerCase()} class="${(el.className||'').toString().slice(0,60)}"> ` +
                  `has ${el.scrollHeight}px of content in ${el.clientHeight}px and nothing can scroll`,
        })
        break  // one per page is enough to flag it
      }
    }

    return out
  }, vp.touch ? 44 : 0)

  for (const r of result) record({ app, route, viewport: vp.name, ...r })
  return result.length
}

/* ─────────────────────────────────────────────────────────────────────────
 * Route inventories, taken from each app's main.tsx router.
 * Params are filled with real ids at runtime where the route needs one.
 * ──────────────────────────────────────────────────────────────────────── */
const EMPLOYEE_ROUTES = [
  '/', '/clock', '/notifications', '/profile', '/conduct', '/suggestions/new',
  '/leave', '/absence', '/calendar', '/schedule', '/performance', '/disputes',
  '/incidents', '/housekeeping', '/villa', '/events', '/chef',
  '/equipment/maintenance', '/equipment/safety-check',
  '/front-desk/checkin', '/gate/hub', '/gate/issue', '/gate/waiver', '/gate/band-lookup',
  '/inventory/count', '/inventory/purchase-request', '/inventory/quick-entry',
  '/pos/tabs', '/pos/kitchen', '/pos/bar', '/pos/spa', '/pos/water-pay',
  '/manager', '/manager/attendance', '/manager/cash', '/manager/front-desk',
  '/manager/leave', '/manager/menu', '/manager/purchases', '/manager/roster',
  '/manager/shifts', '/manager/staff',
]
const OWNER_ROUTES = [
  '/dashboard', '/alerts', '/bookings', '/feedback', '/finance', '/payroll',
  '/purchase-approvals', '/reconciliation', '/settings', '/staff',
]
const STATION_ROUTES = [
  '/', '/pos/tabs', '/pos/kitchen', '/pos/bar', '/pos/spa', '/pos/water-pay',
  '/gate/hub', '/gate/waiver', '/gate/band-lookup', '/front-desk/checkin',
  '/housekeeping', '/villa', '/incidents', '/equipment/safety-check',
]

/** Public screens — no auth, checked separately since they must work logged-out. */
const PUBLIC = [
  { app: 'employee', base: EMPLOYEE, route: '/login' },
  { app: 'employee', base: EMPLOYEE, route: '/register' },
  { app: 'employee', base: EMPLOYEE, route: '/pin' },
  { app: 'owner',    base: OWNER,    route: '/login' },
  { app: 'station',  base: STATION,  route: '/login' },
]

/* ─────────────────────────────────────────────────────────────────────────
 * The sweep
 * ──────────────────────────────────────────────────────────────────────── */
const APPS = [
  { app: 'employee', base: EMPLOYEE, user: 'amara.wanjiku', routes: EMPLOYEE_ROUTES },
  { app: 'owner',    base: OWNER,    user: 'amara.wanjiku', routes: OWNER_ROUTES },
  { app: 'station',  base: STATION,  user: 'amara.wanjiku', routes: STATION_ROUTES },
]

for (const vp of VIEWPORTS) {
  test.describe(`${vp.name} (${vp.width}x${vp.height})`, () => {
    test.describe.configure({ mode: 'serial' })

    test(`public screens @ ${vp.name}`, async ({ browser }) => {
      const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, hasTouch: vp.touch })
      const page = await ctx.newPage()
      const errors: string[] = []
      page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
      page.on('pageerror', e => errors.push(String(e)))

      for (const { app, base, route } of PUBLIC) {
        errors.length = 0
        await page.goto(base + route, { waitUntil: 'networkidle' }).catch(() => {})
        await page.waitForTimeout(400)   // let entry animations settle
        await auditPage(page, app, route, vp)
        for (const e of errors.slice(0, 3)) {
          record({ app, route, viewport: vp.name, kind: 'CONSOLE_ERROR', detail: e.slice(0, 200) })
        }
      }
      await ctx.close()
    })

    for (const { app, base, user, routes } of APPS) {
      test(`${app} @ ${vp.name}`, async ({ browser }) => {
        test.setTimeout(300_000)
        const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, hasTouch: vp.touch })
        await seedAuth(ctx, app, user)
        const page = await ctx.newPage()
        const errors: string[] = []
        page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
        page.on('pageerror', e => errors.push(String(e)))

        for (const route of routes) {
          errors.length = 0
          await page.goto(base + route, { waitUntil: 'networkidle' }).catch(() => {})
          await page.waitForTimeout(500)

          // A screen that bounced back to /login means the seeded session was
          // rejected — record it rather than silently auditing the login page.
          if (page.url().includes('/login') && route !== '/login') {
            record({ app, route, viewport: vp.name, kind: 'AUTH_BOUNCE', detail: `redirected to ${page.url()}` })
            continue
          }
          await auditPage(page, app, route, vp)
          for (const e of errors.slice(0, 3)) {
            record({ app, route, viewport: vp.name, kind: 'CONSOLE_ERROR', detail: e.slice(0, 200) })
          }
        }
        await ctx.close()
      })
    }
  })
}

test.afterAll(async () => {
  fs.writeFileSync(path.join(OUT, 'findings.json'), JSON.stringify(findings, null, 2))

  // Group by kind, then by app+route, so the report reads as a to-do list.
  const byKind = new Map<string, Finding[]>()
  for (const f of findings) {
    if (!byKind.has(f.kind)) byKind.set(f.kind, [])
    byKind.get(f.kind)!.push(f)
  }
  const lines: string[] = ['# UI Sweep Findings', '']
  lines.push(`Total: ${findings.length} findings across ${new Set(findings.map(f => f.app + f.route)).size} screens`, '')
  for (const [kind, fs_] of [...byKind.entries()].sort((a, b) => b[1].length - a[1].length)) {
    lines.push(`## ${kind} (${fs_.length})`, '')
    const seen = new Set<string>()
    for (const f of fs_) {
      const key = `${f.app}${f.route}${f.detail}`
      if (seen.has(key)) continue
      seen.add(key)
      lines.push(`- **${f.app}${f.route}** [${f.viewport}] — ${f.detail}`)
    }
    lines.push('')
  }
  fs.writeFileSync(path.join(OUT, 'FINDINGS.md'), lines.join('\n'))
  console.log(`\n=== ${findings.length} findings written to ${OUT}/FINDINGS.md ===`)
  for (const [kind, fs_] of byKind) console.log(`  ${kind}: ${fs_.length}`)
})
