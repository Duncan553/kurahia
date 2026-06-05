# Kurahia Backend — Project Context

> **Auto-loaded by Claude Code at session start. Read fully before any work in this repo.**

---

## 1. What this is

Resort management backend for a Kenyan hotel/resort (Waterfront Kurahia).
Solo-built by Wachira. **453 passing, 1 skipped (Phase B security review + Phase C-ext payment sockets complete).**

**Stack:** Python 3.12, Flask 3, Flask-SQLAlchemy 2.0, Flask-JWT-Extended, Flask-Migrate, Argon2 (passwords + PINs), Waitress (prod server). SQLite in dev, Postgres in prod. Tailscale for remote owner access.

**Shape:** Single Flask app exposing JSON API consumed by tablets/screens on hotel LAN + two installed phone apps (employee, owner) + CLI tools for the owner.

---

## 2. Current phase

**Phase C-ext: Payment sockets — COMPLETE.** Working tree clean. 453 passing, 1 skipped.

- ✅ Phase A: Backend chunks 1-10 (264 baseline tests, feature-complete)
- ✅ Phase B: Adversarial security review — all 6 categories done
  - 13 production bugs caught and fixed (+123 tests across test_security_category_1-6.py)
  - Cat 5 follow-up: audit-log atomicity sweep across 33 files (single-commit write pattern)
  - HUMAN_THREATS.md runbook written for owner (Cat 6)
- ✅ Phase C-1: Infrastructure-switch readiness (Postgres verified, secrets templated, cron + TLS documented)
- ✅ Phase C-ext: All three payment sockets built, tested, documented (21 commits, +66 tests)
  - M-Pesa Daraja: STK Push + C2B callback + routes (docs/MPESA_SANDBOX_TESTING.md)
  - Bank Transfer: SMS forwarder + Equity/KCB/Co-op API + routes (docs/BANK_SOCKET_ACTIVATION.md)
  - Card Gateway: Pesapal/DPO/Cellulant + IPN handler + routes (docs/CARD_GATEWAY_ACTIVATION.md)
- ⏳ Phase C-2: Real-data seeding (awaits owner answers via partner)
- ⏳ Phase C-3: Shadow week + go-live runbook
- ⏳ Phase D: Frontend (4-7 weeks estimated, parked until C-2 + C-3 complete)

---

## 3. Engineering invariants — NEVER violate

These rules are in effect across every file. If a proposed change breaks one, REJECT it and ask first.

1. **Money is `Decimal`, never `float`.** Quantities likewise. End-to-end.
2. **Live values are DERIVED from append-only records, not stored.**
   - Stock = SUM(StockMovement.change_amount)
   - Tab balance = SUM(charges) − SUM(payments)
   - Equipment.is_due_service = @property derived from last_service_utc
3. **Historical facts are FROZEN at write time, not editable.**
   - OrderItem.unit_price_snapshot
   - CashReconciliation.expected_amount
   - AuditLog rows
   - Booking.base_total
4. **Every write:** wrapped in a DB transaction + carries `idempotency_key` + writes an audit log entry.
5. **Every error response:** carries a plain-English `message` field for frontend display.
6. **Disable, never delete.** Every business entity has `is_active`. Hard deletes are prohibited.
7. **Kill switch on every protected endpoint.** Re-load user, re-check `is_active` and role on EVERY request. JWT alone is never trusted.
8. **All timestamps stored UTC, server-stamped.** Never trust client time.
9. **DB-level enforcement of every business rule that can be a constraint** (UNIQUE on idempotency keys, PK on cash_recon_payments.payment_id, CHECK on StockMovement.change_amount, FKs everywhere). Defense in depth.
10. **Configuration through data, not code.** Roles, departments, menu items, judge baselines, WiFi allow-list, watch-list flags — all DB-resident, owner-editable.

---

## 4. Codebase layout

