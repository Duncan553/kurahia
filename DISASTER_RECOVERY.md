# Disaster Recovery Runbook — Kurahia Backend

> **Status:** Verified on 2026-06-01 against SQLite dev DB.
> Production environment uses Postgres — adapt `restore` steps to `pg_restore` where noted.

---

## 1. Verified Backup / Restore Procedure

### 5.5 — Backup/restore round-trip

**Backup (daily cron, runs at 03:30)**
```bash
flask system_cli backup --dest /backups/kurahia
```
- SQLite: copies the DB file via `shutil.copy2`
- Postgres: runs `pg_dump "{DATABASE_URL}" > dest_file`
- Output: `backup_YYYYMMDD_HHMMSS.db` (SQLite) or `.sql` (Postgres)

**Verification after backup**
```bash
# SQLite:
sqlite3 /backups/kurahia/backup_YYYYMMDD_HHMMSS.db "PRAGMA integrity_check"
# → must return: ok

sqlite3 /backups/kurahia/backup_YYYYMMDD_HHMMSS.db ".tables" | wc -w
# → must return: 52 (all tables present)

sqlite3 /backups/kurahia/backup_YYYYMMDD_HHMMSS.db "SELECT version_num FROM alembic_version"
# → must match current migration head
```

**Round-trip restore (SQLite dev environment)**

Verified 2026-06-01:
```bash
# 1. Record current row counts
sqlite3 instance/kurahia_dev.db "SELECT COUNT(*) FROM audit_logs"
sqlite3 instance/kurahia_dev.db "SELECT COUNT(*) FROM payments"
sqlite3 instance/kurahia_dev.db "SELECT COUNT(*) FROM bookings"

# 2. Back up
flask system_cli backup --dest /tmp/restore_test

# 3. Simulate loss — rename current DB
mv instance/kurahia_dev.db instance/kurahia_dev.db.broken

# 4. Restore
cp /tmp/restore_test/backup_YYYYMMDD_HHMMSS.db instance/kurahia_dev.db

# 5. Verify counts match
sqlite3 instance/kurahia_dev.db "SELECT COUNT(*) FROM audit_logs"
sqlite3 instance/kurahia_dev.db "SELECT COUNT(*) FROM payments"
sqlite3 instance/kurahia_dev.db "SELECT COUNT(*) FROM bookings"

# 6. Verify audit chain
flask audit_cli verify-chain
# → must return: Audit chain OK

# 7. Run full test suite
pytest
# → must match original count
```

**Round-trip restore (Postgres production)**
```bash
# 1. Stop the app server
systemctl stop kurahia

# 2. Drop and recreate the DB (DESTRUCTIVE — confirm backup is good first)
psql -U postgres -c "DROP DATABASE kurahia_prod;"
psql -U postgres -c "CREATE DATABASE kurahia_prod;"

# 3. Restore
psql -U postgres kurahia_prod < /backups/kurahia/backup_YYYYMMDD_HHMMSS.sql

# 4. Verify
flask db current          # should match backup-time migration head
flask audit_cli verify-chain
pytest

# 5. Restart
systemctl start kurahia
```

**Observed result (2026-06-01):**
- Backup file: 708 KB, 52 tables, `PRAGMA integrity_check = ok`
- Schema migration version present: `8a0894874ea2`
- Round-trip: counts matched on restore

---

## 2. File-Write Atomicity Notes (Attack 5.6)

### All file-write paths in the application

| Path | File written? | Atomic? |
|------|--------------|---------|
| `POST /inventory/purchases` | No. `receipt_photo_path` is a **DB string** (a path the caller already uploaded elsewhere). The app stores the string, not the file. | N/A — no file written by the app |
| `flask system_cli backup` | Yes. `shutil.copy2(source, dest)` writes a DB copy to disk. | Atomic at the OS level (copy2 is not transactional). If the server dies mid-copy, a partial `.db` file may exist. Run `PRAGMA integrity_check` on every backup before trusting it. |
| `app.logger.exception(...)` | Writes to stderr/stdout only (see Section 3). No file. | N/A |

**Conclusion:** The only file the app writes is the backup copy. No receipt images, no profile photos, no log files are written to disk by the application layer. All media paths are stored as strings pointing to files that are assumed to already exist (uploaded out-of-band). There is no file-write path that could leave partial state in the DB.

**Disk-full scenario:** If the disk fills during backup, `shutil.copy2` raises `OSError: No space left on device`. The backup command catches this and prints an error to stderr — the DB itself is never touched. The app continues running normally. Cron should send an alert if `flask system_cli backup` exits non-zero.

---

## 3. Log Volume and Rotation (Attack 5.7)

### Current logging configuration

No `FileHandler`, `RotatingFileHandler`, or `basicConfig` calls exist in the application code. Flask's default logging is used, which writes to **stderr only** (captured by the process supervisor or systemd journal).

```bash
# In production — logs go to systemd journal:
journalctl -u kurahia -f

# Or if running directly:
waitress-serve ... 2>/var/log/kurahia/app.log
```

### Log explosion risk

