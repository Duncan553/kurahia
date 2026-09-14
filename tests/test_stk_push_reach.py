"""
The person standing at the table can send the M-Pesa prompt.

/finance/mpesa/charge was gated at MANAGER_LEVEL, which put it out of reach of
the only person who is ever holding the bill. A waiter is level 1.

Prompting is the SAFER of the two acts: recording a payment by hand lets a
staff member assert money arrived when none did, while a prompt cannot move
anything without the guest entering their own PIN. Holding the safer path to a
higher bar pushed everyone onto the weaker one.
"""
import pytest


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


BODY = {"amount": 100, "phone_number": "0712345678",
        "tab_id": "t-1", "payment_id": "p-1"}


class TestWhoMaySendThePrompt:
    def test_a_waiter_is_not_refused_for_being_a_waiter(self, client, waiter_token):
        """The socket is dormant in tests, so the honest pass mark is: NOT 403.

        503 means "reached the handler, integration not configured" — which is
        the correct answer here and proves the permission no longer blocks."""
        rv = client.post("/finance/mpesa/charge", json=BODY, headers=_hdr(waiter_token))
        assert rv.status_code != 403, rv.get_json()
        assert rv.status_code == 503
        assert "not configured" in rv.get_json()["error"].lower()

    def test_the_dormant_answer_tells_you_what_to_do_instead(self, client, waiter_token):
        """Invariant 5. A waiter with a guest waiting needs the fallback named."""
        rv = client.post("/finance/mpesa/charge", json=BODY, headers=_hdr(waiter_token))
        assert "manual" in rv.get_json().get("fallback", "").lower()

    def test_a_manager_can_still_send_it(self, client, manager_token):
        rv = client.post("/finance/mpesa/charge", json=BODY, headers=_hdr(manager_token))
        assert rv.status_code != 403

    def test_being_signed_in_is_not_enough(self, client, app):
        """Matches POST /tabs/<id>/payments: taking money needs you on shift.

        The exact sentence depends on WHY you are not on shift — no profile, or
        a profile that has not clocked in — so this pins the refusal and that it
        explains itself, not one particular wording."""
        rv = client.post("/auth/login", json={"username": "waiter1", "password": "WaiterPass1!"})
        tok = rv.get_json()["access_token"]          # signed in, never clocked in
        rv = client.post("/finance/mpesa/charge", json=BODY, headers=_hdr(tok))
        assert rv.status_code == 403
        msg = rv.get_json()["error"]
        assert msg and msg[0].isupper() and msg.endswith("."), msg
