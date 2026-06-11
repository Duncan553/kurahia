# F-17 Runtime Verification — PWA Install + Offline + Push

Date: 2026-06-11 · Method: built app under `vite preview :4173` + Flask `:5000`,
driven by Playwright headless Chromium (`scripts/verify_f17.mjs`).

## Automated runtime checks — 15/15 pass

| # | Check | Result |
|---|---|---|
| 1 | manifest.webmanifest valid (name, standalone, 4 icons) | ✅ |
| 2 | Service worker registers and controls the page | ✅ |
| 3 | push-config dormant mode returns clean JSON, no errors | ✅ |
| 4 | Menu + inbox caches primed online (200) | ✅ |
| 5 | UI login lands on /clock | ✅ |
| 6 | Offline banner "Offline — showing saved data" | ✅ |
| 7 | Offline: /menu/items served from cache (200) | ✅ |
| 8 | Offline: /notifications/inbox served from cache (200) | ✅ |
| 9 | Offline: /kitchen/queue NOT cached (network fail) | ✅ |
| 10 | Offline: /finance/* NOT cached (network fail) | ✅ |
| 11 | Offline: /auth/* NOT cached (network fail) | ✅ |
| 12 | Offline clock-in queued to IndexedDB (F-7 preserved under SW) | ✅ |
| 13 | Reconnect: queue drained to 0, event synced | ✅ |
| 14 | Reconnect: "Back online" banner | ✅ |
| 15 | Offline full reload: app shell renders from precache | ✅ |

## Push send-path probe (real crypto)

Headless Chromium cannot complete a real FCM push registration
(`AbortError: Registration failed`) — an environment limit, not a code path.
Instead the send path was proven against a local fake push service:

- Real VAPID keys generated with `vapid --gen`
- `push-config` configured mode returns the public key ✅
- Subscription row with a real browser-grade ECDH keypair (SECP256R1)
- `push_to_user()` → pywebpush encrypted and POSTed **209 bytes** to the
  endpoint, fake service answered 201, `sent count: 1` ✅
- Dormant mode restored after the probe

## Remaining manual check (needs a real device)

Full receive-side test — push arrives on a locked tablet, tap routes via the
shared `notificationRoutes` map — requires real Chrome + FCM. Run once on a
resort tablet after setting VAPID keys (see .env.example). Everything up to
the FCM hop is verified above.

## Side effects cleaned

- teststaff clock-in created by the offline-drain test → clocked out
- Probe subscription row deactivated (is_active=False, per invariant 6)
