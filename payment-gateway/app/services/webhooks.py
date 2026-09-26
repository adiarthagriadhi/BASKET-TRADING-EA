import json

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import Merchant, WebhookDelivery
from ..security import sign_payload

# Bisa diganti di test untuk memakai transport tiruan.
http_client_factory = lambda: httpx.Client(timeout=get_settings().webhook_timeout_seconds)  # noqa: E731


def enqueue_event(db: Session, merchant: Merchant, event_type: str, data: dict) -> WebhookDelivery | None:
    if not merchant.webhook_url:
        return None
    delivery = WebhookDelivery(merchant_id=merchant.id, event_type=event_type, payload={})
    db.add(delivery)
    db.flush()
    delivery.payload = {"id": delivery.id, "type": event_type, "data": data}
    return delivery


def deliver(delivery_id: str, session_factory=None) -> None:
    """Kirim satu webhook. Dipanggil sebagai background task / worker."""
    db = (session_factory or SessionLocal)()
    try:
        delivery = db.get(WebhookDelivery, delivery_id)
        if delivery is None or delivery.delivered:
            return
        if delivery.attempts >= get_settings().webhook_max_attempts:
            return
        merchant = db.get(Merchant, delivery.merchant_id)
        if not merchant or not merchant.webhook_url:
            return
        body = json.dumps(delivery.payload, separators=(",", ":"), default=str).encode()
        headers = {
            "Content-Type": "application/json",
            "X-Signature": sign_payload(merchant.webhook_secret, body),
            "X-Event-Id": delivery.id,
        }
        delivery.attempts += 1
        try:
            with http_client_factory() as client:
                resp = client.post(merchant.webhook_url, content=body, headers=headers)
            delivery.last_status_code = resp.status_code
            delivery.delivered = 200 <= resp.status_code < 300
            delivery.last_error = None if delivery.delivered else f"HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            delivery.last_error = str(exc)[:500]
        db.commit()
    finally:
        db.close()
