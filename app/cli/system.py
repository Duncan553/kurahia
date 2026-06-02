"""
cli/system.py — Operational tooling.

flask system status         — health check + pending counts
flask system backup         — database backup (SQLite: file copy; Postgres: pg_dump)
flask audit verify-chain    — walk the audit-log hash chain
flask judge run-weekly      — fire the weekly ratio analysis
flask judge run-daily       — fire the daily spoilage/watchlist scan
flask system check-alerts   — sweep for new actionable conditions, create JudgeAlerts
"""
import os
import shutil
import click
from datetime import datetime, timezone
from flask import Blueprint
from app.extensions import db

system_cli_bp = Blueprint("system_cli", __name__)
audit_cli_bp  = Blueprint("audit_cli",  __name__)
judge_cli_bp  = Blueprint("judge_cli",  __name__)


@system_cli_bp.cli.command("status")
def system_status():
    """Quick health check: DB, pending notifications, unacked alerts."""
    from app.models.notification import Notification, NotificationStatus
    from app.models.judge_alert import JudgeAlert, AlertStatus

    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = "OK"
    except Exception as e:
        db_ok = f"ERROR: {e}"

    pending_notifs = db.session.query(Notification).filter_by(
        status=NotificationStatus.QUEUED.value
    ).count()
    open_alerts = db.session.query(JudgeAlert).filter_by(
        status=AlertStatus.OPEN.value
    ).count()

    click.echo(f"Database:             {db_ok}")
    click.echo(f"Pending notifications: {pending_notifs}")
    click.echo(f"Open alerts:           {open_alerts}")
    click.echo(f"Timestamp (UTC):       {datetime.now(timezone.utc).isoformat()}")


