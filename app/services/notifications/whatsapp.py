"""
WhatsApp delivery socket.
Replace this function body with a real WhatsApp Business API call when the account is ready.
The dispatcher calls this; UNCONFIGURED is a first-class outcome, surfaced to the owner.
"""


def send_whatsapp(phone: str, body: str) -> tuple[str, str]:
    """
    Returns (status_code, message).
    SENT: delivered.
    UNCONFIGURED: gateway not set up — dispatcher falls back to SMS.
    """
    # ← plug in WhatsApp Business API here when credentials are available
    return ("UNCONFIGURED", "WhatsApp gateway not connected.")
