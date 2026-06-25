import { chromium } from 'playwright';
import { AxeBuilder } from '@axe-core/playwright';

const SEED_PASSWORD = process.env.SEED_PASSWORD ?? SEED_PASSWORD;
const jwt = await fetch('http://localhost:5000/auth/login', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'wachira', password: SEED_PASSWORD }),
}).then(r => r.json()).then(d => d.access_token);

const b = await chromium.launch({
  headless: true,
  executablePath: '/home/wachira/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome',
});
const ctx = await b.newContext({ viewport: { width: 768, height: 1024 } });
await ctx.route('http://localhost:5000/auth/login', r =>
  r.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify({ access_token: jwt, refresh_token: jwt }) })
);
const page = await ctx.newPage();
await page.goto('http://localhost:5176/login');
await page.waitForLoadState('domcontentloaded');
await page.waitForTimeout(400);
await page.locator('input[autocomplete="username"]').fill('wachira');
await page.locator('input[type="password"]').first().fill(SEED_PASSWORD);
await page.locator('button[type="submit"]').click();
await page.waitForTimeout(2000);

// Navigate to clock
await page.evaluate(p => window.history.pushState({}, '', p), '/clock');
await page.evaluate(() => window.dispatchEvent(new PopStateEvent('popstate', { state: {} })));
await page.waitForTimeout(1500);

const res = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
const vs = res.violations.filter(v => v.id === 'color-contrast');
console.log('color-contrast violations on ClockScreen:');
for (const v of vs) {
  for (const n of v.nodes.slice(0, 8)) {
    console.log('HTML:', n.html.slice(0, 200));
    const msg = n.any?.[0]?.message || n.all?.[0]?.message || '';
    console.log('MSG:', msg.slice(0, 180));
    console.log('');
  }
}

await b.close();
