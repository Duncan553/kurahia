/**
 * F-18 Part A verify — axe recheck after accessibility fixes.
 * Runs against all 15 audited screens (employee + owner PWAs).
 */
import { chromium } from 'playwright';
import { AxeBuilder } from '@axe-core/playwright';

const EMP_BASE      = 'http://localhost:5176';
const OWN_BASE      = 'http://localhost:5175';
const APIURL        = 'http://localhost:5000';
const SEED_PASSWORD = process.env.SEED_PASSWORD ?? SEED_PASSWORD;

async function getJWT() {
  const r = await fetch(`${APIURL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'wachira', password: SEED_PASSWORD }),
  });
  return (await r.json()).access_token;
}

async function axeCheck(page, name) {
  await page.waitForTimeout(1200);
  const res = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  return {
    name,
    critical: res.violations.filter(v => v.impact === 'critical'),
    serious:  res.violations.filter(v => v.impact === 'serious'),
    url: page.url(),
  };
}

async function spaNav(page, path) {
  await page.evaluate(p => window.history.pushState({}, '', p), path);
  await page.evaluate(() => window.dispatchEvent(new PopStateEvent('popstate', { state: {} })));
  await page.waitForTimeout(1000);
}

async function auditPWA(label, base, screens, jwt, loginCreds) {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/home/wachira/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome',
  });
  const ctx = await browser.newContext({ viewport: { width: 768, height: 1024 } });
  await ctx.route(`${APIURL}/auth/login`, route =>
    route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ access_token: jwt, refresh_token: jwt }) })
  );

  const page = await ctx.newPage();
  const results = [];
  try {
    // Public screens
    for (const [name, path] of screens.filter(s => !s[2])) {
      await page.goto(`${base}${path}`);
      await page.waitForLoadState('domcontentloaded');
      results.push(await axeCheck(page, name));
    }
    // Login
    await page.goto(`${base}/login`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(400);
    const ui = page.locator('input[autocomplete="username"], input[type="text"]').first();
    await ui.fill(loginCreds.username);
    const pi = page.locator('input[type="password"]').first();
    if (await pi.count() > 0) await pi.fill(loginCreds.password);
    const sb = page.locator('button[type="submit"]');
    if (await sb.count() > 0) await sb.click();
    await page.waitForTimeout(2000);
    const postUrl = page.url();
    if (postUrl.includes('/pin/setup')) {
      for (let r = 0; r < 2; r++) {
        for (const d of ['1','2','3','4']) {
          const b = page.locator(`button[aria-label="${d}"]`);
          if (await b.count() > 0) await b.first().click();
          await page.waitForTimeout(100);
        }
        await page.waitForTimeout(500);
      }
    }
    // Auth screens via SPA nav
    for (const [name, path, needsAuth] of screens.filter(s => s[2])) {
      await spaNav(page, path);
      results.push(await axeCheck(page, name));
    }
  } finally {
    await browser.close();
  }
  return results;
}

async function main() {
  const jwt = await getJWT();

  const empScreens = [
    ['LoginScreen',        '/login',         false],
    ['PinEntryScreen',     '/pin',           false],
    ['ClockScreen',        '/clock',         true],
    ['WaiterTabsScreen',   '/pos/tabs',      true],
    ['KitchenQueueScreen', '/pos/kitchen',   true],
    ['BarQueueScreen',     '/pos/bar',       true],
    ['GateHubScreen',      '/gate/hub',      true],
    ['ServicePayScreen',   '/pos/spa',       true],
    ['ManagerScreen',      '/manager',       true],
    ['StaffAccountsScreen','/manager/staff', true],
  ];
  const ownScreens = [
    ['LoginScreen',          '/login',      false],
    ['PinEntryScreen',       '/pin',        false],
    ['DashboardScreen',      '/dashboard',  true],
    ['AlertsScreen',         '/alerts',     true],
    ['ReconciliationScreen', '/finance',    true],
  ];

  const empRes = await auditPWA('Employee', EMP_BASE, empScreens, jwt, { username: 'wachira', password: SEED_PASSWORD });
  const ownRes = await auditPWA('Owner',    OWN_BASE, ownScreens, jwt, { username: 'wachira', password: SEED_PASSWORD });

  console.log('\n╔══════════════════════════════════════════╗');
  console.log('║  POST-FIX axe RECHECK (Part A verify)   ║');
  console.log('╚══════════════════════════════════════════╝\n');

  let totalCrit = 0, totalSer = 0;
  for (const [pwa, results] of [['EMPLOYEE', empRes], ['OWNER', ownRes]]) {
    console.log(`── ${pwa} PWA ──`);
    for (const r of results) {
      const c = r.critical.length, s = r.serious.length;
      totalCrit += c; totalSer += s;
      const tag = c ? '🔴 CRITICAL' : s ? '🟠 SERIOUS' : '✅ CLEAN';
      console.log(`${tag}  ${r.name}`);
      if (c) console.log(`  critical: ${r.critical.map(v=>v.id).join(', ')}`);
      if (s) console.log(`  serious:  ${r.serious.map(v=>v.id).join(', ')}`);
    }
    console.log('');
  }
  console.log(`TOTAL: ${totalCrit} critical, ${totalSer} serious across ${empRes.length + ownRes.length} screens`);
  if (totalCrit === 0 && totalSer === 0) {
    console.log('\n✅ GATE PASSED — zero critical + serious violations');
  } else {
    console.log('\n❌ GATE FAILED — violations remain');
    process.exit(1);
  }
}
main().catch(e => { console.error(e); process.exit(1); });
