from __future__ import annotations

from datetime import date, timedelta


def register(client, email, name="测试"):
    sent = client.post("/api/auth/code", json={"email": email})
    assert sent.status_code == 200, sent.text
    from app.mail import captured_code
    response = client.post("/api/auth/register", json={"email": email, "password": "password1", "display_name": name, "code": captured_code(email)})
    assert response.status_code == 200, response.text
    return response.json()


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_auth_and_header(client):
    denied = client.post("/api/auth/register", json={"email": "a@example.com", "password": "password1", "display_name": "甲"}, headers={"X-Kanban": "0"})
    assert denied.status_code == 403
    user = register(client, "a@example.com", "甲")
    assert user["email"] == "a@example.com"
    assert client.get("/api/auth/me").json()["display_name"] == "甲"
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    logged = client.post("/api/auth/login", json={"email": "a@example.com", "password": "password1"})
    assert logged.status_code == 200
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-password"}).status_code == 401


def test_register_requires_email_code(client):
    from datetime import datetime

    from app.db import session_factory
    from app.mail import captured_code
    from app.models import EmailCode, utcnow

    body = {"email": "c@example.com", "password": "password1", "display_name": "丙", "code": "000000"}
    assert client.post("/api/auth/register", json=body).status_code == 400
    sent = client.post("/api/auth/code", json={"email": "c@example.com"})
    assert sent.status_code == 200
    assert sent.json()["retry_after"] == 60
    assert client.post("/api/auth/code", json={"email": "c@example.com"}).status_code == 429
    real = captured_code("c@example.com")
    wrong = "000000" if real != "000000" else "111111"
    assert client.post("/api/auth/register", json={**body, "code": wrong}).status_code == 400
    db = session_factory()()
    row = db.get(EmailCode, "c@example.com")
    row.sent_at = utcnow() - timedelta(seconds=120)
    row.expires_at = datetime(2000, 1, 1)
    db.commit()
    db.close()
    assert client.post("/api/auth/register", json={**body, "code": real}).status_code == 400
    user = register(client, "c@example.com", "丙")
    assert user["email"] == "c@example.com"
    assert client.post("/api/auth/code", json={"email": "c@example.com"}).status_code == 409


def test_register_code_locks_after_misses(client):
    from app.mail import captured_code

    email = "lock@example.com"
    assert client.post("/api/auth/code", json={"email": email}).status_code == 200
    real = captured_code(email)
    wrong = "000000" if real != "000000" else "111111"
    body = {"email": email, "password": "password1", "display_name": "锁", "code": wrong}
    for _ in range(5):
        assert client.post("/api/auth/register", json=body).status_code == 400
    assert client.post("/api/auth/register", json={**body, "code": real}).status_code == 400


def test_project_board_and_quota(client):
    register(client, "owner@example.com", "拥有者")
    created = client.post("/api/projects", json={"name": "春季发布", "description": "第一块板", "color": "#D63A56"})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["quota"]["used"] == 1
    project_id = body["project"]["id"]
    notes = client.get("/api/notifications").json()
    created_note = next(item for item in notes["items"] if item["type"] == "project_created")
    assert created_note["title"] == "项目已创建"
    assert created_note["body"] == "你创建了「春季发布」"
    assert created_note["project_id"] == project_id
    assert notes["unread"] == 1
    board = client.get(f"/api/projects/{project_id}/board").json()
    assert [column["name"] for column in board["columns"]] == ["待办", "进行中", "已完成"]
    assert {label["name"] for label in board["labels"]} == {"重要", "设计", "开发", "阻塞"}
    first = board["columns"][0]["id"]
    second = board["columns"][1]["id"]
    card = client.post(f"/api/projects/{project_id}/cards", json={"column_id": first, "title": "写首页"})
    assert card.status_code == 200, card.text
    card_id = card.json()["id"]
    moved = client.post(f"/api/cards/{card_id}/move", json={"column_id": second, "index": 0})
    assert moved.status_code == 200, moved.text
    assert card_id in moved.json()["columns"][0]["card_ids"] or card_id in moved.json()["columns"][1]["card_ids"]
    detail = client.get(f"/api/cards/{card_id}").json()
    assert detail["card"]["column_id"] == second
    listed = client.post(f"/api/cards/{card_id}/checklists", json={"title": "验收"})
    assert listed.status_code == 200, listed.text
    item = client.post(f"/api/checklists/{listed.json()['id']}/items", json={"text": "手机宽度"})
    assert item.status_code == 200
    checked = client.patch(f"/api/checklist-items/{item.json()['id']}", json={"done": True})
    assert checked.json()["done"] is True
    comment = client.post(f"/api/cards/{card_id}/comments", json={"body": "记得看移动端"})
    assert comment.status_code == 200
    assert comment.json()["comments"][0]["body"] == "记得看移动端"


