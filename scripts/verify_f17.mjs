// F-17 runtime verification — run against `vite preview` (built app + real SW).
//   NODE_PATH=/tmp/node_modules node scripts/verify_f17.mjs
// Needs: Flask on :5000 (current code), employee preview on :4173.
//
// Order matters: the auth store is in-memory, so a full reload logs out.
// Everything that needs an authenticated UI happens without reloads;
// the offline app-shell reload test runs LAST.
import { chromium } from 'playwright'

const SEED_PASSWORD = process.env.SEED_PASSWORD ?? SEED_PASSWORD;
const BASE = 'http://localhost:4173'
const results = []
const step = (name, ok, detail = '') => {
  results.push({ name, ok })
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ' — ' + detail : ''}`)
}

const idbCount = () => new Promise((res) => {
  const req = indexedDB.open('kurahia-offline')
  req.onsuccess = () => {
    try {
      const cnt = req.result.transaction('clock-queue', 'readonly').objectStore('clock-queue').count()
      cnt.onsuccess = () => res(cnt.result)
      cnt.onerror = () => res(-1)
    } catch { res(-2) }
  }
  req.onerror = () => res(-1)
})

const browser = await chromium.launch()
const context = await browser.newContext()
const page = await context.newPage()

// ── 1. Manifest ───────────────────────────────────────────────────────────────
await page.goto(BASE + '/login')
const manifest = await page.evaluate(() => fetch('/manifest.webmanifest').then((r) => r.json()))
step('manifest valid', manifest.name === 'Kurahia Staff' && manifest.display === 'standalone'
  && manifest.icons?.length === 4, `name="${manifest.name}" icons=${manifest.icons?.length}`)

// ── 2. SW registers and controls the page (reload BEFORE login is safe) ──────
await page.evaluate(() => navigator.serviceWorker.ready)
await page.reload()
await page.waitForTimeout(500)
const controlled = await page.evaluate(() => !!navigator.serviceWorker.controller)
step('service worker controls page', controlled)

// ── 3. Push-config: dormant mode is clean JSON, and caches prime online ─────
const prime = await page.evaluate(async () => {
  const login = await fetch('/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'teststaff', password: SEED_PASSWORD }),
  }).then((r) => r.json())
  const h = { Authorization: `Bearer ${login.access_token}` }
  const push = await fetch('/notifications/push-config', { headers: h }).then((r) => r.json())
  const menu = await fetch('/menu/items', { headers: h })
  const inbox = await fetch('/notifications/inbox', { headers: h })
  return { push, menu: menu.status, inbox: inbox.status, token: login.access_token }
})
step('push-config dormant clean', prime.push.configured === false && /dormant/i.test(prime.push.message),
  prime.push.message)
step('caches primed online', prime.menu === 200 && prime.inbox === 200,
  `menu=${prime.menu} inbox=${prime.inbox}`)

// ── 4. Login through the real UI → lands on /clock ──────────────────────────
await page.fill('input[type="text"]', 'teststaff')
await page.fill('input[type="password"]', SEED_PASSWORD)
await page.click('button[type="submit"]')
await page.waitForURL(/\/clock/, { timeout: 10_000 })
step('login lands on /clock', page.url().endsWith('/clock'), page.url())
await page.waitForTimeout(1000)

// ── 5. GO OFFLINE (no reload — store stays alive) ────────────────────────────
await context.setOffline(true)
await page.evaluate(() => window.dispatchEvent(new Event('offline')))
await page.waitForTimeout(500)

const bannerOffline = await page.evaluate(() => document.body.innerText)
step('offline banner shows', /Offline — showing saved data/.test(bannerOffline))

// Cached endpoints serve; queues and money do NOT
const offline = await page.evaluate(async (token) => {
  const h = { Authorization: `Bearer ${token}` }
  const get = (u) => fetch(u, { headers: h }).then((r) => r.status).catch(() => 'NETWORK_FAIL')
  return {
    menu: await get('/menu/items'),
    inbox: await get('/notifications/inbox'),
    kitchen: await get('/kitchen/queue'),
    finance: await get('/finance/mpesa/status'),
    auth: await fetch('/auth/login', { method: 'POST' }).then((r) => r.status).catch(() => 'NETWORK_FAIL'),
  }
}, prime.token)
step('offline: menu served from cache', offline.menu === 200, `status=${offline.menu}`)
step('offline: inbox served from cache', offline.inbox === 200, `status=${offline.inbox}`)
step('offline: kitchen queue NOT cached', offline.kitchen === 'NETWORK_FAIL', `got=${offline.kitchen}`)
step('offline: finance NOT cached', offline.finance === 'NETWORK_FAIL', `got=${offline.finance}`)
step('offline: auth NOT cached', offline.auth === 'NETWORK_FAIL', `got=${offline.auth}`)

// ── 6. Offline clock-in queues to IndexedDB (F-7 preserved under the SW) ────
const clockBtn = page.locator('button').filter({ hasText: /^Clock (In|Out)$/ })
await clockBtn.first().click()
await page.waitForTimeout(800)
const queued = await page.evaluate(idbCount)
step('offline clock event queued in IDB', queued >= 1, `queue size=${queued}`)
await page.screenshot({ path: '/tmp/f17_offline.png' })

// ── 7. Reconnect: queue drains, banner flips ─────────────────────────────────
await context.setOffline(false)
await page.evaluate(() => window.dispatchEvent(new Event('online')))
await page.waitForTimeout(2500)
const drained = await page.evaluate(idbCount)
step('reconnect: queue drained', drained === 0, `queue size=${drained}`)
const bannerBack = await page.evaluate(() => document.body.innerText)
step('reconnect: "Back online" banner', /Back online/.test(bannerBack))
await page.screenshot({ path: '/tmp/f17_online.png' })

// ── 8. LAST: offline full reload — app shell from precache ──────────────────
await context.setOffline(true)
await page.goto(BASE + '/clock').catch(() => {})
await page.waitForTimeout(1500)
const shell = await page.evaluate(() => ({
  text: document.body.innerText.length,
  url: location.pathname,
}))
// Reload kills the in-memory store → AuthGate sends /pin. That screen
// rendering AT ALL while offline proves the precache + NavigationRoute work.
step('offline reload: app shell renders from precache', shell.text > 20,
  `chars=${shell.text} landed=${shell.url}`)
await page.screenshot({ path: '/tmp/f17_shell_offline.png' })

await browser.close()
const fails = results.filter((r) => !r.ok).length
console.log(`\n${results.length - fails}/${results.length} passed`)
process.exit(fails ? 1 : 0)
