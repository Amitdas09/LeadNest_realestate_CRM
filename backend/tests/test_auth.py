from sqlalchemy import select

from app.models import AuditEvent
from tests.conftest import DEFAULT_PASSWORD


def _actions(db) -> list[str]:
    db.expire_all()
    return [e.action for e in db.scalars(select(AuditEvent).order_by(AuditEvent.id))]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_login_success_returns_token_and_audits(client, db, make_user):
    user = make_user("agent")
    r = client.post("/api/v1/auth/login", json={"email": user.email.upper(), "password": DEFAULT_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == user.email
    assert "password_hash" not in body["user"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == str(user.id)
    assert me.json()["last_login_at"] is not None
    assert _actions(db) == ["auth.login"]


def test_wrong_password_rejected_with_standard_error_body(client, db, make_user):
    user = make_user("agent")
    r = client.post("/api/v1/auth/login", json={"email": user.email, "password": "wrong-password"})
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == "invalid_credentials"
    assert body["correlation_id"] == r.headers["X-Correlation-ID"]
    assert _actions(db) == ["auth.login_failed"]


def test_unknown_email_gets_same_message(client, make_user):
    make_user("agent")
    r = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert r.status_code == 401
    assert r.json()["message"] == "Email or password is incorrect."


def test_inactive_user_cannot_log_in(client, make_user):
    user = make_user("agent", active=False)
    r = client.post("/api/v1/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD})
    assert r.status_code == 401


def test_token_stops_working_after_deactivation(client, make_user, login):
    admin = make_user("admin")
    agent = make_user("agent")
    agent_headers = login(agent)
    r = client.patch(f"/api/v1/users/{agent.id}", json={"is_active": False}, headers=login(admin))
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=agent_headers).status_code == 401


def test_missing_and_garbage_tokens_rejected(client):
    assert client.get("/api/v1/auth/me").json()["code"] == "not_authenticated"
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_token"


def test_incoming_correlation_id_is_echoed(client):
    r = client.get("/api/v1/auth/me", headers={"X-Correlation-ID": "abc123"})
    assert r.headers["X-Correlation-ID"] == "abc123"
    assert r.json()["correlation_id"] == "abc123"
