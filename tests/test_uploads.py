"""
test_uploads.py — Tests for POST /uploads/<category>.

Covers valid uploads (PNG, JPEG, WebP), category gating, file-type
enforcement, size limits, missing-file handling, and auth.
"""
import io
import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def fake_image(filename="test.png", size=100):
    """
    Return a (BytesIO, filename) tuple that passes the extension check.
    Uses the minimal PNG magic bytes so seeks work correctly;
    the handler only checks the extension, not the actual file structure.
    """
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * max(0, size - 8)
    return (io.BytesIO(data), filename)


# ── Valid uploads ──────────────────────────────────────────────────────────────

def test_upload_png_to_menu(client, manager_token):
    """PNG → menu returns 201 with a /images/menu/ path."""
    rv = client.post(
        "/uploads/menu",
        data={"file": fake_image("photo.png")},
        content_type="multipart/form-data",
        headers=auth(manager_token),
    )
    assert rv.status_code == 201
    data = rv.get_json()
    assert "path" in data
    assert data["path"].startswith("/images/menu/")


def test_upload_jpeg_to_profile(client, manager_token):
    """JPEG → profile returns 201 with a path."""
    rv = client.post(
        "/uploads/profile",
        data={"file": fake_image("headshot.jpg")},
        content_type="multipart/form-data",
        headers=auth(manager_token),
    )
    assert rv.status_code == 201
    assert "path" in rv.get_json()


def test_upload_webp_to_general(client, manager_token):
    """WebP → general category uses the /images/uploads/ public path."""
    rv = client.post(
        "/uploads/general",
        data={"file": fake_image("banner.webp")},
        content_type="multipart/form-data",
        headers=auth(manager_token),
    )
    assert rv.status_code == 201
    assert rv.get_json()["path"].startswith("/images/uploads/")


def test_upload_returns_filename(client, manager_token):
    """Response includes a 'filename' field alongside 'path'."""
    rv = client.post(
        "/uploads/menu",
        data={"file": fake_image("menu_item.png")},
        content_type="multipart/form-data",
        headers=auth(manager_token),
    )
    assert rv.status_code == 201
    assert "filename" in rv.get_json()


# ── File-type enforcement ──────────────────────────────────────────────────────

def test_pdf_rejected(client, manager_token):
    """PDF extension → 400."""
    rv = client.post(
        "/uploads/menu",
        data={"file": (io.BytesIO(b"%PDF-1.4"), "document.pdf")},
        content_type="multipart/form-data",
        headers=auth(manager_token),
    )
    assert rv.status_code == 400


def test_exe_rejected(client, manager_token):
    """EXE extension → 400."""
    rv = client.post(
        "/uploads/menu",
        data={"file": (io.BytesIO(b"MZ"), "malware.exe")},
        content_type="multipart/form-data",
        headers=auth(manager_token),
    )
    assert rv.status_code == 400


# ── Request-shape validation ───────────────────────────────────────────────────

def test_missing_file_field_rejected(client, manager_token):
    """Multipart request with no 'file' field → 400."""
    rv = client.post(
        "/uploads/menu",
        data={},
        content_type="multipart/form-data",
        headers=auth(manager_token),
    )
    assert rv.status_code == 400


def test_unknown_category_rejected(client, manager_token):
    """Category not in UPLOAD_TARGETS → 400."""
    rv = client.post(
        "/uploads/unknown_category",
        data={"file": fake_image()},
        content_type="multipart/form-data",
        headers=auth(manager_token),
    )
    assert rv.status_code == 400


# ── Size limit ─────────────────────────────────────────────────────────────────

def test_file_over_5mb_rejected(client, manager_token):
    """6 MB PNG → 400 (MAX_FILE_SIZE = 5 MB)."""
    big = (io.BytesIO(b"\x00" * (6 * 1024 * 1024)), "big.png")
    rv = client.post(
        "/uploads/menu",
        data={"file": big},
        content_type="multipart/form-data",
        headers=auth(manager_token),
    )
    assert rv.status_code == 400


# ── Auth ───────────────────────────────────────────────────────────────────────

def test_unauthenticated_upload_rejected(client):
    """No JWT → 401 (require_active_user wraps jwt_required)."""
    rv = client.post(
        "/uploads/menu",
        data={"file": fake_image()},
        content_type="multipart/form-data",
    )
    assert rv.status_code == 401
