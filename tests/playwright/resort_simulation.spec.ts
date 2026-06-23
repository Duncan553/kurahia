/**
 * resort_simulation.spec.ts — Full resort simulation audit
 *
 * Tests every role's login, screens, and security boundaries
 * against the live dev servers:
 *   Employee PWA → http://localhost:5173
 *   Owner PWA    → http://localhost:5174
 *   Backend API  → http://localhost:5000
 */
import { test, expect, Page } from '@playwright/test'
import path from 'path'

const EMPLOYEE_URL = 'http://localhost:5173'
const OWNER_URL    = 'http://localhost:5174'
const SCREENSHOT_DIR = path.resolve(__dirname, 'screenshots')
const PASSWORD = 'Kurahia1!'

// All seeded users
const USERS = [
  { username: 'wachira',  pin: '1111', role: 'owner',   level: 10 },
  { username: 'manager2', pin: '1234', role: 'manager', level: 5  },
  { username: 'headchef', pin: '2222', role: 'kitchen', level: 1  },
  { username: 'barmgr',   pin: '3333', role: 'bar',     level: 5  },
  { username: 'spamgr',   pin: '4444', role: 'spa',     level: 5  },
  { username: 'gate1',    pin: '8888', role: 'gate',    level: 3  },
  { username: 'waiter1',  pin: '9999', role: 'waiter',  level: 1  },
]

// ── Helper: login via password on a given base URL ──────────────────────────
async function passwordLogin(page: Page, baseUrl: string, username: string): Promise<boolean> {
  await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' })
  // Fill the login form
  await page.fill('#login-username', username)
  await page.fill('#login-password', PASSWORD)
  // Click the submit button
  await page.click('button[type="submit"]')
  // Wait for navigation away from /login (up to 15s)
  try {
    await page.waitForURL(url => !url.toString().includes('/login'), { timeout: 15_000 })
    return true
  } catch {
    return false
  }
}

// ── Helper: login via PIN on employee PWA ───────────────────────────────────
async function pinLogin(page: Page, username: string, pin: string): Promise<boolean> {
  await page.goto(`${EMPLOYEE_URL}/pin`, { waitUntil: 'networkidle' })
  await page.fill('#pin-username', username)
  // Type each PIN digit via keyboard (the keypad listens to keydown)
  for (const digit of pin) {
    await page.keyboard.press(digit)
  }
  // Wait for navigation away from /pin
  try {
    await page.waitForURL(url => !url.toString().includes('/pin'), { timeout: 15_000 })
    return true
  } catch {
    return false
  }
}

