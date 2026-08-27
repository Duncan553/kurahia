# Found Issues — To-Do List

Opened 2026-08-26 during the emoji→icon sweep. These are problems that **already
existed** before that sweep (verified by stashing the sweep and re-running the
tests: identical failures either way). Nothing here was caused by the icon work.

Ordered by severity.

---

## 1. `Button` is missing `aria-disabled` and `aria-busy` — real a11y bug

**Status:** ✅ FIXED 2026-08-26 · **Severity:** medium (accessibility) ·
**Test:** `Button.test.tsx` now 4/4 passing

**Root cause.** `shared_ui/src/components/Button.tsx:52-57` computes
`const isDisabled = disabled || loading` and passes it to the native
`disabled={isDisabled}` attribute — but never sets `aria-disabled` or `aria-busy`.

Why that matters: a native `disabled` button is removed from the accessibility
tree in some screen readers, so the user gets *silence* rather than "Save,
dimmed, busy". During a `loading` save this is the worst case — the user has no
idea the action is in flight.

**The tests were correct here; the component was wrong.** Fixed the component,
not the test — `Button.tsx` now sets both:

```tsx
disabled={isDisabled}
aria-disabled={isDisabled || undefined}   // `|| undefined` omits the attribute
aria-busy={loading || undefined}          // instead of rendering ="false"
```

---

## 2. `Input` / `Select` tests were never updated after the FormField refactor

**Status:** ✅ FIXED 2026-08-26 · **Severity:** started as low (stale tests), but
rewriting them uncovered a **real bug** — see "the red border" below ·
**Tests:** was 4 failures in `Input.test.tsx` + 4 in `Select.test.tsx`

**Root cause.** The tests were written against an older component API:

```tsx
render(<Input label="Email address" />)                              // test
render(<Input label="Password" error="Must be at least 8 chars" />)  // test
```

But `Input` and `Select` were later refactored into **bare, unlabelled controls**:

```tsx
export interface InputProps extends ComponentPropsWithoutRef<'input'> {
  error?: boolean      // ← now a boolean flag, not a message string
}                      // ← and there is no `label` prop at all
```

Labelling moved out to `FormField` (`shared_ui/src/components/FormField.tsx`),
which is the right design — one component owns label + error text + `htmlFor`
wiring, and `Input` just styles a box. The tests were simply never migrated.

So `screen.getByLabelText('Email address')` finds nothing → all 4 fail on the
same line. The `error="string"` assertions fail for the same reason.

**What was done.** Both test files were rewritten against the real API and now
also cover the integration path (rendering through `FormField`), which is how
these controls are used at all 10 call sites. `FormField` had **zero tests**
despite owning all label/error wiring for every form in all 3 apps — it now has
8 of its own in `FormField.test.tsx`.

One old test was **deleted, not ported**: `Input` had a character-count
assertion (`0/10` → `10/10`, turning red past 90%). That feature was removed
from the component in the same refactor. The test was asserting a feature that
no longer exists.

### The red border — a real bug this uncovered

While rewriting, `grep` turned up something worse than stale tests:

```
$ grep -rn "<Input" -A8 employee_pwa/src owner_pwa/src station_pwa/src | grep "error="
(no results)
```

**Not one call site in the entire codebase ever passed `error` to `Input`.** The
red-border styling in `Input.tsx:25-27` was dead code. A user who failed
validation on the register form saw the message appear below the field — but the
box itself stayed grey. All 10 `FormField` call sites pass `error` to
*`FormField`*, and nobody remembered to also thread it down to the control.

**Fixed at the source**, so no call site has to remember. `FormField` now
`cloneElement`s its child to inject three things:

```tsx
error: Boolean(error),                    // the red border, at last
'aria-invalid': error ? true : undefined,
'aria-describedby': error ? errorId : showHelp ? helpId : undefined,
```

`aria-describedby` was the other half and is its own a11y fix: without it a
screen reader announces the input and the error as two unrelated things, so the
user hears "Phone Number, edit text" and never learns *why* it was rejected. The
error `<p>` also got `role="alert"` so it is announced the moment validation
fails, not only if the user happens to tab back onto the field.

### Two more things the same pass turned up

- **`shared_ui` did not typecheck standalone at all.** `npx tsc --noEmit` inside
  `shared_ui/` exited 2. The apps passed because their tsconfig is looser and
  only pulls in what they actually import. Now exits 0.