def test_invite_requires_approval(client):
    register(client, "owner@example.com", "拥有者")
    project_id = client.post("/api/projects", json={"name": "协作", "description": "", "color": "#3D6B8A"}).json()["project"]["id"]
    client.post("/api/auth/logout")
    guest = register(client, "guest@example.com", "客人")
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password1"}).status_code == 200
    missing = client.post(f"/api/projects/{project_id}/invites", json={"email": "nobody@example.com", "role": "member"})
    assert missing.status_code == 404
    invited = client.post(f"/api/projects/{project_id}/invites", json={"email": "guest@example.com", "role": "member"})
    assert invited.status_code == 200, invited.text
    assert invited.json()["invites"][0]["email"] == "guest@example.com"
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "guest@example.com", "password": "password1"}).status_code == 200
    notes = client.get("/api/notifications").json()
    pending = [item for item in notes["items"] if item["status"] == "pending"]
    assert pending and pending[0]["type"] == "project_invite"
    assert client.get("/api/projects").json()["projects"] == []
    accepted = client.post(f"/api/notifications/{pending[0]['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    projects = client.get("/api/projects").json()["projects"]
    assert projects[0]["id"] == project_id
    assert projects[0]["role"] == "member"
    assert guest["id"]


def test_reject_and_viewer_cannot_write(client):
    register(client, "owner@example.com", "拥有者")
    project_id = client.post("/api/projects", json={"name": "只读", "description": "", "color": "#5C6B52"}).json()["project"]["id"]
    column_id = client.get(f"/api/projects/{project_id}/board").json()["columns"][0]["id"]
    client.post("/api/auth/logout")
    register(client, "view@example.com", "观察")
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password1"})
    client.post(f"/api/projects/{project_id}/invites", json={"email": "view@example.com", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "view@example.com", "password": "password1"})
    note_id = client.get("/api/notifications").json()["items"][0]["id"]
    assert client.post(f"/api/notifications/{note_id}/reject").status_code == 200
    assert client.get("/api/projects").json()["projects"] == []
    client.post("/api/auth/logout")
    register(client, "reader@example.com", "读者")
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "owner@example.com", "password": "password1"})
    client.post(f"/api/projects/{project_id}/invites", json={"email": "reader@example.com", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "reader@example.com", "password": "password1"})
    note_id = next(item["id"] for item in client.get("/api/notifications").json()["items"] if item["status"] == "pending")
    client.post(f"/api/notifications/{note_id}/accept")
    denied = client.post(f"/api/projects/{project_id}/cards", json={"column_id": column_id, "title": "不该成功"})
    assert denied.status_code == 403


def test_daily_project_cap(client, monkeypatch):
    register(client, "cap@example.com", "限额")
    monkeypatch.setenv("DAILY_PROJECT_LIMIT", "2")
    assert client.post("/api/projects", json={"name": "一", "description": "", "color": "#D63A56"}).status_code == 200
    assert client.post("/api/projects", json={"name": "二", "description": "", "color": "#C47B2B"}).status_code == 200
    blocked = client.post("/api/projects", json={"name": "三", "description": "", "color": "#5C6B52"})
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "今天最多创建 2 个项目，明天再来"


def test_attachment_and_due(client):
    register(client, "files@example.com", "文件")
    project_id = client.post("/api/projects", json={"name": "附件", "description": "", "color": "#8A4B5A"}).json()["project"]["id"]
    column_id = client.get(f"/api/projects/{project_id}/board").json()["columns"][0]["id"]
    card_id = client.post(f"/api/projects/{project_id}/cards", json={"column_id": column_id, "title": "带附件"}).json()["id"]
    uploaded = client.post(f"/api/cards/{card_id}/attachments", files={"file": ("note.txt", b"hello", "text/plain")})
    assert uploaded.status_code == 200, uploaded.text
    file_id = uploaded.json()["id"]
    downloaded = client.get(f"/api/attachments/{file_id}/file")
    assert downloaded.status_code == 200
    assert downloaded.content == b"hello"
    due = (date.today() - timedelta(days=1)).isoformat()
    patched = client.patch(f"/api/cards/{card_id}", json={"due_on": due, "priority": "high", "done": True})
    assert patched.status_code == 200, patched.text
    assert patched.json()["card"]["due_on"] == due
    assert patched.json()["card"]["done"] is True
    tasks = client.get("/api/me/cards").json()["cards"]
    assert tasks == []
    client.put(f"/api/cards/{card_id}/assignees", json={"ids": [client.get("/api/auth/me").json()["id"]]})
    tasks = client.get("/api/me/cards").json()["cards"]
    assert tasks[0]["title"] == "带附件"


def test_duplicate_card_lands_after_original(client):
    register(client, "dup@example.com", "复制")
    project_id = client.post("/api/projects", json={"name": "复制", "description": "", "color": "#D63A56"}).json()["project"]["id"]
    column_id = client.get(f"/api/projects/{project_id}/board").json()["columns"][0]["id"]
    ids = [
        client.post(f"/api/projects/{project_id}/cards", json={"column_id": column_id, "title": name}).json()["id"]
        for name in ("A", "B", "C")
    ]
    copy_id = client.post(f"/api/cards/{ids[0]}/duplicate", json={}).json()["id"]
    order = [card["id"] for card in client.get(f"/api/projects/{project_id}/board").json()["columns"][0]["cards"]]
    assert order == [ids[0], copy_id, ids[1], ids[2]]


def test_card_detail_reports_checklist_progress(client):
    register(client, "check@example.com", "清单")
    project_id = client.post("/api/projects", json={"name": "清单", "description": "", "color": "#3D6B8A"}).json()["project"]["id"]
    column_id = client.get(f"/api/projects/{project_id}/board").json()["columns"][0]["id"]
    card_id = client.post(f"/api/projects/{project_id}/cards", json={"column_id": column_id, "title": "带清单"}).json()["id"]
    checklist_id = client.post(f"/api/cards/{card_id}/checklists", json={"title": "步骤"}).json()["id"]
    done_item = client.post(f"/api/checklists/{checklist_id}/items", json={"text": "已完成"}).json()["id"]
    client.post(f"/api/checklists/{checklist_id}/items", json={"text": "未完成"})
    client.patch(f"/api/checklist-items/{done_item}", json={"done": True})
    detail = client.get(f"/api/cards/{card_id}").json()
    assert detail["card"]["checklist"] == {"done": 1, "total": 2}
