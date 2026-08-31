"""
services/payment_attach.py — put money that arrived on its own onto the right tab.

THE PROBLEM. Most payments know their tab because we started them: a cashier
taps a tab and records cash, or an STK push is fired at a specific tab and the
callback carries the id back. Two paths do NOT:

  M-Pesa C2B    the guest pays the paybill straight from their phone. Safaricom
                tells us a number and a receipt. It does not tell us who.
  Bank SMS      a transfer lands and the forwarder reads the alert. Same story.

Both wrote a Payment with tab_id=NULL. The money was real, it counted in
revenue, and it settled NOBODY'S bill — so a guest who paid their villa by
bank transfer still showed the full room outstanding and was refused check-out
at the desk while their money sat in the ledger.

There is no way to guess the owner from an SMS, and guessing would be worse
than not trying. A HUMAN knows: the guest in Villa 6 says "I sent it", the
manager looks at the reconciliation screen and matches the two. This is that
step, so the reconcile screens can finish the job they start.

Filling a NULL tab_id, never moving an attached one — the same rule the villa
deposit follows. Balances stay derived, so the tab reflects it immediately.
"""
from app.extensions import db
from app.models.tab import Tab, TabStatus
from app.models.payment import Payment


def attach_payment_to_tab(payment: Payment, tab_id: str) -> tuple[bool, str]:
    """Attach an unattached payment to a tab.

    Returns (ok, plain-English reason). Refuses rather than moving money that
    already belongs somewhere: re-pointing a payment that is already on a tab
    would silently change TWO balances, and whoever reads the second one has no
    way of knowing why it moved.
    """
    if payment.tab_id == tab_id:
        return True, ""                      # already there; a re-match is fine

    if payment.tab_id is not None:
        return False, ("This payment is already settled against another bill. "
                       "Reverse it there first if it was matched by mistake.")

    tab = db.session.get(Tab, tab_id)
    if not tab:
        return False, "That bill could not be found."
    if tab.status == TabStatus.CLOSED.value:
        return False, ("That bill is already closed. Re-open it or record the "
                       "money against the guest's new bill.")

    payment.tab_id = tab_id
    return True, ""
