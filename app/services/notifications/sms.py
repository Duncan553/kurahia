"""
SMS delivery socket.
Replace this function body with a real SMS gateway call (Africa's Talking, Twilio, etc.)
when credentials are available. Same shape as whatsapp.py — swap one function body.
"""


def send_sms(phone: str, body: str) -> tuple[str, str]:
    """
    Returns (status_code, message).
    SENT: delivered.
    UNCONFIGURED: gateway not set up — dispatcher marks notification FAILED.
    """
    # ← plug in SMS gateway here
    return ("UNCONFIGURED", "SMS gateway not connected.")
