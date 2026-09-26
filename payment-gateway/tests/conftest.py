import os
import tempfile

import httpx
import pytest

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ADMIN_TOKEN"] = "test-admin"
os.environ["ENVIRONMENT"] = "sandbox"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import webhooks  # noqa: E402

ADMIN = {"X-Admin-Token": "test-admin"}


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def webhook_inbox(monkeypatch):
    """Tangkap semua webhook keluar alih-alih mengirim ke jaringan."""
    inbox: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        inbox.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(webhooks, "http_client_factory", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return inbox


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def merchant(client, webhook_inbox):
    r = client.post(
        "/admin/merchants",
        json={"name": "Toko Maju", "email": "owner@tokomaju.id", "webhook_url": "https://tokomaju.id/hook"},
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    data["auth"] = {"Authorization": f"Bearer {data['api_key']}"}
    return data
