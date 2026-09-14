"""
Who may SEE room readiness, and who may change it.

"Which villa can I give this guest?" is asked at the front desk with a guest
standing there. The answer lives in the cleaning table, which front desk could
not read — so the desk either walked to the housekeeping tablet or guessed.

Reading is widened. Doing the work is not.
"""
from app.extensions import db


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


class TestHousekeepingVisibility:
    def test_front_desk_can_read_readiness(self, client, app):
        from app.models.user import User
        from app.models.role import Role
        from app.models.department import Department
        with app.app_context():
            fd_role = Role(name="front_desk", level=3)
            dept = db.session.query(Department).filter_by(name="Front-of-House").one()
            db.session.add(fd_role); db.session.flush()
            u = User(username="desk1", role_id=fd_role.id, department_id=dept.id)
            u.set_password("DeskPass1!")
            db.session.add(u); db.session.commit()
        tok = client.post("/auth/login",
                          json={"username": "desk1", "password": "DeskPass1!"}
                          ).get_json()["access_token"]
        assert client.get("/housekeeping/status", headers=_hdr(tok)).status_code == 200

    def test_a_waiter_still_cannot(self, client, waiter_token):
        """Widening the read is not opening it to everyone."""
        rv = client.get("/housekeeping/status", headers=_hdr(waiter_token))
        assert rv.status_code == 403

    def test_manager_can_read(self, client, manager_token):
        assert client.get("/housekeeping/status", headers=_hdr(manager_token)).status_code == 200
