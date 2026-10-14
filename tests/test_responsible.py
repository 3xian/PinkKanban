from __future__ import annotations

from sqlalchemy import text

from app.db import get_engine, upgrade_schema
from app.mail import captured_code


def register(client, email, name="测试"):
    sent = client.post("/api/auth/code", json={"email": email})
    assert sent.status_code == 200, sent.text
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "password1", "display_name": name, "code": captured_code(email)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def login(client, email):
    assert client.post("/api/auth/login", json={"email": email, "password": "password1"}).status_code == 200


def invite_and_join(client, project_id, owner_email, email, role="member"):
    login(client, owner_email)
    invited = client.post(f"/api/projects/{project_id}/invites", json={"email": email, "role": role})
    assert invited.status_code == 200, invited.text
    client.post("/api/auth/logout")
    login(client, email)
    pending = next(item for item in client.get("/api/notifications").json()["items"] if item["status"] == "pending")
    assert client.post(f"/api/notifications/{pending['id']}/accept").status_code == 200
    client.post("/api/auth/logout")
    login(client, owner_email)


def notes(client, type_name, card_id):
    return [
        item
        for item in client.get("/api/notifications").json()["items"]
        if item["type"] == type_name and item["card_id"] == card_id
    ]


def notes_as(client, email, type_name, card_id, restore):
    client.post("/api/auth/logout")
    login(client, email)
    found = notes(client, type_name, card_id)
    client.post("/api/auth/logout")
    login(client, restore)
    return found