```
kurahia/
├── app/
│   ├── __init__.py             create_app() factory
│   ├── extensions.py           db, jwt, migrate (init_app pattern)
│   ├── config.py               development / testing / production
│   ├── models/                 45+ SQLAlchemy models
│   ├── auth/                   login, refresh, PIN, account creation
│   ├── inventory/              items, counts, movements, purchases
│   ├── pos/                    menu, orders, kitchen/bar queues, payments
│   ├── finance/                cash, M-Pesa/bank/card reconciliation + dormant sockets, budgets
│   ├── hr/                     profiles, clock-in, shifts, leave, performance
│   ├── bookings/               resources, bookings, deposits, waivers
│   ├── gate/                   wristband issuance, reconciliation, forfeit
│   ├── events/                 events, assignments, allocations, alerts
│   ├── notifications/          inbox + dispatcher
│   ├── suggestions/            two-tier routing (MANAGEMENT vs OWNER_PRIVATE)
│   ├── conduct/                versioned rules + signing + compliance
│   ├── disputes/               dispute lifecycle (with is_owner_only)
│   ├── feedback/               guest feedback (wakes performance score)
│   ├── calendar_view/          dated entries + planning triggers
│   ├── dashboard/              10 owner aggregation endpoints
│   ├── equipment/              equipment + maintenance + safety
│   ├── services/               business logic per domain
│   ├── judge/engine.py         silent theft detection
│   ├── cli/                    flask CLI commands
│   └── utils/                  shared helpers
├── tests/                      453+ pytest tests
├── migrations/                 Alembic migration files
├── docs/
│   ├── SYSTEM_OVERVIEW.md          ← start here if new to the codebase
│   ├── MPESA_SANDBOX_TESTING.md
│   ├── BANK_SOCKET_ACTIVATION.md
│   └── CARD_GATEWAY_ACTIVATION.md
├── docs/SYSTEM_OVERVIEW.md        ← master doc, read before pattern changes
├── PAYMENTS_DESIGN.md             ← payment architecture + all three sockets
├── CLI_REFERENCE.md
├── DEPLOY.md
└── .env.example
```

---

## 5. The 15 cross-cutting patterns

When adding new code, follow the existing patterns. Each is documented in detail in §4 (patterns) of `docs/SYSTEM_OVERVIEW.md`.

1. App factory (create_app)
2. init_app decoupling for extensions
3. Argon2 for passwords + PINs (constant-time verify, never `==`)
4. JWT + per-request kill switch (re-check is_active and role)
5. Hash-chained audit log (prev_hash + entry_hash)
6. Append-only ledgers (stock movements, charges, payments, clock events, audit, conduct signatures, notifications, cash reconciliations, maintenance logs)
7. Derived state — stock level
8. Derived state — tab balance (same keystone, applied to money)
9. Snapshot vs derived — freeze history, derive live values
10. Idempotency keys (app check + DB UNIQUE = defense in depth)
11. SELECT FOR UPDATE for atomic counters (wristband numbering)
12. Join table as structural enforcement (cash_recon_payments.payment_id as PK)
13. State machines as declarative dicts (VALID_*_TRANSITIONS)
14. Socket / dormancy pattern (3 active, 3 dormant)
15. Query-level authorization (OWNER_PRIVATE rows STRUCTURALLY ABSENT for non-owners)

---

## 6. Dormant sockets — activate by setting env vars

Three payment sockets are fully implemented. They are dormant by default and activate
when their required env vars are set. See `docs/` for activation runbooks.

| Socket | File | Activation env var(s) | Runbook |
|---|---|---|---|
| M-Pesa Daraja | `app/finance/mpesa_daraja.py` | `MPESA_CONSUMER_KEY` + 4 others | docs/MPESA_SANDBOX_TESTING.md |
| Bank Transfer (SMS) | `app/finance/bank_transfer.py` | `BANK_SMS_WEBHOOK_SECRET` | docs/BANK_SOCKET_ACTIVATION.md |
| Bank Transfer (API) | `app/finance/bank_transfer.py` | `BANK_PROVIDER` + `BANK_API_KEY` | docs/BANK_SOCKET_ACTIVATION.md |
| Card Gateway | `app/finance/card_gateway.py` | `CARD_PROVIDER` + `CARD_API_KEY` + 2 others | docs/CARD_GATEWAY_ACTIVATION.md |

