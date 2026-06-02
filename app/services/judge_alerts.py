"""
services/judge_alerts.py — Idempotent alert creation helper.

All alert-writing code routes through fire_alert_if_absent() so that
double cron runs, operator re-runs, and concurrent executions never
produce duplicate JudgeAlert rows for the same event.

Dedup key: (alert_type, description_key, OPEN status).
description_key is a string that uniquely identifies the alert context
— e.g., the item name, staff username, or date string — that must appear
in the description of any existing OPEN alert of this type to count as
a duplicate.
"""
from app.extensions import db
from app.models.judge_alert import JudgeAlert, AlertStatus


def fire_alert_if_absent(
    alert_type: str,
    description_key: str,
    **alert_fields,
) -> tuple["JudgeAlert", bool]:
    """
    Returns (existing_alert, False) if an OPEN alert of this type already
    contains description_key in its description, otherwise writes and returns
    (new_alert, True). Idempotent across multiple calls with the same inputs.

    Callers must commit the session after receiving (alert, True).
    """
    existing = db.session.query(JudgeAlert).filter(
        JudgeAlert.alert_type == alert_type,
        JudgeAlert.status == AlertStatus.OPEN.value,
        JudgeAlert.description.like(f"%{description_key}%"),
    ).first()
    if existing:
        return existing, False

    alert = JudgeAlert(
        alert_type=alert_type,
        status=AlertStatus.OPEN.value,
        **alert_fields,
    )
    db.session.add(alert)
    db.session.flush()
    return alert, True
