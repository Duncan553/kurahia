import { chromium } from 'playwright';
import { AxeBuilder } from '@axe-core/playwright';

const EMP_BASE = 'http://localhost:5173';
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

  // Intercept login to inject real JWT so Zustand auth store picks it up
  await ctx.route(`${APIURL}/auth/login`, route =>
    route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ access_token: jwt, refresh_token: jwt }) })
  );

  const page = await ctx.newPage();
  const results = [];
  try {
    // Login via the UI so Zustand state is populated
    await page.goto(`${EMP_BASE}/login`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(600);
    const ui = page.locator('input[type="text"]').first();
    await ui.fill('wachira');
    const pi = page.locator('input[type="password"]').first();
    if (await pi.count() > 0) await pi.fill('Kurahia1!');
    const sb = page.locator('button[type="submit"]').first();
    if (await sb.count() > 0) await sb.first().click();
    await page.waitForTimeout(3000);

    // Stage 4 surfaces to audit:

    // 4.2 — ManagerScreen (Stock Alerts tile)
    await spaNav(page, '/manager');
    results.push(await axeCheck(page, 'ManagerScreen (Stock Alerts tile)'));

    // 4.1 — MenuManageScreen (closed state — recipe buttons visible)
    await spaNav(page, '/manager/menu');
    results.push(await axeCheck(page, 'MenuManageScreen (list view)'));

    // 4.1 — MenuManageScreen recipe drawer open: click first Recipe button if present
    const recipeBtn = page.locator('button:has-text("Recipe")').first();
    if (await recipeBtn.count() > 0) {
      await recipeBtn.click();
      await page.waitForTimeout(1500);
      results.push(await axeCheck(page, 'MenuManageScreen (recipe drawer open)'));
      // Close drawer
      const closeBtn = page.locator('[aria-label*="close"], [aria-label*="Close"], button:has-text("Cancel")').first();
      if (await closeBtn.count() > 0) await closeBtn.click();
      await page.waitForTimeout(500);
    } else {
      console.log('⚠ No Recipe button found — skipping drawer audit');
    }

    // 4.4 — WaiterTabDetailScreen (sold-out rendering)
    // Navigate to tabs list, click the first open tab
    await spaNav(page, '/pos/tabs');
    await page.waitForTimeout(2000);
    const tabLink = page.locator('a[href*="/pos/tabs/"]').first();
    if (await tabLink.count() > 0) {
      await tabLink.click();
      await page.waitForTimeout(2000);
      results.push(await axeCheck(page, 'WaiterTabDetailScreen (sold-out items)'));
    } else {
      // Try direct navigation to any open tab
      const resp = await fetch(`${APIURL}/tabs`, { headers: { Authorization: `Bearer ${jwt}` }});
      const tabs = await resp.json();
      const openTab = (Array.isArray(tabs) ? tabs : []).find(t => t.status === 'OPEN');
      if (openTab) {
        await spaNav(page, `/pos/tabs/${openTab.id}`);
        results.push(await axeCheck(page, 'WaiterTabDetailScreen (sold-out items)'));
      } else {
        console.log('⚠ No open tabs — skipping WaiterTabDetailScreen');
      }
    }

    // 4.5 — KioskMenuScreen (sold-out rendering)
    await spaNav(page, '/kiosk/menu');
    results.push(await axeCheck(page, 'KioskMenuScreen (sold-out items)'));

  } finally {
    await browser.close();
  }

  let totalCrit = 0, totalSer = 0;
  console.log('\n── EMPLOYEE PWA axe sweep (Stage 4) ──');
  for (const r of results) {
    const c = r.critical.length, s = r.serious.length;
    totalCrit += c; totalSer += s;
    const tag = c ? '🔴 CRITICAL' : s ? '🟠 SERIOUS' : '✅';
    console.log(`${tag}  ${r.name}`);
    if (c) r.critical.forEach(v =>
      console.log(`    critical: ${v.id} — ${v.nodes.length} node${v.nodes.length>1?'s':''}`));
    if (s) r.serious.forEach(v =>
      console.log(`    serious:  ${v.id} — ${v.nodes.length} node${v.nodes.length>1?'s':''}`));
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