Diagnostic for each: `GET /finance/mpesa/status`, `/finance/bank/status`, `/finance/card/status`.
All return `{"configured": bool, "message": str}` — plain English on what's missing.

Two notification stubs remain (true "one function body" swaps when credentials arrive):

| Socket | File | Function | Needs |
|---|---|---|---|
| WhatsApp | `app/services/notifications/whatsapp.py` | `send_whatsapp` | Meta Business API + approved templates, OR Twilio / Africa's Talking |
| SMS | `app/services/notifications/sms.py` | `send_sms` | Africa's Talking (recommended for Kenya): username + API key + sender ID |

Both currently return `("UNCONFIGURED", "...")`. Activating each is one function body — no other code changes.

---

## 7. Test discipline

- All tests use pytest with the in-memory SQLite testing config
- Test files: `tests/test_<domain>.py`
- Security categories: `tests/test_security_category_<N>.py`
- Every new endpoint test verifies: 200 path + role check + idempotency + audit log written + plain-English error
- State-machine entities: every transition tested, every illegal transition rejected with plain-English message
- Run all tests before commit: `pytest`

---

## 8. Working with this codebase — rules

1. **Read `docs/SYSTEM_OVERVIEW.md` before proposing pattern changes.** It's the source of truth. Don't reinvent.
2. **Match existing patterns.** New endpoints get role check + idempotency + audit log + plain-English errors. New entities get is_active + UTC + Decimal-where-money.
3. **No deletes. No floats for money. No hardcoded role/department lists.** Adding these is a regression.
4. **One logical change per commit.** Descriptive message: e.g., `"Chunk N: short description"` or `"Security Category N: <attack name>"`.
5. **Migrations are mandatory for schema changes:** `flask db migrate -m "..."` then `flask db upgrade`.
6. **Don't run `pytest` or `git` for the user just to show output.** They can run it themselves. Save context budget for actual building.
7. **For sweeping changes, propose them first, then execute.** Don't run a long edit chain without confirmation.

---

## 9. How to communicate with Wachira

- **Big picture first**, then details. Always.
- **Dummy → engineer → where-in-code** when teaching a new concept.
- **Honest about the work, kind about him.** Brutal feedback on code; never on his ability.
- **Backend logic before any frontend.** Frontend is parked until Phase C-2 (data seeding) and Phase C-3 (shadow week) are complete.
- **Match his energy:** direct, alive, fast. No corporate fluff. No padding.
- **Capture tangents quickly, then steer back** to the main goal.
- **When stuck, explain WHY it broke** — root cause, not just the fix.
- **`LOCK IT` trigger:** when Wachira says this, produce a precise 6-part copy-paste build brief:
  1. Goal in one line
  2. Stack / tools
  3. Build steps in order (logic/backend before frontend)
  4. Decisions already baked in (no re-asking)
  5. What to skip for now
  6. The exact first step to run
  Tight and precise. No fluff.

---

## 10. Quick reference — common commands

```bash
# Run tests
pytest                                  # all 453+
pytest tests/test_pos.py -v             # one file, verbose
pytest tests/test_pos.py::test_xyz      # one test
pytest -x                               # stop on first failure

# DB
flask db migrate -m "..."               # new migration
flask db upgrade                        # apply pending migrations

# Health + ops
flask system status                     # quick health check
flask system backup                     # backup
flask audit verify-chain                # verify hash chain integrity
flask judge run-daily / run-weekly      # judge analysis
flask events deliver-due                # dispatch QUEUED notifications
flask gate close-day                    # EOD: forfeit unused band credits
flask bookings flag-no-shows            # daily no-show sweep

# Git
git log --oneline                       # commit history
git diff                                # uncommitted changes
git checkout <commit> -- .              # restore everything from a commit
```

Full CLI reference: `CLI_REFERENCE.md`.

---

*End of project context. Begin work.*
