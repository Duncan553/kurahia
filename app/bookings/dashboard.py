"""
bookings/dashboard.py — Front-desk / owner dashboard data.
Arrivals, departures, current occupancy, pending waivers.
"""
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.booking import Booking, BookingStatus
from app.models.bookable_resource import ResourceType
from app.models.waiver import Waiver, WaiverActivityType
from app.services.booking import get_deposit_total
from app.services.tab import get_tab_balance

dashboard_bp = Blueprint("front_desk", __name__, url_prefix="/front-desk")

FRONT_DESK_LEVEL = 3


@dashboard_bp.get("/today")
@require_active_user
def front_desk_today():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < FRONT_DESK_LEVEL:
        return jsonify({"error": "Staff or above required."}), 403

    today     = datetime.now(timezone.utc).date()
    day_start = datetime(today.year, today.month, today.day)
    day_end   = day_start + timedelta(days=1)

    # Arrivals expected today (CONFIRMED or HELD)
    arrivals = db.session.query(Booking).filter(
        Booking.check_in_planned_utc >= day_start,
        Booking.check_in_planned_utc < day_end,
        Booking.status.in_([BookingStatus.CONFIRMED.value, BookingStatus.HELD.value]),
    ).all()

    # Departures expected today (CHECKED_IN)
    departures = db.session.query(Booking).filter(
        Booking.check_out_planned_utc >= day_start,
        Booking.check_out_planned_utc < day_end,
        Booking.status == BookingStatus.CHECKED_IN.value,
    ).all()

    # Current occupancy (all CHECKED_IN)
    occupancy = db.session.query(Booking).filter(
        Booking.status == BookingStatus.CHECKED_IN.value,
    ).all()

    # Pending waivers: WATER_ACTIVITY bookings today without active waiver
    water_bookings = db.session.query(Booking).filter(
        Booking.check_in_planned_utc >= day_start,
        Booking.check_in_planned_utc < day_end,
        Booking.status.in_([
            BookingStatus.CONFIRMED.value,
            BookingStatus.CHECKED_IN.value,
        ]),
    ).all()
    pending_waivers = []
    for b in water_bookings:
        if b.resource and b.resource.resource_type == ResourceType.WATER_ACTIVITY.value:
            has_w = db.session.query(Waiver).filter_by(
                booking_id=b.id,
                activity_type=WaiverActivityType.WATER_ACTIVITY.value,
                is_active=True,
            ).first()
            if not has_w:
                pending_waivers.append({
                    "booking_id":  b.id,
                    "guest_name":  b.guest_name,
                    "resource":    b.resource.name,
                    "check_in":    b.check_in_planned_utc.isoformat(),
                })

    return jsonify({
        "date": today.isoformat(),
        "arrivals": [{
            "booking_id":     b.id,
            "guest_name":     b.guest_name,
            "resource":       b.resource.name if b.resource else None,
            "status":         b.status,
            "deposit_paid":   str(get_deposit_total(b.id)),
            "deposit_required": str(b.deposit_required),
        } for b in arrivals],
        "departures": [{
            "booking_id":    b.id,
            "guest_name":    b.guest_name,
            "resource":      b.resource.name if b.resource else None,
            "tab_balance":   str(get_tab_balance(b.tab_id)) if b.tab_id else "0",
        } for b in departures],
        "occupancy": [{
            "booking_id":  b.id,
            "guest_name":  b.guest_name,
            "resource":    b.resource.name if b.resource else None,
            "tab_id":      b.tab_id,
            "tab_balance": str(get_tab_balance(b.tab_id)) if b.tab_id else "0",
        } for b in occupancy],
        "pending_waivers": pending_waivers,
    }), 200
