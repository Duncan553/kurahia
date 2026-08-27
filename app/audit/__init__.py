"""
audit/ — read access to the hash-chained audit trail.

The trail is the system's strongest control: every write appends a row whose
entry_hash covers the previous row's hash, so removing or editing history breaks
the chain detectably. Until now it was reachable ONLY through
`flask audit verify-chain`, which meant the owner could not answer "who voided
that order at 9pm?" without an SSH session — the best-designed feature in the
codebase was, in practice, unusable.

OWNER ONLY, deliberately. The log records what managers did, so a manager must
not be able to read it: someone reviewing their own trail is not a control. It
is also strictly read-only — there is no endpoint here that writes, edits or
deletes an entry, because an audit trail you can reach through the API is an
audit trail an attacker can reach too.
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.utils.auth_decorators import require_active_user

audit_bp = Blueprint("audit", __name__, url_prefix="/audit")

OWNER_LEVEL = 10
MAX_PAGE_SIZE = 200


def _require_owner(actor):
    if actor.role.level < OWNER_LEVEL:
        return jsonify({
            "error": "Only the owner can read the audit trail."
        }), 403
    return None


@audit_bp.get("/logs")
@require_active_user
def list_logs():
    """Filterable, paginated audit history — newest first."""
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err

    q = db.session.query(AuditLog)

    # Free-text-ish filters. `action` matches a PREFIX so "menu." finds every
    # menu action without the caller needing to know the full verb list.
    if who := (request.args.get("actor") or "").strip():
        q = q.filter(AuditLog.actor.ilike(f"%{who}%"))
    if action := (request.args.get("action") or "").strip():
        q = q.filter(AuditLog.action.ilike(f"{action}%"))
    if target := (request.args.get("target") or "").strip():
        q = q.filter(AuditLog.target.ilike(f"%{target}%"))

    # Dates are inclusive day bounds in the resort's own terms; the caller sends
    # plain YYYY-MM-DD and should not have to think about UTC.
    for param, op in (("from", "gte"), ("to", "lte")):
        raw = (request.args.get(param) or "").strip()
        if not raw:
            continue
        try:
            day = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return jsonify({"error": f"{param} must be YYYY-MM-DD."}), 400
        if op == "gte":
            q = q.filter(AuditLog.timestamp >= day)
        else:
            q = q.filter(AuditLog.timestamp < day.replace(hour=23, minute=59, second=59))

    total = q.count()

    try:
        limit = min(int(request.args.get("limit", 50)), MAX_PAGE_SIZE)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify({"error": "limit and offset must be whole numbers."}), 400

    rows = (q.order_by(AuditLog.timestamp.desc())
             .limit(limit).offset(offset).all())

    return jsonify({
        "total": total,
        "limit": limit,
        "offset": offset,
        "entries": [{
            "id":        r.id,
            "actor":     r.actor,
            "action":    r.action,
            "target":    r.target,
            "details":   r.details,
            "timestamp": r.timestamp.isoformat(),
        } for r in rows],
    }), 200


@audit_bp.get("/verify")
@require_active_user
def verify():
    """Re-walk the whole chain and report whether history is intact.

    This is the part that makes the trail worth having: it is not enough to SHOW
    the history, the owner has to be able to confirm nobody rewrote it.
    """
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err

    ok, reason = AuditLog.verify_chain()
    return jsonify({
        "intact": ok,
        "detail": "Every entry hashes to the one before it — history is unaltered."
                  if ok else reason,
        "entries_checked": db.session.query(AuditLog).count(),
    }), 200


@audit_bp.get("/actions")
@require_active_user
def list_actions():
    """The distinct action verbs present, so a UI can offer a real filter list
    instead of asking the owner to guess what the system calls things."""
    actor = db.session.get(User, get_jwt_identity())
    if (err := _require_owner(actor)):
        return err

    rows = db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    return jsonify([r[0] for r in rows]), 200
