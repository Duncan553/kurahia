/**
 * proposal_findings.spec.ts — the two findings the proposal names that had no test.
 *
 * Section 12 of the proposal lists what the review found wrong. Six of those
 * fixes were already held by a test that fails when the fix is removed. These
 * two were not, so the proposal was claiming them on the word of a commit.
 *
 * Run (servers already up: backend :5000, owner :5174, station :5176):
 *   npx playwright test proposal_findings
 */
import { test, expect } from '@playwright/test'
import { api, appPage, APPS } from './lib/capture'

const MANAGER = 'brian.mwangi'
const OWNER   = 'amara.wanjiku'

/* ── Finding 3: a wedding could be booked and never run ─────────────────────
 * Drives one event through EVERY step a real one takes, using only the screen:
 * confirm → staff it → set stock aside → issue it → start → stock comes back → finish.
 * The API is only used to set the event up and to check each step really landed. */
test('a booked event can be confirmed, staffed, stocked, started and finished from the screen', async ({ browser }) => {
  test.setTimeout(120_000)

  // Set-up through the API: an event starting in an hour, like a real booking.
  const types = await api('GET', '/event-types', MANAGER)
  expect(types.data.length, 'no event types to book against').toBeGreaterThan(0)
  const title = `Proof wedding ${Date.now()}`                 // unique, so we find OUR card
  const start = new Date(Date.now() + 60 * 60_000)
  // Every event is held somewhere. A venue of its own, so a rerun never clashes.
  const venue = await api('POST', '/bookable-resources', MANAGER, {
    name: `Proof lawn ${Date.now()}`, resource_type: 'EVENT_VENUE', capacity: 200, base_price: '50000',
  })
  expect(venue.status).toBe(201)
  const made = await api('POST', '/events', MANAGER, {
    title, event_type_id: types.data[0].id, venue_id: venue.data.id,
    starts_at_utc: start.toISOString(),
    ends_at_utc: new Date(start.getTime() + 4 * 60 * 60_000).toISOString(),
    expected_guests: 80, location: 'Lawn', idempotency_key: crypto.randomUUID(),
  })
  expect(made.status).toBe(201)
  const id = made.data.id
  const status = async () => (await api('GET', `/events/${id}`, MANAGER)).data.status

  const { ctx, page } = await appPage(browser, 'station', MANAGER)
  await page.goto(`${APPS.station.base}/events`)

  // The drawer lives inside the card. If the card leaves the list, so do the buttons.
  const card = page.locator('.glass-card', { hasText: title })
  const drawer = page.getByRole('dialog')
  const openPanel = async () => {
    await card.getByRole('button', { name: 'Staff & stock' }).click()
    await expect(drawer).toBeVisible()
  }
  const toastSays = (t: RegExp) => expect(page.getByText(t).first()).toBeVisible()

  await openPanel()
  await drawer.getByRole('button', { name: 'Confirm it' }).click()
  await expect.poll(status).toBe('CONFIRMED')

  // Staff it: first real person in the list, doing "Bar".
  await drawer.getByLabel('Person').selectOption({ index: 1 })
  await drawer.getByLabel('Doing what').fill('Bar')
  await drawer.getByRole('button', { name: 'Add' }).click()
  await expect.poll(async () =>
    (await api('GET', `/events/${id}/assignments`, MANAGER)).data.length).toBe(1)

  // Set one unit aside, then issue it — the moment stock really leaves the store.
  await drawer.getByLabel('Item').selectOption({ index: 1 })
  await drawer.getByLabel('How much').fill('1')
  await drawer.getByRole('button', { name: 'Set aside' }).click()
  await toastSays(/Set aside/)
  await drawer.getByRole('button', { name: 'Issue' }).click()
  await toastSays(/Issued/)

  // Start. The guests have arrived — the event must STILL be on the screen.
  await drawer.getByRole('button', { name: 'Start' }).click()
  await expect.poll(status).toBe('IN_PROGRESS')
  await page.reload()
  await expect(card, 'a started event vanished from the Events screen').toBeVisible()
  await openPanel()

  // The crate comes back, then the event is closed.
  await drawer.getByRole('button', { name: 'Came back' }).click()
  await toastSays(/Returned/)
  await expect.poll(async () =>
    (await api('GET', `/events/${id}/inventory`, MANAGER)).data.allocations[0].status).toBe('RETURNED')
  await drawer.getByRole('button', { name: 'Finish' }).click()
  await expect.poll(status).toBe('COMPLETED')

  // Switch the test venue off (never delete), so reruns do not fill the
  // manager's venue list with proof lawns.
  await api('POST', `/bookable-resources/${venue.data.id}/disable`, MANAGER)

  await ctx.close()
})

/* ── Finding 8: two owner tiles were inventing their numbers ─────────────────
 * Every Resort Health tile must equal what the API says it counts. The bug was
 * "Open Incidents" reading the theft-alert list: 0 while two guests were hurt. */
test('every Resort Health tile shows the number the API holds for it', async ({ browser }) => {
  const [incidents, gate, overview] = await Promise.all([
    api('GET', '/incidents', OWNER),
    api('GET', '/gate/today-stats', OWNER),
    api('GET', '/dashboard/overview', OWNER),
  ])
  const open = incidents.data.filter((i: { actioned: boolean }) => !i.actioned).length
  // With zero open incidents "0" is right either way, and this test would prove nothing.
  expect(open, 'need at least one open incident for this test to mean anything').toBeGreaterThan(0)

  const { ctx, page } = await appPage(browser, 'owner', OWNER)
  await page.goto(`${APPS.owner.base}/dashboard`)
  await expect(page.getByRole('heading', { name: 'Resort Health' })).toBeVisible()

  // A tile is the card holding its label; its figure is the bold tabular number.
  // Exact text, not "contains" — "2" is inside "12", and that would pass a wrong tile.
  const expectTile = async (label: string, value: number) =>
    expect(page.locator('.glass-card', { has: page.getByText(label, { exact: true }) })
      .locator('span.tabular-nums'), label).toHaveText(String(value))

  await expectTile('Open Incidents', open)
  await expectTile('Guests Inside',  gate.data.inside_now)
  await expectTile('Arrivals Today', overview.data.bookings.arrivals_today)

  // The two invented tiles must not come back under any name.
  await expect(page.getByText('Spa Utilization')).toHaveCount(0)
  await expect(page.getByText('Dining Reservations')).toHaveCount(0)

  await ctx.close()
})
