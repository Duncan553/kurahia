"""
test_scenarios_owner.py — adversarial scenarios for the OWNER boundary.

The question this file asks, over and over, is not "does the UI hide it?" but
"can a manager REACH it?".  Every BAD-path test below is written from the
attacker's chair: the actor is manager1 (level 5) or waiter1 (level 1), and the
target is something only owner1 (level 10) is supposed to touch.

Levels (seeded in conftest): owner=10, manager=5, head_chef=3, staff/waiter=1.

Three tests are named `test_HOLE_*`.  Those assert the CURRENT, BROKEN
behaviour on purpose so the suite stays green while the finding is on record.
When the hole is fixed those tests will fail loudly — that is the signal to
flip the assertion, not to delete the test.  Each one names the file and line.
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from app.extensions import db


# ── helpers ───────────────────────────────────────────────────────────────────

def H(token):
    """Authorization header for a JWT."""
    return {"Authorization": f"Bearer {token}"}


def _user_id(username):
    from app.models.user import User
    return db.session.query(User).filter_by(username=username).first().id


def _role_id(name):
    from app.models.role import Role
    return db.session.query(Role).filter_by(name=name).first().id


def _profile_id(username):
    """EmployeeProfile id for a username — the *_token fixtures create these."""
    from app.models.employee_profile import EmployeeProfile
    from app.models.user import User
    u = db.session.query(User).filter_by(username=username).first()
    return db.session.query(EmployeeProfile).filter_by(user_id=u.id).first().id


CANARY = "CANARY-8f3a-the-manager-took-4000-from-the-till"


@pytest.fixture
def private_suggestion(client, waiter_token):
    """An anonymous OWNER_PRIVATE suggestion accusing the manager.

    Submitted by a level-1 waiter, which is the real-world shape: the person
    with the least power is the one who needs the channel to be airtight.
    """
    rv = client.post("/suggestions", headers=H(waiter_token), json={
        "category": "OWNER_PRIVATE",
        "subject": "Cash missing from the bar float",
        "body": CANARY,
        "anonymous": True,
    })
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()["id"]


@pytest.fixture
def owner_only_dispute(client, waiter_token, waiter_profile):
    """An is_owner_only dispute naming the manager as its subject."""
    rv = client.post("/disputes", headers=H(waiter_token), json={
        "category": "CONDUCT_VIOLATION",
        "description": CANARY,
        "priority": "HIGH",
        "is_owner_only": True,
    })
    assert rv.status_code == 201, rv.get_json()
    return rv.get_json()["id"]


@pytest.fixture
def open_alert(app):
    """One OPEN JudgeAlert — the theft-detection engine pointing at manager1."""
    from app.models.judge_alert import JudgeAlert, AlertStatus, AlertSeverity
    a = JudgeAlert(
        alert_type="VARIANCE",
        severity=AlertSeverity.HIGH.value,
        description=f"Stock variance on Tusker Lager — {CANARY}",
        status=AlertStatus.OPEN.value,
    )
    db.session.add(a)
    db.session.commit()
    return a.id


# ═══════════════════════════════════════════════════════════════════════════════
# 1. OWNER_PRIVATE SUGGESTIONS — structural absence, attacked from every angle
# ═══════════════════════════════════════════════════════════════════════════════

def test_owner_sees_the_private_suggestion(client, owner_token, private_suggestion):
    """GOOD path — the whole point of the channel."""
    rv = client.get("/suggestions", headers=H(owner_token))
    assert rv.status_code == 200
    assert private_suggestion in [s["id"] for s in rv.get_json()]

    rv = client.get(f"/suggestions/{private_suggestion}", headers=H(owner_token))
    assert rv.status_code == 200
    assert rv.get_json()["body"] == CANARY


def test_manager_list_omits_the_private_suggestion(client, manager_token, private_suggestion):
    """BAD path — the row is filtered out of the query, not the template."""
    rv = client.get("/suggestions", headers=H(manager_token))
    assert rv.status_code == 200
    assert rv.get_json() == []                      # not even a redacted stub
    assert CANARY not in rv.get_data(as_text=True)


def test_manager_direct_get_by_id_is_a_404_not_a_403(client, manager_token, private_suggestion):
    """A 403 would confirm the row EXISTS. It must be indistinguishable from
    a suggestion id the attacker invented."""
    real = client.get(f"/suggestions/{private_suggestion}", headers=H(manager_token))
    fake = client.get(f"/suggestions/{uuid.uuid4()}", headers=H(manager_token))
    assert real.status_code == 404
    assert fake.status_code == 404
    assert real.get_json() == fake.get_json()       # byte-identical denial


def test_manager_cannot_review_the_private_suggestion(client, manager_token, private_suggestion):
    rv = client.post(f"/suggestions/{private_suggestion}/review",
                     headers=H(manager_token), json={"status": "DISMISSED"})
    assert rv.status_code == 404

    # And it really was not written to — the owner still sees it as NEW.
    from app.models.suggestion import Suggestion
    assert db.session.get(Suggestion, private_suggestion).status == "NEW"


def test_status_filter_cannot_be_used_to_smuggle_the_row_out(client, manager_token,
                                                             private_suggestion):
    """The category filter is applied BEFORE the caller-supplied status filter,
    so no combination of query params reaches an OWNER_PRIVATE row."""
    for status in ("NEW", "UNDER_REVIEW", "ACTIONED", "DISMISSED", "", "%", "' OR 1=1--"):
        rv = client.get(f"/suggestions?status={status}", headers=H(manager_token))
        assert rv.status_code == 200
        assert CANARY not in rv.get_data(as_text=True)


def test_manager_cannot_learn_the_count_of_private_suggestions(client, manager_token,
                                                               waiter_token):
    """Even the NUMBER of private suggestions is owner-only information —
    a manager who can watch the count tick up knows someone reported them."""
    for i in range(3):
        client.post("/suggestions", headers=H(waiter_token), json={
            "category": "OWNER_PRIVATE", "subject": f"p{i}", "body": CANARY,
            "anonymous": True,
        })
    client.post("/suggestions", headers=H(waiter_token), json={
        "category": "MANAGEMENT", "subject": "public", "body": "more forks please",
    })
    rv = client.get("/suggestions", headers=H(manager_token))
    assert len(rv.get_json()) == 1                   # only the MANAGEMENT one

    # /dashboard/suggestions and /dashboard/staff both publish the private
    # count — both must slam the door on a manager.
    assert client.get("/dashboard/suggestions", headers=H(manager_token)).status_code == 403
    assert client.get("/dashboard/staff",       headers=H(manager_token)).status_code == 403


def test_level_1_staff_cannot_list_suggestions_at_all(client, waiter_token, private_suggestion):
    """The waiter who FILED it still cannot read the queue back."""
    assert client.get("/suggestions", headers=H(waiter_token)).status_code == 403
    assert client.get(f"/suggestions/{private_suggestion}",
                      headers=H(waiter_token)).status_code == 403


def test_HOLE_manager_reads_owner_private_suggestion_via_notifications(
        client, manager_token, private_suggestion):
    """HOLE — app/notifications/core.py:79-91 (`GET /notifications`).

    The endpoint is gated at MANAGER_LEVEL and, with no `user_id` param, is not
    scoped to the caller at all: it returns the newest 100 notifications for
    EVERY recipient, including the owner's.

    app/suggestions/core.py:105-114 puts the first 200 characters of an
    OWNER_PRIVATE suggestion into that notification's `body`, its subject into
    `subject`, and its id into `reference_id`.

    Net effect: the query-layer filter in list_suggestions/get_suggestion is
    perfect and completely bypassed. The manager reads the accusation in full,
    learns who is being told, and gets the row id — one endpoint over.

    Verified by running it: the manager's response body literally contains the
    CANARY string planted in the suggestion.
    """
    rv = client.get("/notifications", headers=H(manager_token))
    assert rv.status_code == 200

    leaked = [n for n in rv.get_json()
              if n["reference_type"] == "SUGGESTION_OWNER"]
    assert leaked, "fixture did not create the owner notification"
    assert CANARY in leaked[0]["body"]                       # ← the hole
    assert leaked[0]["reference_id"] == private_suggestion   # ← and the row id


def test_HOLE_manager_can_target_the_owners_inbox_by_user_id(client, manager_token,
                                                             private_suggestion):
    """Same hole, aimed. `?user_id=` takes any id, including the owner's, and
    /auth/users (app/auth/users.py:204) hands a manager the owner's id for free.
    """
    owner_id = _user_id("owner1")
    assert owner_id in [u["id"] for u in
                        client.get("/auth/users", headers=H(manager_token)).get_json()]

    rv = client.get(f"/notifications?user_id={owner_id}", headers=H(manager_token))
    assert rv.status_code == 200
    assert CANARY in rv.get_data(as_text=True)               # ← the owner's inbox


def test_password_reset_warning_to_the_owner_is_also_readable_by_the_manager(
        client, manager_token):
    """The credential-seizure warning (app/auth/users.py:29-69) exists so the
    owner learns a manager reset a subordinate's password. Through the same
    unscoped inbox the manager can read that warning — and therefore confirm
    whether the owner has been told yet."""
    staff_id = _user_id("staff1")
    rv = client.patch(f"/auth/users/{staff_id}", headers=H(manager_token),
                      json={"password": "NewPass123!"})
    assert rv.status_code == 200

    rv = client.get("/notifications", headers=H(manager_token))
    bodies = " ".join(n["body"] or "" for n in rv.get_json())
    assert "reset the password" in bodies                     # ← visible to the actor


# ═══════════════════════════════════════════════════════════════════════════════
# 2. OWNER-ONLY DISPUTES (is_owner_only)
# ═══════════════════════════════════════════════════════════════════════════════

def test_owner_sees_and_can_claim_the_owner_only_dispute(client, owner_token,
                                                         owner_only_dispute):
    rv = client.get("/disputes", headers=H(owner_token))
    assert owner_only_dispute in [d["id"] for d in rv.get_json()]

    rv = client.post(f"/disputes/{owner_only_dispute}/claim", headers=H(owner_token))
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "UNDER_REVIEW"


def test_manager_list_omits_the_owner_only_dispute(client, manager_token,
                                                   owner_only_dispute):
    rv = client.get("/disputes", headers=H(manager_token))
    assert rv.status_code == 200
    assert owner_only_dispute not in [d["id"] for d in rv.get_json()]
    assert CANARY not in rv.get_data(as_text=True)


def test_manager_cannot_claim_resolve_or_dismiss_an_owner_only_dispute(
        client, manager_token, owner_only_dispute):
    """Every lifecycle verb goes through _get_dispute_visible (disputes/core.py:111),
    so all three return the same structural 404."""
    for path, body in (("claim", {}),
                       ("resolve", {"resolution_notes": "nothing to see"}),
                       ("dismiss", {"reason": "unfounded"})):
        rv = client.post(f"/disputes/{owner_only_dispute}/{path}",
                         headers=H(manager_token), json=body)
        assert rv.status_code == 404, path

    from app.models.dispute import Dispute
    assert db.session.get(Dispute, owner_only_dispute).status == "OPEN"


def test_manager_cannot_filter_an_owner_only_dispute_into_view(client, manager_token,
                                                               owner_only_dispute):
    for status in ("OPEN", "UNDER_REVIEW", "RESOLVED", "DISMISSED", ""):
        rv = client.get(f"/disputes?status={status}", headers=H(manager_token))
        assert rv.status_code == 200
        assert owner_only_dispute not in [d["id"] for d in rv.get_json()]


def test_manager_cannot_learn_the_owner_only_dispute_count(client, manager_token,
                                                           owner_only_dispute):
    """/dashboard/staff publishes open_disputes.owner_private — owner-gated."""
    assert client.get("/dashboard/staff", headers=H(manager_token)).status_code == 403
    assert client.get("/dashboard/conduct", headers=H(manager_token)).status_code == 403


def test_the_filer_can_still_see_their_own_owner_only_dispute(client, waiter_token,
                                                              owner_only_dispute):
    """Documented, deliberate: disputes/core.py:203-207 scopes a level-1 actor to
    disputes they reported. They wrote it, so it is not a disclosure — but note
    that it means `is_owner_only` is confidentiality FROM MANAGEMENT, not
    anonymity from the filer's own session."""
    rv = client.get("/disputes", headers=H(waiter_token))
    assert rv.status_code == 200
    assert owner_only_dispute in [d["id"] for d in rv.get_json()]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. OWNER-ONLY ENDPOINTS — the manager and the waiter both get 403