@system_cli_bp.cli.command("backup")
@click.option("--dest", default="./backups", help="Destination directory for backup files")
def system_backup(dest):
    """Backup the database. SQLite: copies the file. Postgres: runs pg_dump."""
    from flask import current_app
    os.makedirs(dest, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if "sqlite" in db_url:
        # Extract file path from sqlite:///path/to/file.db
        path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
        if not os.path.isabs(path):
            path = os.path.join(current_app.instance_path, path.lstrip("/"))
        dest_file = os.path.join(dest, f"backup_{ts}.db")
        try:
            shutil.copy2(path, dest_file)
            click.echo(f"SQLite backup saved to {dest_file}")
        except Exception as e:
            click.echo(f"Backup failed: {e}", err=True)
    else:
        dest_file = os.path.join(dest, f"backup_{ts}.sql")
        ret = os.system(f'pg_dump "{db_url}" > "{dest_file}"')
        if ret == 0:
            click.echo(f"Postgres backup saved to {dest_file}")
        else:
            click.echo("pg_dump failed — check DATABASE_URL and pg_dump availability.", err=True)


@system_cli_bp.cli.command("check-alerts")
def check_alerts():
    """
    Sweep for actionable conditions and create JudgeAlerts for any found.
    Idempotent — skips alert types already OPEN for the same context.
    """
    from app.models.inventory_item import InventoryItem
    from app.models.judge_alert import JudgeAlert, AlertSeverity, AlertStatus
    from app.models.booking import Booking, BookingStatus
    from app.models.bookable_resource import ResourceType
    from app.models.waiver import Waiver, WaiverActivityType
    from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus
    from app.models.conduct_rule import ConductRule
    from app.models.conduct_signature import ConductSignature
    from app.models.employee_profile import EmployeeProfile
    from app.services.stock import get_current_stock
    from app.services.judge_alerts import fire_alert_if_absent
    from decimal import Decimal
    from datetime import timedelta

    created = 0
    now = datetime.now(timezone.utc)

    def _fire(alert_type, description_key, severity, description):
        _, fired = fire_alert_if_absent(
            alert_type=alert_type,
            description_key=description_key,
            item_id=None, severity=severity.value,
            description=description, period_start=now, period_end=now,
        )
        return 1 if fired else 0

    # 1. Low stock items
    for item in db.session.query(InventoryItem).filter_by(is_active=True).all():
        stock = get_current_stock(item.id)
        if stock <= Decimal(str(item.reorder_level)):
            created += _fire("LOW_STOCK", item.name, AlertSeverity.MEDIUM,
                f"{item.name}: current stock {stock}{item.unit} at or below "
                f"reorder level ({item.reorder_level}{item.unit}). Reorder now.")

    # 2. Water-activity bookings tomorrow without waivers
    tomorrow_start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    tomorrow_end   = tomorrow_start + timedelta(days=1)
    water_bookings = db.session.query(Booking).filter(
        Booking.check_in_planned_utc >= tomorrow_start,
        Booking.check_in_planned_utc < tomorrow_end,
        Booking.status.in_([BookingStatus.CONFIRMED.value, BookingStatus.CHECKED_IN.value]),
    ).all()
    for b in water_bookings:
        if b.resource and b.resource.resource_type == ResourceType.WATER_ACTIVITY.value:
            has_w = db.session.query(Waiver).filter_by(
                booking_id=b.id, activity_type=WaiverActivityType.WATER_ACTIVITY.value,
                is_active=True,
            ).first()
            if not has_w:
                created += _fire("WAIVER_MISSING", b.guest_name, AlertSeverity.HIGH,
                    f"{b.guest_name} has a water-activity booking tomorrow "
                    f"({b.resource.name}) but no signed waiver. Collect waiver before the session.")

    # 3. Unsigned conduct rules
    active_rules = db.session.query(ConductRule).filter_by(is_active=True).all()
    all_profiles = db.session.query(EmployeeProfile).filter_by(is_active=True).all()
    for rule in active_rules:
        signed_ids = {s.employee_id for s in db.session.query(ConductSignature).filter_by(
            conduct_rule_id=rule.id).all()}
        unsigned_count = sum(1 for p in all_profiles if p.id not in signed_ids)
        if unsigned_count > 0:
            created += _fire("CONDUCT_UNSIGNED", rule.rule_key, AlertSeverity.LOW,
                f"{unsigned_count} employee(s) have not signed the '{rule.title}' "
                f"conduct rule (v{rule.version}). Follow up on compliance.")

    # 4. M-Pesa unmatched payments
    try:
        unmatched = db.session.query(PaymentReconciliation).filter_by(
            status=PaymentReconciliationStatus.UNMATCHED.value
        ).count()
        if unmatched > 3:
            created += _fire("MPESA_UNMATCHED", "M-Pesa", AlertSeverity.MEDIUM,
                f"{unmatched} M-Pesa payments are unmatched. "
                "Review the M-Pesa reconciliation report.")
    except Exception:
        pass

    db.session.commit()
    click.echo(f"Created {created} new alert(s).")


# ── Audit ──────────────────────────────────────────────────────────────────────

@audit_cli_bp.cli.command("verify-chain")
def verify_chain():
    """Walk the audit log hash chain and report integrity status."""
    from app.models.audit_log import AuditLog
    ok, message = AuditLog.verify_chain()
    if ok:
        total = db.session.query(AuditLog).count()
        click.echo(f"Audit chain OK — {total} entries verified.")
    else:
        click.echo(f"AUDIT CHAIN BROKEN: {message}", err=True)
        raise SystemExit(1)


# ── Judge ──────────────────────────────────────────────────────────────────────

@judge_cli_bp.cli.command("run-weekly")
@click.option("--days", default=7, show_default=True, help="Period length in days")
def run_weekly(days):
    """Fire the judge's weekly consumption-to-revenue ratio analysis."""
    from app.judge.engine import run_weekly
    from datetime import timedelta
    now  = datetime.now(timezone.utc)
    end  = now
    start = now - timedelta(days=days)
    alerts = run_weekly(start, end)
    click.echo(f"Weekly judge: {alerts} alert(s) fired for the last {days} days.")


@judge_cli_bp.cli.command("run-daily")
def run_daily():
    """Fire the judge's daily spoilage/watch-list check."""
    from app.judge.engine import run_daily
    alerts = run_daily(datetime.now(timezone.utc))
    click.echo(f"Daily judge: {alerts} alert(s) fired.")
