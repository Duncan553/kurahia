/**
 * F-19 Stage 1 — cross-browser smoke + visual regression baselines
 * Usage: node scripts/f19-stage1.mjs
 * Requires: employee preview on :4174, owner preview on :4175, backend on :5000
 */
import { chromium, firefox, webkit } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const SEED_PASSWORD = process.env.SEED_PASSWORD ?? SEED_PASSWORD;

const __dir = path.dirname(fileURLToPath(import.meta.url));
const REPO   = path.join(__dir, '..');
const SNAPS  = path.join(REPO, 'tests/visual/__screenshots__');
const EMP    = 'http://localhost:4174';
const OWN    = 'http://localhost:4175';
const API    = 'http://localhost:5000';

const EXE    = '/home/wachira/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome';

// ── Auth helper ────────────────────────────────────────────────────────────────

async function getJWT() {
  const r = await fetch(`${API}/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'wachira', password: SEED_PASSWORD }),
  });
  if (!r.ok) throw new Error(`Auth failed: ${r.status}`);
  return (await r.json()).access_token;
}

async function loginSPA(page, base, creds = { username: 'wachira', password: SEED_PASSWORD }) {
  await page.goto(`${base}/login`);
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(600);
  await page.locator('input[autocomplete="username"], input[type="text"]').first().fill(creds.username);
  const pass = page.locator('input[type="password"]').first();
  if (await pass.count() > 0) await pass.fill(creds.password);
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(2500);
  // Handle PIN setup if prompted
  const url = page.url();
  if (url.includes('/pin/setup') || url.includes('/pin')) {
    // Try clicking pin digits
    for (let r = 0; r < 2; r++) {
      for (const d of ['1','2','3','4']) {
        const b = page.locator(`button[aria-label="${d}"]`);
        if (await b.count() > 0) { await b.first().click(); await page.waitForTimeout(80); }
      }
      await page.waitForTimeout(400);
    }
  }
  await page.waitForTimeout(1000);
}

async function spaNav(page, path) {
  await page.evaluate(p => window.history.pushState({}, '', p), path);
  await page.evaluate(() => window.dispatchEvent(new PopStateEvent('popstate', { state: {} })));
  await page.waitForTimeout(1200);
}

// ── Snapshot helper ────────────────────────────────────────────────────────────

function snapDir(viewport) {
  const key = viewport.width >= 1000 ? 'desktop' : 'mobile';
  const dir = path.join(SNAPS, key);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

async function snap(page, name, viewport) {
  const dir = snapDir(viewport);
  const file = path.join(dir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  return file;
}

// ── Cross-browser smoke test ──────────────────────────────────────────────────

async function smokeBrowser(browserType, browserName, jwt, results) {
  const launchOpts = browserName === 'chromium'
    ? { headless: true, executablePath: EXE }
    : { headless: true };

  let browser;
  try {
    browser = await browserType.launch(launchOpts);
  } catch (e) {
    const isNotInstalled = e.message.includes('Executable') || e.message.includes('not found');
    const status = isNotInstalled ? 'skip' : 'fail';
    for (const t of ['login+PIN flow', 'clock-in renders', 'service worker active', 'owner dashboard renders']) {
      results.push({ browser: browserName, test: t, pass: false, status, note: isNotInstalled ? 'browser not installed' : e.message });
    }
    return;
  }

  const ctx = await browser.newContext({ viewport: { width: 768, height: 1024 } });
  await ctx.route(`${API}/auth/login`, route =>
    route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ access_token: jwt, refresh_token: jwt }) })
  );
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text().slice(0,120)); });

  const check = async (name, fn) => {
    try {
      await fn();
      results.push({ browser: browserName, test: name, pass: true, errors: [] });
    } catch (e) {
      results.push({ browser: browserName, test: name, pass: false, note: e.message.slice(0,120), errors });
    }
  };

  // 1. Login flow
  await check('login+PIN flow', async () => {
    await page.goto(`${EMP}/login`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(600);
    await page.locator('input[autocomplete="username"]').first().fill('wachira');
    await page.locator('input[type="password"]').first().fill(SEED_PASSWORD);
    // button is disabled until both fields are filled
    await page.locator('button[type="submit"]:not([disabled])').click();
    await page.waitForTimeout(2500);
    // After login, should be on /clock or /pin - not /login
    const url = page.url();
    if (url.includes('/login')) throw new Error(`Still on login: ${url}`);
  });

  // 2. Clock-in (employee)
  await check('clock-in renders', async () => {
    await spaNav(page, '/clock');
    const clkBtn = page.locator('button').filter({ hasText: /clock in|clocked in|on duty|tap to/i }).first();
    if (await clkBtn.count() === 0) {
      // Check that SOMETHING renders — not an error
      const body = await page.locator('body').textContent();
      if (!body || body.trim().length < 10) throw new Error('Clock screen empty');
    }
  });

  // 3. Service worker registered
  await check('service worker active', async () => {
    const swActive = await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return false;
      const reg = await navigator.serviceWorker.getRegistration();
      return !!(reg?.active || reg?.installing || reg?.waiting);
    });
    if (!swActive) throw new Error('SW not registered');
  });

  await browser.close();

  // Owner dashboard
  let ownerBrowser;
  try {
    ownerBrowser = await browserType.launch(launchOpts);
  } catch { return; }
  const octx = await ownerBrowser.newContext({ viewport: { width: 1280, height: 800 } });
  await octx.route(`${API}/auth/login`, route =>
    route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ access_token: jwt, refresh_token: jwt }) })
  );
  const opage = await octx.newPage();
  const oerrors = [];
  opage.on('console', msg => { if (msg.type() === 'error') oerrors.push(msg.text().slice(0,120)); });

  await check('owner dashboard renders', async () => {
    await opage.goto(`${OWN}/login`);
    await opage.waitForLoadState('domcontentloaded');
    await opage.waitForTimeout(600);
    await opage.locator('input[autocomplete="username"]').first().fill('wachira');
    await opage.locator('input[type="password"]').first().fill(SEED_PASSWORD);
    await opage.locator('button[type="submit"]:not([disabled])').click();
    await opage.waitForTimeout(2500);
    await spaNav(opage, '/dashboard');
    const body = await opage.locator('body').textContent();
    if (!body || body.length < 20) throw new Error('Dashboard empty');
  });

  await ownerBrowser.close();
}

// ── Visual regression screenshots ─────────────────────────────────────────────

async function captureScreenshots(jwt) {
  const viewports = [
    { width: 1280, height: 800, name: 'desktop' },
    { width: 393,  height: 851, name: 'mobile'  },
  ];

  const empScreens = [
    ['LoginScreen',          '/login',         false],
    ['ClockScreen',          '/clock',         true ],
    ['WaiterTabsScreen',     '/pos/tabs',      true ],
    ['KitchenQueueScreen',   '/pos/kitchen',   true ],
    ['GateHubScreen',        '/gate/hub',      true ],
    ['ServicePayScreen',     '/pos/spa',       true ],
    ['ManagerScreen',        '/manager',       true ],
    ['NotificationsScreen',  '/notifications', true ],
    ['KioskMenuScreen',      '/kiosk/menu',    false],
    ['KioskFeedbackScreen',  '/kiosk/feedback',false],
  ];

  const ownScreens = [
    ['LoginScreen',          '/login',     false],
    ['DashboardScreen',      '/dashboard', true ],
    ['AlertsScreen',         '/alerts',    true ],
    ['PayrollDraftScreen',   '/payroll',   true ],
    ['ReconciliationScreen', '/finance',   true ],
  ];

  const captured = [];

  for (const vp of viewports) {
    const browser = await chromium.launch({ headless: true, executablePath: EXE });

    // Employee
    const ectx = await browser.newContext({ viewport: vp });
    await ectx.route(`${API}/auth/login`, r =>
      r.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ access_token: jwt, refresh_token: jwt }) })
    );
    const epage = await ectx.newPage();

    // Login employee
    await epage.goto(`${EMP}/login`);
    await epage.waitForLoadState('domcontentloaded');
    await epage.waitForTimeout(500);

    for (const [name, route, needsAuth] of empScreens) {
      try {
        if (!needsAuth) {
          await epage.goto(`${EMP}${route}`);
          await epage.waitForLoadState('domcontentloaded');
          await epage.waitForTimeout(800);
        } else {
          await spaNav(epage, route);
        }
        const file = await snap(epage, `emp-${name}`, vp);
        captured.push({ name: `emp-${name} (${vp.name})`, file, ok: true });
      } catch (e) {
        captured.push({ name: `emp-${name} (${vp.name})`, ok: false, note: e.message.slice(0,80) });
      }
    }

    // Owner
    const octx = await browser.newContext({ viewport: vp });
    await octx.route(`${API}/auth/login`, r =>
      r.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ access_token: jwt, refresh_token: jwt }) })
    );
    const opage = await octx.newPage();
    await opage.goto(`${OWN}/login`);
    await opage.waitForLoadState('domcontentloaded');
    await opage.waitForTimeout(500);

    for (const [name, route, needsAuth] of ownScreens) {
      try {
        if (!needsAuth) {
          await opage.goto(`${OWN}${route}`);
          await opage.waitForLoadState('domcontentloaded');
          await opage.waitForTimeout(800);
        } else {
          await spaNav(opage, route);
        }
        const file = await snap(opage, `own-${name}`, vp);
        captured.push({ name: `own-${name} (${vp.name})`, file, ok: true });
      } catch (e) {
        captured.push({ name: `own-${name} (${vp.name})`, ok: false, note: e.message.slice(0,80) });
      }
    }

    await browser.close();
  }
  return captured;
}

// ── Main ───────────────────────────────────────────────────────────────────────

async function main() {
  console.log('\n╔══════════════════════════════════════╗');
  console.log('║  F-19 Stage 1 — Measurement Pass     ║');
  console.log('╚══════════════════════════════════════╝\n');

  // Get JWT
  console.log('→ Authenticating with backend...');
  let jwt;
  try {
    jwt = await getJWT();
    console.log('  ✓ JWT obtained\n');
  } catch (e) {
    console.log('  ✗ Backend auth failed:', e.message);
    console.log('  (smoke tests will use network mock only)\n');
    jwt = 'mock';
  }

  // ── Cross-browser smoke ──────────────────────────────────────────────────
  console.log('━━━ CROSS-BROWSER SMOKE TESTS ━━━\n');
  const smokeResults = [];

  for (const [btype, bname] of [[chromium, 'chromium'], [firefox, 'firefox'], [webkit, 'webkit']]) {
    console.log(`  Testing ${bname}...`);
    try {
      await smokeBrowser(btype, bname, jwt, smokeResults);
    } catch (e) {
      smokeResults.push({ browser: bname, test: 'browser launch', pass: false, note: e.message });
    }
  }

  // Print smoke results
  const browsers = ['chromium', 'firefox', 'webkit'];
  const tests = [...new Set(smokeResults.map(r => r.test))];
  console.log('\n  Browser          | login+PIN | clock-in | SW active | dashboard');
  console.log('  ─────────────────┼───────────┼──────────┼───────────┼──────────');
  for (const b of browsers) {
    const row = tests.map(t => {
      const r = smokeResults.find(r => r.browser === b && r.test === t);
      if (!r) return '    n/a    ';
      if (r.pass) return '   PASS    ';
      if (r.status === 'skip') return '   SKIP    ';
      return '   FAIL    ';
    });
    console.log(`  ${b.padEnd(16)} | ${row.join(' | ')}`);
  }

  // Print failures
  const fails = smokeResults.filter(r => !r.pass);
  if (fails.length) {
    console.log('\n  Failures:');
    fails.forEach(f => console.log(`    ✗ ${f.browser} / ${f.test}: ${f.note || ''}`));
    if (fails.some(f => f.errors?.length)) {
      console.log('\n  Console errors:');
      fails.filter(f => f.errors?.length).forEach(f =>
        f.errors.forEach(e => console.log(`    [${f.browser}] ${e}`))
      );
    }
  } else {
    console.log('\n  ✅ All smoke tests PASS');
  }

  // ── Visual regression screenshots ────────────────────────────────────────
  console.log('\n\n━━━ VISUAL REGRESSION BASELINES ━━━\n');
  console.log('  Capturing screenshots at 1280×800 (desktop) and 393×851 (mobile)...\n');

  let snapResults = [];
  try {
    snapResults = await captureScreenshots(jwt);
  } catch (e) {
    console.log('  Screenshot capture failed:', e.message);
  }

  const okSnaps  = snapResults.filter(s => s.ok);
  const badSnaps = snapResults.filter(s => !s.ok);
  console.log(`  ✓ Captured: ${okSnaps.length} screenshots`);
  okSnaps.forEach(s => console.log(`    ${s.name}`));
  if (badSnaps.length) {
    console.log(`\n  ✗ Failed: ${badSnaps.length}`);
    badSnaps.forEach(s => console.log(`    ${s.name}: ${s.note}`));
  }
  console.log(`\n  Saved to: tests/visual/__screenshots__/`);

  // ── Summary ───────────────────────────────────────────────────────────────
  const smokePassed = smokeResults.filter(r => r.pass).length;
  const smokeTotal  = smokeResults.length;
  console.log('\n\n━━━ STAGE 1 SUMMARY ━━━\n');
  console.log(`  Smoke tests:   ${smokePassed}/${smokeTotal} passed`);
  console.log(`  Screenshots:   ${okSnaps.length}/${snapResults.length} captured`);
  console.log(`  Saved to:      tests/visual/__screenshots__/\n`);
}

main().catch(e => { console.error(e); process.exit(1); });