# ═══════════════════════════════════════════════════════════════════════════════

WIFI_ROUTES = [
    ("GET",  "/hr/wifi",                  None),
    ("POST", "/hr/wifi",                  {"ssid": "evil", "ip_cidr": "0.0.0.0/0"}),
    ("PATCH", "/hr/wifi/{id}",            {"ip_cidr": "0.0.0.0/0"}),
    ("POST", "/hr/wifi/{id}/disable",     {}),
    ("POST", "/hr/wifi/{id}/enable",      {}),
]


@pytest.mark.parametrize("method,path,body", WIFI_ROUTES)
@pytest.mark.parametrize("who", ["manager", "waiter"])
def test_only_the_owner_touches_the_wifi_allow_list(client, manager_token, waiter_token,
                                                    wifi_allowed, method, path, body, who):
    """The allow-list is what makes clock-in mean "physically on site". A manager
    who could add 0.0.0.0/0 could clock in from home, or clock a friend in."""
    token = manager_token if who == "manager" else waiter_token
    url = path.format(id=wifi_allowed.id)
    rv = client.open(url, method=method, headers=H(token), json=body)
    assert rv.status_code == 403, f"{method} {url} as {who}"
    assert "owner" in rv.get_json()["error"].lower()


def test_owner_can_work_the_wifi_allow_list_end_to_end(client, owner_token):
    """GOOD path — all five routes."""
    rv = client.post("/hr/wifi", headers=H(owner_token),
                     json={"ssid": "kurahia-staff", "ip_cidr": "10.0.0.0/24", "label": "Main"})
    assert rv.status_code == 201
    eid = rv.get_json()["id"]

    assert client.get("/hr/wifi", headers=H(owner_token)).status_code == 200
    assert client.patch(f"/hr/wifi/{eid}", headers=H(owner_token),
                        json={"ip_cidr": "10.0.1.0/24"}).status_code == 200
    assert client.post(f"/hr/wifi/{eid}/disable", headers=H(owner_token)).status_code == 200
    assert client.post(f"/hr/wifi/{eid}/enable", headers=H(owner_token)).status_code == 200

    # A junk CIDR is refused in plain English, not with a stack trace.
    rv = client.post("/hr/wifi", headers=H(owner_token),
                     json={"ssid": "x", "ip_cidr": "not-a-network"})
    assert rv.status_code == 400
    assert "CIDR" in rv.get_json()["error"]


