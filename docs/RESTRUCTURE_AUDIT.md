# Full System Restructure Audit

> Conducted 2026-06-18. Read-only.

## Summary — What EXISTS vs What's MISSING

### FULLY EXISTS (surface, don't rebuild)
- Wristband system: issue, forfeit, deactivate, reconcile, KSh 3,000 entry fee, tab-linked
- Gate: day-guest path (pay+band), deactivation, forfeit sweep, reconciliation, headcount
- Payment sockets: M-Pesa Daraja, Bank Transfer, Card Gateway — all DORMANT, env-key gated, /status diagnostics present
- Receipts: GET /receipts/:tab_id — structured data (charges, payments, balance, who, when)
- Cash reconciliation: create, pending cash per staff, shortfall detection
- All 4 "unfired" judge types: CASH_SHORTFALL_PATTERN, MPESA_FLAGGED, BANK_FLAGGED, VOID_ABUSE — all WIRED with fire_alert_if_absent
- Tab system: charges, payments, balance, close
- Kill switch on every request (is_active + role recheck)
- Audit log on every write operation
- Business day cutoff (configurable, Africa/Nairobi)
- Auto-close clean days + alert on problems

### PARTIALLY EXISTS (needs enhancement)
- Gate: booked-guest path — booking verification exists but no band-free admission flow
- Receipts: per-tab only, no central search/calendar screen — need to build a list endpoint
- Stock check on orders: checks is_active but NOT in_stock before accepting order items
- Health: returns {"status":"ok"} — doesn't check DB
- Reconciliation: front desk can reconcile, but no "who-reconciles-what" visibility screen

### MISSING (needs build)
- MenuItem image field + upload
- BUDGET_EXCEEDED judge alert
- Central receipts search screen (list all tabs with date/staff filters)
- Idle brand animation
- Tablet assignment model
- Stock pre-check warning before order accept
- Real /health with DB check
- Cron last-run timestamps
- Sentry-ready wiring

## Detail by Area

### WRISTBAND — FULLY EXISTS
- `app/services/gate.py:25` — ENTRY_FEE = Decimal("3000")
- `app/services/gate.py:89` — issue_band() creates Tab + Payment(3000) + Wristband
- `app/gate/core.py:51` — POST /gate/issue-band
- `app/gate/core.py:108` — POST /gate/deactivate-band/:number
- `app/gate/core.py:131` — GET /gate/bands/:number (lookup)
- `app/gate/core.py:154` — GET /gate/active-bands
- `app/gate/core.py:208` — POST /gate/forfeit-day (EOD sweep)
- `app/gate/core.py:237` — GET /gate/reconciliation
- Band→Tab: every wristband links to a tab_id. Purchases charge the tab.
  Spend > 3,000 → balance shows as positive (owed). Spend < 3,000 → forfeit.

### PAYMENT SOCKETS — ALL DORMANT, ALL WIRED
- M-Pesa: `app/finance/mpesa_daraja.py` — STK push, C2B callback, /mpesa/status
- Bank: `app/finance/bank_transfer.py` — SMS webhook, API, /bank/status
- Card: `app/finance/card_gateway.py` — IPN handler, /card/status
- Each: dormant when env vars missing, activates with NO code change

### JUDGE ALERTS — ALL 4 "UNFIRED" TYPES EXIST
- CASH_SHORTFALL_PATTERN: `app/finance/cash.py:143` — fires on N consecutive shortfalls
- VOID_ABUSE: `app/finance/analytics.py:57` — fires on high void rate vs average
- MPESA_FLAGGED: `app/finance/mpesa.py:157` — fires on unverified M-Pesa payments
- BANK_FLAGGED: `app/finance/bank.py:155` — fires on flagged bank entries
- BUDGET_EXCEEDED: DOES NOT EXIST — need to build

### RECEIPTS — EXISTS PER-TAB, NO CENTRAL SEARCH
- `app/pos/receipts.py:18` — GET /receipts/:tab_id returns full receipt data
- MISSING: list endpoint to search across all tabs by date/staff/amount

### HEALTH — SHALLOW
- `app/__init__.py:159` — returns {"status":"ok"}, no DB check

### MENU IMAGES — MISSING
- MenuItem model has no image/photo field

### STOCK PRE-CHECK — MISSING
- `app/pos/orders.py:95` checks is_active but NOT in_stock
- Sold-out items can be ordered (caught at consumption time, not order time)

### IDLE ANIMATION — MISSING
- Only kiosk has a 60s idle timer (redirects to welcome)
