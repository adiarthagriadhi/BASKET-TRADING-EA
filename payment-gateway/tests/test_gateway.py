import json

from app.security import verify_signature

from .conftest import ADMIN


def create_payment(client, merchant, **overrides):
    body = {"reference_id": "ORDER-1", "amount": 100_000, "method": "QRIS", **overrides}
    return client.post("/v1/payments", json=body, headers=merchant["auth"])


def test_admin_auth_required(client):
    assert client.get("/admin/merchants").status_code == 422
    assert client.get("/admin/merchants", headers={"X-Admin-Token": "wrong"}).status_code == 401


def test_merchant_api_key_auth(client, merchant):
    assert client.get("/v1/me", headers={"Authorization": "Bearer sk_test_nope"}).status_code == 401
    r = client.get("/v1/me", headers=merchant["auth"])
    assert r.status_code == 200 and r.json()["email"] == "owner@tokomaju.id"


def test_duplicate_merchant_email(client, merchant):
    r = client.post("/admin/merchants", json={"name": "X", "email": "owner@tokomaju.id"}, headers=ADMIN)
    assert r.status_code == 409


def test_create_qris_payment_with_fee(client, merchant):
    r = create_payment(client, merchant)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "PENDING"
    assert p["fee"] == 700  # 0,7% MDR
    assert p["net_amount"] == 99_300
    assert "qr_string" in p["instructions"]
    assert p["checkout_url"].endswith(f"/checkout/{p['id']}")


def test_virtual_account_requires_valid_bank(client, merchant):
    assert create_payment(client, merchant, method="VIRTUAL_ACCOUNT", channel="XYZ").status_code == 422
    r = create_payment(client, merchant, method="VIRTUAL_ACCOUNT", channel="bca")
    assert r.status_code == 201
    assert r.json()["instructions"]["va_number"].startswith("39358")
    assert r.json()["fee"] == 4_000


def test_qris_limit_and_minimum(client, merchant):
    assert create_payment(client, merchant, amount=10_000_001).status_code == 422
    assert create_payment(client, merchant, amount=500).status_code == 422


def test_idempotency(client, merchant):
    h = {**merchant["auth"], "Idempotency-Key": "abc"}
    body = {"reference_id": "ORDER-9", "amount": 50_000, "method": "QRIS"}
    first = client.post("/v1/payments", json=body, headers=h)
    again = client.post("/v1/payments", json=body, headers=h)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    conflict = client.post("/v1/payments", json={**body, "amount": 60_000}, headers=h)
    assert conflict.status_code == 409


def test_duplicate_reference_rejected(client, merchant):
    assert create_payment(client, merchant).status_code == 201
    assert create_payment(client, merchant).status_code == 409


def test_payments_are_isolated_between_merchants(client, merchant):
    pid = create_payment(client, merchant).json()["id"]
    other = client.post("/admin/merchants", json={"name": "Lain", "email": "lain@x.id"}, headers=ADMIN).json()
    r = client.get(f"/v1/payments/{pid}", headers={"Authorization": f"Bearer {other['api_key']}"})
    assert r.status_code == 404


def test_pay_flow_updates_balance_and_sends_signed_webhook(client, merchant, webhook_inbox):
    pid = create_payment(client, merchant).json()["id"]
    r = client.post(f"/v1/simulate/payments/{pid}/pay", headers=merchant["auth"])
    assert r.status_code == 200 and r.json()["status"] == "PAID"
    assert client.post(f"/v1/simulate/payments/{pid}/pay", headers=merchant["auth"]).status_code == 409

    bal = client.get("/v1/balance", headers=merchant["auth"]).json()
    assert bal == {
        "merchant_id": merchant["id"], "currency": "IDR", "balance": 99_300,
        "gross_volume": 100_000, "total_fees": 700, "total_refunds": 0,
    }

    events = [json.loads(req.content) for req in webhook_inbox]
    assert [e["type"] for e in events] == ["payment.created", "payment.paid"]
    paid_req = webhook_inbox[-1]
    assert verify_signature(merchant["webhook_secret"], paid_req.content, paid_req.headers["X-Signature"])
    assert not verify_signature("whsec_wrong", paid_req.content, paid_req.headers["X-Signature"])


def test_refunds(client, merchant, webhook_inbox):
    pid = create_payment(client, merchant).json()["id"]
    assert client.post(f"/v1/payments/{pid}/refunds", json={}, headers=merchant["auth"]).status_code == 409
    client.post(f"/v1/simulate/payments/{pid}/pay", headers=merchant["auth"])

    r = client.post(f"/v1/payments/{pid}/refunds", json={"amount": 30_000}, headers=merchant["auth"])
    assert r.status_code == 201
    assert client.get(f"/v1/payments/{pid}", headers=merchant["auth"]).json()["status"] == "PARTIALLY_REFUNDED"
    too_much = client.post(f"/v1/payments/{pid}/refunds", json={"amount": 70_001}, headers=merchant["auth"])
    assert too_much.status_code == 422

    # Refund penuh sisanya melebihi saldo (fee sudah dipotong), jadi ditolak.
    assert client.post(f"/v1/payments/{pid}/refunds", json={}, headers=merchant["auth"]).status_code == 409
    assert client.post(f"/v1/payments/{pid}/refunds", json={"amount": 69_300}, headers=merchant["auth"]).status_code == 201
    assert client.get("/v1/balance", headers=merchant["auth"]).json()["balance"] == 0
    assert json.loads(webhook_inbox[-1].content)["type"] == "refund.succeeded"


def test_expiry(client, merchant, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal
    from app.models import Payment

    pid = create_payment(client, merchant).json()["id"]
    with SessionLocal() as db:
        db.get(Payment, pid).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.post(f"/v1/simulate/payments/{pid}/pay", headers=merchant["auth"]).status_code == 409
    assert client.get(f"/v1/payments/{pid}", headers=merchant["auth"]).json()["status"] == "EXPIRED"


def test_expire_job(client, merchant):
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal
    from app.models import Payment

    pid = create_payment(client, merchant).json()["id"]
    with SessionLocal() as db:
        db.get(Payment, pid).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.post("/admin/jobs/expire-payments", headers=ADMIN).json() == {"expired_events": 1}


def test_webhook_retry(client, merchant, monkeypatch):
    import httpx

    from app.services import webhooks

    monkeypatch.setattr(
        webhooks, "http_client_factory",
        lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
    )
    create_payment(client, merchant)
    hooks = client.get("/v1/webhooks", headers=merchant["auth"]).json()
    assert hooks[0]["delivered"] is False and hooks[0]["last_status_code"] == 500

    monkeypatch.setattr(
        webhooks, "http_client_factory",
        lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
    )
    assert client.post("/admin/jobs/retry-webhooks", headers=ADMIN).json() == {"queued": 1}
    hooks = client.get("/v1/webhooks", headers=merchant["auth"]).json()
    assert hooks[0]["delivered"] is True and hooks[0]["attempts"] == 2


def test_rotate_api_key(client, merchant):
    r = client.post(f"/admin/merchants/{merchant['id']}/api-keys", headers=ADMIN)
    assert r.status_code == 201
    assert client.get("/v1/me", headers=merchant["auth"]).status_code == 401
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {r.json()['api_key']}"}).status_code == 200


def test_checkout_page(client, merchant):
    pid = create_payment(client, merchant, description="<script>x</script>").json()["id"]
    r = client.get(f"/checkout/{pid}")
    assert r.status_code == 200
    assert "Rp 100.000" in r.text and "<script>x" not in r.text