def test_manager_and_waiter_are_locked_out_of_system_settings(client, manager_token,
                                                              waiter_token):
    for token in (manager_token, waiter_token):
        assert client.get("/admin/settings", headers=H(token)).status_code == 403
        assert client.patch("/admin/settings", headers=H(token),
                            json={"business_day_start_hour": 12}).status_code == 403

    # And nothing moved.
    rv = client.get("/admin/settings", headers=H(manager_token))
    assert rv.status_code == 403


def test_owner_changes_a_system_setting_and_it_is_audited(client, owner_token):
    rv = client.patch("/admin/settings", headers=H(owner_token),
                      json={"business_day_start_hour": 6})
    assert rv.status_code == 200
    assert rv.get_json()["updated"] == ["business_day_start_hour"]
    assert client.get("/admin/settings", headers=H(owner_token)).get_json(
        )["business_day_start_hour"] == "6"

    rv = client.get("/audit/logs?action=admin.setting.update", headers=H(owner_token))
    assert rv.get_json()["total"] == 1


AUDIT_ROUTES = ["/audit/logs", "/audit/verify", "/audit/actions"]


@pytest.mark.parametrize("path", AUDIT_ROUTES)
@pytest.mark.parametrize("who", ["manager", "waiter", "chef"])
def test_nobody_below_the_owner_reads_the_audit_trail(client, manager_token, waiter_token,
                                                      chef_token, path, who):
    """The trail records what managers did. A manager reviewing their own trail
    is not a control. head_chef (level 3) is included because level 3 is the
    level that is easy to forget when gates are written against 5 and 10."""
    token = {"manager": manager_token, "waiter": waiter_token, "chef": chef_token}[who]
    rv = client.get(path, headers=H(token))
    assert rv.status_code == 403, path


