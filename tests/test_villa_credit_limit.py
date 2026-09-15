"""
A room needs a ceiling, the way a wristband already has one.

Measured before writing this: a KSh 3,000 day wristband is stopped at KSh 6,000,
while an overnight villa — the far more expensive account — accepted a
KSh 500,000 charge without a word. check_band_credit returned (True, "") for
anything that was not a band.

It is a STOP, not a block: the message sends the guest to front house to settle
or to have the limit raised, and the limit is per-booking so raising it is one
guest's decision with a name on it, not a property-wide loosening.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest

from app.extensions import db
from app.models.tab import Tab, TabStatus, TabType
from app.models.booking import Booking
from app.services.tab import check_tab_credit, VILLA_DEFAULT_HEADROOM


@pytest.fixture
def villa_tab(app, manager_token):
    from app.models.user import User
    from app.models.bookable_resource import BookableResource
    with app.app_context():
        who = db.session.query(User).filter_by(username="manager1").one()
        res = db.session.query(BookableResource).first()
        if not res:
            res = BookableResource(name="Villa 9", resource_type="VILLA",
                                   base_price=Decimal("50000"))
            db.session.add(res); db.session.flush()
        tab = Tab(reference="Villa 9 / Test Guest", tab_type=TabType.VILLA.value,
                  status=TabStatus.OPEN.value, opened_by_id=who.id,
                  opened_at_utc=datetime.now(timezone.utc))
        db.session.add(tab); db.session.flush()
        b = Booking(resource_id=res.id, guest_name="Test Guest",
                    guest_phone="+254700000111",
                    check_in_planned_utc=datetime.now(timezone.utc),
                    check_out_planned_utc=datetime.now(timezone.utc) + timedelta(days=2),
                    base_total=Decimal("100000"), deposit_required=Decimal("30000"),
                    tab_id=tab.id, created_by_id=who.id,
                    idempotency_key=str(uuid.uuid4()))
        db.session.add(b); db.session.commit()
        return tab.id, b.id


class TestVillaCreditLimit:
    def test_a_charge_inside_the_limit_is_allowed(self, app, villa_tab):
        tab_id, _ = villa_tab
        with app.app_context():
            ok, _ = check_tab_credit(tab_id, Decimal("1000"))
            assert ok is True

    def test_the_unlimited_charge_is_now_refused(self, app, villa_tab):
        """The exact probe that exposed this: KSh 500,000 onto a room."""
        tab_id, _ = villa_tab
        with app.app_context():
            ok, msg = check_tab_credit(tab_id, Decimal("500000"))
            assert ok is False
            assert "front house" in msg.lower()

    def test_the_default_limit_is_the_stay_plus_an_extras_allowance(self, app, villa_tab):
        """The baseline moved, and this is why.

        It used to be deposit + headroom. But the WHOLE STAY is charged to the
        folio at check-in, so a 100,000 villa with a 30,000 deposit sat at
        70,000 against a 50,000 ceiling before the guest had bought anything —
        room service was refused on a room that had spent nothing, which is how
        it was reported from the floor.

        The room is not the risk: it is committed and the deposit secures it.
        What needs a ceiling is what a guest can run up ON TOP of it, so the
        limit is the stay's own value plus the extras allowance."""
        tab_id, _ = villa_tab
        with app.app_context():
            limit = Decimal("100000") + VILLA_DEFAULT_HEADROOM   # base_total, not deposit
            assert check_tab_credit(tab_id, limit - Decimal("1"))[0] is True
            assert check_tab_credit(tab_id, limit + Decimal("1"))[0] is False

    def test_a_lunch_on_an_unpaid_room_is_not_refused(self, app, villa_tab):
        """The bug in one line: the stay is on the folio, the guest orders lunch."""
        tab_id, _ = villa_tab
        with app.app_context():
            from app.models.charge import Charge
            from app.models.user import User as _U
            who = db.session.query(_U).filter_by(username="manager1").one()
            db.session.add(Charge(tab_id=tab_id, amount=Decimal("100000"),
                                  description="Accommodation — Villa 9, 1 night",
                                  created_by_id=who.id,
                                  idempotency_key=str(uuid.uuid4())))
            db.session.commit()
            ok, msg = check_tab_credit(tab_id, Decimal("1800"))
            assert ok is True, msg

    def test_front_house_can_raise_it_for_one_guest(self, app, villa_tab):
        tab_id, booking_id = villa_tab
        with app.app_context():
            b = db.session.get(Booking, booking_id)
            b.credit_limit = Decimal("400000")
            db.session.commit()
            assert check_tab_credit(tab_id, Decimal("300000"))[0] is True
            assert check_tab_credit(tab_id, Decimal("500000"))[0] is False

    def test_a_walk_in_table_is_untouched(self, app, manager_token):
        """Only rooms and bands have ceilings; a table settles at the table."""
        from app.models.user import User
        with app.app_context():
            who = db.session.query(User).filter_by(username="manager1").one()
            t = Tab(reference="Terrace 2", tab_type=TabType.WALK_IN.value,
                    status=TabStatus.OPEN.value, opened_by_id=who.id,
                    opened_at_utc=datetime.now(timezone.utc))
            db.session.add(t); db.session.commit()
            assert check_tab_credit(t.id, Decimal("500000"))[0] is True
