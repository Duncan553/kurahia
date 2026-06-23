"""
app/reports/__init__.py — PDF export endpoints.

Three reports:
  GET /reports/receipt/<tab_id>             — receipt PDF for a closed tab
  GET /reports/daily-summary?date=YYYY-MM-DD — daily operations summary PDF
  GET /reports/occupancy?from=YYYY-MM-DD&to=YYYY-MM-DD — villa occupancy report PDF

All return application/pdf with Content-Disposition: attachment.
Uses reportlab for PDF generation — no external dependencies beyond that.
"""
from .routes import pdf_reports_bp

__all__ = ["pdf_reports_bp"]