def test_the_audit_trail_exposes_no_write_verb(client, owner_token):
    """Read-only by construction: even the owner cannot POST/PATCH/DELETE it."""
    for method in ("POST", "PATCH", "PUT", "DELETE"):
        rv = client.open("/audit/logs", method=method, headers=H(owner_token))
        assert rv.status_code == 405, method


JUDGE_ROUTES = [("GET", "/judge/alerts"), ("POST", "/judge/alerts/{id}/acknowledge")]


@pytest.mark.parametrize("method,path", JUDGE_ROUTES)
@pytest.mark.parametrize("who", ["manager", "waiter", "chef"])
def test_judge_alert_feed_is_owner_only(client, manager_token, waiter_token, chef_token,
                                        open_alert, method, path, who):
    token = {"manager": manager_token, "waiter": waiter_token, "chef": chef_token}[who]
    rv = client.open(path.format(id=open_alert), method=method, headers=H(token), json={})
    assert rv.status_code == 403
    assert rv.get_json()["error"] == "Owner only."


def test_owner_reads_and_acknowledges_a_judge_alert(client, owner_token, open_alert):
    rv = client.get("/judge/alerts", headers=H(owner_token))
    assert rv.status_code == 200
    assert open_alert in [a["id"] for a in rv.get_json()]

    rv = client.post(f"/judge/alerts/{open_alert}/acknowledge", headers=H(owner_token))
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "ACKNOWLEDGED"


DASHBOARD_OWNER_ONLY = [
    "/dashboard/inventory", "/dashboard/finance", "/dashboard/bookings",
    "/dashboard/staff", "/dashboard/conduct", "/dashboard/suggestions",
    "/dashboard/calendar", "/dashboard/feedback", "/dashboard/equipment",
    "/dashboard/alerts",
]


@pytest.mark.parametrize("path", DASHBOARD_OWNER_ONLY)
@pytest.mark.parametrize("who", ["manager", "waiter"])
def test_owner_dashboards_refuse_everyone_else(client, manager_token, waiter_token,
                                               path, who):
    token = manager_token if who == "manager" else waiter_token
    rv = client.get(path, headers=H(token))
    assert rv.status_code == 403, path
    assert "Owner access required" in rv.get_json()["error"]


@pytest.mark.parametrize("path", DASHBOARD_OWNER_ONLY)
def test_owner_dashboards_all_answer_for_the_owner(client, owner_token, path):
    """GOOD path — a 403-only test proves nothing if the endpoint is broken for
    everybody."""
    assert client.get(path, headers=H(owner_token)).status_code == 200


def test_HOLE_manager_reads_judge_alerts_through_dashboard_overview(
        client, manager_token, open_alert):
    """HOLE — app/dashboard/core.py:116-120, inside `/dashboard/overview`.

    /dashboard/overview is gated at MANAGER_LEVEL (core.py:44), unlike every
    other dashboard endpoint. It embeds the three newest OPEN JudgeAlerts —
    id, type, severity and the first 120 characters of the description.

    JudgeAlert is documented "Owner-only" (app/models/judge_alert.py:3) and is
    owner-gated everywhere else: /judge/alerts (judge/routes.py:20-23) and
    /dashboard/alerts (core.py:699). The judge is the silent theft-detection
    engine — the manager is exactly who it watches. Handing them the live feed
    tells a thief they have been noticed and gives them the alert id.

    Verified by running it: the CANARY planted in the alert description comes
    back inside the manager's /dashboard/overview response.
    """
    rv = client.get("/dashboard/overview", headers=H(manager_token))
    assert rv.status_code == 200
    ids = [a["id"] for a in rv.get_json()["top_alerts"]]
    assert open_alert in ids                                  # ← the hole
    assert CANARY[:40] in rv.get_data(as_text=True)