def test_responsible_user_lifecycle(client):
    owner = register(client, "lead-owner@example.com", "拥有者")
    project_id = client.post("/api/projects", json={"name": "负责人", "description": "", "color": "#D63A56"}).json()["project"]["id"]
    board = client.get(f"/api/projects/{project_id}/board").json()
    column_id = board["columns"][0]["id"]
    other_column = board["columns"][1]["id"]
    created = client.post(f"/api/projects/{project_id}/cards", json={"column_id": column_id, "title": "交付"})
    assert created.status_code == 200, created.text
    card = created.json()
    card_id = card["id"]
    assert card["responsible_user_id"] is None
    assert card["assignee_ids"] == []
    assert card["created_by"] == owner["id"]

    client.post("/api/auth/logout")
    guest = register(client, "lead-guest@example.com", "客人")
    client.post("/api/auth/logout")
    outsider = register(client, "lead-out@example.com", "外人")
    client.post("/api/auth/logout")
    viewer = register(client, "lead-view@example.com", "只读")
    invite_and_join(client, project_id, "lead-owner@example.com", "lead-guest@example.com")
    invite_and_join(client, project_id, "lead-owner@example.com", "lead-view@example.com", "viewer")

    denied = client.patch(f"/api/cards/{card_id}", json={"responsible_user_id": outsider["id"]})
    assert denied.status_code == 400
    assert denied.json()["detail"] == "只能指定项目成员"
    assert client.get(f"/api/cards/{card_id}").json()["card"]["responsible_user_id"] is None

    first = client.patch(f"/api/cards/{card_id}", json={"responsible_user_id": guest["id"]})
    assert first.status_code == 200, first.text
    body = first.json()["card"]
    assert body["responsible_user_id"] == guest["id"]
    assert guest["id"] in body["assignee_ids"]
    assert owner["id"] not in body["assignee_ids"]
    board_card = next(card for column in client.get(f"/api/projects/{project_id}/board").json()["columns"] for card in column["cards"] if card["id"] == card_id)
    assert board_card["responsible_user_id"] == guest["id"]
    assert guest["id"] in board_card["assignee_ids"]
    actions = [item["action"] for item in first.json()["activity"]]
    assert "card.responsible" in actions
    assert "card.assigned" in actions
    client.post("/api/auth/logout")
    login(client, "lead-guest@example.com")
    assert len(notes(client, "card_responsible", card_id)) == 1
    assert notes(client, "card_assigned", card_id) == []
    assert client.get("/api/me/cards").json()["cards"][0]["title"] == "交付"
    client.post("/api/auth/logout")
    login(client, "lead-owner@example.com")

    again = client.patch(f"/api/cards/{card_id}", json={"responsible_user_id": guest["id"]})
    assert again.json()["card"]["responsible_user_id"] == guest["id"]
    client.post("/api/auth/logout")
    login(client, "lead-guest@example.com")
    assert len(notes(client, "card_responsible", card_id)) == 1
    client.post("/api/auth/logout")
    login(client, "lead-owner@example.com")

    client.put(f"/api/cards/{card_id}/assignees", json={"ids": [guest["id"], owner["id"]]})
    switched = client.patch(f"/api/cards/{card_id}", json={"responsible_user_id": owner["id"]})
    switched_card = switched.json()["card"]
    assert switched_card["responsible_user_id"] == owner["id"]
    assert set(switched_card["assignee_ids"]) == {guest["id"], owner["id"]}
    assert notes(client, "card_responsible", card_id) == []
    assert notes(client, "card_assigned", card_id) == []

    cleared = client.patch(f"/api/cards/{card_id}", json={"responsible_user_id": None})
    assert cleared.json()["card"]["responsible_user_id"] is None
    assert set(cleared.json()["card"]["assignee_ids"]) == {guest["id"], owner["id"]}
    untouched = client.patch(f"/api/cards/{card_id}", json={"priority": "low"})
    assert untouched.json()["card"]["responsible_user_id"] is None
    assert untouched.json()["card"]["priority"] == "low"

    client.patch(f"/api/cards/{card_id}", json={"responsible_user_id": guest["id"]})
    removed = client.put(f"/api/cards/{card_id}/assignees", json={"ids": [owner["id"]]})
    assert removed.status_code == 200, removed.text
    assert removed.json()["card"]["responsible_user_id"] is None
    assert removed.json()["card"]["assignee_ids"] == [owner["id"]]
    assert "card.responsible" in [item["action"] for item in removed.json()["activity"]]

    client.patch(f"/api/cards/{card_id}", json={"responsible_user_id": owner["id"], "done": True})
    moved = client.post(f"/api/cards/{card_id}/move", json={"column_id": other_column, "index": 0})
    assert moved.status_code == 200, moved.text
    assert client.post(f"/api/cards/{card_id}/archive").status_code == 200
    restored = client.post(f"/api/cards/{card_id}/restore")
    assert restored.json()["card"]["responsible_user_id"] == owner["id"]
    assert restored.json()["card"]["done"] is True

    client.post("/api/auth/logout")
    login(client, "lead-view@example.com")
    visible = client.get(f"/api/cards/{card_id}").json()["card"]
    assert visible["responsible_user_id"] == owner["id"]
    assert visible["can_edit"] is False
    forbidden = client.patch(f"/api/cards/{card_id}", json={"responsible_user_id": viewer["id"]})
    assert forbidden.status_code == 403
    client.post("/api/auth/logout")
    login(client, "lead-owner@example.com")
    roles = {person["id"]: person["role"] for person in client.get(f"/api/projects/{project_id}").json()["members"]}
    assert roles[viewer["id"]] == "viewer"
    assert roles[guest["id"]] == "member"
    assert roles[owner["id"]] == "owner"

    mine = client.get("/api/me/cards").json()["cards"]
    assert [item["title"] for item in mine] == ["交付"]
    client.put(f"/api/cards/{card_id}/assignees", json={"ids": []})
    assert client.get(f"/api/cards/{card_id}").json()["card"]["responsible_user_id"] is None
    assert client.get("/api/me/cards").json()["cards"] == []


