"""Shared helpers for tests that need an account to charge against.

The floor can no longer open an account with nobody attached: every bill at
this resort belongs to a wristband or a room (app/pos/tabs.py::open_tab). A
waiter asking for a nameless "Table 7" now gets a 403 telling them to take the
guest's band number or open their room.

Most POS tests do not care how the account came to exist — they care what
happens to an order, a charge or a payment once one does. Rather than teach
every file to issue a wristband first, they open the account through the
manager override, which is the same door a duty manager uses when a band is
lost or the gate tablet is down.

Tests that are ABOUT the rule (who may open what) do not use this: they call
the endpoint directly and assert the refusal.
"""


def manager_auth(client):
    """Headers for manager1 — the role allowed to open an account by hand.

    Clocks them in as well: POST /tabs carries @require_clocked_in, and a
    manager who exists but is off duty is refused exactly like anyone else.
    """
    from tests.conftest import _clock_in, _get_or_create_profile
    rv = client.post("/auth/login",
                     json={"username": "manager1", "password": "ManagerPass1!"})
    _clock_in(_get_or_create_profile("manager1", "Test Manager", "+254700000002"))
    return {"Authorization": f"Bearer {rv.get_json()['access_token']}"}


def open_tab(client, reference="Table 9", assign_to=None, **fields):
    """Open an account a POS test can charge against. Returns the tab dict.

    `assign_to` is a username: the manager opens the account and hands the
    table to that person, which is how a floor works now — the account exists
    before the waiter reaches it, and being ASSIGNED is what makes it theirs.
    Tests that used to say "the waiter opened it" mean this.
    """
    payload = {"reference": reference, **fields}
    rv = client.post("/tabs", json=payload, headers=manager_auth(client))
    assert rv.status_code == 201, rv.get_json()
    tab = rv.get_json()

    if assign_to:
        from app.extensions import db
        from app.models.user import User
        user = db.session.query(User).filter_by(username=assign_to).first()
        assert user, f"no such user: {assign_to}"
        rv = client.post(f"/tabs/{tab['id']}/assign", json={"employee_id": user.id},
                         headers=manager_auth(client))
        assert rv.status_code == 200, rv.get_json()
    return tab
