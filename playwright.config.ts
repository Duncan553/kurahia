import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/playwright',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: 0,
  use: {
    headless: true,
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    screenshot: 'off', // we take manual screenshots
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
})
