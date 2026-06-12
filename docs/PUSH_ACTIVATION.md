# Web Push — Activation & Real-Device Testing

## State

- Backend socket: `app/services/notifications/webpush.py` (dormant pattern)
- Dev keys: **already active** — `instance/private_key.pem` + `.env` (gitignored).
  `GET /notifications/push-config` → `configured: true`.
- Production: generate fresh keys on the prod box (`vapid --gen` inside
  `instance/`), set the three vars in the prod `.env`. Never reuse dev keys.

## Why you can't just open the LAN IP

Service workers (and therefore push) only run in a **secure context**:
`https://…` or `http://localhost`. A tablet opening `http://192.168.x.x:4173`
gets no service worker, no install prompt, no push. Two ways around it:

### Option A — Android tablet over USB (fastest for testing)

1. Enable Developer Options + USB debugging on the tablet, plug into the dev machine.
2. ```bash
   adb reverse tcp:4173 tcp:4173   # tablet's localhost:4173 → dev machine
   ```
3. On the tablet, open Chrome → `http://localhost:4173` — that IS a secure
   context. Service worker registers, install prompt appears.

### Option B — Tailscale serve (production-aligned, no cable)

The resort already uses Tailscale. On the dev machine:
```bash
tailscale serve --bg https / http://localhost:4173
```
Any device on the tailnet opens `https://<machine>.<tailnet>.ts.net` — valid
HTTPS certificate, full PWA behavior. This is also the go-live shape.

## The receive-side test (the one step automation can't do)

1. Tablet → app → log in as any staff with a profile (e.g. `waiter2`).
2. On `/clock` (personal account) tap **Enable** on the "Get notified" card →
   Chrome permission prompt → Allow. (`POST /notifications/push-subscribe` fires.)
3. Close the app completely (swipe away).
4. Trigger a notification — simplest: kitchen marks any order item **Ready**
   (pings the order's waiter), or approve a leave request.
5. ✅ Push appears in the tablet's notification shade.
6. Tap it → app opens on the right screen (`order_ready` → Tables,
   `leave_request` → Schedule — `src/lib/notificationRoutes.ts`).

## Troubleshooting

| Symptom | Cause |
|---|---|
| No "Enable" card | Push unsupported (not secure context) or permission already decided — reset in Chrome site settings |
| Enable does nothing | `push-config` dormant — check the three VAPID vars, restart Flask |
| Subscribed but nothing arrives | Tablet offline / battery saver killing Chrome; check `push_subscriptions.is_active` (410s auto-deactivate) |
| Tap opens wrong screen | reference_type missing from `notificationRoutes.ts` map |
