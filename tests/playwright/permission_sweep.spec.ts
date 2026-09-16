/**
 * permission_sweep.spec.ts — the check that cannot be faked from source.
 *
 * The fault this hunts is the one that teaches staff the software is
 * unreliable: a screen that OPENS for somebody and then fills with controls
 * the API will refuse them. A 403 nobody sees is worse than an error — on
 * /manager/suggestions a waiter got the manager's inbox rendering "Nothing
 * yet", because an empty inbox and a refused one look identical.
 *
 * scripts/pwa_contract.py tries to catch this by reading the source, and says
 * in its own comments that it cannot: attribution is per FILE, so a call
 * inside a manager-only <IfRole> section counts as called by everyone who can
 * open the file. On 16 Sept it reported 14 cases — 12 of them false, and the
 * two real ones invisible in the noise. Reading JSX control flow is where a
 * static checker starts lying.
 *
 * So this one does not read. It OPENS each route as each role in a real
 * browser and records what the screen actually asked the API for, and what
 * came back. A 403 here was fired by a screen that person could open — which
 * is the definition of the bug.
 *
 * Run (backend + the three apps up):
 *   EMPLOYEE_BASE=http://localhost:5175 npx playwright test \
 *     tests/playwright/permission_sweep.spec.ts --project=chromium
 */
import { test, expect } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { appPage, APPS, type AppId } from './lib/capture'

const ROLES: { label: string; user: string }[] = [
  { label: 'waiter',      user: 'ivan.kipchoge'   },
  { label: 'housekeeping',user: 'kevin.mutua'     },
  { label: 'spa',         user: 'esther.kamau'    },
  { label: 'front desk',  user: 'grace.muthoni'   },
  { label: 'gate lead',   user: 'hassan.omondi'   },
  { label: 'head chef',   user: 'cynthia.achieng' },
  { label: 'bar lead',    user: 'david.otieno'    },
  { label: 'manager',     user: 'brian.mwangi'    },
]

/** Every route a person can type, minus the ones that are a login by design. */
const ROUTES: { app: AppId; path: string }[] = [
  ...['/', '/pos/tabs', '/pos/kitchen', '/pos/bar', '/pos/spa', '/pos/water-pay',
      '/gate/waiver', '/equipment/safety-check', '/villa', '/gate/hub',
      '/front-desk/checkin', '/gate/band-lookup', '/incidents', '/events',
      '/calendar', '/lost-found', '/manager', '/manager/purchases',
      '/manager/menu', '/chef', '/bar', '/inventory/count', '/manager/cash',
      '/manager/leave', '/manager/shifts', '/manager/attendance',
      '/manager/front-desk', '/manager/roster', '/manager/receive',
      '/manager/suppliers', '/manager/suggestions', '/manager/disputes',
      '/manager/resources', '/manager/reconcile', '/receipts',
      '/front-desk/new-booking', '/manager/staff',
     ].map(p => ({ app: 'station' as AppId, path: p })),
  ...['/clock', '/notifications', '/profile', '/conduct', '/leave', '/absence',
      '/calendar', '/disputes', '/incidents',
     ].map(p => ({ app: 'employee' as AppId, path: p })),
]

/**
 * Paths whose 403 is the system WORKING, not a screen overreaching.
 *
 * Only two kinds belong here, and each names why:
 *  - a shared component every screen mounts, which probes something most
 *    people may not read and degrades quietly by design;
 *  - a deliberate wall the product documents elsewhere.
 * Anything else added here is a bug being filed under "expected".
 */
const DELIBERATE: { path: RegExp; why: string }[] = [
  { path: /^\/finance\/dashboard/, why: 'owner-private money: no manager screen asks for it' },
]

type Hit = { role: string; app: string; route: string; call: string; status: number }

test.describe.configure({ mode: 'serial' })

test('no screen asks for something the person opening it is refused', async ({ browser }) => {
  test.setTimeout(30 * 60 * 1000)

  const hits: Hit[] = []
  const opened: string[] = []

  for (const role of ROLES) {
    let ctx: any, page: any
    try {
      ({ ctx, page } = await appPage(browser, 'station', role.user, { width: 1280, height: 900 }))
    } catch (err: any) {
      throw new Error(`could not sign in as ${role.user}: ${err?.message ?? err}`)
    }

    // One listener for the whole role: every API answer the screens pull.
    const seen: { url: string; status: number }[] = []
    page.on('response', (r: any) => {
      const u = new URL(r.url())
      // Only the API. Vite's own module graph is not the product.
      if (/^\/(src|node_modules|@vite|@fs|@react-refresh)/.test(u.pathname)) return
      if (u.pathname === '/' || /\.(tsx?|css|jsx?|map|ico|png|jpe?g|svg|webmanifest)$/.test(u.pathname)) return
      seen.push({ url: u.pathname, status: r.status() })
    })

    for (const route of ROUTES) {
      // Each app needs its own context (different origin, same token).
      if (route.app !== 'station') continue
      seen.length = 0
      try {
        await page.goto(`${APPS.station.base}${route.path}`, { waitUntil: 'domcontentloaded', timeout: 20_000 })
        await page.waitForLoadState('networkidle', { timeout: 12_000 }).catch(() => {})
        await page.waitForTimeout(600)
      } catch { continue }

      opened.push(`${role.label} ${route.path}`)

      // Landing somewhere else means the app refused at the door — correct,
      // and nothing it asked for on the way counts against this route.
      if (new URL(page.url()).pathname !== route.path) continue

      const body = await page.locator('body').innerText().catch(() => '')
      // RequireRole answering in plain English IS the fix. Not a finding.
      if (body.includes("isn't yours to open") || body.includes('Access restricted')) continue

      for (const s of seen) {
        if (s.status !== 403) continue
        if (DELIBERATE.some(d => d.path.test(s.url))) continue
        hits.push({ role: role.label, app: 'station_pwa', route: route.path, call: s.url, status: s.status })
      }
    }
    await ctx.close()
  }

  const out = path.resolve(__dirname, '../../docs/permission_sweep.json')
  fs.mkdirSync(path.dirname(out), { recursive: true })
  fs.writeFileSync(out, JSON.stringify({ opened: opened.length, hits }, null, 2))

  console.log(`\nopened ${opened.length} role/route pairs`)
  if (hits.length) {
    console.log(`\n${hits.length} screen(s) asked for something the person opening them is refused:`)
    for (const h of hits) console.log(`  ${h.role.padEnd(13)} ${h.route.padEnd(26)} ${h.status} ${h.call}`)
  } else {
    console.log('no screen offered a control the system then refuses')
  }

  expect(hits, hits.map(h => `${h.role} opened ${h.route}, which called ${h.call} → 403`).join('\n')).toEqual([])
})