- **`index.ts` exported a type that never existed** — `SelectOption` was
  re-exported from `./components/Select`, which has never defined it. Removed.
- **`StatusBadge.tsx` had two dead icon components**, `Pause` and `ArrowIn`.
  Nothing referenced them (`held` uses `Clock`, `checked-in` uses `Check`). Removed.

---

## 3. 8,218 files of `shared_ui/node_modules` are committed to git

**Status:** ✅ FIXED 2026-08-26 (staged, not yet committed) ·
**Severity:** medium (repo hygiene, bloat)

**Root cause.** `.gitignore` ignores node_modules **per-app by name**:

```
employee_pwa/node_modules/
owner_pwa/node_modules/
```

`shared_ui/` and `station_pwa/` were added to the project *after* that list was
written, and nobody appended them. `station_pwa` got lucky (0 tracked files),
but `shared_ui/node_modules` was committed — 8,218 files. `.git` is now 68 MB.

A visible symptom: `git status` shows
`shared_ui/node_modules/.vite/vitest/…/results.json` as modified every single
time the test suite runs, so real changes get buried in noise.

**What was done:**
1. ✅ Replaced the per-app lines in `.gitignore` with global `node_modules/` and
   `.vite/` rules that match at any depth. (`dist/` was already global on line 10.)
2. ✅ `git rm -r --cached shared_ui/node_modules` — 8,218 deletions are **staged
   but not committed**. The files are untouched on disk; all 3 apps still
   typecheck and build. Commit the removal to finish it.
3. ⏳ **Still open, optional:** the 68 MB is only reclaimed by a history rewrite
   (`git filter-repo`). That is destructive and rewrites every commit hash — only
   do it deliberately, and settle the unpushed-branch situation below first.

**Do this before pushing.** `chunk-10-final-hardening` is 66 commits ahead of
its remote AND missing one remote-only commit (`e34d868 Update README.md`, made
directly on GitHub), so a plain `git push` is rejected as non-fast-forward. Merge
or rebase that one commit first. Do **not** combine a history rewrite with that
merge in one step — resolve the push first, rewrite later if at all.

---

## 4. Three screens are byte-identical copies across two apps

**Status:** ✅ FIXED 2026-08-26 · **Severity:** low-medium (maintenance trap)

`diff` reports **zero** difference between the `employee_pwa` and `station_pwa`
copies of:

- `src/screens/WaiterTabDetailScreen.tsx`
- `src/screens/IncidentScreen.tsx`
- `src/screens/StationQueues.tsx`

This bit during the icon sweep: every edit had to be made once and then manually
`cp`'d to the second app. The next person who edits only one copy creates a
silent divergence between the two apps.

**What was done.** All three moved to `shared_ui/src/screens/`. The coupling was
`../lib/axios`, `../stores/authStore` and `../lib/audio` — and those turned out
to be **byte-identical between employee_pwa and station_pwa too**, so they were
hoisted to `shared_ui/src/lib/` and `shared_ui/src/stores/` as well.
`owner_pwa` deliberately keeps its own `axios`/`authStore`: those genuinely
differ, and were left alone.

**The trick that kept this small.** A naive move would have meant rewriting ~98
import sites (`axios` alone is imported in 50 employee_pwa files). Instead every
old path keeps a one-line re-export shim:

```ts
// employee_pwa/src/lib/axios.ts
export * from '@shared/lib/axios'
export { default } from '@shared/lib/axios'
```

So every existing `import api from '../lib/axios'` and every router entry kept
working untouched. Files changed: 3 moved + 9 shims, not 98 rewrites.

**Cost worth knowing about.** `shared_ui` was a thin presentational package —
peer deps of react/framer-motion, one real dep. These screens fetch data, so it
now also peer-depends on `axios`, `@tanstack/react-query`, and `react-router-dom`,
and its tsconfig needs `vite/client` types for `import.meta.env`. That is a real
change to what the package *is*. It was the right call here because the
alternative (threading `api` and `useAuthStore` in as props through three large
screens) is worse, but a future screen should not be hoisted reflexively — if it
only shares markup, keep it in the app.

### Bugs this surfaced in `StationQueues.tsx`

