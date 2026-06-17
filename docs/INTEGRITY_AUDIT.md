# Referential Integrity Audit

> Conducted 2026-06-17. Read-only audit of add/edit/remove propagation.

---

## Summary

| Entity | Add propagates? | Edit propagates? | Remove handled? | Stale-copy bugs |
|--------|----------------|-----------------|-----------------|-----------------|
| Departments | ✅ FK refs everywhere | ✅ Live joins | ✅ is_active guard on new assignments | **2 CRITICAL** hardcoded name checks |
| Menu items | ✅ | ✅ | ✅ is_active filter on orders/listing | None |
| Inventory items | ✅ | ✅ | ✅ is_active filter everywhere | 1 cosmetic (RecipeLine.unit copy) |
| Users/staff | ✅ | ✅ | ✅ kill switch on every request | None (AuditLog.actor is intentional) |
| Recipes | ✅ | ✅ deactivate+recreate | ✅ is_active filter | None |
| Budgets | ✅ | ✅ live spend derivation | ✅ is_active filter | None |
| Bookings | ✅ | ✅ | ✅ status filter excludes CANCELLED | None (base_total is intentional snapshot) |
| Pack size/category | ✅ | ✅ live computation | N/A | None |
| Roles | ✅ FK refs | ✅ | ✅ | None |

---

## CRITICAL Bugs (runtime logic coupled to hardcoded department names)

### 1. `pos/orders.py:53` — Kitchen/Bar staff order creation guard

```python
if actor.department and actor.department.name in ("Kitchen", "Bar") and actor.role.level < MANAGER_LEVEL:
```

**Risk:** If "Kitchen" department is renamed to "Main Kitchen", kitchen staff gain the ability to create customer orders (privilege escalation).

**Fix:** Check if user's department matches a prep-station department structurally, not by name string. Add `is_prep_station` boolean to Department model, or compare against PrepStation enum values.

### 2. `services/consumption.py:165` — No-recipe alert head chef lookup

```python
Department.name == "Kitchen",
```

**Risk:** If "Kitchen" is renamed, no-recipe alerts silently stop finding the head chef. Falls back to owner (not catastrophic, but degraded).

**Fix:** Use role level + department relationship, or structural flag.

---

## MINOR

### 3. `inventory/purchases.py:94` — Hardcoded "General" fallback

Display-only fallback for system-generated requests with no requester. Not a logic bug.

---

## ACCEPTABLE (intentional frozen snapshots per invariant #3)

| Frozen field | Location | Why acceptable |
|-------------|----------|----------------|
| OrderItem.unit_price_snapshot | order_item.py | Price locked at order time — historical fact |
| OrderItem.prep_station_snapshot | order_item.py | Routing locked at order time |
| Booking.base_total | booking.py | Price locked at booking creation |
| Charge.description | charge.py | Human-readable receipt text, append-only |
| AuditLog.actor | audit_log.py | Username string for tamper-evident chain |
| RecipeLine.unit | recipe_line.py | Cosmetic copy; math uses live pack_size |

## ACCEPTABLE (seed/CLI only, not runtime)

- `cli/seed.py` — hardcoded department list for initial seeding
- `cli/inventory.py` — hardcoded department names in seed tuples
- `cli/conduct.py`, `cli/pos.py` — "General" lookup for seed data

---

## Clean Patterns Confirmed

- All models use UUID FK references, not name copies
- All runtime consumers read names via SQLAlchemy relationship traversal (live joins)
- Kill switch re-checks is_active on every request
- Budget spend derived live from purchase movements
- Stock levels derived live from SUM(StockMovement.change_amount)
- pack_size changes propagate because StockMovements store computed amounts
- Recipe edits propagate because consumers filter is_active=True
- Booking cancellation excluded from dashboards via status filters
