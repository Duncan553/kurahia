"""
cli/conduct.py — Conduct + calendar seed commands.

flask conduct seed-rules          → seed 8-point default code of conduct
flask calendar seed-kenya-holidays → seed Kenyan public holidays next 12 months
flask feedback seed-sample        → seed sample guest feedback
"""
import click
from datetime import datetime, timezone, timedelta
from flask import Blueprint
from app.extensions import db

conduct_cli_bp = Blueprint("conduct", __name__)


@conduct_cli_bp.cli.command("seed-rules")
def seed_rules():
    """Seed default 8-point code of conduct."""
    from app.models.conduct_rule import ConductRule, RuleCategory
    from app.models.user import User

    owner = db.session.query(User).filter_by(username="owner1").first()
    if not owner:
        click.echo("owner1 not found — run flask seed first.")
        return

    rules = [
        ("respect-all-persons",    "Respect All Persons",
         "Treat every colleague, guest, and visitor with dignity and courtesy.",
         RuleCategory.RESPECT.value),
        ("no-discrimination",      "No Discrimination or Harassment",
         "Discrimination or harassment based on gender, tribe, religion, or any other ground is prohibited.",
         RuleCategory.RESPECT.value),
        ("punctuality",            "Punctuality and Reliability",
         "Arrive on time for all scheduled shifts. Notify your supervisor at least 2 hours in advance if unable to attend.",
         RuleCategory.PUNCTUALITY.value),
        ("uniform-grooming",       "Uniform and Grooming Standards",
         "Wear your full uniform while on duty. Maintain personal hygiene and a professional appearance.",
         RuleCategory.GENERAL.value),
        ("safety-workplace",       "Workplace Safety",
         "Follow all safety procedures. Report hazards immediately. Never operate equipment you are not trained for.",
         RuleCategory.SAFETY.value),
        ("guest-confidentiality",  "Guest Confidentiality",
         "Guest names, contact details, and preferences are strictly confidential. Do not share with third parties.",
         RuleCategory.CONFIDENTIALITY.value),
        ("cash-handling",          "Cash Handling Integrity",
         "All cash must be counted and reconciled per shift. Discrepancies must be reported immediately.",
         RuleCategory.GENERAL.value),
        ("property-care",          "Care of Property",
         "Resort equipment and property must be handled with care. Report damage immediately.",
         RuleCategory.GENERAL.value),
    ]

    created = 0
    for rule_key, title, body, category in rules:
        if db.session.query(ConductRule).filter_by(rule_key=rule_key, is_active=True).first():
            continue
        db.session.add(ConductRule(
            rule_key=rule_key, version=1,
            title=title, body=body, category=category,
            created_by_id=owner.id,
        ))
        created += 1

    db.session.commit()
    click.echo(f"Seeded {created} conduct rule(s).")


calendar_cli_bp = Blueprint("calendar", __name__)


@calendar_cli_bp.cli.command("seed-kenya-holidays")
def seed_kenya_holidays():
    """Seed Kenyan public holidays for the next 12 months."""
    from app.models.calendar_entry import CalendarEntry, CalendarEntryType
    from app.models.user import User

    owner = db.session.query(User).filter_by(username="owner1").first()
    if not owner:
        click.echo("owner1 not found — run flask seed first.")
        return

    year = datetime.now(timezone.utc).year
    holidays = [
        (f"{year}-01-01", "New Year's Day"),
        (f"{year}-04-18", "Good Friday"),
        (f"{year}-04-21", "Easter Monday"),
        (f"{year}-05-01", "Labour Day"),
        (f"{year}-06-01", "Madaraka Day"),
        (f"{year}-10-10", "Huduma Day"),
        (f"{year}-10-20", "Mashujaa Day"),
        (f"{year}-12-12", "Jamhuri Day"),
        (f"{year}-12-25", "Christmas Day"),
        (f"{year}-12-26", "Boxing Day"),
        (f"{year+1}-01-01", "New Year's Day (Next Year)"),
    ]

    created = 0
    for date_str, name in holidays:
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if db.session.query(CalendarEntry).filter_by(title=name, date_start_utc=day).first():
            continue
        db.session.add(CalendarEntry(
            title=name,
            entry_type=CalendarEntryType.HOLIDAY.value,
            date_start_utc=day,
            date_end_utc=day + timedelta(days=1),
            is_peak=True,
            planning_trigger_offset_days=14,
            description=f"Kenya public holiday: {name}",
            created_by_id=owner.id,
        ))
        created += 1

    db.session.commit()
    click.echo(f"Seeded {created} Kenyan holiday(s).")


feedback_cli_bp = Blueprint("feedback_cli", __name__)


@feedback_cli_bp.cli.command("seed-sample")
def seed_sample_feedback():
    """Seed sample guest feedback."""
    from app.models.guest_feedback import GuestFeedback
    from app.models.employee_profile import EmployeeProfile
    from app.models.department import Department

    dept = db.session.query(Department).filter_by(name="General").first()
    profile = db.session.query(EmployeeProfile).first()

    samples = [
        ("Alice Wanjiku", 5, "Excellent service, very attentive staff!"),
        ("Bob Kamau",     4, "Great food, will come back."),
        ("Carol Odhiambo", 3, "Average experience, could improve wait times."),
        ("Dave Mugo",     5, "Perfect evening, loved the ambiance."),
    ]

    created = 0
    for name, score, comment in samples:
        idem = f"seed-fb-{name.replace(' ', '-').lower()}"
        if db.session.query(GuestFeedback).filter_by(idempotency_key=idem).first():
            continue
        db.session.add(GuestFeedback(
            guest_name=name,
            score=score,
            comments=comment,
            department_id=dept.id if dept else None,
            served_by_employee_id=profile.id if profile else None,
            idempotency_key=idem,
        ))
        created += 1

    db.session.commit()
    click.echo(f"Seeded {created} feedback record(s).")
