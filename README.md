# Kurahia Resort Management Suite

A high-integrity, full-stack operational ecosystem designed to manage the end-to-end lifecycle of a boutique resort. 

### Why this project?
Kurahia addresses specific operational frictions in hospitality: data fragmentation, inventory leakage, and financial reconciliation errors. Built for scale and auditability, it provides management with real-time visibility from the front desk to the kitchen.

---

## Architecture & Modules
| Chunk | Focus | Functionality |
|-------|-------|-------------|
| 1 | Foundation | Auth, RBAC, Departments, User Roles |
| 2 | Inventory | Lifecycle Tracking, Stock Counts, Purchases |
| 3 | POS | Menu, Tab Management, Order Processing |
| 4 | Finance | M-Pesa Integration, Cash Recon, Analytics |
| 5 | HR | Profiles, Shifts, Clock-in/out, Performance |
| 6 | Bookings | Villa Management, Deposits, Check-in/out |
| 7 | Gate | Wristbands, Entry Credit, BAND Tabs |
| 8 | Events | Alert Cascade, Notifications, Suggestions |
| 9 | Conduct | Dispute Resolution, Feedback, Calendar |
| 10 | Dashboard | Owner Aggregations, Equipment Hardening |

---

## Technical Rigor & Design Principles
* **Data Integrity:** Append-only model (no hard deletes; corrections = new rows).
* **Financial Precision:** Strict `Decimal` usage (no floats in money or stock domains).
* **Security:** Adversarial-tested backend with structural authorization (Owner-private data is isolated from manager queries).
* **Auditability:** Hash-chained audit logs; verify integrity via `flask audit verify-chain`.
* **Scalability:** Modular architecture with dormant service hooks for M-Pesa Daraja, WhatsApp, and SMS gateways.

---

## Getting Started (Dev)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # Edit your secrets
flask db upgrade
flask seed
flask run
