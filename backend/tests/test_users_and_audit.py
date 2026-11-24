import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent


def test_agent_and_manager_cannot_manage_users_and_denial_is_audited(client, db, make_user, login):
    for role in ("agent", "manager"):
        user = make_user(role)
        r = client.get("/api/v1/users", headers=login(user))
        assert r.status_code == 403
        assert r.json()["code"] == "forbidden"
    db.expire_all()
    denied = db.scalars(select(AuditEvent).where(AuditEvent.action == "access.denied")).all()
    assert len(denied) == 2
    assert denied[0].entity_id == "GET /api/v1/users"


def test_admin_creates_user_email_lowercased(client, make_user, login):
    admin = make_user("admin")
    r = client.post(
        "/api/v1/users",
        json={"email": "New.Agent@Example.com", "full_name": "  Priya  ", "role": "agent",
              "password": "a-long-password"},
        headers=login(admin),
    )
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "new.agent@example.com"
    assert r.json()["full_name"] == "Priya"

    # The new user can log in.
    r = client.post("/api/v1/auth/login",
                    json={"email": "new.agent@example.com", "password": "a-long-password"})
    assert r.status_code == 200


def test_duplicate_email_rejected(client, make_user, login):
    admin = make_user("admin")
    existing = make_user("agent")
    r = client.post(
        "/api/v1/users",
        json={"email": existing.email.upper(), "full_name": "Dup", "role": "agent",
              "password": "a-long-password"},
        headers=login(admin),
    )
    assert r.status_code == 409
    assert r.json()["field_errors"] == {"email": "Already in use."}


def test_validation_errors_use_standard_body(client, make_user, login):
    admin = make_user("admin")
    r = client.post(
        "/api/v1/users",
        json={"email": "not-an-email", "full_name": "  ", "role": "superuser", "password": "short"},
        headers=login(admin),
    )
    assert r.status_code == 422
    fields = r.json()["field_errors"]
    assert {"email", "full_name", "role", "password"} <= set(fields)


def test_role_change_is_audited_with_before_and_after(client, db, make_user, login):
    admin = make_user("admin")
    agent = make_user("agent")
    r = client.patch(f"/api/v1/users/{agent.id}", json={"role": "manager"}, headers=login(admin))
    assert r.status_code == 200
    assert r.json()["role"] == "manager"
    db.expire_all()
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "user.role_change"))
    assert event.details == {"from": "agent", "to": "manager"}
    assert event.actor_user_id == admin.id
    assert event.entity_id == str(agent.id)


def test_admin_cannot_demote_or_deactivate_self(client, make_user, login):
    admin = make_user("admin")
    headers = login(admin)
    r = client.patch(f"/api/v1/users/{admin.id}", json={"role": "agent"}, headers=headers)
    assert r.status_code == 400
    r = client.patch(f"/api/v1/users/{admin.id}", json={"is_active": False}, headers=headers)
    assert r.status_code == 400


def test_password_reset_by_admin(client, make_user, login):
    admin = make_user("admin")
    agent = make_user("agent")
    r = client.patch(f"/api/v1/users/{agent.id}", json={"password": "brand-new-password"},
                     headers=login(admin))
    assert r.status_code == 200
    r = client.post("/api/v1/auth/login",
                    json={"email": agent.email, "password": "brand-new-password"})
    assert r.status_code == 200


def test_audit_log_readable_by_manager_not_agent(client, make_user, login):
    manager = make_user("manager")
    agent = make_user("agent")
    r = client.get("/api/v1/audit", headers=login(manager))
    assert r.status_code == 200
    assert r.json()["total"] >= 1  # at least the manager's own login
    assert client.get("/api/v1/audit", headers=login(agent)).status_code == 403


@pytest.mark.parametrize("statement", [
    "UPDATE audit_events SET action = 'tampered'",
    "DELETE FROM audit_events",
])
def test_audit_log_is_append_only(db, make_user, client, login, statement):
    login(make_user("agent"))  # creates an auth.login event
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text(statement))
    db.rollback()