def test_HOLE_manager_can_silence_a_judge_alert_about_themselves(
        client, manager_token, owner_token, open_alert):
    """HOLE — app/dashboard/core.py:733-753 and 756-782.

    /dashboard/alerts/<id>/acknowledge and /action-taken are gated at
    MANAGER_LEVEL, while the identical verb at /judge/alerts/<id>/acknowledge
    is owner-only (judge/routes.py:59). Chained with the leak above, a manager
    reads the alert id from /dashboard/overview and then RESOLVES it. The
    owner's default feeds — /judge/alerts (defaults to status=OPEN) and
    /dashboard/alerts (defaults to status=active) — no longer show it.

    Verified by running it: after the manager's call the owner's default
    /judge/alerts response is empty, and the audit trail is the only remaining
    trace.
    """
    rv = client.post(f"/dashboard/alerts/{open_alert}/action-taken",
                     headers=H(manager_token), json={"notes": "checked, all fine"})
    assert rv.status_code == 200                              # ← the hole
    assert rv.get_json()["status"] == "RESOLVED"

    # The owner's default view no longer contains it.
    rv = client.get("/judge/alerts", headers=H(owner_token))
    assert open_alert not in [a["id"] for a in rv.get_json()]

    # The one saving grace: it IS in the audit trail, attributed to the manager.
    rv = client.get("/audit/logs?action=alert.action_taken", headers=H(owner_token))
    assert rv.get_json()["total"] == 1
    assert rv.get_json()["entries"][0]["actor"] == "manager1"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PURCHASE APPROVAL — the money gate
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def pending_request(client, manager_token):
    """A PENDING purchase request raised by the manager."""
    rv = client.post("/inventory/purchase-requests", headers=H(manager_token),
                     json={"item_description": "Two crates of Tusker", "quantity": "2"})
    assert rv.status_code == 201
    return rv.get_json()["id"]


def test_manager_cannot_approve_a_purchase_request(client, manager_token, pending_request):
    rv = client.post(f"/inventory/purchase-requests/{pending_request}/approve",
                     headers=H(manager_token), json={"action": "approve"})
    assert rv.status_code == 403
    assert rv.get_json()["error"] == "Only the owner can approve purchase requests."

    from app.models.purchase_request import PurchaseRequest
    assert db.session.get(PurchaseRequest, pending_request).status == "PENDING"


def test_manager_cannot_reject_one_either(client, manager_token, pending_request):
    """`action` is caller-supplied — reject is the same privileged decision."""
    rv = client.post(f"/inventory/purchase-requests/{pending_request}/approve",
                     headers=H(manager_token), json={"action": "reject"})
    assert rv.status_code == 403


def test_waiter_cannot_even_raise_or_see_purchase_requests(client, waiter_token,
                                                           pending_request):
    assert client.get("/inventory/purchase-requests",
                      headers=H(waiter_token)).status_code == 403
    assert client.post("/inventory/purchase-requests", headers=H(waiter_token),
                       json={"item_description": "x", "quantity": "1"}).status_code == 403
    assert client.post(f"/inventory/purchase-requests/{pending_request}/approve",
                       headers=H(waiter_token), json={}).status_code == 403


def test_owner_approves_the_managers_request(client, owner_token, manager_token,
                                             pending_request):
    """GOOD path — manager proposes a budget, owner decides."""
    rv = client.post(f"/inventory/purchase-requests/{pending_request}/propose",
                     headers=H(manager_token), json={"estimated_cost": "4800"})
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "PROPOSED"

    rv = client.post(f"/inventory/purchase-requests/{pending_request}/approve",
                     headers=H(owner_token), json={"action": "approve"})
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "APPROVED"


def test_owner_cannot_approve_a_request_they_raised_themselves(client, owner_token):
    """Separation of duties survives even at the top of the tree."""
    rv = client.post("/inventory/purchase-requests", headers=H(owner_token),
                     json={"item_description": "New tyres for my car", "quantity": "4"})
    pr_id = rv.get_json()["id"]

    rv = client.post(f"/inventory/purchase-requests/{pr_id}/approve",
                     headers=H(owner_token), json={"action": "approve"})
    assert rv.status_code == 403
    assert "your own" in rv.get_json()["error"]


