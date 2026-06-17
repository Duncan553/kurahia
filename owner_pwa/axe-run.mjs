import { chromium } from 'playwright';
import { AxeBuilder } from '@axe-core/playwright';

const OWN_BASE = 'http://localhost:5177';
const APIURL   = 'http://localhost:5000';

async function getJWT() {
  const r = await fetch(`${APIURL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'wachira', password: 'Kurahia1!' }),
  });
  return (await r.json()).access_token;
}

async function axeCheck(page, name) {
  await page.waitForTimeout(1500);
  const res = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  return {
    name,
    critical: res.violations.filter(v => v.impact === 'critical'),
    serious:  res.violations.filter(v => v.impact === 'serious'),
  };
}

async function spaNav(page, path) {
  await page.evaluate(p => window.history.pushState({}, '', p), path);
  await page.evaluate(() => window.dispatchEvent(new PopStateEvent('popstate', { state: {} })));
  await page.waitForTimeout(1500);
}

async function main() {
  const jwt = await getJWT();
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
    // Login + get into authenticated state
    await page.goto(`${OWN_BASE}/login`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(600);
    const ui = page.locator('input[autocomplete="username"], input[type="text"]').first();
    await ui.fill('wachira');
    const pi = page.locator('input[type="password"]').first();
    if (await pi.count() > 0) await pi.fill('Kurahia1!');
    const sb = page.locator('button[type="submit"]:not([disabled]), button[type="submit"]');
    if (await sb.count() > 0) await sb.first().click();
    await page.waitForTimeout(3000);

    // Audit each owner screen
    const screens = [
      'DashboardScreen',          '/dashboard',
      'AlertsScreen',             '/alerts',
      'FinanceScreen',            '/finance',
      'PurchaseApprovalsScreen',  '/purchase-approvals',
      'ReconciliationScreen',     '/reconciliation',
      'StaffScreen',              '/staff',
      'BookingsScreen',           '/bookings',
      'SettingsScreen',           '/settings',
    ];
    for (let i = 0; i < screens.length; i += 2) {
      const [name, path] = [screens[i], screens[i+1]];
      await spaNav(page, path);
      results.push(await axeCheck(page, name));
    }
  } finally {
    await browser.close();
  }

  let totalCrit = 0, totalSer = 0;
  console.log('\n── OWNER PWA axe sweep (F-O-7) ──');
  for (const r of results) {
    const c = r.critical.length, s = r.serious.length;
    totalCrit += c; totalSer += s;
    const tag = c ? '🔴 CRITICAL' : s ? '🟠 SERIOUS' : '✅';
    console.log(`${tag}  ${r.name}`);
    if (c) console.log(`    critical: ${r.critical.map(v => v.id).join(', ')}`);
    if (s) console.log(`    serious:  ${r.serious.map(v => v.id).join(', ')}`);
  }
  console.log(`\nTOTAL: ${totalCrit} critical, ${totalSer} serious across ${results.length} screens`);
  if (totalCrit === 0 && totalSer === 0) {
    console.log('✅ GATE PASSED — zero critical + serious');
  } else {
    console.log('❌ GATE FAILED');
    process.exit(1);
  }
}
main().catch(e => { console.error(e); process.exit(1); });
