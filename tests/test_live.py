"""Real SSE and transaction tests against a temporary SQLite database only."""
import asyncio
import socket
from threading import Thread
import time

import httpx
import pytest
import uvicorn

from app import db as database
from app.constants import SESSION_COOKIE
from app.live import BoardEvents, board_changed, board_events
from app.main import app
from app.models import User
from app.security import sign_session


@pytest.fixture()
def live_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'live.db').as_posix()}")
    database.reset_engine()
    database.init_db()
    with database.session_factory()() as db:
        db.add_all([
            User(id=1, email="live@example.com", display_name="Owner", password_hash="unused", avatar_color="#D63A56"),
            User(id=2, email="other@example.com", display_name="Other", password_hash="unused", avatar_color="#D63A56"),
        ])
        db.commit()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", ws="none", timeout_graceful_shutdown=2))
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(150):
        if server.started:
            break
        time.sleep(.02)
    assert server.started, "Local SSE test server failed to start"
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{sock.getsockname()[1]}", headers={"X-Kanban": "1"}, timeout=3) as client:
            client.cookies.set(SESSION_COOKIE, sign_session(1))
            yield client
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        database.reset_engine()


def project(client):
    response = client.post("/api/projects", json={"name": "Live board"})
    assert response.status_code == 200, response.text
    project_id = response.json()["project"]["id"]
    return project_id, client.get(f"/api/projects/{project_id}/board").json()


def event(lines):
    name, data = None, None
    for line in lines:
        if line.startswith("event: "):
            name = line[7:]
        elif line.startswith("data: "):
            data = line[6:]
        elif not line and name:
            return name, data
    raise AssertionError("SSE stream ended without an event")


def test_events_require_login_and_membership(live_client):
    client = live_client
    project_id, _ = project(client)
    client.cookies.clear()
    assert client.get(f"/api/projects/{project_id}/events").status_code == 401
    client.cookies.set(SESSION_COOKIE, sign_session(2))
    assert client.get(f"/api/projects/{project_id}/events").status_code == 404


def test_committed_card_label_and_profile_changes_reach_stream(live_client):
    client = live_client
    project_id, board = project(client)
    url = f"/api/projects/{project_id}/events"
    with client.stream("GET", url) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        assert "no-store" in response.headers["cache-control"]
        lines = response.iter_lines()
        assert event(lines) == ("ready", "{}")
        created = client.post(f"/api/projects/{project_id}/cards", json={"column_id": board["columns"][0]["id"], "title": "Committed card"})
        assert created.status_code == 200, created.text
        assert event(lines) == ("change", "{}")
        assert client.get(f"/api/projects/{project_id}/board").json()["columns"][0]["cards"][0]["title"] == "Committed card"
        # Label edits do not update project.updated_at, but must still invalidate the board.
        assert client.patch(f'/api/labels/{board["labels"][0]["id"]}', json={"name": "Renamed", "color": "#D63A56"}).status_code == 200
        assert event(lines) == ("change", "{}")
        assert client.patch("/api/auth/me", json={"avatar_id": "pet-1"}).status_code == 200
        assert event(lines) == ("change", "{}")
    with client.stream("GET", url) as response:
        assert event(response.iter_lines()) == ("ready", "{}")


def test_removed_member_stream_is_closed_without_further_board_events(live_client):
    client = live_client
    project_id, _ = project(client)
    assert client.post(f"/api/projects/{project_id}/invites", json={"email": "other@example.com", "role": "viewer"}).status_code == 200
    with httpx.Client(base_url=client.base_url, headers={"X-Kanban": "1"}, timeout=3) as other:
        other.cookies.set(SESSION_COOKIE, sign_session(2))
        note = other.get("/api/notifications").json()["items"][0]
        assert other.post(f'/api/notifications/{note["id"]}/accept').status_code == 200
        assert other.get(f'/api/projects/{project_id}/board').status_code == 200
        with other.stream("GET", f"/api/projects/{project_id}/events") as response:
            assert response.status_code == 200, response.read()
            lines = response.iter_lines()
            assert event(lines)[0] == "ready"
            assert client.delete(f"/api/projects/{project_id}/members/2").status_code == 200
            assert event(lines) == ("unavailable", "{}")
            assert list(lines) == []


def test_heartbeat_rechecks_revoked_tokens_without_holding_database_connections(live_client, monkeypatch):
    from app.routers import events

    monkeypatch.setattr(events, "HEARTBEAT_SECONDS", .05)
    client = live_client
    project_id, _ = project(client)
    token = client.post("/api/auth/tokens", json={"name": "Stream test"}).json()
    with client.stream("GET", f"/api/projects/{project_id}/events", headers={"Authorization": f'Bearer {token["token"]}'}) as response:
        lines = response.iter_lines()
        assert event(lines)[0] == "ready"
        assert database.get_engine().pool.checkedout() == 0
        assert client.delete(f'/api/auth/tokens/{token["id"]}').status_code == 200
        assert event(lines) == ("unavailable", "{}")
        assert list(lines) == []


def test_board_events_publish_after_commit_and_never_on_rollback(live_client):
    async def check():
        with board_events.subscribe(123) as queue:
            transaction = database.get_db()
            db = next(transaction)
            board_changed(db, 123)
            await asyncio.sleep(0)
            assert queue.empty()
            with pytest.raises(StopIteration):
                next(transaction)
            await asyncio.wait_for(queue.get(), 1)
            transaction = database.get_db()
            db = next(transaction)
            board_changed(db, 123)
            with pytest.raises(RuntimeError, match="rollback"):
                transaction.throw(RuntimeError("rollback"))
            await asyncio.sleep(0)
            assert queue.empty()
    asyncio.run(check())


def test_broker_coalesces_changes_isolates_projects_and_cleans_up():
    async def check():
        broker = BoardEvents()
        with broker.subscribe(1) as first, broker.subscribe(2) as other:
            broker.publish({1})
            broker.publish({1})
            await asyncio.sleep(0)
            assert first.qsize() == 1
            assert other.empty()
        assert not broker._listeners
    asyncio.run(check())