`shared_ui`'s tsconfig is stricter than the apps' (`noUnusedLocals`,
`noUnusedParameters`), so moving the file exposed problems the apps never flagged:

- **`items` was `any[]`.** `useQuery` had no type param and
  `api.get(endpoint).then(r => r.data)` returns `any`, so every downstream
  `.map(i => …)` silently lost its typing — 6 implicit-`any` params and a
  `Set<unknown>` that should have been `Set<string>`. Fixed by typing it at the
  source: `useQuery<QueueItem[]>` + `api.get<QueueItem[]>`.
- **Two dead declarations:** `timerRef` (never attached to anything) and
  `statusLabels` (never read — and its `PENDING` entry was
  `station === 'BAR' ? 'NEW ORDER' : 'NEW ORDER'`, identical in both branches).

---

## 5. `pytest` at repo root fails to collect — NOT introduced here

**Status:** open · **Severity:** low (dev friction) · **Backend code untouched
by this session** — the only non-frontend file changed was `.gitignore`.

Running bare `pytest` from the repo root dies before running a single test:

```
ERROR scripts/e2e_test.py  - NameError: name 'SEED_PASSWORD' is not defined
ERROR scripts/full_test.py - NameError: name 'SEED_PASSWORD' is not defined
ERROR scripts/chaos_test.py - AssertionError: Owner login failed
!!!! Interrupted: 3 errors during collection !!!!
```

**Root cause.** There is no pytest config anywhere — no `pytest.ini`, no
`[tool.pytest]` in `pyproject.toml`, no `setup.cfg`. With no `testpaths`, pytest
scans the whole repo and picks up `scripts/*_test.py`, which are **operator
scripts, not unit tests**: they expect a live server and a `SEED_PASSWORD` env
var.

`pytest tests/` works fine. But CLAUDE.md §10 documents the command as plain
`pytest`, so anyone following the docs hits this.

**Status update:** ✅ FIXED — `pytest.ini` added with `testpaths = tests` and
`norecursedirs`. Bare `pytest` now collects 770 tests in 0.47s.

---

## 6. The test suite took 25 minutes. It now takes ~100 seconds.

**Status:** ✅ FIXED 2026-08-26 · **Severity:** high (dev velocity)

Measured before: **1508s (25m 08s)** for 770 tests — ~2s per test, on in-memory
SQLite. Two independent causes.

### 6a. Argon2 was ~86% of the runtime

`app/models/user.py:16` builds one hasher at library defaults:

```
time_cost=3, memory_cost=64MiB, parallelism=4  →  186ms/hash, 210ms/verify
```

Those are the CORRECT production numbers — Argon2 is meant to be slow; that is
the security property. The problem is `tests/conftest.py`'s `app` fixture is
**function-scoped** and seeds **9 password/PIN hashes for every test**:

```
9 x 186ms  ≈ 1.7s per test, before a single assertion runs
770 x 1.7s ≈ 1300s   of the observed 1508s
```

**Fix:** `conftest.py` swaps the module-level `_ph` for a weak hasher. This lives
entirely in the test harness — `app/models/user.py` is NOT modified, so there is
no code path by which weak parameters reach production. Measured on
`test_finance.py`: **70.75s → 19.29s**, same 31 tests passing.

### 6b. The suite ran single-threaded on an 8-core machine

`pytest-xdist` was not installed. With `-n 4` the full suite finishes in ~90s.

**Result: 1508s → ~100s total (15x).** Nothing was weakened in production.

---

## 7. Two genuinely flaky tests — timing-attack tests under parallelism

**Status:** ✅ FIXED 2026-08-26 · **Severity:** medium (false CI failures)

`test_security_category_4.py::TestUsernameEnumerationLogin` and
`::TestPINLoginEnumeration` prove you cannot enumerate usernames by timing
`/auth/login`: the "no such user" path runs a DUMMY Argon2 verify so both paths
cost the same, asserted within 30%.

**They are flaky for two separate reasons, and both were proven, not guessed:**

1. **They depend on real Argon2 cost.** The equalisation only holds while the
   hash DOMINATES the request. At ~210ms it does. At ~1ms (6a above) it does not
   — DB lookup and Flask overhead become comparable and blow the 30% tolerance.
