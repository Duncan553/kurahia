# F-15.7 Smoke Test Results

Date: 2026-06-11

## Services
- Flask backend: port 5000 ✅
- Employee PWA: port 5173 ✅
- Owner PWA: port 5174 ✅

## Build
- `employee_pwa pnpm build` → clean (586 modules) ✅
- `owner_pwa pnpm build` → clean (556 modules) ✅

## F-15.7a: Two-step staff creation (clock-in blocker fix)
| Check | Result |
|---|---|
| Login as wachira (owner) | ✅ |
| Manager nav → Manager hub | ✅ |
| Staff tile → Staff Accounts screen | ✅ |
| Create new account → step 1 form | ✅ |
| Meta endpoint (roles + depts) | ✅ |
| Step 1 submit → step 2 form | ✅ |
| Step 2 submit → credentials card shown | ✅ |
| DB: user + profile both created | ✅ |
| Phone normalization `0722…` → `+254722…` | ✅ |
| "No profile" badge for users without profile | ✅ (wachira, testmanager show badge) |

## F-15.7b: Purchase free-text + Button + palette
| Check | Result |
|---|---|
| PurchaseRequestScreen: "not in list" toggle visible | ✅ |
| Toggle click → description input shown | ✅ |
| "← Back to item list" link shown | ✅ |
| `bg-white` → `bg-cream-card` across 10 screens | ✅ |
| Raw `<button>` submit → `<Button>` in QuickEntry + PurchaseRequest | ✅ |

## Known non-bugs
- TanStack Query refetch lag: new user appears in list after ~1s (query invalidation correct, timing in Playwright 500ms too short)
