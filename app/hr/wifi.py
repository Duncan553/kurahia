"""
hr/wifi.py — WiFiAllowList management (owner-only).
Owner adds/removes/edits allowed networks. The clock-in endpoint validates against this.
"""
import ipaddress
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.wifi_allow_list import WiFiAllowList
from app.models.audit_log import AuditLog

wifi_bp = Blueprint("hr_wifi", __name__, url_prefix="/hr")

OWNER_LEVEL = 10


def _validate_cidr(cidr_str: str) -> bool:
    try:
        ipaddress.ip_network(cidr_str, strict=False)
        return True
    except ValueError:
        return False


@wifi_bp.post("/wifi")
@require_active_user
def create_wifi():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can manage the WiFi allow-list."}), 403

    data    = request.get_json(silent=True) or {}
    ssid    = (data.get("ssid") or "").strip()
    ip_cidr = (data.get("ip_cidr") or "").strip()
    label   = (data.get("label") or "").strip() or None

    if not ssid or not ip_cidr:
        return jsonify({"error": "ssid and ip_cidr are required."}), 400
    if not _validate_cidr(ip_cidr):
        return jsonify({"error": f"'{ip_cidr}' is not a valid CIDR range (e.g. 192.168.1.0/24)."}), 400

    entry = WiFiAllowList(ssid=ssid, ip_cidr=ip_cidr, label=label)
    db.session.add(entry)
    db.session.commit()
    AuditLog.log(actor=actor.username, action="hr.wifi.create",
                 details=f"ssid={ssid} cidr={ip_cidr}")
    db.session.commit()
    return jsonify({"id": entry.id, "ssid": ssid, "ip_cidr": ip_cidr}), 201


@wifi_bp.get("/wifi")
@require_active_user
def list_wifi():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can view the WiFi allow-list."}), 403
    include_disabled = request.args.get("include_disabled", "false").lower() == "true"
    query = db.session.query(WiFiAllowList)
    if not include_disabled:
        query = query.filter_by(is_active=True)
    entries = query.all()
    return jsonify([{
        "id": e.id, "ssid": e.ssid, "ip_cidr": e.ip_cidr,
        "label": e.label, "is_active": e.is_active,
    } for e in entries]), 200


@wifi_bp.patch("/wifi/<entry_id>")
@require_active_user
def edit_wifi(entry_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can edit the WiFi allow-list."}), 403
    entry = db.session.get(WiFiAllowList, entry_id)
    if not entry:
        return jsonify({"error": "WiFi entry not found."}), 404
    data = request.get_json(silent=True) or {}
    if "ssid" in data:
        entry.ssid = data["ssid"].strip()
    if "ip_cidr" in data:
        if not _validate_cidr(data["ip_cidr"]):
            return jsonify({"error": f"'{data['ip_cidr']}' is not a valid CIDR range."}), 400
        entry.ip_cidr = data["ip_cidr"].strip()
    if "label" in data:
        entry.label = data["label"]
    db.session.commit()
    AuditLog.log(actor=actor.username, action="hr.wifi.edit", target=entry_id)
    db.session.commit()
    return jsonify({"id": entry.id, "ssid": entry.ssid, "ip_cidr": entry.ip_cidr,
                    "is_active": entry.is_active}), 200


@wifi_bp.post("/wifi/<entry_id>/disable")
@require_active_user
def disable_wifi(entry_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can disable WiFi entries."}), 403
    entry = db.session.get(WiFiAllowList, entry_id)
    if not entry:
        return jsonify({"error": "WiFi entry not found."}), 404
    entry.is_active = False
    db.session.commit()
    AuditLog.log(actor=actor.username, action="hr.wifi.disable", target=entry_id)
    db.session.commit()
    return jsonify({"id": entry.id, "is_active": False}), 200


@wifi_bp.post("/wifi/<entry_id>/enable")
@require_active_user
def enable_wifi(entry_id):
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can enable WiFi entries."}), 403
    entry = db.session.get(WiFiAllowList, entry_id)
    if not entry:
        return jsonify({"error": "WiFi entry not found."}), 404
    entry.is_active = True
    db.session.commit()
    AuditLog.log(actor=actor.username, action="hr.wifi.enable", target=entry_id)
    db.session.commit()
    return jsonify({"id": entry.id, "is_active": True}), 200