def test_an_approved_request_cannot_be_approved_twice(client, owner_token, pending_request):
    client.post(f"/inventory/purchase-requests/{pending_request}/approve",
                headers=H(owner_token), json={"action": "approve"})
    rv = client.post(f"/inventory/purchase-requests/{pending_request}/approve",
                     headers=H(owner_token), json={"action": "reject"})
    assert rv.status_code == 400
    assert "already" in rv.get_json()["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. HIERARCHY — can a manager climb?
# ═══════════════════════════════════════════════════════════════════════════════

def test_manager_cannot_create_an_owner_account(client, manager_token):
    rv = client.post("/auth/users", headers=H(manager_token), json={
        "username": "owner2", "password": "Sneaky1!", "role_id": _role_id("owner"),
    })
    assert rv.status_code == 403
    assert "at or above your own role level" in rv.get_json()["error"]

    from app.models.user import User
    assert db.session.query(User).filter_by(username="owner2").first() is None


def test_manager_cannot_create_a_second_manager(client, manager_token):
    """"Below your own level" means strictly below — a peer is not allowed."""
    rv = client.post("/auth/users", headers=H(manager_token), json={
        "username": "manager2", "password": "Sneaky1!", "role_id": _role_id("manager"),
    })
    assert rv.status_code == 403


def test_manager_cannot_promote_themselves(client, manager_token):
    """PATCH on self fails on the outranking check before role_id is even read
    (app/auth/users.py:141)."""
    rv = client.patch(f"/auth/users/{_user_id('manager1')}", headers=H(manager_token),
                      json={"role_id": _role_id("owner")})
    assert rv.status_code == 403

    from app.models.user import User
    assert db.session.get(User, _user_id("manager1")).role.level == 5


def test_manager_cannot_promote_a_subordinate_to_owner(client, manager_token):
    """A proxy climb: promote a staffer you control, then log in as them."""
    rv = client.patch(f"/auth/users/{_user_id('staff1')}", headers=H(manager_token),
                      json={"role_id": _role_id("owner")})
    assert rv.status_code == 403
    assert "at or above your own level" in rv.get_json()["error"]

    from app.models.user import User
    assert db.session.get(User, _user_id("staff1")).role.level == 1


def test_manager_cannot_edit_or_deactivate_the_owner(client, manager_token):
    owner_id = _user_id("owner1")
    assert client.patch(f"/auth/users/{owner_id}", headers=H(manager_token),
                        json={"password": "Pwned123!"}).status_code == 403
    assert client.post(f"/auth/deactivate/{owner_id}",
                       headers=H(manager_token)).status_code == 403
    assert client.post(f"/auth/reset-lockout/{owner_id}",
                       headers=H(manager_token)).status_code == 403
    assert client.post(f"/auth/users/{owner_id}/activate",
                       headers=H(manager_token)).status_code == 403

    from app.models.user import User
    assert db.session.get(User, owner_id).is_active is True


def test_the_owner_role_is_not_even_offered_to_a_manager(client, manager_token):
    """Both role listings filter on `Role.level < actor.role.level`
    (auth/users.py:249, admin/roles.py:38) — the owner role is not enumerable."""
    rv = client.get("/auth/users/meta", headers=H(manager_token))
    assert rv.status_code == 200
    assert [r for r in rv.get_json()["roles"] if r["level"] >= 10] == []

    rv = client.get("/admin/roles", headers=H(manager_token))
    assert rv.status_code == 200
    assert [r for r in rv.get_json() if r["level"] >= 10] == []


def test_manager_cannot_mint_a_level_99_role(client, manager_token):
    """Role CRUD is owner-only, so "create a super-role then assign it to
    myself" is closed at step one."""
    rv = client.post("/admin/roles", headers=H(manager_token),
                     json={"name": "god", "level": 99})
    assert rv.status_code == 403
    assert "Only the owner can manage roles" in rv.get_json()["error"]


def test_manager_cannot_raise_an_existing_role_level(client, manager_token):
    """The other route to the same place: edit `manager` to level 11."""
    rv = client.patch(f"/admin/roles/{_role_id('manager')}", headers=H(manager_token),
                      json={"level": 11})
    assert rv.status_code == 403

    from app.models.role import Role
    assert db.session.get(Role, _role_id("manager")).level == 5


def test_owner_cannot_deactivate_their_own_account(client, owner_token):
    """`actor.role.level <= target.role.level` is non-strict, so the owner is
    caught by their own rule. Deliberate and load-bearing: the resort would be
    locked out of every owner-only endpoint permanently."""
    rv = client.post(f"/auth/deactivate/{_user_id('owner1')}", headers=H(owner_token))
    assert rv.status_code == 403

    from app.models.user import User
    assert db.session.get(User, _user_id("owner1")).is_active is True


def test_the_owner_cannot_create_a_second_owner_through_the_api(client, owner_token):
    """Same non-strict rule seen from the other side. Not a security hole — an
    OPERATIONAL one: there is no API path to a spare owner account, so losing
    owner1 means a CLI/DB intervention. Recorded here so the constraint is
    visible rather than discovered during an outage."""
    rv = client.post("/auth/users", headers=H(owner_token), json={
        "username": "owner2", "password": "SecondOwner1!", "role_id": _role_id("owner"),
    })
    assert rv.status_code == 403

    rv = client.get("/auth/users/meta", headers=H(owner_token))
    assert [r for r in rv.get_json()["roles"] if r["name"] == "owner"] == []


def test_owner_can_create_a_manager_and_the_manager_can_create_staff(client, owner_token):
    """GOOD path — the hierarchy is a ladder, not a wall."""
    rv = client.post("/auth/users", headers=H(owner_token), json={
        "username": "manager9", "password": "RealManager1!", "role_id": _role_id("manager"),
    })
    assert rv.status_code == 201

    rv = client.post("/auth/login", json={"username": "manager9",
                                          "password": "RealManager1!"})
    tok = rv.get_json()["access_token"]
    rv = client.post("/auth/users", headers=H(tok), json={
        "username": "waiter9", "password": "RealWaiter1!", "role_id": _role_id("staff"),
    })
    assert rv.status_code == 201


def test_a_deactivated_owner_token_stops_working_immediately(client, app, owner_token):
    """Kill switch: the JWT stays cryptographically valid, the session does not.
    Tests the owner specifically — the account whose token is worth the most."""
    assert client.get("/audit/logs", headers=H(owner_token)).status_code == 200

    from app.models.user import User
    db.session.get(User, _user_id("owner1")).is_active = False
    db.session.commit()

    rv = client.get("/audit/logs", headers=H(owner_token))
    assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# 6. THE AUDIT HASH-CHAIN
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def some_history(client, owner_token):
    """A handful of real audited writes so the chain has links to break.

    NOTE the row at index 0 is NOT the settings change — requesting the
    owner_token fixture already logged a `user.login`. Tests that need a
    specific row look it up by action, never by position.
    """
    client.patch("/admin/settings", headers=H(owner_token),
                 json={"business_day_start_hour": 7})
    client.post("/hr/wifi", headers=H(owner_token),
                json={"ssid": "net-a", "ip_cidr": "10.1.0.0/24"})
    client.post("/hr/wifi", headers=H(owner_token),
                json={"ssid": "net-b", "ip_cidr": "10.2.0.0/24"})
    from app.models.audit_log import AuditLog
    return db.session.query(AuditLog).order_by(AuditLog.timestamp.asc()).all()


def _audit_row(action):
    from app.models.audit_log import AuditLog
    return db.session.query(AuditLog).filter_by(action=action).first()


def test_owner_can_verify_the_chain(client, owner_token, some_history):
    rv = client.get("/audit/verify", headers=H(owner_token))
    assert rv.status_code == 200
    assert rv.get_json()["intact"] is True
    assert rv.get_json()["entries_checked"] >= 3


def test_editing_a_hashed_field_breaks_the_chain(client, app, owner_token, some_history):
    """Rewriting `actor` — "it wasn't me, it was the waiter" — is caught."""
    from app.models.audit_log import AuditLog
    row = some_history[1]
    row.actor = "waiter1"
    db.session.commit()

    rv = client.get("/audit/verify", headers=H(owner_token))
    assert rv.get_json()["intact"] is False
    assert "Chain broken" in rv.get_json()["detail"]


def test_removing_a_middle_entry_breaks_the_chain(client, app, owner_token, some_history):
    from app.models.audit_log import AuditLog
    db.session.delete(some_history[1])
    db.session.commit()

    rv = client.get("/audit/verify", headers=H(owner_token))
    assert rv.get_json()["intact"] is False


def test_the_details_field_is_inside_the_hash(client, app, owner_token,
                                              some_history):
    """WAS A HOLE — app/models/audit_log.py `_compute_hash`.

        raw = f"{actor}|{action}|{target or ''}|{timestamp}|{prev_hash or ''}"

    `details` is absent. Everything the trail says about WHAT CHANGED lives in
    `details`: "price 1800 -> 900" (pos/menu.py), "PASSWORD RESET"
    (auth/users.py:168), "value={val}" (admin/settings.py:67), "qty=… cost=…"
    (inventory/purchases.py:367). Anyone with DB write access can rewrite all
    of it and /audit/verify still reports "history is unaltered" — which is
    worse than no chain, because the owner is told it is clean.

    Verified by running it: the row's `details` is changed to a lie, the chain
    still verifies, and the lie comes back out of /audit/logs.
    """
    row = _audit_row("admin.setting.update")
    assert row.details == "value=7"
    row.details = "value=0  (rewritten by the attacker)"
    db.session.commit()

    rv = client.get("/audit/verify", headers=H(owner_token))
    assert rv.get_json()["intact"] is False, \
        "details was rewritten and the chain still called itself clean"
    assert "Chain broken" in rv.get_json().get("detail", "")


def test_truncating_the_tail_of_the_chain_is_detected(client, app, owner_token,
                                                     some_history):
    """WAS A HOLE — same file, `verify_chain`.

    Verification walks forward from row 1 and only checks that each row hashes
    to its predecessor. Delete the LAST n rows and every survivor still hashes
    correctly, so the chain reports intact. There is no signed head, no row
    counter, no external anchor.

    This is the shape a real cover-up takes: do the thing, then drop the tail of
    the log. A middle deletion is caught (test above); the tail is not.

    Verified by running it: two of three entries are deleted and /audit/verify
    still answers intact, with a silently smaller entries_checked.
    """
    from app.models.audit_log import AuditLog
    before = client.get("/audit/verify", headers=H(owner_token)).get_json()["entries_checked"]

    for row in some_history[-2:]:
        db.session.delete(row)
    db.session.commit()

    rv = client.get("/audit/verify", headers=H(owner_token))
    assert rv.get_json()["intact"] is False, \
        "two entries were deleted from the end and nothing noticed"
    assert "SHORTER" in rv.get_json().get("detail", "")
    assert rv.get_json()["entries_checked"] == before - 2


def test_owner_actions_are_actually_written_to_the_trail(client, owner_token):
    """The trail is only a control if the owner-only writes reach it."""
    client.post("/hr/wifi", headers=H(owner_token),
                json={"ssid": "audited", "ip_cidr": "10.9.0.0/24"})
    rv = client.get("/audit/logs?action=hr.wifi.create", headers=H(owner_token))
    assert rv.get_json()["total"] == 1
    assert rv.get_json()["entries"][0]["actor"] == "owner1"


def test_a_refused_manager_action_writes_nothing(client, manager_token, owner_token):
    """A 403 must not leave a half-written row — the trail would then record
    actions that never happened.

    Careful with the measurement: requesting manager_token performs a real
    login, which IS audited, so "manager1 has zero audit rows" would be a false
    alarm. The assertion is that no wifi/settings row exists at all.
    """
    client.post("/hr/wifi", headers=H(manager_token),
                json={"ssid": "evil", "ip_cidr": "0.0.0.0/0"})
    client.patch("/admin/settings", headers=H(manager_token),
                 json={"business_day_start_hour": 3})

    for action in ("hr.wifi.create", "admin.setting.update"):
        rv = client.get(f"/audit/logs?action={action}", headers=H(owner_token))
        assert rv.get_json()["total"] == 0, action

    # The manager's only audit row is their login.
    rv = client.get("/audit/logs?actor=manager1", headers=H(owner_token))
    assert {e["action"] for e in rv.get_json()["entries"]} <= {"user.login"}


# ═══════════════════════════════════════════════════════════════════════════════
# 7. REPORTS AND EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("who", ["manager", "waiter", "chef"])
def test_pdf_reports_that_are_owner_only_stay_owner_only(client, manager_token,
                                                         waiter_token, chef_token, who):
    """A PDF is an export — the easiest way for a whole day's figures to walk
    out of the building."""
    token = {"manager": manager_token, "waiter": waiter_token, "chef": chef_token}[who]
    rv = client.get("/reports/daily-summary?date=2026-08-01", headers=H(token))
    assert rv.status_code == 403
    assert "Only the owner" in rv.get_json()["error"]

    rv = client.get("/reports/occupancy?from=2026-08-01&to=2026-08-02", headers=H(token))
    assert rv.status_code == 403
    assert "Only the owner" in rv.get_json()["error"]


@pytest.fixture
def a_villa(app, general_dept_id):
    """/reports/occupancy 404s with no active VILLA resource — the seed has
    none, so the GOOD-path test has to supply one. (First run of this test
    reported a 404 that was my missing fixture, not a broken endpoint.)"""
    from decimal import Decimal
    from app.models.bookable_resource import BookableResource, ResourceType
    v = BookableResource(name="Villa 1", resource_type=ResourceType.VILLA.value,
                         capacity=4, base_price=Decimal("15000"),
                         department_id=general_dept_id)
    db.session.add(v)
    db.session.commit()
    return v


def test_owner_can_pull_both_pdf_reports(client, owner_token, a_villa):
    rv = client.get("/reports/daily-summary?date=2026-08-01", headers=H(owner_token))
    assert rv.status_code == 200
    assert rv.headers["Content-Type"] == "application/pdf"

    rv = client.get("/reports/occupancy?from=2026-08-01&to=2026-08-02",
                    headers=H(owner_token))
    assert rv.status_code == 200
    assert rv.headers["Content-Type"] == "application/pdf"


def test_staff_cash_report_is_manager_and_above_by_design(client, owner_token,
                                                          manager_token, waiter_token):
    """Documented as the cashier reconciliation tool (pos/orders.py:437), so
    manager access is correct — but a waiter must not be able to read another
    waiter's cash total."""
    frm = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None).isoformat()
    to  = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    sid = _user_id("waiter1")
    qs = f"?staff_id={sid}&from={frm}&to={to}"

    assert client.get(f"/reports/staff-cash{qs}", headers=H(owner_token)).status_code == 200
    assert client.get(f"/reports/staff-cash{qs}", headers=H(manager_token)).status_code == 200
    assert client.get(f"/reports/staff-cash{qs}", headers=H(waiter_token)).status_code == 403


def test_finance_period_close_is_not_reachable_by_a_waiter(client, waiter_token):
    """Closing a period freezes the books. Level 1 must not be near it."""
    rv = client.post("/finance/close-period", headers=H(waiter_token),
                     json={"period": "2026-08"})
    assert rv.status_code == 403
