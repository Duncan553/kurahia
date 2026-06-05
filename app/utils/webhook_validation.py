"""
utils/webhook_validation.py — Shared payload hygiene checks for public webhook endpoints.

Called by all three public callback endpoints BEFORE processing:
  POST /finance/mpesa/callback
  POST /finance/bank/sms-forward
  POST /finance/card/callback

Returns (True, None) if the payload passes all checks.
Returns (False, "plain English reason") if any check fails.
Endpoints still return 200 to the caller on failure (never trigger retries).
"""
from flask import Request

_DEFAULT_MAX_BYTES = 100_000   # 100 KB — well under nginx 10M limit, catches abuse early


def validate_webhook_payload(
    request: Request, max_size_bytes: int = _DEFAULT_MAX_BYTES
) -> tuple[bool, str | None]:
    """
    Basic hygiene checks for incoming webhook payloads.

    Checks (in order):
    1. Content-Type must be application/json
    2. Body must not be empty
    3. Body must be parseable JSON
    4. Body must not exceed max_size_bytes
    """
    content_type = request.content_type or ""
    if "application/json" not in content_type.lower():
        return False, f"Invalid Content-Type '{content_type}' — expected application/json."

    raw = request.get_data()
    if not raw:
        return False, "Empty request body."

    if len(raw) > max_size_bytes:
        return False, f"Payload too large: {len(raw)} bytes (limit {max_size_bytes})."

    # JSON parseability — get_json(silent=True) returns None on failure
    if request.get_json(silent=True) is None:
        return False, "Request body is not valid JSON."

    return True, None
