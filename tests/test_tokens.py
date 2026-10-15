from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.constants import SESSION_COOKIE
from app.db import get_db
from app.main import app
from app.models import AccessToken, Base, User, utcnow
from app.security import hash_access_token, sign_session


@pytest.fixture()
def token_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            User(id=1, email="owner@example.com", password_hash="unused", display_name="Owner", avatar_color="#D63A56"),
            User(id=2, email="other@example.com", password_hash="unused", display_name="Other", avatar_color="#D63A56"),
        ])
        db.commit()

    def isolated_db():
        with Session(engine) as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = isolated_db
    client = TestClient(app, headers={"X-Kanban": "1"})
    client.cookies.set(SESSION_COOKIE, sign_session(1))
    try:
        yield client, engine
    finally:
        client.close()
        app.dependency_overrides.pop(get_db)
        engine.dispose()


def issue(client, **values):
    result = client.post("/api/auth/tokens", json={"name": "Coding agent", **values})
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()


def test_token_lifecycle_and_permissions(token_client):
    client, engine = token_client
    created = issue(client)
    with Session(engine) as db:
        row = db.get(AccessToken, created["id"])
        assert row.token_hash == hash_access_token(created["token"])
        assert row.token_hash != created["token"]
    listed = client.get("/api/auth/tokens").json()["items"]
    assert listed == [{key: value for key, value in created.items() if key != "token"}]
    client.cookies.clear()
    bearer = {"Authorization": f"Bearer {created['token']}"}
    assert client.get("/api/auth/me", headers=bearer).json()["email"] == "owner@example.com"
    project = client.post("/api/projects", json={"name": "Agent project"}, headers=bearer)
    assert project.status_code == 200, project.text
    project_id = project.json()["project"]["id"]
    assert client.post("/api/projects", json={"name": "Missing header"}, headers={**bearer, "X-Kanban": "0"}).status_code == 403
    for method, path, body in [("GET", "/api/auth/tokens", None), ("POST", "/api/auth/tokens", {"name": "Nested"}), ("DELETE", f"/api/auth/tokens/{created['id']}", None)]:
        assert client.request(method, path, json=body, headers=bearer).status_code == 403
    client.cookies.set(SESSION_COOKIE, sign_session(2))
    assert client.delete(f"/api/auth/tokens/{created['id']}").status_code == 404
    other = issue(client)
    other_bearer = {"Authorization": f"Bearer {other['token']}"}
    assert client.get(f"/api/projects/{project_id}/board", headers=other_bearer).status_code == 404
    client.cookies.set(SESSION_COOKIE, sign_session(1))
    assert client.delete(f"/api/auth/tokens/{created['id']}").status_code == 200
    assert client.get("/api/auth/me", headers=bearer).status_code == 401
    assert client.get("/api/auth/me").status_code == 200


def test_expiry_and_authorization_precedence(token_client):
    client, engine = token_client
    created = issue(client, expires_in_days=1)
    with Session(engine) as db:
        row = db.get(AccessToken, created["id"])
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    for header in [f"Bearer {created['token']}", "Bearer invalid", "Bearer", "Basic ignored", ""]:
        assert client.get("/api/auth/me", headers={"Authorization": header}).status_code == 401
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize("values", [{"name": " "}, {"name": "x" * 61}, {"expires_in_days": 0}, {"expires_in_days": 366}, {"expires_in_days": 1.5}])
def test_invalid_token_input(token_client, values):
    client, engine = token_client
    assert client.post("/api/auth/tokens", json={"name": "Agent", **values}).status_code == 422
    with Session(engine) as db:
        assert db.scalar(select(AccessToken)) is None


def test_unlimited_token_survives_time_and_can_be_revoked(token_client, monkeypatch):
    client, engine = token_client
    unlimited = issue(client, expires_in_days=None)
    finite = issue(client, expires_in_days=365)
    assert unlimited["expires_at"] is None
    with Session(engine) as db:
        assert db.get(AccessToken, unlimited["id"]).expires_at is None
    future = utcnow() + timedelta(days=366)
    monkeypatch.setattr("app.deps.utcnow", lambda: future)
    bearer = {"Authorization": f"Bearer {unlimited['token']}"}
    assert client.get("/api/auth/me", headers=bearer).status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {finite['token']}"}).status_code == 401
    listed = client.get("/api/auth/tokens").json()["items"]
    assert next(item for item in listed if item["id"] == unlimited["id"])["expires_at"] is None
    assert client.delete(f"/api/auth/tokens/{unlimited['id']}").status_code == 200
    assert client.get("/api/auth/me", headers=bearer).status_code == 401
