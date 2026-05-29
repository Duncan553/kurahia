# CLI Reference — Kurahia Resort Backend

Every `flask <group> <command>` listed below. Run from the project root with the virtualenv active.

## Setup
```bash
flask seed                    # seed roles, departments, users, menu items
flask db upgrade              # apply all pending migrations
```

## Inventory
```bash
flask inventory seed-items    # seed sample inventory items
flask inventory seed-movements # seed sample stock movements
```

## POS
```bash
flask pos seed-menu           # seed full menu
```

## Finance
```bash
flask finance seed-budgets    # seed monthly department budgets
```

## HR
```bash
flask hr seed-employees       # seed sample employee profiles + shifts
```

## Bookings
```bash
flask bookings seed-resources # seed villas, event field, water activities
flask bookings seed-sample    # sample bookings (past/present/future)
flask bookings flag-no-shows  # sweep past-check-in bookings → NO_SHOW
flask bookings release-holds --hours 24  # auto-cancel expired HELD bookings
```

## Gate
```bash
flask gate close-day [--date YYYY-MM-DD] [--actor username]
                              # EOD sweep: forfeit ACTIVE bands, run gate judge signals
flask gate seed-bands [--count 3]  # seed sample bands for today (dev only)
```

## Events
```bash
flask events seed-types       # seed default event types (WEDDING, CORPORATE_DAY, ...)
flask events seed-sample      # sample event with assignment + allocation
flask events deliver-due      # dispatch all QUEUED notifications past their scheduled time
flask events flag-incomplete  # flag IN_PROGRESS events past their end time
```

## Conduct / Calendar / Feedback
```bash
flask conduct seed-rules      # seed 8-point default code of conduct
flask calendar seed-kenya-holidays  # seed Kenyan public holidays (next 12 months)
flask feedback seed-sample    # seed sample guest feedback
```

## Judge (Silent Variance Brain)
```bash
flask judge run-weekly [--days 7]  # consumption-to-revenue ratio analysis
flask judge run-daily              # spoilage spike + watch-list check
```

## System
```bash
flask system status           # DB health, pending notifications, open alerts
flask system backup [--dest ./backups]  # SQLite copy or pg_dump
flask system check-alerts     # sweep actionable conditions → create JudgeAlerts
flask audit verify-chain      # walk audit-log hash chain, assert integrity
```
