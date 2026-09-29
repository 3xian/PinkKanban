import os

os.environ["DATABASE_URL"] = "mysql+pymysql://kanban:kanban@127.0.0.1:3307/kanban_test?charset=utf8mb4"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["DAILY_PROJECT_LIMIT"] = "30"

import pytest
from fastapi.testclient import TestClient

from app.db import reset_engine, truncate_all
from app.limit import _hits
from app.main import app


@pytest.fixture()
def client():
    reset_engine()
    truncate_all()
    _hits.clear()
    with TestClient(app, headers={"X-Kanban": "1"}) as test_client:
        yield test_client
    reset_engine()
