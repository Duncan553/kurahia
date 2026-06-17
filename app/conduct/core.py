"""
conduct/core.py — Code-of-conduct versioning, signing, compliance reporting.

Versioning rule: POST /conduct/rules with an existing rule_key → creates version+1,
deactivates prior version. History is never lost.
Compliance: manager view of who hasn't signed each current (is_active) version.
"""
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.conduct_rule import ConductRule, RuleCategory
from app.models.conduct_signature import ConductSignature
from app.models.employee_profile import EmployeeProfile
from app.models.audit_log import AuditLog

conduct_bp = Blueprint("conduct_core", __name__, url_prefix="/conduct")

OWNER_LEVEL   = 10
MANAGER_LEVEL = 5
STAFF_LEVEL   = 1


def _rule_dict(r: ConductRule) -> dict:
    return {
        "id": r.id, "rule_key": r.rule_key, "version": r.version,
        "title": r.title, "body": r.body, "category": r.category,
        "is_active": r.is_active,
        "created_at": r.created_at_utc.isoformat(),
    }


# ── Rules ─────────────────────────────────────────────────────────────────────

@conduct_bp.post("/rules")
@require_active_user
def create_or_update_rule():
    """
    If rule_key exists → create new version (v+1), deactivate previous.
    If rule_key is new → create v1.
    Owner-only: only the owner can publish or update conduct rules.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Owner required to create or update conduct rules."}), 403

    data     = request.get_json(silent=True) or {}
    rule_key = (data.get("rule_key") or "").strip().lower().replace(" ", "-")
    title    = (data.get("title") or "").strip()
    body     = (data.get("body") or "").strip()
    category = (data.get("category") or "").upper()

    if not rule_key or not title or not body:
        return jsonify({"error": "rule_key, title, and body are required."}), 400
    if category not in RuleCategory.__members__:
        return jsonify({"error": f"category must be one of {list(RuleCategory.__members__)}."}), 400

    # Find current active version for this rule_key
    current = db.session.query(ConductRule).filter_by(
        rule_key=rule_key, is_active=True
    ).order_by(ConductRule.version.desc()).first()

    new_version = (current.version + 1) if current else 1

    # Deactivate the previous version
    if current:
        current.is_active = False

    rule = ConductRule(
        rule_key=rule_key, version=new_version,
        title=title, body=body, category=category,
        created_by_id=actor.id,
    )
    db.session.add(rule)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="conduct.rule.publish",
                 details=f"{rule_key} v{new_version}")
    db.session.commit()
    return jsonify(_rule_dict(rule)), 201


@conduct_bp.get("/rules")
@require_active_user
def list_rules():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < STAFF_LEVEL:
        return jsonify({"error": "Login required."}), 403
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    active_only = request.args.get("active", "true").lower() != "false"
    q = db.session.query(ConductRule)
    if not include_disabled and active_only:
        q = q.filter_by(is_active=True)
    return jsonify([_rule_dict(r) for r in q.order_by(
        ConductRule.rule_key, ConductRule.version.desc()
    ).all()]), 200


@conduct_bp.get("/rules/<rule_id>/versions")
@require_active_user
def rule_versions(rule_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403
    rule = db.session.get(ConductRule, rule_id)
    if not rule:
        return jsonify({"error": "Rule not found."}), 404
    versions = db.session.query(ConductRule).filter_by(
        rule_key=rule.rule_key
    ).order_by(ConductRule.version.desc()).all()
    return jsonify([_rule_dict(r) for r in versions]), 200


# ── Signing ───────────────────────────────────────────────────────────────────

@conduct_bp.post("/sign")
@require_active_user
def sign_rule():
    """Employee signs the current active version of a rule. Idempotent."""
    actor = db.session.get(User, get_jwt_identity())
    profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id).first()
    if not profile:
        return jsonify({"error": "Employee profile required to sign conduct rules."}), 400

    data    = request.get_json(silent=True) or {}
    rule_id = data.get("conduct_rule_id")
    idem    = data.get("idempotency_key") or str(uuid.uuid4())

    if not rule_id:
        return jsonify({"error": "conduct_rule_id is required."}), 400
    rule = db.session.get(ConductRule, rule_id)
    if not rule:
        return jsonify({"error": "Rule not found."}), 404

    # Idempotent: already signed this version
    existing = db.session.query(ConductSignature).filter_by(
        employee_id=profile.id, conduct_rule_id=rule_id
    ).first()
    if existing:
        return jsonify({"id": existing.id, "duplicate": True}), 200

    sig = ConductSignature(
        employee_id=profile.id,
        conduct_rule_id=rule_id,
        signed_proof=data.get("signed_proof"),
        idempotency_key=idem,
    )
    db.session.add(sig)
    db.session.flush()
    AuditLog.log(actor=actor.username, action="conduct.sign",
                 details=f"rule={rule_id} v{rule.version}")
    db.session.commit()
    return jsonify({
        "id": sig.id, "rule_key": rule.rule_key,
        "version": rule.version, "signed_at": sig.signed_at_utc.isoformat(),
    }), 201


@conduct_bp.get("/signatures/<employee_id>")
@require_active_user
def get_signatures(employee_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        # Employees can see their own
        profile = db.session.query(EmployeeProfile).filter_by(user_id=actor.id).first()
        if not profile or profile.id != employee_id:
            return jsonify({"error": "Manager or above required to view others' signatures."}), 403

    sigs = db.session.query(ConductSignature).filter_by(employee_id=employee_id).all()
    return jsonify([{
        "id": s.id,
        "rule_key": s.rule.rule_key if s.rule else None,
        "version": s.rule.version if s.rule else None,
        "title": s.rule.title if s.rule else None,
        "signed_at": s.signed_at_utc.isoformat(),
    } for s in sigs]), 200


# ── Compliance report ─────────────────────────────────────────────────────────

@conduct_bp.get("/compliance")
@require_active_user
def compliance_report():
    """
    Per active rule version: list employees who haven't signed.
    department query param filters by department.
    """
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < MANAGER_LEVEL:
        return jsonify({"error": "Manager or above required."}), 403

    dept_id = request.args.get("department_id")
    active_rules = db.session.query(ConductRule).filter_by(is_active=True).all()
    all_employees = db.session.query(EmployeeProfile).filter_by(is_active=True)
    if dept_id:
        # Filter employees by department via their User → Department
        all_employees = all_employees.join(
            User, EmployeeProfile.user_id == User.id
        ).filter(User.department_id == dept_id)
    all_employees = all_employees.all()

    report = []
    for rule in active_rules:
        signed_ids = {s.employee_id for s in db.session.query(ConductSignature).filter_by(
            conduct_rule_id=rule.id
        ).all()}
        unsigned = [e for e in all_employees if e.id not in signed_ids]
        published = rule.created_at_utc.strftime("%-d %b")
        report.append({
            "rule_id":           rule.id,
            "rule_key":          rule.rule_key,
            "title":             rule.title,
            "version":           rule.version,
            "unsigned_count":    len(unsigned),
            "unsigned_employees": [e.full_name for e in unsigned],
            "message": (
                f"{len(unsigned)} employee(s) haven't signed the updated "
                f"'{rule.title}' rule (v{rule.version}, published {published})."
                if unsigned else
                f"All employees have signed '{rule.title}' (v{rule.version})."
            ),
        })
    return jsonify(report), 200
