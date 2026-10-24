"""Avatar profile regressions use an isolated in-memory database."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.constants import AVATAR_IDS, SESSION_COOKIE
from app.db import get_db
from app.main import app
from app.models import Base, User
from app.security import sign_session


@pytest.fixture()
def avatar_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, email="avatar@example.com", password_hash="unused", display_name="测试", avatar_color="#D63A56"))
        db.commit()

    def isolated_db():
        with Session(engine) as db:
            yield db
            db.commit()

    app.dependency_overrides[get_db] = isolated_db
    client = TestClient(app, headers={"X-Kanban": "1"})
    client.cookies.set(SESSION_COOKIE, sign_session(1))
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.pop(get_db)
        engine.dispose()


def test_legacy_avatar_default_and_profile_persistence(avatar_client):
    client = avatar_client
    assert client.get("/api/auth/me").json()["avatar_id"] == "male-1"
    for avatar_id in AVATAR_IDS:
        response = client.patch("/api/auth/me", json={"avatar_id": avatar_id})
        assert response.status_code == 200, response.text
        assert client.get("/api/auth/me").json()["avatar_id"] == avatar_id
    response = client.patch("/api/auth/me", json={"display_name": "新名字"})
    assert response.json()["avatar_id"] == "robot-6"
    project = client.post("/api/projects", json={"name": "头像测试"}).json()["project"]
    board = client.get(f"/api/projects/{project['id']}/board").json()
    assert board["members"][0]["avatar_id"] == "robot-6"
    assert client.get("/api/bootstrap").json()["user"]["avatar_id"] == "robot-6"


@pytest.mark.parametrize("invalid", [None, "", "pet-7", "male-0", "../secret", "https://example.com/avatar.png"])
def test_avatar_rejects_values_outside_presets(avatar_client, invalid):
    response = avatar_client.patch("/api/auth/me", json={"avatar_id": invalid})
    assert response.status_code == 422
    assert avatar_client.get("/api/auth/me").json()["avatar_id"] == "male-1"


def test_versioned_avatars_cache_without_stale_application_assets(avatar_client):
    client = avatar_client
    url = "/static/avatars/male-1.webp?v=1"
    image = client.get(url)
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/webp"
    assert image.headers["cache-control"] == "public, max-age=31536000, immutable"
    unchanged = client.get(url, headers={"If-None-Match": image.headers["etag"]})
    assert unchanged.status_code == 304
    assert unchanged.headers["cache-control"] == image.headers["cache-control"]
    for path in ("/static/avatars/male-1.webp", "/static/css/app.css?v=1", "/static/js/avatars.js"):
        assert client.get(path).headers["cache-control"] == "no-cache"
    missing = client.get("/static/avatars/missing.webp?v=1")
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-cache"
