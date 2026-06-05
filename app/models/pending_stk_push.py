"""
PendingSTKPush — short-lived record linking a Daraja STK Push checkout_request_id
to the originating tab. Persisted in DB so server restarts don't orphan in-flight pushes.

Row is created when initiate_stk_push() succeeds and deleted when handle_stk_callback()
confirms payment. Rows older than expires_at_utc are eligible for cleanup via
`flask mpesa cleanup-expired-stk`.

If cleanup removes a row before its callback arrives, the payment still lands via
idempotency but without a tab assignment — it goes to Pending Payments for manual
assignment. Acceptable fallback (same as before persistence was added).
"""
import uuid
from datetime import datetime, timezone, timedelta
from app.extensions import db


class PendingSTKPush(db.Model):
    __tablename__ = "pending_stk_pushes"

    id                  = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    checkout_request_id = db.Column(db.String(128), nullable=False, unique=True, index=True)
    tab_id              = db.Column(db.String(36), nullable=True)
    payment_id          = db.Column(db.String(36), nullable=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    # Safaricom STK Push expires in ~5 min; give an extra hour before cleanup sweep
    expires_at_utc = db.Column(db.DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return f"<PendingSTKPush checkout={self.checkout_request_id[:20]} tab={self.tab_id}>"
