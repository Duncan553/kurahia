"""
gate/core.py — Gate entry, wristband issuance, lookups, reconciliation.

Role levels:
  GATE_LEVEL   = 3  (manager+ can issue / deactivate / forfeit)
  LOOKUP_LEVEL = 1  (any logged-in staff can look up a band — waiter, spa, etc.)
  MANAGER_LEVEL = 5 (reconciliation + headcount reporting)
"""
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.wristband import Wristband, WristbandStatus
from app.models.gate_headcount import GateHeadcount
from app.models.payment import PaymentMethod
from app.models.audit_log import AuditLog
from app.services.gate import (
    issue_band, close_band, forfeit_day,
    get_band_by_number, get_active_bands, get_reconciliation, check_gate_signals,
)
from app.services.tab import get_tab_balance

gate_bp = Blueprint("gate_core", __name__, url_prefix="/gate")

GATE_LEVEL    = 3    # gate staff (manager+ in current role set)
LOOKUP_LEVEL  = 1    # any logged-in staff
MANAGER_LEVEL = 5


def _band_dict(band: Wristband, include_balance: bool = False) -> dict:
    d = {
        "id":           band.id,
        "band_number":  band.band_number,
        "issue_date":   band.issue_date,
        "status":       band.status,
        "tab_id":       band.tab_id,
        "notes":        band.notes,
        "issued_by":    band.issued_by.username if band.issued_by else None,
        "issued_at":    band.created_at_utc.isoformat(),
    }
    if include_balance:
        d["tab_balance"] = str(get_tab_balance(band.tab_id))
    return d


# ── Issue band ────────────────────────────────────────────────────────────────

@gate_bp.post("/issue-band")
@require_active_user
def issue_band_route():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < GATE_LEVEL:
        return jsonify({"error": "Gate staff or above required to issue wristbands."}), 403

    data     = request.get_json(silent=True) or {}
    method   = (data.get("method") or "").upper()
    idem_key = data.get("idempotency_key") or str(uuid.uuid4())

    if method not in PaymentMethod.__members__:
        return jsonify({"error": f"method must be one of {list(PaymentMethod.__members__)}."}), 400

    # Idempotency — return existing band if key seen before
    existing = db.session.query(Wristband).filter_by(idempotency_key=idem_key).first()
    if existing:
        return jsonify({**_band_dict(existing, include_balance=True), "duplicate": True}), 200

    band = issue_band(
        actor_id=actor.id,
        method=method,
        mpesa_code=data.get("mpesa_code"),
        card_ref=data.get("card_ref"),
        idem_key=idem_key,
        notes=data.get("notes"),
    )
    db.session.flush()
    AuditLog.log(actor=actor.username, action="gate.issue_band",
                 details=f"band={band.band_number} date={band.issue_date}")
    db.session.commit()
    return jsonify(_band_dict(band, include_balance=True)), 201


# ── Deactivate band (customer leaves normally) ────────────────────────────────

@gate_bp.post("/deactivate-band/<int:band_number>")
@require_active_user
def deactivate_band(band_number):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < GATE_LEVEL:
        return jsonify({"error": "Gate staff or above required to deactivate bands."}), 403

    band = get_band_by_number(band_number)
    if not band:
        return jsonify({"error": f"No active band #{band_number} found for today."}), 404

    close_band(band, actor.id, WristbandStatus.DEACTIVATED.value,
               reason=request.get_json(silent=True, force=True) and
               (request.get_json() or {}).get("notes"))
    db.session.flush()
    AuditLog.log(actor=actor.username, action="gate.deactivate_band",
                 details=f"band={band_number}")
    db.session.commit()
    return jsonify(_band_dict(band, include_balance=True)), 200


# ── Look up band by number ────────────────────────────────────────────────────

@gate_bp.get("/bands/<int:band_number>")
@require_active_user
def get_band(band_number):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < LOOKUP_LEVEL:
        return jsonify({"error": "Login required."}), 403

    date_str = request.args.get("date")
    band = get_band_by_number(band_number, date_str)
    if not band:
        # Also check for deactivated/forfeited bands on that date (useful for end-of-day)
        today = date_str or datetime.now(timezone.utc).date().isoformat()
        band = db.session.query(Wristband).filter_by(
            band_number=band_number, issue_date=today
        ).first()
        if not band:
            return jsonify({"error": f"Band #{band_number} not found for today."}), 404

    return jsonify(_band_dict(band, include_balance=True)), 200


# ── Active bands (gate/manager view of who's inside) ─────────────────────────

@gate_bp.get("/active-bands")
@require_active_user
def active_bands():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < GATE_LEVEL:
        return jsonify({"error": "Gate staff or above required."}), 403

    date_str = request.args.get("date")
    bands = get_active_bands(date_str)
    return jsonify([_band_dict(b, include_balance=True) for b in bands]), 200


# ── Record independent headcount ──────────────────────────────────────────────

@gate_bp.post("/headcount")
@require_active_user
def record_headcount():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to record headcount."}), 403

    data     = request.get_json(silent=True) or {}
    date_str = data.get("date") or datetime.now(timezone.utc).date().isoformat()
    counted  = data.get("counted")
    if counted is None:
        return jsonify({"error": "counted is required."}), 400
    try:
        counted = int(counted)
        if counted < 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "counted must be a non-negative integer."}), 400

    existing = db.session.query(GateHeadcount).filter_by(count_date=date_str).first()
    if existing:
        existing.counted = counted
        existing.notes = data.get("notes") or existing.notes
    else:
        hc = GateHeadcount(
            count_date=date_str,
            counted=counted,
            notes=data.get("notes"),
            recorded_by_id=actor.id,
        )
        db.session.add(hc)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="gate.headcount",
                 details=f"date={date_str} counted={counted}")
    db.session.commit()
    return jsonify({"date": date_str, "counted": counted}), 200


# ── EOD forfeit sweep ─────────────────────────────────────────────────────────

@gate_bp.post("/forfeit-day")
@require_active_user
def forfeit_day_route():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to run EOD forfeit."}), 403

    data     = request.get_json(silent=True) or {}
    date_str = data.get("date") or datetime.now(timezone.utc).date().isoformat()

    count, total_unused = forfeit_day(date_str, actor.id)

    # Run judge signals after forfeit so forfeit rates are final
    alerts = check_gate_signals(date_str)
    db.session.flush()

    AuditLog.log(actor=actor.username, action="gate.forfeit_day",
                 details=f"date={date_str} forfeited={count} unused={total_unused}")
    db.session.commit()
    return jsonify({
        "date":            date_str,
        "forfeited":       count,
        "total_unused_credit": str(total_unused),
        "judge_alerts_fired":  alerts,
    }), 200


# ── Reconciliation ────────────────────────────────────────────────────────────

@gate_bp.get("/reconciliation")
@require_active_user
def reconciliation():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required to view reconciliation."}), 403

    date_str = request.args.get("date") or datetime.now(timezone.utc).date().isoformat()
    recon = get_reconciliation(date_str)
    return jsonify(recon), 200