2. **They cannot survive CPU contention.** Argon2 runs at `parallelism=4`; with
   4 xdist workers that is up to 16 threads on 8 cores, so elapsed-time numbers
   become noise. Proven: `pytest -m production_hashing` passes **4/4 serially**
   and fails **2/4 under `-n 4`** — identical code, only contention differs.

**Fix:** a `production_hashing` marker plus a `pytest_runtest_setup` hook that
(a) restores real Argon2 for those tests and (b) skips them under xdist.

It must be a **hook, not a fixture**: argon2 reads its cost parameters from the
stored hash string, not from the verifier — so the swap has to happen before the
`app` fixture seeds users, or `verify()` would replay the cheap parameters baked
into a weak seed hash. A fixture cannot reliably order itself ahead of `app`.

**The two-command workflow (both are needed — see pytest.ini):**

```bash
pytest -n 4                     # 765 passed, 5 skipped, ~90s
pytest -m production_hashing    # the 4 timing tests, serial, ~12s
```

Skipping under `-n` is honest: a timing assertion measured under contention
proves nothing. But it does mean **CI must run the second command**, or the
enumeration-timing defence silently goes unverified.

---

## 8. Budget-exceeded alert has never fired — `Budget` has no `spent` column

**Status:** open · **Severity:** medium (a real detection rule is dead)

`app/judge/engine.py:168`:

```python
spent = Decimal(str(b.spent)) if hasattr(b, 'spent') and b.spent else Decimal("0")
if spent <= budget_amt:
    continue
```

`Budget` (`app/models/budget.py:15-26`) has columns `id, department_id, period,
amount, set_by_id, is_active, created_at_utc, updated_at_utc`. **There is no
`spent` column.** So `hasattr(b, 'spent')` is always False → `spent = 0` →
`0 <= budget_amt` is always true → `continue` always runs. The alert has never
fired, and never can.

Spend is DERIVED elsewhere by `get_budget_spend()`. **Fix:** call that instead of
reading a column that doesn't exist. Roughly a one-line change.

---

## 9. 30% of every performance score is a constant

**Status:** open · **Severity:** medium (silently wrong business metric)

`compute_performance` (`app/services/hr.py:195`) is called with a
**`EmployeeProfile.id`** (`app/hr/performance.py:50`). `Shift.employee_id`,
`LeaveRequest.employee_id` and `ClockEvent.employee_id` all key off that, so
punctuality and attendance are correct.

But:
- `CashReconciliation.staff_id` is a **FK to `users.id`**
  (`app/models/cash_reconciliation.py:39`)
- void rate matches on `Order.created_by_id`, also `users.id`

Comparing a profile id against a user id never matches. So `short_count` is
always 0 and `void_rate_pct` is always 0, which pins **`cash_health = 100`** and
**`void_health = 100`** permanently.

Per `SCORE_WEIGHTS` (`app/services/hr.py:16`) those carry `0.15 + 0.15` — so
**30% of every employee's composite score is a hardcoded 100.** A waiter with
chronic cash shortfalls and a high void rate scores identically to a clean one on
those axes.

**Fix:** resolve the profile → `user_id` before the two money queries.

---

## 10. UI responsive sweep — and a hard lesson about the tool

**Status:** 1 bug fixed, tap-target backlog open

`tests/playwright/ui_sweep.spec.ts` drives all 3 PWAs across every route at
phone (390x844), tablet (820x1180) and desktop (1440x900), asserting: hidden or
covered controls, trapped (unscrollable) content, horizontal page overflow, and
sub-44px tap targets.

### The detector was wrong three times. Most "findings" were mine, not the app's.

| Run | Reported | What was actually broken |
|---|---|---|
| 1 | 1851 | Read `getComputedStyle` on the element instead of walking ancestors, so every link inside the `hidden md:flex` sidebar looked like a 0x0 hidden button |
| 2 | 924 | Clamped hit-test coordinates into the viewport, so anything below the fold reported "covered by the bottom nav"; also flagged `overflow-x-auto` nav items as unreachable |
| 3 | 849 | — |

**Verified empirically, not by reading markup:**
- `station/pos/tabs` "Assign New Table" — at y=1622, below the fold. Scrolled into
  view: `hitIsSelfOrChild: true`. **Not covered.**
- Owner mobile nav — `overflowX: auto`, 390px of 720px content, `canScroll: true`.
  After scrolling, "Settings" sits at x=318..390. **Works as designed** (and
  `AppLayout.tsx:255` documents that choice).
