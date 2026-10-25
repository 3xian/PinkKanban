from test_responsible import register
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import CardIn


def test_create_card_input_validation():
    basic = CardIn(column_id=1, title="  任务  ")
    assert basic.title == "任务"
    assert basic.description == ""
    assert basic.responsible_user_id is None
    assert CardIn(column_id=1, title="任务", due_on="2026-12-01").due_on == date(2026, 12, 1)
    for fields in ({"title": "  "}, {"description": "x" * 20001}, {"due_on": "invalid"}):
        with pytest.raises(ValidationError):
            CardIn(**{"column_id": 1, "title": "任务", **fields})


def test_create_card_details_are_atomic(client):
    owner = register(client, "create-owner@example.com")
    project = client.post("/api/projects", json={"name": "创建任务", "color": "#D63A56"}).json()["project"]
    url = f"/api/projects/{project['id']}"
    board = client.get(f"{url}/board").json()
    payload = dict(column_id=board["columns"][0]["id"], title="交付设计", description="背景\r\n验收标准", due_on="2026-12-01")
    rejected = client.post(f"{url}/cards", json={**payload, "responsible_user_id": 999999})
    assert rejected.status_code == 400
    assert not client.get(f"{url}/board").json()["columns"][0]["cards"]
    created = client.post(f"{url}/cards", json={**payload, "responsible_user_id": owner["id"]})
    assert created.status_code == 200, created.text
    card = client.get(f"/api/cards/{created.json()['id']}").json()["card"]
    assert card["description"] == "背景\n验收标准"
    assert card["due_on"] == "2026-12-01"
    assert card["responsible_user_id"] == owner["id"]
    assert owner["id"] in card["assignee_ids"]
    assert client.post(f"{url}/cards", json={**payload, "description": "x" * 20001}).status_code == 422
    basic = client.post(f"{url}/cards", json={"column_id": payload["column_id"], "title": "只填标题"})
    assert basic.status_code == 200
    assert basic.json()["responsible_user_id"] is None
