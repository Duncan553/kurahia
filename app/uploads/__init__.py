"""
uploads/ — File upload endpoints for images (menu, profile, receipt, villa).

All uploaded files go to the PWA's public/images/ directory so they're
served statically by Vite dev server and precached by the service worker.

Supports: JPEG, PNG, WebP. Max 5MB per file.
"""
import os
import uuid
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.auth_decorators import require_active_user
from app.extensions import db
from app.models.user import User
from app.models.audit_log import AuditLog

uploads_bp = Blueprint("uploads", __name__, url_prefix="/uploads")

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024

UPLOAD_TARGETS = {
    "menu": "employee_pwa/public/images/menu",
    "profile": "employee_pwa/public/images/profiles",
    "receipt": "employee_pwa/public/images/receipts",
    "villa": "employee_pwa/public/images/villas",
    "spa": "employee_pwa/public/images/spa",
    "water": "employee_pwa/public/images/water",
    "general": "employee_pwa/public/images/uploads",
}

MANAGER_LEVEL = 5

# Minimum role level per category. Invariant 7 says re-check role on EVERY
# request — this endpoint had only @require_active_user and no role check at
# all, so any level-1 staff member could overwrite the guest-facing menu
# photos, or drop a file into the receipts directory that cash reconciliation
# treats as evidence. The UI only offered menu uploads to managers, but the UI
# is not the security boundary.
#
# `profile` stays open: a staff member uploading their OWN photo is the point.
# `receipt` stays open because recording a purchase (which requires the receipt
# photo, app/models/purchase.py) is a normal staff duty.
UPLOAD_MIN_LEVEL = {
    "menu":    MANAGER_LEVEL,   # guest-facing content
    "villa":   MANAGER_LEVEL,   # guest-facing content
    "spa":     MANAGER_LEVEL,   # guest-facing content
    "water":   MANAGER_LEVEL,   # guest-facing content
    "general": MANAGER_LEVEL,   # untyped dumping ground — keep it narrow
    "profile": 0,
    "receipt": 0,
}


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _upload_dir(category: str) -> Path:
    # UPLOAD_ROOT lets the test config redirect writes to a tmp dir. Without it
    # the path was always <repo>/employee_pwa/public/images/..., so every run of
    # tests/test_uploads.py permanently littered the developer's working tree
    # with stub images that nothing ever references — that is where the ~50
    # untracked hash-named files in employee_pwa/public/images came from.
    base = Path(current_app.config.get("UPLOAD_ROOT") or Path(current_app.root_path).parent)
    target = UPLOAD_TARGETS.get(category, UPLOAD_TARGETS["general"])
    path = base / target
    path.mkdir(parents=True, exist_ok=True)
    return path


@uploads_bp.post("/<category>")
@require_active_user
def upload_file(category):
    """Upload an image file. Returns the public URL path."""
    actor = db.session.get(User, get_jwt_identity())
    if not actor:
        return jsonify({"error": "User not found."}), 404

    if category not in UPLOAD_TARGETS:
        return jsonify({"error": f"Unknown category '{category}'. Use: {list(UPLOAD_TARGETS.keys())}"}), 400

    min_level = UPLOAD_MIN_LEVEL.get(category, MANAGER_LEVEL)
    if actor.role.level < min_level:
        return jsonify({
            "error": f"Manager or above required to upload {category} images."
        }), 403

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Send as multipart/form-data with field name 'file'."}), 400

    file = request.files["file"]
    if not file.filename or not _allowed(file.filename):
        return jsonify({"error": f"File type not allowed. Use: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({"error": f"File too large. Maximum {MAX_FILE_SIZE // (1024*1024)}MB."}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex[:12]}.{ext}"
    dest = _upload_dir(category) / unique_name
    file.save(str(dest))

    # Derive the URL from where the file ACTUALLY went, not from the category
    # name. Those two disagree: UPLOAD_TARGETS maps "profile" -> images/profiles,
    # "receipt" -> images/receipts, "villa" -> images/villas — all plural — while
    # this line built "/images/profile/…" from the singular key. Every profile
    # photo, receipt scan and villa picture ever uploaded came back as a URL
    # pointing at a directory that does not exist: saved fine, 404 on display,
    # and nothing anywhere reported an error.
    #
    # One source of truth. Adding a category with a mismatched folder name can
    # no longer produce a dead link.
    folder = UPLOAD_TARGETS[category].rsplit("/", 1)[-1]
    public_path = f"/images/{folder}/{unique_name}"

    AuditLog.log(actor=actor.username, action=f"upload.{category}", target=unique_name)
    db.session.commit()

    return jsonify({"path": public_path, "filename": unique_name}), 201
