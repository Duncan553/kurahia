"""
reports/pdf_helpers.py — Reusable reportlab drawing helpers for all PDF reports.

Keeps layout constants and shared functions in one place so each report
endpoint stays lean. Every function takes a Canvas and a y-position,
draws content, and returns the updated y-position.
"""
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# ── Layout constants ─────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4                # 210mm × 297mm
MARGIN = 20 * mm                   # left/right margin
CONTENT_W = PAGE_W - 2 * MARGIN    # usable width
LINE_H = 5 * mm                    # standard line height
RESORT_NAME = "Waterfront Kurahia Resort"


def new_pdf_buffer() -> tuple[BytesIO, canvas.Canvas]:
    """Create an in-memory PDF buffer and canvas."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    return buf, c


def draw_header(c: canvas.Canvas, y: float, title: str, subtitle: str = "") -> float:
    """Draw resort name + report title at the top. Returns new y position."""
    # Resort name
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN, y, RESORT_NAME)
    y -= 6 * mm

    # Report title
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, title)
    y -= 5 * mm

    # Subtitle (date range, tab ref, etc.)
    if subtitle:
        c.setFont("Helvetica", 9)
        c.drawString(MARGIN, y, subtitle)
        y -= 5 * mm

    # Divider line
    y -= 2 * mm
    c.setLineWidth(0.5)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 4 * mm

    return y


def draw_table_header(c: canvas.Canvas, y: float, columns: list[tuple[str, float]]) -> float:
    """Draw a grey-background header row. columns = [(label, x_pos), ...]."""
    # Light grey background
    c.setFillColorRGB(0.9, 0.9, 0.9)
    c.rect(MARGIN, y - 1 * mm, CONTENT_W, 5 * mm, fill=True, stroke=False)

    # Header text
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 8)
    for label, x in columns:
        c.drawString(x, y, label)
    y -= 5 * mm

    return y


def draw_row(c: canvas.Canvas, y: float, values: list[tuple[str, float]],
             bold: bool = False) -> float:
    """Draw one data row. values = [(text, x_pos), ...]."""
    font = "Helvetica-Bold" if bold else "Helvetica"
    c.setFont(font, 8)
    for text, x in values:
        c.drawString(x, y, str(text))
    y -= LINE_H
    return y


def draw_right_aligned(c: canvas.Canvas, y: float, text: str,
                       font: str = "Helvetica", size: int = 8) -> float:
    """Draw text right-aligned to the right margin."""
    c.setFont(font, size)
    c.drawRightString(PAGE_W - MARGIN, y, text)
    return y


def draw_divider(c: canvas.Canvas, y: float) -> float:
    """Draw a thin horizontal divider line."""
    c.setLineWidth(0.3)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 3 * mm
    return y


def draw_section_title(c: canvas.Canvas, y: float, title: str) -> float:
    """Draw a bold section title."""
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, y, title)
    y -= 6 * mm
    return y


def draw_kv(c: canvas.Canvas, y: float, label: str, value: str,
            label_x: float = None) -> float:
    """Draw a key: value pair on one line."""
    x = label_x or MARGIN
    c.setFont("Helvetica", 8)
    c.drawString(x, y, f"{label}:")
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x + 80 * mm, y, str(value))
    y -= LINE_H
    return y


def check_page_break(c: canvas.Canvas, y: float, needed: float = 30 * mm) -> float:
    """If y is too close to the bottom, start a new page."""
    if y < needed:
        c.showPage()
        y = PAGE_H - MARGIN
    return y


def finalize_pdf(c: canvas.Canvas, buf: BytesIO) -> bytes:
    """Save the canvas and return raw PDF bytes."""
    c.save()
    buf.seek(0)
    return buf.read()
