"""
dashboard/core.py — Owner-facing aggregation layer.
All endpoints are owner-only (role.level >= 10). Pure reads — no mutations here.
Each endpoint maps to one screen in the owner dashboard blueprint.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from sqlalchemy import func
from app.extensions import db
from app.models.user import User

dashboard_bp = Blueprint("dashboard_core", __name__, url_prefix="/dashboard")

OWNER_LEVEL   = 10
MANAGER_LEVEL = 5


def _require_owner(actor: User):
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Owner access required for dashboard."}), 403
    return None


def _period_bounds(period: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if period == "week":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


# ── Overview ──────────────────────────────────────────────────────────────────

@dashboard_bp.get("/overview")
@require_active_user
def overview():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    period = request.args.get("period", "today")
    period_start, period_end = _period_bounds(period)

    from app.models.payment import Payment, PaymentMethod
    from app.models.tab import Tab, TabType
    from app.models.booking import Booking, BookingStatus
    from app.models.employee_profile import EmployeeProfile
    from app.models.clock_event import ClockEvent, ClockEventType
    from app.models.shift import Shift, ShiftStatus
    from app.models.inventory_item import InventoryItem
    from app.models.judge_alert import JudgeAlert, AlertStatus
    from app.models.calendar_entry import CalendarEntry
    from app.services.stock import get_current_stock

    # Revenue by tab type and by method
    rev_rows = db.session.query(
        Tab.tab_type,
        Payment.method,
        func.sum(Payment.amount).label("total"),
    ).join(Payment, Payment.tab_id == Tab.id).filter(
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc <= period_end,
    ).group_by(Tab.tab_type, Payment.method).all()

    revenue_by_type = {}
    revenue_by_method = {}
    total_revenue = Decimal("0")
    for row in rev_rows:
        t, m, amt = row.tab_type, row.method, Decimal(str(row.total))
        revenue_by_type[t] = str(Decimal(revenue_by_type.get(t, "0")) + amt)
        revenue_by_method[m] = str(Decimal(revenue_by_method.get(m, "0")) + amt)
        total_revenue += amt

    # Staff on duty (last ClockEvent = CLOCK_IN within 16h)
    sixteen_h_ago = datetime.now(timezone.utc) - timedelta(hours=16)
    all_profiles = db.session.query(EmployeeProfile).filter_by(is_active=True).all()
    on_duty = []
    for p in all_profiles:
        last = db.session.query(ClockEvent).filter_by(employee_id=p.id).order_by(
            ClockEvent.occurred_at_utc.desc()
        ).first()
        if last and last.event_type == ClockEventType.CLOCK_IN.value:
            occ = last.occurred_at_utc.replace(tzinfo=timezone.utc) if last.occurred_at_utc.tzinfo is None else last.occurred_at_utc
            if occ >= sixteen_h_ago:
                on_duty.append(p.full_name)

    # Active bookings
    active_bookings = db.session.query(Booking).filter_by(
        status=BookingStatus.CHECKED_IN.value
    ).count()

    # Today's arrivals + departures
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end   = today_start + timedelta(days=1)
    arrivals = db.session.query(Booking).filter(
        Booking.check_in_planned_utc >= today_start,
        Booking.check_in_planned_utc < today_end,
        Booking.status.in_([BookingStatus.CONFIRMED.value, BookingStatus.HELD.value]),
    ).count()
    departures = db.session.query(Booking).filter(
        Booking.check_out_planned_utc >= today_start,
        Booking.check_out_planned_utc < today_end,
        Booking.status == BookingStatus.CHECKED_IN.value,
    ).count()

    # Inventory alerts (items at or below reorder level)
    items = db.session.query(InventoryItem).filter_by(is_active=True).all()
    low_stock = sum(1 for i in items if get_current_stock(i.id) <= Decimal(str(i.reorder_level)))

    # Top 3 open judge alerts
    alerts = db.session.query(JudgeAlert).filter_by(
        status=AlertStatus.OPEN.value
    ).order_by(JudgeAlert.created_at.desc()).limit(3).all()
    top_alerts = [{"id": a.id, "type": a.alert_type, "severity": a.severity,
                   "description": a.description[:120]} for a in alerts]

    # Week-ahead calendar
    week_end = today_start + timedelta(days=7)
    cal = db.session.query(CalendarEntry).filter(
        CalendarEntry.date_start_utc >= today_start,
        CalendarEntry.date_start_utc <= week_end,
        CalendarEntry.is_active == True,
    ).order_by(CalendarEntry.date_start_utc).all()
    week_calendar = [{"title": c.title, "date": c.date_start_utc.isoformat(),
                      "is_peak": c.is_peak, "type": c.entry_type} for c in cal]

    return jsonify({
        "period": period,
        "revenue": {
            "total": str(total_revenue),
            "by_tab_type": revenue_by_type,
            "by_method":   revenue_by_method,
        },
        "staff": {
            "on_duty": len(on_duty),
            "on_duty_names": on_duty,
        },
        "bookings": {
            "active": active_bookings,
            "arrivals_today": arrivals,
            "departures_today": departures,
        },
        "inventory_alerts": low_stock,
        "top_alerts": top_alerts,
        "week_calendar": week_calendar,
    }), 200


# ── Inventory ─────────────────────────────────────────────────────────────────

@dashboard_bp.get("/inventory")
@require_active_user
def inventory_view():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    from app.models.inventory_item import InventoryItem
    from app.models.stock_movement import StockMovement
    from app.models.judge_alert import JudgeAlert, AlertStatus
    from app.services.stock import get_current_stock

    dept_id = request.args.get("department_id")
    q = db.session.query(InventoryItem).filter_by(is_active=True)
    if dept_id:
        q = q.filter_by(department_id=dept_id)
    items = q.order_by(InventoryItem.name).all()

    summary = []
    for item in items:
        stock = get_current_stock(item.id)
        summary.append({
            "id": item.id, "name": item.name, "unit": item.unit,
            "current_stock": str(stock),
            "reorder_level": str(item.reorder_level),
            "is_low": stock <= Decimal(str(item.reorder_level)),
        })

    recent = db.session.query(StockMovement).order_by(
        StockMovement.timestamp_utc.desc()
    ).limit(10).all()
    recent_movements = [{"item": m.item.name if m.item else None,
                         "reason": m.reason, "amount": str(m.change_amount),
                         "at": m.timestamp_utc.isoformat()} for m in recent]

    open_alerts = db.session.query(JudgeAlert).filter_by(
        status=AlertStatus.OPEN.value
    ).order_by(JudgeAlert.created_at.desc()).limit(20).all()
    alerts = [{"id": a.id, "type": a.alert_type, "severity": a.severity,
               "description": a.description} for a in open_alerts]

    return jsonify({
        "total_skus": len(items),
        "low_stock_count": sum(1 for s in summary if s["is_low"]),
        "items": summary,
        "recent_movements": recent_movements,
        "alerts": alerts,
    }), 200


# ── Finance ───────────────────────────────────────────────────────────────────

@dashboard_bp.get("/finance")
@require_active_user
def finance_view():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    period = request.args.get("period", "month")
    period_start, period_end = _period_bounds(period)

    from app.models.budget import Budget
    from app.models.department import Department
    from app.models.payment import Payment
    from app.models.cash_reconciliation import CashReconciliation, ReconciliationStatus
    from app.models.payment_reconciliation import PaymentReconciliation, PaymentReconciliationStatus
    from app.models.purchase_request import PurchaseRequest, RequestStatus

    departments = db.session.query(Department).all()
    period_str  = period_start.strftime("%Y-%m")
    budget_rows = db.session.query(Budget).filter_by(period=period_str, is_active=True).all()
    budget_map  = {b.department_id: Decimal(str(b.amount)) for b in budget_rows}

    dept_summary = []
    for dept in departments:
        budgeted = budget_map.get(dept.id, Decimal("0"))
        # Spending: sum payments by tab's department — simplified: total payments in period
        dept_summary.append({
            "department": dept.name,
            "budgeted": str(budgeted),
        })

    shortfalls = db.session.query(CashReconciliation).filter_by(
        status=ReconciliationStatus.SHORT.value
    ).count()
    unmatched_mpesa = db.session.query(PaymentReconciliation).filter_by(
        status=PaymentReconciliationStatus.UNMATCHED.value
    ).count() if hasattr(PaymentReconciliationStatus, 'UNMATCHED') else 0
    pending_approvals = db.session.query(PurchaseRequest).filter_by(
        status=RequestStatus.PENDING.value
    ).count()

    total_revenue = db.session.query(func.sum(Payment.amount)).filter(
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc <= period_end,
    ).scalar() or Decimal("0")

    status = "green"
    if shortfalls > 0 or unmatched_mpesa > 3:
        status = "yellow"
    if shortfalls > 3 or unmatched_mpesa > 10:
        status = "red"

    return jsonify({
        "period": period,
        "total_revenue": str(total_revenue),
        "reconciliation_status": status,
        "open_shortfalls": shortfalls,
        "unmatched_mpesa": unmatched_mpesa,
        "pending_approvals": pending_approvals,
        "department_budgets": dept_summary,
    }), 200


# ── Bookings ──────────────────────────────────────────────────────────────────

@dashboard_bp.get("/bookings")
@require_active_user
def bookings_view():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    period = request.args.get("period", "month")
    period_start, period_end = _period_bounds(period)

    from app.models.booking import Booking, BookingStatus
    from app.models.bookable_resource import BookableResource, ResourceType
    from app.models.waiver import Waiver, WaiverActivityType
    from app.models.payment import Payment
    from app.models.tab import Tab, TabType
    from app.services.booking import get_deposit_total

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end   = today_start + timedelta(days=1)

    # Arrivals + departures today
    arrivals = db.session.query(Booking).filter(
        Booking.check_in_planned_utc >= today_start,
        Booking.check_in_planned_utc < today_end,
        Booking.status.in_([BookingStatus.CONFIRMED.value, BookingStatus.HELD.value]),
    ).all()
    departures = db.session.query(Booking).filter(
        Booking.check_out_planned_utc >= today_start,
        Booking.check_out_planned_utc < today_end,
        Booking.status == BookingStatus.CHECKED_IN.value,
    ).all()

    # Occupancy by resource type
    checked_in = db.session.query(Booking).filter_by(
        status=BookingStatus.CHECKED_IN.value
    ).all()
    by_type: dict[str, int] = {}
    for b in checked_in:
        if b.resource:
            t = b.resource.resource_type
            by_type[t] = by_type.get(t, 0) + 1

    # Pending deposits (CONFIRMED but deposit_paid < deposit_required)
    confirmed = db.session.query(Booking).filter_by(
        status=BookingStatus.CONFIRMED.value
    ).all()
    pending_deposits = [
        {"id": b.id, "guest": b.guest_name, "resource": b.resource.name if b.resource else None,
         "deposit_required": str(b.deposit_required),
         "deposit_paid": str(get_deposit_total(b.id))}
        for b in confirmed if get_deposit_total(b.id) < Decimal(str(b.deposit_required))
    ]

    # Pending waivers (water-activity tomorrow)
    tomorrow_start = today_start + timedelta(days=1)
    tomorrow_end   = today_start + timedelta(days=2)
    water_bookings = db.session.query(Booking).filter(
        Booking.check_in_planned_utc >= tomorrow_start,
        Booking.check_in_planned_utc < tomorrow_end,
        Booking.status.in_([BookingStatus.CONFIRMED.value, BookingStatus.CHECKED_IN.value]),
    ).all()
    pending_waivers = []
    for b in water_bookings:
        if b.resource and b.resource.resource_type == ResourceType.WATER_ACTIVITY.value:
            has_w = db.session.query(Waiver).filter_by(
                booking_id=b.id, activity_type=WaiverActivityType.WATER_ACTIVITY.value,
                is_active=True,
            ).first()
            if not has_w:
                pending_waivers.append({"booking_id": b.id, "guest": b.guest_name})

    # Revenue from bookings (VILLA tabs) in period
    villa_revenue = db.session.query(func.sum(Payment.amount)).join(
        Tab, Payment.tab_id == Tab.id
    ).filter(
        Tab.tab_type == TabType.VILLA.value,
        Payment.created_at_utc >= period_start,
        Payment.created_at_utc <= period_end,
    ).scalar()

    return jsonify({
        "occupancy_by_type": by_type,
        "arrivals_today": [{"id": b.id, "guest": b.guest_name} for b in arrivals],
        "departures_today": [{"id": b.id, "guest": b.guest_name} for b in departures],
        "pending_deposits": pending_deposits,
        "pending_waivers_tomorrow": pending_waivers,
        "villa_revenue": str(villa_revenue or Decimal("0")),
    }), 200


# ── Staff ─────────────────────────────────────────────────────────────────────

@dashboard_bp.get("/staff")
@require_active_user
def staff_view():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    from app.models.employee_profile import EmployeeProfile
    from app.models.clock_event import ClockEvent, ClockEventType
    from app.models.shift import Shift, ShiftStatus
    from app.models.dispute import Dispute, DisputeStatus
    from app.models.suggestion import Suggestion, SuggestionCategory, SuggestionStatus
    from app.services.hr import compute_performance

    all_profiles = db.session.query(EmployeeProfile).filter_by(is_active=True).all()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end   = today_start + timedelta(days=1)
    sixteen_h   = datetime.now(timezone.utc) - timedelta(hours=16)

    clocked_in = []
    for p in all_profiles:
        last = db.session.query(ClockEvent).filter_by(employee_id=p.id).order_by(
            ClockEvent.occurred_at_utc.desc()
        ).first()
        if last and last.event_type == ClockEventType.CLOCK_IN.value:
            occ = last.occurred_at_utc
            if occ.tzinfo is None:
                occ = occ.replace(tzinfo=timezone.utc)
            if occ >= sixteen_h:
                clocked_in.append(p.id)

    # Scheduled today but not clocked in
    today_shifts = db.session.query(Shift).filter(
        Shift.scheduled_start_utc >= today_start,
        Shift.scheduled_start_utc < today_end,
        Shift.status == ShiftStatus.SCHEDULED.value,
    ).all()
    absent = sum(1 for s in today_shifts if s.employee_id not in clocked_in)

    # Disputes and suggestions
    open_disputes_mgmt = db.session.query(Dispute).filter(
        Dispute.status == DisputeStatus.OPEN.value,
        Dispute.is_owner_only == False,
    ).count()
    open_disputes_owner = db.session.query(Dispute).filter(
        Dispute.status == DisputeStatus.OPEN.value,
        Dispute.is_owner_only == True,
    ).count()
    mgmt_suggestions = db.session.query(Suggestion).filter_by(
        category=SuggestionCategory.MANAGEMENT.value,
        status=SuggestionStatus.NEW.value,
    ).count()
    owner_suggestions = db.session.query(Suggestion).filter_by(
        category=SuggestionCategory.OWNER_PRIVATE.value,
        status=SuggestionStatus.NEW.value,
    ).count()

    # Quick performance snapshot (current month, top 3 / bottom 3)
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    perf_rows = []
    for p in all_profiles[:15]:  # cap at 15 for perf
        try:
            scores = compute_performance(p.id, month_start, datetime.now(timezone.utc))
            perf_rows.append({
                "id": p.id, "name": p.full_name,
                "composite": float(scores["composite_score"]),
            })
        except Exception:
            pass
    perf_rows.sort(key=lambda x: x["composite"], reverse=True)
    top_performers    = [{"name": r["name"], "score": r["composite"]} for r in perf_rows[:3]]
    bottom_performers = [{"name": r["name"], "score": r["composite"]} for r in perf_rows[-3:]]

    return jsonify({
        "active_employees": len(all_profiles),
        "on_duty": len(clocked_in),
        "absent_today": absent,
        "open_disputes": {"management": open_disputes_mgmt, "owner_private": open_disputes_owner},
        "new_suggestions": {"management": mgmt_suggestions, "owner_private": owner_suggestions},
        "top_performers": top_performers,
        "bottom_performers": bottom_performers,
    }), 200


# ── Conduct ───────────────────────────────────────────────────────────────────

@dashboard_bp.get("/conduct")
@require_active_user
def conduct_view():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    from app.models.conduct_rule import ConductRule
    from app.models.conduct_signature import ConductSignature
    from app.models.employee_profile import EmployeeProfile
    from app.models.dispute import Dispute, DisputeStatus

    active_rules = db.session.query(ConductRule).filter_by(is_active=True).all()
    all_employees = db.session.query(EmployeeProfile).filter_by(is_active=True).all()
    total_emp = len(all_employees)

    compliance = []
    for rule in active_rules:
        signed_count = db.session.query(ConductSignature).filter_by(
            conduct_rule_id=rule.id
        ).count()
        pct = round(signed_count / total_emp * 100) if total_emp else 0
        compliance.append({
            "rule_key": rule.rule_key, "title": rule.title,
            "version": rule.version, "signed_pct": pct,
            "unsigned_count": total_emp - signed_count,
        })

    recent_disputes = db.session.query(Dispute).filter_by(
        status=DisputeStatus.OPEN.value
    ).order_by(Dispute.created_at_utc.desc()).limit(5).all()

    return jsonify({
        "active_rules": len(active_rules),
        "compliance": compliance,
        "overall_compliance_pct": round(
            sum(c["signed_pct"] for c in compliance) / len(compliance)
        ) if compliance else 100,
        "open_disputes": len(recent_disputes),
        "recent_disputes": [{"id": d.id, "category": d.category,
                              "priority": d.priority} for d in recent_disputes],
    }), 200


# ── Suggestions ───────────────────────────────────────────────────────────────

@dashboard_bp.get("/suggestions")
@require_active_user
def suggestions_view():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    from app.models.suggestion import Suggestion, SuggestionCategory, SuggestionStatus

    mgmt = db.session.query(Suggestion).filter_by(
        category=SuggestionCategory.MANAGEMENT.value
    ).order_by(Suggestion.created_at_utc.desc()).limit(10).all()
    private = db.session.query(Suggestion).filter_by(
        category=SuggestionCategory.OWNER_PRIVATE.value
    ).order_by(Suggestion.created_at_utc.desc()).limit(10).all()

    def _s(s: Suggestion) -> dict:
        return {"id": s.id, "subject": s.subject, "status": s.status,
                "submitted_by": s.submitted_by_name or "anonymous",
                "created_at": s.created_at_utc.isoformat()}

    return jsonify({
        "management":    [_s(s) for s in mgmt],
        "owner_private": [_s(s) for s in private],
    }), 200


# ── Calendar ──────────────────────────────────────────────────────────────────

@dashboard_bp.get("/calendar")
@require_active_user
def calendar_view():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    from app.models.calendar_entry import CalendarEntry
    from app.models.event import Event, EventStatus

    def _parse(val: str | None) -> datetime | None:
        if not val:
            return None
        try:
            dt = datetime.fromisoformat(val)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    now = datetime.now(timezone.utc)
    from_dt = _parse(request.args.get("from")) or now
    to_dt   = _parse(request.args.get("to"))   or (now + timedelta(days=30))

    entries = db.session.query(CalendarEntry).filter(
        CalendarEntry.date_start_utc >= from_dt,
        CalendarEntry.date_start_utc <= to_dt,
        CalendarEntry.is_active == True,
    ).order_by(CalendarEntry.date_start_utc).all()

    events = db.session.query(Event).filter(
        Event.starts_at_utc >= from_dt,
        Event.starts_at_utc <= to_dt,
        Event.status.in_([EventStatus.PLANNED.value, EventStatus.CONFIRMED.value,
                           EventStatus.IN_PROGRESS.value]),
    ).order_by(Event.starts_at_utc).all()

    return jsonify({
        "calendar_entries": [{
            "id": e.id, "title": e.title, "type": e.entry_type,
            "date": e.date_start_utc.isoformat(), "is_peak": e.is_peak,
        } for e in entries],
        "events": [{
            "id": e.id, "title": e.title, "status": e.status,
            "starts_at": e.starts_at_utc.isoformat(),
        } for e in events],
    }), 200


# ── Feedback ──────────────────────────────────────────────────────────────────

@dashboard_bp.get("/feedback")
@require_active_user
def feedback_view():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    period = request.args.get("period", "month")
    period_start, period_end = _period_bounds(period)

    from app.models.guest_feedback import GuestFeedback
    from app.models.department import Department
    from app.models.employee_profile import EmployeeProfile

    # Overall average
    overall = db.session.query(func.avg(GuestFeedback.score)).filter(
        GuestFeedback.created_at_utc >= period_start,
        GuestFeedback.created_at_utc <= period_end,
    ).scalar()

    # Per-department average
    dept_avgs = db.session.query(
        GuestFeedback.department_id,
        func.avg(GuestFeedback.score).label("avg"),
        func.count(GuestFeedback.id).label("count"),
    ).filter(
        GuestFeedback.created_at_utc >= period_start,
        GuestFeedback.created_at_utc <= period_end,
        GuestFeedback.department_id.isnot(None),
    ).group_by(GuestFeedback.department_id).all()

    dept_rows = []
    for row in sorted(dept_avgs, key=lambda r: r.avg or 0, reverse=True):
        dept = db.session.get(Department, row.department_id)
        dept_rows.append({
            "department": dept.name if dept else row.department_id,
            "avg_score": str(round(Decimal(str(row.avg)), 2)),
            "count": row.count,
        })

    # Per-staff ranking
    staff_avgs = db.session.query(
        GuestFeedback.served_by_employee_id,
        func.avg(GuestFeedback.score).label("avg"),
        func.count(GuestFeedback.id).label("count"),
    ).filter(
        GuestFeedback.created_at_utc >= period_start,
        GuestFeedback.created_at_utc <= period_end,
        GuestFeedback.served_by_employee_id.isnot(None),
    ).group_by(GuestFeedback.served_by_employee_id).all()

    staff_rows = []
    for row in sorted(staff_avgs, key=lambda r: r.avg or 0, reverse=True):
        p = db.session.get(EmployeeProfile, row.served_by_employee_id)
        staff_rows.append({
            "employee": p.full_name if p else row.served_by_employee_id,
            "avg_score": str(round(Decimal(str(row.avg)), 2)),
            "count": row.count,
        })

    # Recent comments
    recent = db.session.query(GuestFeedback).filter(
        GuestFeedback.created_at_utc >= period_start,
        GuestFeedback.comments.isnot(None),
    ).order_by(GuestFeedback.created_at_utc.desc()).limit(10).all()

    return jsonify({
        "period": period,
        "overall_avg": str(round(Decimal(str(overall)), 2)) if overall else None,
        "by_department": dept_rows,
        "by_staff": staff_rows,
        "recent_comments": [{"score": f.score, "comment": f.comments,
                              "guest": f.guest_name} for f in recent],
    }), 200


# ── Equipment ─────────────────────────────────────────────────────────────────

@dashboard_bp.get("/equipment")
@require_active_user
def equipment_view():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    from app.models.equipment import Equipment, EquipmentStatus

    all_eq = db.session.query(Equipment).filter_by(is_active=True).all()
    due_service = [e for e in all_eq if e.is_due_service]
    in_maintenance = [e for e in all_eq if e.status == EquipmentStatus.MAINTENANCE.value]

    return jsonify({
        "total": len(all_eq),
        "due_service": [{
            "id": e.id, "name": e.name, "type": e.equipment_type,
            "last_service": e.last_service_utc.isoformat() if e.last_service_utc else None,
            "interval_days": e.service_interval_days,
        } for e in due_service],
        "in_maintenance": [{"id": e.id, "name": e.name} for e in in_maintenance],
    }), 200


# ── Unified alerts feed ───────────────────────────────────────────────────────

@dashboard_bp.get("/alerts")
@require_active_user
def alerts_feed():
    actor = db.session.get(User, get_jwt_identity())
    err = _require_owner(actor)
    if err:
        return err

    from app.models.judge_alert import JudgeAlert, AlertStatus

    status_filter = request.args.get("status", "active")
    q = db.session.query(JudgeAlert)
    if status_filter == "active":
        q = q.filter_by(status=AlertStatus.OPEN.value)

    alerts = q.order_by(JudgeAlert.created_at.desc()).limit(50).all()

    RECOMMENDED = {
        "RATIO":                   "Review consumption vs sales for the flagged item.",
        "SPOILAGE_SPIKE":          "Check cold storage and delivery records for this item.",
        "VARIANCE":                "Run a manual stock count and compare with system records.",
        "GATE_REVENUE_MISMATCH":   "Cross-check gate cash with band issuance log. Count receipts.",
        "GATE_HEADCOUNT_MISMATCH": "Review gate entry log vs physical turnstile count.",
        "GATE_FORFEIT_ANOMALY":    "Review this gate staff member's band issuance pattern.",
        "EVENT_NOT_CLOSED":        "Complete or cancel this event in the system.",
    }

    return jsonify([{
        "id":               a.id,
        "type":             a.alert_type,
        "severity":         a.severity,
        "description":      a.description,
        "recommended_action": RECOMMENDED.get(a.alert_type,
                               "Review this alert and take appropriate action."),
        "status":           a.status,
        "created_at":       a.created_at.isoformat(),
    } for a in alerts]), 200


@dashboard_bp.post("/alerts/<alert_id>/acknowledge")
@require_active_user
def acknowledge_alert(alert_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    from app.models.judge_alert import JudgeAlert, AlertStatus
    from app.models.audit_log import AuditLog

    alert = db.session.get(JudgeAlert, alert_id)
    if not alert:
        return jsonify({"error": "Alert not found."}), 404

    alert.status              = AlertStatus.ACKNOWLEDGED.value
    alert.acknowledged_at     = datetime.now(timezone.utc)
    alert.acknowledged_by_id  = actor.id
    db.session.flush()
    AuditLog.log(actor=actor.username, action="alert.acknowledge", target=alert_id)
    db.session.commit()
    return jsonify({"id": alert.id, "status": alert.status}), 200


@dashboard_bp.post("/alerts/<alert_id>/action-taken")
@require_active_user
def action_taken(alert_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    from app.models.judge_alert import JudgeAlert, AlertStatus
    from app.models.audit_log import AuditLog

    alert = db.session.get(JudgeAlert, alert_id)
    if not alert:
        return jsonify({"error": "Alert not found."}), 404

    data  = request.get_json(silent=True) or {}
    notes = (data.get("notes") or "").strip()
    if not notes:
        return jsonify({"error": "notes are required to mark action taken."}), 400

    alert.status             = AlertStatus.RESOLVED.value
    alert.acknowledged_at    = datetime.now(timezone.utc)
    alert.acknowledged_by_id = actor.id
    db.session.flush()
    AuditLog.log(actor=actor.username, action="alert.action_taken",
                 target=alert_id, details=notes[:200])
    db.session.commit()
    return jsonify({"id": alert.id, "status": alert.status}), 200
