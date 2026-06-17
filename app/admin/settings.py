"""
admin/settings.py — System settings CRUD. Owner only.
GET  /admin/settings
PATCH /admin/settings
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.models.audit_log import AuditLog

settings_bp = Blueprint("admin_settings", __name__, url_prefix="/admin/settings")

OWNER_LEVEL = 10

KNOWN_KEYS = {
    "business_day_start_hour": {"type": "int", "min": 0, "max": 23, "default": "6"},
}


@settings_bp.get("")
@require_active_user
def get_settings():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can view system settings."}), 403

    result = {}
    for key, meta in KNOWN_KEYS.items():
        row = db.session.get(SystemSetting, key)
        result[key] = row.value if row else meta["default"]
    return jsonify(result), 200


@settings_bp.patch("")
@require_active_user
def update_settings():
    actor = db.session.get(User, get_jwt_identity())
    if actor.role.level < OWNER_LEVEL:
        return jsonify({"error": "Only the owner can change system settings."}), 403

    data = request.get_json(silent=True) or {}
    updated = []

    for key, val in data.items():
        if key not in KNOWN_KEYS:
            continue
        meta = KNOWN_KEYS[key]
        if meta["type"] == "int":
            try:
                v = int(val)
            except (ValueError, TypeError):
                return jsonify({"error": f"{key} must be an integer."}), 400
            if v < meta["min"] or v > meta["max"]:
                return jsonify({"error": f"{key} must be between {meta['min']} and {meta['max']}."}), 400

        with db.session.begin_nested():
            row = db.session.get(SystemSetting, key)
            if row:
                row.value = str(val)
            else:
                db.session.add(SystemSetting(key=key, value=str(val)))

        AuditLog.log(actor=actor.username, action="admin.setting.update",
                     target=key, details=f"value={val}")
        updated.append(key)

    db.session.commit()
    return jsonify({"updated": updated}), 200
