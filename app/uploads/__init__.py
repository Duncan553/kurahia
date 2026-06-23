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


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _upload_dir(category: str) -> Path:
    base = Path(current_app.root_path).parent
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

    public_path = f"/images/{category}/{unique_name}" if category != "general" else f"/images/uploads/{unique_name}"

    AuditLog.log(actor=actor.username, action=f"upload.{category}", target=unique_name)
    db.session.commit()

    return jsonify({"path": public_path, "filename": unique_name}), 201