- `station/villa` "Book Villa" — `hitSelf: true` before and after scrolling. The
  station layout has the nav as a `shrink-0` flex SIBLING of an
  `overflow-y-auto` main, so it structurally cannot overlay. **Not covered.**

**Lesson for the next sweep: a control below the fold is not hidden, and an
element inside a scrollable ancestor is not unreachable. Prove it before filing it.**

### The one real layout bug — FIXED

`owner/login` scrolled sideways on a 390px phone: 435px of content, caused by a
decorative `w-[480px] h-[480px]` ambient glow. It is `pointer-events-none` at 7%
opacity, so clipping costs nothing — added `overflow-x-hidden` to its container
(`owner_pwa/src/screens/LoginScreen.tsx:72`).

### Open: 88 distinct sub-44px tap targets

Real UX signal, not yet actioned. Worst offenders are icon buttons:
- `owner/dashboard` "Refresh all tiles" — **14x14px**
- `owner/dashboard` "Search" — **16x16px**
- avatar buttons at 28-32px
- filter chips at 85x32px, text links at ~20px tall

44px is the WCAG/Apple touch guideline. The icon buttons are the ones a real
thumb will genuinely miss; inline text links are more forgiving.

### Minor: duplicate landmark

Both the desktop sidebar (`AppLayout.tsx:175`) and the mobile bar
(`AppLayout.tsx:261`) use `aria-label="Owner navigation"`. A screen reader sees
two identically-named navigation landmarks.

### Minor: three login forms, three id conventions

`employee_pwa` uses `#username`/`#password`, `owner_pwa` uses
`#login-username`/`#login-password`, `station_pwa` uses `#pin-username`. Any
cross-app test has to special-case all three.

### Stale: `resort_simulation.spec.ts` tests users that don't exist

Its `USERS` list (`wachira`, `manager2`, `headchef`, `barmgr`, …) matches nothing
in the seeded DB, which actually holds `amara.wanjiku`, `brian.mwangi`,
`cynthia.achieng`, `grace.muthoni`, `hassan.omondi`, `joyce.wambua`, etc.

---

## 11. The test suite littered the working tree — and 24 stubs are committed

**Status:** ✅ root cause FIXED · ⏳ 24 tracked files await your call

This solves the long-standing mystery of the untracked hash-named files in
`employee_pwa/public/images/{menu,profiles,uploads}`.

**Root cause.** `_upload_dir()` in `app/uploads/__init__.py` resolved to
`<repo>/employee_pwa/public/images/<category>` with no override, so
`tests/test_uploads.py` wrote real files into the developer's working tree on
every run and never cleaned up.

**Proven, not assumed:** one run of `test_uploads.py` took `menu/` from 54 files
to 56. Every one of these files is **exactly 100 bytes** — a PNG magic header
followed by 92 zero bytes — and **nothing references them**: 0 of 29 menu items
have an `image_url`. 44 of the 54 accumulated during this session's own runs.

**Fixed:** added an `UPLOAD_ROOT` config key; `TestingConfig` points it at a
`tempfile.mkdtemp()`. Verified — `test_uploads.py` passes 10/10 and the file
count no longer moves.

**Cleanup done:** removed the 40 untracked stubs.

**Still open — your decision.** **24 of these stub files are already COMMITTED**
to the repo from earlier runs. They are provably junk by the same test (100
bytes, identical PNG stub header, referenced by nothing), but removing tracked
files is the owner's call, so they were left alone. To clear them:

```bash
find employee_pwa/public/images/{menu,profiles,uploads} -type f -size -101c -size +99c \
  -exec git rm --cached {} +
```

Note the **real** menu photos are named (`grilled-tilapia.jpg`, `beef-burger.jpg`,
16-23KB) and are unaffected by any size-based filter.

---

## 12. `tsc --noEmit` was checking NOTHING — and it hid a broken screen

**Status:** ✅ FIXED (21 errors → 0) · **Severity:** HIGH — this is the most
important finding of the session

### The measurement was broken

Every app's root `tsconfig.json` is:

```json
{ "files": [], "references": [{ "path": "./tsconfig.app.json" }, ...] }
```

