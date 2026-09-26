import json

import httpx
import pytest

from app.config import get_settings
from app.providers import get_provider, shopeepay

SECRET = "sp-secret"


class FakeShopeePay:
    """Meniru server ShopeePay: menyimpan order dan memverifikasi tanda tangan."""

    def __init__(self):
        self.orders: dict[str, dict] = {}
        self.requests: list[tuple[str, dict]] = []
        self.fail_create = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Airpay-ClientId"] == "client-1"
        assert shopeepay.verify(SECRET, request.content, request.headers["X-Airpay-Req-H"])
        body = json.loads(request.content)
        path = request.url.path
        self.requests.append((path, body))
        if path == shopeepay.PATH_CREATE_ORDER:
            if self.fail_create:
                return httpx.Response(200, json={"errcode": 5, "debug_msg": "merchant inactive"})
            self.orders[body["payment_reference_id"]] = {"amount": body["amount"], "status": 2}
            ref = body["payment_reference_id"]
            return httpx.Response(200, json={
                "request_id": body["request_id"], "errcode": 0, "debug_msg": "success",
                "redirect_url_app": f"shopeeid://pay/{ref}", "redirect_url_http": f"https://pay.shopee.co.id/{ref}",
            })
        if path == shopeepay.PATH_CHECK_TRANSACTION:
            order = self.orders[body["reference_id"]]
            return httpx.Response(200, json={"errcode": 0, "transaction": order})
        if path == shopeepay.PATH_REFUND:
            return httpx.Response(200, json={"errcode": 0})
        return httpx.Response(404, json={"errcode": 404})

    def notify(self, client, payment_id):
        body = json.dumps({"payment_reference_id": payment_id, "payment_status": 1}).encode()
        return client.post("/callbacks/shopeepay", content=body,
                           headers={"X-Airpay-Req-H": shopeepay.sign(SECRET, body)})


@pytest.fixture
def fake(monkeypatch):
    settings = get_settings()
    for k, v in {
        "shopeepay_client_id": "client-1", "shopeepay_secret_key": SECRET,
        "shopeepay_merchant_ext_id": "m-1", "shopeepay_store_ext_id": "s-1",
    }.items():
        monkeypatch.setattr(settings, k, v)
    server = FakeShopeePay()
    monkeypatch.setattr(get_provider("shopeepay"), "http_client_factory",
                        lambda: httpx.Client(transport=httpx.MockTransport(server.handler)))
    return server


def pay_with_shopeepay(client, merchant, **kw):
    body = {"reference_id": "SP-1", "amount": 75_000, "method": "EWALLET", "channel": "shopeepay", **kw}
    return client.post("/v1/payments", json=body, headers=merchant["auth"])


def test_create_order_calls_shopeepay(client, merchant, fake):
    r = pay_with_shopeepay(client, merchant)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["instructions"]["checkout_url"] == f"https://pay.shopee.co.id/{p['id']}"
    assert p["instructions"]["deeplink_url"].startswith("shopeeid://")
    path, sent = fake.requests[0]
    assert path == shopeepay.PATH_CREATE_ORDER
    assert sent["amount"] == 7_500_000  # x100
    assert sent["merchant_ext_id"] == "m-1" and sent["payment_reference_id"] == p["id"]


def test_shopeepay_error_returns_502(client, merchant, fake):
    fake.fail_create = True
    assert pay_with_shopeepay(client, merchant).status_code == 502


def test_other_ewallets_still_use_simulator(client, merchant, fake):
    r = pay_with_shopeepay(client, merchant, channel="OVO")
    assert r.status_code == 201 and fake.requests == []


def test_notification_marks_paid_only_after_confirmation(client, merchant, fake, webhook_inbox):
    pid = pay_with_shopeepay(client, merchant).json()["id"]

    # Notifikasi masuk tapi ShopeePay masih bilang PENDING -> tidak berubah
    assert fake.notify(client, pid).json()["errcode"] == 0
    assert client.get(f"/v1/payments/{pid}", headers=merchant["auth"]).json()["status"] == "PENDING"

    fake.orders[pid]["status"] = 3
    assert fake.notify(client, pid).status_code == 200
    assert client.get(f"/v1/payments/{pid}", headers=merchant["auth"]).json()["status"] == "PAID"
    assert client.get("/v1/balance", headers=merchant["auth"]).json()["balance"] == 75_000 - 1_125
    assert json.loads(webhook_inbox[-1].content)["type"] == "payment.paid"

    # Notifikasi ganda aman
    assert fake.notify(client, pid).status_code == 200
    assert client.get("/v1/balance", headers=merchant["auth"]).json()["balance"] == 73_875


def test_notification_rejects_bad_signature(client, merchant, fake):
    pid = pay_with_shopeepay(client, merchant).json()["id"]
    fake.orders[pid]["status"] = 3
    body = json.dumps({"payment_reference_id": pid}).encode()
    r = client.post("/callbacks/shopeepay", content=body, headers={"X-Airpay-Req-H": "forged"})
    assert r.status_code == 401
    assert client.get(f"/v1/payments/{pid}", headers=merchant["auth"]).json()["status"] == "PENDING"


def test_amount_mismatch_is_not_marked_paid(client, merchant, fake):
    pid = pay_with_shopeepay(client, merchant).json()["id"]
    fake.orders[pid] = {"status": 3, "amount": 100}
    assert fake.notify(client, pid).status_code == 502
    assert client.get(f"/v1/payments/{pid}", headers=merchant["auth"]).json()["status"] == "PENDING"


def test_manual_sync_and_failed_status(client, merchant, fake):
    pid = pay_with_shopeepay(client, merchant).json()["id"]
    fake.orders[pid]["status"] = 4
    r = client.post(f"/v1/payments/{pid}/sync", headers=merchant["auth"])
    assert r.json()["status"] == "FAILED"


def test_refund_goes_to_shopeepay(client, merchant, fake):
    pid = pay_with_shopeepay(client, merchant).json()["id"]
    fake.orders[pid]["status"] = 3
    client.post(f"/v1/payments/{pid}/sync", headers=merchant["auth"])
    r = client.post(f"/v1/payments/{pid}/refunds", json={"amount": 25_000}, headers=merchant["auth"])
    assert r.status_code == 201 and r.json()["status"] == "SUCCEEDED"
    path, sent = fake.requests[-1]
    assert path == shopeepay.PATH_REFUND and sent["amount"] == 2_500_000


def test_callback_disabled_without_credentials(client):
    assert client.post("/callbacks/shopeepay", content=b"{}").status_code == 404


def test_late_payment_after_local_expiry_is_recorded(client, merchant, fake):
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal
    from app.models import Payment

    pid = pay_with_shopeepay(client, merchant).json()["id"]
    with SessionLocal() as db:
        db.get(Payment, pid).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.get(f"/v1/payments/{pid}", headers=merchant["auth"]).json()["status"] == "EXPIRED"
    fake.orders[pid]["status"] = 3
    assert fake.notify(client, pid).status_code == 200
    assert client.get(f"/v1/payments/{pid}", headers=merchant["auth"]).json()["status"] == "PAID"
