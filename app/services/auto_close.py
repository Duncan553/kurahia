"""
auto_close.py — Scheduled job at business-day cutoff.

Checks the just-ended business day:
  ALL GREEN → auto-close (same freeze as manual PeriodClose) + quiet owner notification
  ANY FAIL  → do NOT close, alert owner naming the problem

Conditions for "all green":
  1. Every CASH payment in the period is reconciled (appears in cash_recon_payments)
  2. No CashReconciliation with status SHORT
  3. No PaymentReconciliation with status FLAGGED
  4. No open disputes (status OPEN or UNDER_REVIEW)
  5. No open judge alerts (status OPEN, severity HIGH+)

Manual close always available via POST /finance/close-period regardless of this.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from app.extensions import db
from app.models.payment import Payment, PaymentMethod
from app.models.cash_reconciliation import CashReconciliation, ReconciliationStatus, cash_recon_payments
from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus
from app.models.dispute import Dispute, DisputeStatus
from app.models.judge_alert import JudgeAlert, AlertStatus, AlertSeverity
from app.models.period_close import PeriodClose, PeriodCloseStatus
from app.models.notification import Notification, NotificationStatus, NotificationReferenceType
from app.models.user import User
from app.models.role import Role
from app.models.audit_log import AuditLog


def check_day_health(day_start: datetime, day_end: datetime) -> list[str]:
    """Return list of problems. Empty list = all green."""
    problems = []

    # 1. Unreconciled CASH payments
    reconciled_ids = {row.payment_id for row in db.session.query(cash_recon_payments).all()}
    unreconciled = db.session.query(Payment).filter(
        Payment.method == PaymentMethod.CASH.value,
        Payment.created_at_utc >= day_start,
        Payment.created_at_utc < day_end,
        ~Payment.id.in_(reconciled_ids) if reconciled_ids else Payment.id.isnot(None),
    ).count()
    if unreconciled > 0:
        problems.append(f"{unreconciled} cash payment{'s' if unreconciled != 1 else ''} not reconciled")

    # 2. Cash shortfalls
    shortfalls = db.session.query(CashReconciliation).filter(
        CashReconciliation.created_at_utc >= day_start,
        CashReconciliation.created_at_utc < day_end,
        CashReconciliation.status == ReconciliationStatus.SHORT.value,
    ).all()
    for s in shortfalls:
        problems.append(f"Cash shortfall KSh {abs(s.difference)} ({s.cashier.username if s.cashier else '?'})")

    # 3. Flagged payment reconciliations
    flagged = db.session.query(PaymentReconciliation).filter(
        PaymentReconciliation.created_at_utc >= day_start,
        PaymentReconciliation.created_at_utc < day_end,
        PaymentReconciliation.status == PaymentReconciliationStatus.FLAGGED.value,
    ).count()
    if flagged > 0:
        problems.append(f"{flagged} flagged payment reconciliation{'s' if flagged != 1 else ''}")

    # 4. Open disputes
    open_disputes = db.session.query(Dispute).filter(
        Dispute.status.in_([DisputeStatus.OPEN.value, DisputeStatus.UNDER_REVIEW.value]),
    ).count()
    if open_disputes > 0:
        problems.append(f"{open_disputes} open dispute{'s' if open_disputes != 1 else ''}")

    # 5. Open HIGH+ judge alerts
    high_alerts = db.session.query(JudgeAlert).filter(
        JudgeAlert.status == AlertStatus.OPEN.value,
        JudgeAlert.severity.in_([AlertSeverity.HIGH.value]),
    ).count()
    if high_alerts > 0:
        problems.append(f"{high_alerts} unresolved HIGH judge alert{'s' if high_alerts != 1 else ''}")

    return problems


def _get_owner() -> User | None:
    return db.session.query(User).join(User.role).filter(
        Role.level >= 10, User.is_active == True
    ).first()


def _notify_owner(subject: str, body: str):
    owner = _get_owner()
    if not owner:
        return
    db.session.add(Notification(
        recipient_user_id=owner.id,
        reference_type=NotificationReferenceType.GENERAL.value,
        subject=subject,
        body=body,
        status=NotificationStatus.QUEUED.value,
        scheduled_for_utc=datetime.now(timezone.utc),
        idempotency_key=str(uuid.uuid4()),
    ))


def _day_revenue(day_start: datetime, day_end: datetime) -> Decimal:
    from sqlalchemy import func
    result = db.session.query(func.sum(Payment.amount)).filter(
        Payment.created_at_utc >= day_start,
        Payment.created_at_utc < day_end,
    ).scalar()
    return Decimal(str(result)) if result else Decimal("0")


def auto_close_day(day_start: datetime, day_end: datetime) -> tuple[bool, list[str]]:
    """
    Check health + auto-close if clean. Returns (closed, problems).
    """
    already = db.session.query(PeriodClose).filter(
        PeriodClose.period_start_utc >= day_start,
        PeriodClose.period_start_utc < day_end,
    ).first()
    if already:
        return True, []

    problems = check_day_health(day_start, day_end)

    if problems:
        _notify_owner(
            "Day not auto-closed — needs attention",
            "The following issues prevented auto-close:\n• " + "\n• ".join(problems),
        )
        AuditLog.log(actor="system", action="autoclose.held",
                     details="; ".join(problems))
        db.session.commit()
        return False, problems

    revenue = _day_revenue(day_start, day_end)

    # Auto-close: expected cash = sum of all cash recons in period
    from sqlalchemy import func
    expected = db.session.query(func.sum(CashReconciliation.actual_amount)).filter(
        CashReconciliation.created_at_utc >= day_start,
        CashReconciliation.created_at_utc < day_end,
    ).scalar() or Decimal("0")

    with db.session.begin_nested():
        pc = PeriodClose(
            period_start_utc=day_start,
            period_end_utc=day_end,
            closed_by_id=(_get_owner() or db.session.query(User).first()).id,
            safe_count=expected,
            expected_total_cash=expected,
            difference=Decimal("0"),
            status=PeriodCloseStatus.BALANCED.value,
            notes="Auto-closed (all green)",
            idempotency_key=f"autoclose-{day_start.date().isoformat()}",
        )
        db.session.add(pc)

    _notify_owner(
        f"Day closed · KSh {revenue:,.0f} revenue · all reconciled",
        f"Business day {day_start.date()} auto-closed. Revenue: KSh {revenue:,.0f}. "
        f"All cash reconciled, no disputes, no flagged payments.",
    )
    AuditLog.log(actor="system", action="autoclose.success",
                 target=str(day_start.date()), details=f"revenue={revenue}")
    db.session.commit()
    return True, []