`files: []` plus project references means **plain `npx tsc --noEmit` type-checks
zero files and exits 0.** It is not a weak check — it is *no* check. The real
build runs `tsc -b` (see `package.json`: `"build": "tsc -b && vite build"`).

`vite build` doesn't cover for it either: Vite uses esbuild, which strips types
without checking them. So a green build and a green `tsc --noEmit` together
proved nothing.

**Use `npx tsc -b --force`.** Under it: employee 16 errors, owner 4, station 1.

### What it was hiding: `/inventory/quick-entry` was unusable

The FormField refactor removed `label` and `options` from `Input`/`Select`, but
**never migrated the call sites**. React silently drops an unknown prop on a
component, so:

- `<Select options={...}>` → options ignored → **a dropdown with ZERO options**
- `<Input label="...">` → spread onto the DOM as `<input label="Item *">`, an
  invalid attribute → **no visible label, nothing linked for a screen reader**

Proven in a real browser before fixing:

```
{ optionCount: 0, options: [], hasLabelAttr: true, labelAttr: "Item *", labelledBy: false }
```

**Zero options.** Nobody could pick an item, so stock could not be logged at all.
Six dropdowns were affected across 5 files (`WaiverScreen` in both employee and
station — the duplicate problem from #4 again), plus 18 `label` sites in 7 files.

**Fix:** restored `options` and `label` on `Select`/`Input` centrally rather than
rewriting 18 call sites — and `label` now renders a real `<label htmlFor>` wired
to a `useId()`, so the markup is *better* than before it broke. Re-verified:

```
{ optionCount: 1, first3: ["Select item…"], strayLabelAttr: false, realLabel: "Item *" }
```

(Only the placeholder shows because `GET /inventory/items` genuinely returns
`[]` — **no inventory items are seeded**. That is a seed-data gap, not a bug.)

`SelectOption` — removed earlier in this session as a "phantom export" — is real
again and exported.

### Also hidden: the "Access restricted" screen was a dead end

`RoleGate` in all three apps passed `message=` and `action={{label,onClick}}` to
`EmptyState`, whose props are `icon`/`title`/`description`/`actionLabel`/
`onAction`. Both were silently dropped, and required `icon` was missing entirely.
A user hitting a page above their role saw the words "Access restricted" with **no
explanation and no way back**. Fixed in all three apps.

### Also hidden

- `employee/LoginScreen.tsx:40` — `decodeJWT` is generic defaulting to
  `Record<string, unknown>`, so every claim was `unknown`: 3 errors in one
  `setAuth` call. Now instantiated with a real claim shape.
- `station/main.tsx` passed `level="page"` to `ErrorBoundary`, which accepts
  only `'screen' | 'tile'`.
- Four unused imports.

**Recommendation:** change the `build` script or CI to fail on `tsc -b`, and stop
trusting `tsc --noEmit` in this repo.

---

## 13. station_pwa is not actually a PWA

**Status:** open · **Severity:** medium (offline is exactly what tablets need)

`station_pwa/tsconfig.app.json` referenced `vite-plugin-pwa/client` types, but:

- `vite-plugin-pwa` is **not** in `station_pwa/package.json`
- `station_pwa/vite.config.ts` never imports `VitePWA`
- `station_pwa/dist/sw.js` **does not exist**, while `employee_pwa/dist/sw.js`
  and `owner_pwa/dist/sw.js` both do

So the station app has no service worker, no manifest, no offline caching and is
not installable — despite the name. The stale `types` entry (scaffolding copied
from the other apps) was removed so the app typechecks; **adding real PWA support
is left as a product decision**, since it needs a manifest, icons and a caching
strategy.

This matters more here than anywhere else: the station tablets are the POS and
kitchen displays running on the resort LAN, which is precisely where a dropped
connection should not stop service. `employee_pwa` even has an offline clock-in
queue (`ClockScreen.tsx` `enqueueClockEvent`) — station has nothing equivalent.

---

## Not broken — done and verified 2026-08-26

- **Emoji → icon sweep.** All raw emoji (`📍 👤 🔔 🔇 🎉`) and glyph-as-icon
  characters (`✓ ✗ ⚠ ○ ◌ ◐ ×`) removed from all 3 PWAs, replaced by the new
  `shared_ui/src/components/Icon.tsx`. All 3 apps typecheck clean (`tsc
  --noEmit`, exit 0) and build clean (`vite build`, exit 0).