The only application-level log line is `app.logger.exception("Unhandled exception")` in the generic 500 handler. Under a hostile script hammering a failing endpoint:
- Each 500 writes one stack trace to stderr (~1 KB)
- 100 req/sec = ~100 KB/sec = ~360 MB/hour
- systemd journal has a default rate limit (`RateLimitBurst=1000, RateLimitIntervalSec=30`) that throttles this

**Recommended production setup:**
```ini
# /etc/systemd/system/kurahia.service
[Service]
StandardOutput=journal
StandardError=journal
# systemd journal rotation handles the rest
```

If writing to a file, use `logrotate`:
```
/var/log/kurahia/app.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        systemctl reload kurahia
    endscript
}
```

---

## 4. Known Operational Gaps (surfaced by Cat 5 tests)

These are **reported only** — not yet fixed. Discuss before patching.

### GAP-5.1: Booking commit and audit log are in separate transactions

`create_booking()` commits the `Booking` row, then calls `AuditLog.log()` in a
second `db.session.commit()`. If a fault occurs between the two commits (disk full,
server crash), the booking persists without an audit trail entry.

**Impact:** Booking exists, is charged, is visible — but has no audit record.
The hash chain is intact (no tamper), but the chain has a gap for this event.

**Same pattern exists in:** all routes that do two-commit write+audit (payments,
orders, reconciliations). The entire codebase follows this pattern.

**Mitigation options:**
A) Combine booking + audit log into a single `db.session.commit()` call.
B) Accept the gap — the booking itself is the source of truth; audit loss is
   detective (you can reconstruct from booking data), not destructive.

### GAP-5.2a: `judge run-daily` not idempotent

Calling `run_daily()` twice with the same data creates duplicate `JudgeAlert` rows
for the same spoilage event. The `check_alerts` command has an `_open_exists()`
guard; `run_daily` does not.

**Fix:** Add `if not _open_exists("SPOILAGE_SPIKE", item.name): _fire_alert(...)` in `run_daily`.

### GAP-5.2b: `events flag-incomplete` not idempotent

Same gap: no deduplication guard before creating `EVENT_NOT_CLOSED` alerts.
Double cron run → double alerts for each overdue event.

**Fix:** Add `if not _open_exists("EVENT_NOT_CLOSED", ev.id): ...` in `flag_incomplete`.

---

## 5. Disaster Recovery Runbook

### Scenario A: Server process crashes (Waitress dies)

```bash
# Check what killed it
journalctl -u kurahia --since "-1h" | tail -50

# Restart
systemctl restart kurahia

# Verify DB integrity
flask audit_cli verify-chain
flask system_cli status
```
No data loss — SQLite/Postgres is ACID. Any in-flight requests were rolled back.

---

### Scenario B: Power loss / hard reboot mid-transaction

SQLite WAL mode and Postgres both recover automatically on next startup.

```bash
# After reboot — check for corruption
sqlite3 instance/kurahia_dev.db "PRAGMA integrity_check"
# → should return: ok

# If corruption detected:
# 1. Stop app
# 2. Restore from last backup (Section 1)
# 3. Accept data loss from the period since last backup
```

---

### Scenario C: Database file corrupted or deleted

```bash
# 1. Stop app immediately
systemctl stop kurahia

# 2. Find most recent backup
ls -lt /backups/kurahia/ | head -5

# 3. Restore (see Section 1 for full procedure)
cp /backups/kurahia/backup_YYYYMMDD_HHMMSS.db instance/kurahia_dev.db

# 4. Verify
sqlite3 instance/kurahia_dev.db "PRAGMA integrity_check"
flask audit_cli verify-chain

# 5. Restart
systemctl start kurahia

# Data loss: everything since the last successful backup (max 24 hours).
# Check cron log to confirm last backup time.
```

---

### Scenario D: Disk fills

```bash
# 1. Identify what's filling the disk
df -h
du -sh /var/log/* /backups/* /tmp/*

# 2. If logs are the culprit:
journalctl --vacuum-size=500M

# 3. If old backups are the culprit:
ls -lt /backups/kurahia/ | tail -n +15 | awk '{print $9}' | xargs rm
# (keeps 14 most recent backups)

# 4. The app DB itself will stop accepting writes when the disk is full.
#    Flask will return 500 for any write request.
#    The DB is not corrupted — reads still work.
#    No manual repair needed — just free space and the app resumes.
```

---

### Scenario E: Network partition (Tailscale drops, owner loses remote access)

```bash
# On the server itself:
flask system_cli status    # confirms app is alive
flask audit_cli verify-chain

# Restore Tailscale:
sudo tailscale up

# No data impact — the app runs on the LAN regardless of Tailscale state.
```

---

### Scenario F: Clock skew on server

All timestamps are stored in UTC using the server's clock. Client clocks are
never trusted.

```bash
# Check server time drift
timedatectl status
# NTP synced: yes  ← required

# If drifted:
timedatectl set-ntp true
chronyc tracking   # drift should be < 100ms
```

Impact if clock drifts: `locked_until` in auth may extend or shorten lockout windows.
`created_at_utc` timestamps on records may be slightly off. Audit chain is not affected
(chain is by hash, not time order). No data corruption.

---

*End of runbook. For Cat 5 test results, see `tests/test_security_category_5.py`.*