def test_member_exit_clears_responsible_and_copy_keeps_it(client):
    register(client, "exit-owner@example.com", "拥有者")
    project_id = client.post("/api/projects", json={"name": "退出", "description": "", "color": "#3D6B8A"}).json()["project"]["id"]
    column_id = client.get(f"/api/projects/{project_id}/board").json()["columns"][0]["id"]
    client.post("/api/auth/logout")
    staying = register(client, "exit-stay@example.com", "留下")
    client.post("/api/auth/logout")
    leaving = register(client, "exit-leave@example.com", "离开")
    client.post("/api/auth/logout")
    removed = register(client, "exit-removed@example.com", "被移除")
    invite_and_join(client, project_id, "exit-owner@example.com", "exit-stay@example.com")
    invite_and_join(client, project_id, "exit-owner@example.com", "exit-leave@example.com")
    invite_and_join(client, project_id, "exit-owner@example.com", "exit-removed@example.com")

    owned = client.post(f"/api/projects/{project_id}/cards", json={"column_id": column_id, "title": "留下的"}).json()["id"]
    abandoned = client.post(f"/api/projects/{project_id}/cards", json={"column_id": column_id, "title": "离开的"}).json()["id"]
    kicked = client.post(f"/api/projects/{project_id}/cards", json={"column_id": column_id, "title": "移除的"}).json()["id"]
    client.patch(f"/api/cards/{owned}", json={"responsible_user_id": staying["id"]})
    client.put(f"/api/cards/{owned}/assignees", json={"ids": [staying["id"], leaving["id"]]})
    client.patch(f"/api/cards/{abandoned}", json={"responsible_user_id": leaving["id"]})
    client.patch(f"/api/cards/{kicked}", json={"responsible_user_id": removed["id"]})
    before = len(notes_as(client, "exit-stay@example.com", "card_responsible", owned, "exit-owner@example.com"))

    client.post("/api/auth/logout")
    login(client, "exit-leave@example.com")
    assert client.post(f"/api/projects/{project_id}/leave").status_code == 200
    client.post("/api/auth/logout")
    login(client, "exit-owner@example.com")
    left = client.get(f"/api/cards/{abandoned}").json()["card"]
    assert left["responsible_user_id"] is None
    assert left["assignee_ids"] == []
    kept = client.get(f"/api/cards/{owned}").json()["card"]
    assert kept["responsible_user_id"] == staying["id"]
    assert leaving["id"] not in kept["assignee_ids"]
    assert staying["id"] in kept["assignee_ids"]

    assert client.delete(f"/api/projects/{project_id}/members/{removed['id']}").status_code == 200
    gone = client.get(f"/api/cards/{kicked}").json()["card"]
    assert gone["responsible_user_id"] is None
    assert gone["assignee_ids"] == []
    assert client.get(f"/api/cards/{owned}").json()["card"]["responsible_user_id"] == staying["id"]

    copy = client.post(f"/api/cards/{owned}/duplicate")
    assert copy.status_code == 200, copy.text
    copied = copy.json()
    assert copied["responsible_user_id"] == staying["id"]
    assert copied["assignee_ids"] == [staying["id"]]
    original = client.get(f"/api/cards/{owned}").json()["card"]
    assert original["responsible_user_id"] == staying["id"]
    order = [card["id"] for card in client.get(f"/api/projects/{project_id}/board").json()["columns"][0]["cards"]]
    assert order.index(copied["id"]) == order.index(owned) + 1
    assert len(notes_as(client, "exit-stay@example.com", "card_responsible", copied["id"], "exit-owner@example.com")) == 0
    assert len(notes_as(client, "exit-stay@example.com", "card_responsible", owned, "exit-owner@example.com")) == before


def test_upgrade_keeps_existing_card_rows(client):
    register(client, "old-owner@example.com", "历史")
    project_id = client.post("/api/projects", json={"name": "历史库", "description": "", "color": "#5C6B52"}).json()["project"]["id"]
    column_id = client.get(f"/api/projects/{project_id}/board").json()["columns"][0]["id"]
    card_id = client.post(f"/api/projects/{project_id}/cards", json={"column_id": column_id, "title": "旧卡片"}).json()["id"]
    me = client.get("/api/auth/me").json()["id"]
    client.put(f"/api/cards/{card_id}/assignees", json={"ids": [me]})
    client.patch(f"/api/cards/{card_id}", json={"description": "不能丢", "priority": "high"})

    engine = get_engine()
    with engine.begin() as conn:
        names = conn.execute(
            text(
                "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cards' "
                "AND COLUMN_NAME = 'responsible_user_id' AND REFERENCED_TABLE_NAME IS NOT NULL"
            )
        ).scalars().all()
        for name in names:
            if not name.replace("_", "").isalnum():
                raise AssertionError(name)
            conn.execute(text(f"ALTER TABLE cards DROP FOREIGN KEY `{name}`"))
        conn.execute(text("ALTER TABLE cards DROP COLUMN responsible_user_id"))

    upgrade_schema()
    detail = client.get(f"/api/cards/{card_id}").json()["card"]
    assert detail["title"] == "旧卡片"
    assert detail["description"] == "不能丢"
    assert detail["priority"] == "high"
    assert detail["assignee_ids"] == [me]
    assert detail["responsible_user_id"] is None

    upgraded = client.patch(f"/api/cards/{card_id}", json={"responsible_user_id": me})
    assert upgraded.status_code == 200, upgraded.text
    assert upgraded.json()["card"]["responsible_user_id"] == me
    upgrade_schema()
    kept = client.get(f"/api/cards/{card_id}").json()["card"]
    assert kept["title"] == "旧卡片"
    assert kept["description"] == "不能丢"
    assert kept["assignee_ids"] == [me]
    assert kept["responsible_user_id"] == me
