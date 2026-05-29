# Kurahia Resort — Backend API

Flask/SQLAlchemy REST API for a boutique resort. 10 chunks, production-ready.

## Quick start (dev)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit SECRET_KEY + JWT_SECRET_KEY
flask db upgrade
flask seed
flask run
```

Tests:
```bash
pytest                        # 264 tests, ~7 min
pytest tests/test_pos.py -v   # run a specific chunk
```

## Architecture

| Chunk | What it does |
|-------|-------------|
| 1 | Foundation: users, roles, departments, auth |
| 2 | Inventory: items, movements, stock counts, purchases |
| 3 | POS: menu, tabs, orders, charges, payments |
| 4 | Finance: cash recon, M-Pesa, budgets, analytics |
| 5 | HR: profiles, shifts, clock-in, leave, performance |
| 6 | Bookings: villas, deposits, waivers, check-in/out |
| 7 | Gate: wristbands, entry credit, BAND tabs |
| 8 | Events: alert cascade, notifications, suggestions |
| 9 | Conduct: signing, disputes, feedback, calendar |
| 10 | Dashboard: owner aggregations, equipment, hardening |

## Dormant sockets (ready to activate)

- **M-Pesa Daraja**: `app/finance/mpesa.py` — replace one function body
- **WhatsApp gateway**: `app/services/notifications/whatsapp.py` — replace one function body
- **SMS gateway**: `app/services/notifications/sms.py` — replace one function body

## Key design principles

- Append-only: no deletes; corrections = new rows
- Decimal everywhere: no floats in money or stock domains
- State machines enforced at the data layer on every lifecycle model
- Structural authorization: OWNER_PRIVATE rows don't exist in manager queries
- Audit log is hash-chained; verify with `flask audit verify-chain`

## Production checklist

See `DEPLOY.md`.