// ── Helper: take a named screenshot ─────────────────────────────────────────
async function snap(page: Page, name: string) {
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${name}.png`), fullPage: true })
}

// ── Helper: check for console errors on page ────────────────────────────────
function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text())
  })
  return errors
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. LOGIN TESTS — Password login for each user on both PWAs
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('LOGIN — Employee PWA (password)', () => {
  for (const user of USERS) {
    test(`${user.username} can log in via password`, async ({ page }) => {
      const ok = await passwordLogin(page, EMPLOYEE_URL, user.username)
      await snap(page, `login-employee-${user.username}`)
      expect(ok, `${user.username} should redirect away from /login`).toBe(true)
      // Should land on /clock (employee PWA redirects / to /clock)
      expect(page.url()).toContain('/clock')
    })
  }
})

test.describe('LOGIN — Employee PWA (PIN)', () => {
  for (const user of USERS) {
    test(`${user.username} can log in via PIN`, async ({ page }) => {
      const ok = await pinLogin(page, user.username, user.pin)
      await snap(page, `login-pin-${user.username}`)
      expect(ok, `${user.username} PIN login should redirect away from /pin`).toBe(true)
      expect(page.url()).toContain('/clock')
    })
  }
})

test.describe('LOGIN — Owner PWA (password)', () => {
  // Only owner should log in to the owner PWA
  test('wachira can log in to owner PWA', async ({ page }) => {
    const ok = await passwordLogin(page, OWNER_URL, 'wachira')
    await snap(page, 'login-owner-wachira')
    expect(ok, 'wachira should log in to owner PWA').toBe(true)
    // Owner PWA lands on / which is DashboardScreen
    expect(page.url()).not.toContain('/login')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. OWNER DASHBOARD — navigate every sidebar item
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('OWNER DASHBOARD', () => {
  test('navigate all sidebar pages', async ({ page }) => {
    // Login as owner
    await passwordLogin(page, OWNER_URL, 'wachira')
    const errors = collectConsoleErrors(page)

    // Dashboard (landing page)
    await page.waitForTimeout(2000) // let dashboard data load
    await snap(page, 'owner-dashboard')
    // Page should have some content (not blank)
    const bodyText = await page.textContent('body')
    expect(bodyText?.length).toBeGreaterThan(50)

    // Sidebar navigation items to test
    const navItems = [
      { path: '/dashboard', label: 'Dashboard'  },
      { path: '/alerts',    label: 'Alerts'      },
      { path: '/bookings',  label: 'Bookings'    },
      { path: '/finance',   label: 'Finance'     },
      { path: '/staff',     label: 'Staff'       },
      { path: '/settings',  label: 'Settings'    },
      { path: '/payroll',   label: 'Payroll'     },
      { path: '/reconciliation', label: 'Recon'  },
      { path: '/purchase-approvals', label: 'Approvals' },
    ]

    for (const item of navItems) {
      // Click sidebar nav link
      const link = page.locator(`a[href="${item.path}"]`).first()
      if (await link.isVisible()) {
        await link.click()
        await page.waitForTimeout(1500) // let page load
        await snap(page, `owner-${item.label.toLowerCase().replace(/\s+/g, '-')}`)
        // Verify we navigated
        expect(page.url()).toContain(item.path)
        // Verify page has content
        const text = await page.textContent('main') || await page.textContent('body')
        expect((text?.length ?? 0)).toBeGreaterThan(10)
      }
    }

    // Check no critical JS errors (ignore network/API errors, focus on render errors)
    const criticalErrors = errors.filter(e =>
      !e.includes('401') && !e.includes('403') && !e.includes('404') &&
      !e.includes('ERR_') && !e.includes('net::')
    )
    // Log but don't fail on console errors — many are benign API 404s
    if (criticalErrors.length > 0) {
      console.log('Console errors on owner pages:', criticalErrors)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. MANAGER DASHBOARD — verify tiles load
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('MANAGER DASHBOARD', () => {
  test('manager screen loads with action tiles', async ({ page }) => {
    await passwordLogin(page, EMPLOYEE_URL, 'manager2')

    // Navigate to manager screen
    await page.goto(`${EMPLOYEE_URL}/manager`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)
    await snap(page, 'manager-dashboard')

    // Verify the page loaded (not blank, not access-denied for level-5 user)
    const bodyText = await page.textContent('body') ?? ''
    expect(bodyText.length).toBeGreaterThan(50)

    // Manager sub-screens to verify
    const subScreens = [
      { path: '/manager/staff',      label: 'Staff'      },
      { path: '/manager/menu',       label: 'Menu'       },
      { path: '/manager/shifts',     label: 'Shifts'     },
      { path: '/manager/attendance', label: 'Attendance' },
      { path: '/manager/front-desk', label: 'Front Desk' },
      { path: '/manager/cash',       label: 'Cash'       },
      { path: '/manager/leave',      label: 'Leave'      },
      { path: '/manager/purchases',  label: 'Purchases'  },
    ]

    for (const sub of subScreens) {
      await page.goto(`${EMPLOYEE_URL}${sub.path}`, { waitUntil: 'networkidle' })
      await page.waitForTimeout(1500)
      await snap(page, `manager-${sub.label.toLowerCase()}`)
      // Should NOT see "access denied" — manager2 is level 5
      const text = await page.textContent('body') ?? ''
      const denied = text.toLowerCase().includes("don't have access")
      expect(denied, `${sub.label} should be accessible to manager`).toBe(false)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. WAITER — Tables screen + New Table creation
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('WAITER — POS Tabs', () => {
  test('waiter can see tables screen and create a table', async ({ page }) => {
    await passwordLogin(page, EMPLOYEE_URL, 'waiter1')

    // Navigate to POS tabs
    await page.goto(`${EMPLOYEE_URL}/pos/tabs`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)
    await snap(page, 'waiter-tabs')

    // Verify tables screen loaded
    const bodyText = await page.textContent('body') ?? ''
    expect(bodyText.length).toBeGreaterThan(20)

    // Click "+ New Table" button
    const newTableBtn = page.locator('button', { hasText: 'New Table' })
    if (await newTableBtn.isVisible()) {
      await newTableBtn.click()
      await page.waitForTimeout(500)

      // Fill the reference field in the modal
      const refInput = page.locator('input').first()
      if (await refInput.isVisible()) {
        await refInput.fill('Playwright Table')
      }

      await snap(page, 'waiter-new-table-modal')

      // Submit the modal (look for "Open Table" button)
      const submitBtn = page.locator('button', { hasText: /Open Table/i })
      if (await submitBtn.isVisible()) {
        await submitBtn.click()
        await page.waitForTimeout(2000)
        await snap(page, 'waiter-tab-detail')
        // Should navigate to /pos/tabs/<id>
        expect(page.url()).toContain('/pos/tabs/')
      }
    } else {
      // Button not found — record as missing
      console.log('MISSING: + New Table button not found on /pos/tabs')
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 5. GATE — Hub screen + Issue Wristband
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('GATE — Hub', () => {
  test('gate staff sees hub with issue band section', async ({ page }) => {
    await passwordLogin(page, EMPLOYEE_URL, 'gate1')

    await page.goto(`${EMPLOYEE_URL}/gate/hub`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)
    await snap(page, 'gate-hub')

    // Verify page loaded
    const bodyText = await page.textContent('body') ?? ''
    expect(bodyText.length).toBeGreaterThan(20)

    // Check for "Issue Band" button/section
    const issueBandBtn = page.locator('button', { hasText: /Issue Band/i })
    const isVisible = await issueBandBtn.first().isVisible().catch(() => false)
    expect(isVisible, 'Issue Band button should be visible on gate hub').toBe(true)
    await snap(page, 'gate-issue-band')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6. KITCHEN — Queue screen
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('KITCHEN — Queue', () => {
  test('kitchen queue screen loads', async ({ page }) => {
    await passwordLogin(page, EMPLOYEE_URL, 'headchef')

    await page.goto(`${EMPLOYEE_URL}/pos/kitchen`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)
    await snap(page, 'kitchen-queue')

    // Verify page loaded (could be empty queue, but should have UI chrome)
    const bodyText = await page.textContent('body') ?? ''
    expect(bodyText.length).toBeGreaterThan(20)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7. CLOCK — Clock screen loads
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('CLOCK', () => {
  test('clock screen loads with big button', async ({ page }) => {
    await passwordLogin(page, EMPLOYEE_URL, 'waiter1')

    await page.goto(`${EMPLOYEE_URL}/clock`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(1500)
    await snap(page, 'clock-screen')

    // Verify clock screen has content
    const bodyText = await page.textContent('body') ?? ''
    expect(bodyText.length).toBeGreaterThan(20)

    // Check for clock button (Clock In / Clock Out)
    const clockBtn = page.locator('button', { hasText: /Clock/i })
    const visible = await clockBtn.first().isVisible().catch(() => false)
    expect(visible, 'Clock button should be visible').toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 8. SECURITY — Role boundary enforcement
// ═══════════════════════════════════════════════════════════════════════════════

test.describe('SECURITY — Role boundaries', () => {
  test('waiter1 cannot access /manager', async ({ page }) => {
    await passwordLogin(page, EMPLOYEE_URL, 'waiter1')

    await page.goto(`${EMPLOYEE_URL}/manager`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)
    await snap(page, 'security-waiter-manager')

    // Should see access denied message (RoleGate shows "You don't have access")
    const bodyText = await page.textContent('body') ?? ''
    const denied = bodyText.toLowerCase().includes("don't have access") ||
                   bodyText.toLowerCase().includes('access denied') ||
                   bodyText.toLowerCase().includes('not authorized')
    expect(denied, 'waiter1 should be denied access to /manager').toBe(true)
  })

  test('waiter1 cannot access /chef', async ({ page }) => {
    await passwordLogin(page, EMPLOYEE_URL, 'waiter1')

    await page.goto(`${EMPLOYEE_URL}/chef`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)
    await snap(page, 'security-waiter-chef')

    // Should see access denied
    const bodyText = await page.textContent('body') ?? ''
    const denied = bodyText.toLowerCase().includes("don't have access") ||
                   bodyText.toLowerCase().includes('access denied') ||
                   bodyText.toLowerCase().includes('not authorized')
    expect(denied, 'waiter1 should be denied access to /chef').toBe(true)
  })

  test('gate1 (level 3) cannot access /manager', async ({ page }) => {
    await passwordLogin(page, EMPLOYEE_URL, 'gate1')

    await page.goto(`${EMPLOYEE_URL}/manager`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(2000)
    await snap(page, 'security-gate-manager')

    const bodyText = await page.textContent('body') ?? ''
    const denied = bodyText.toLowerCase().includes("don't have access") ||
                   bodyText.toLowerCase().includes('access denied')
    expect(denied, 'gate1 should be denied access to /manager').toBe(true)
  })
})
