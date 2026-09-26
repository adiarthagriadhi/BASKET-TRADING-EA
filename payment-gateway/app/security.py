import hashlib
import hmac
import secrets
import time

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import ApiKey, Merchant


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_key() -> str:
    env = "live" if get_settings().environment == "production" else "test"
    return f"sk_{env}_{secrets.token_urlsafe(32)}"


def generate_webhook_secret() -> str:
    return f"whsec_{secrets.token_urlsafe(32)}"


def sign_payload(secret: str, body: bytes, timestamp: int | None = None) -> str:
    """Header X-Signature: t=<unix>,v1=<hex HMAC-SHA256(secret, "<t>.<body>")>."""
    ts = timestamp if timestamp is not None else int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify_signature(secret: str, body: bytes, header: str, tolerance: int = 300) -> bool:
    """Dipakai merchant (atau test) untuk memverifikasi webhook."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs(time.time() - ts) > tolerance:
        return False
    return hmac.compare_digest(sign_payload(secret, body, ts), header)


def require_admin(x_admin_token: str = Header(...)) -> None:
    if not hmac.compare_digest(x_admin_token, get_settings().admin_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid admin token")


def get_current_merchant(
    authorization: str = Header(..., description="Bearer sk_..."),
    db: Session = Depends(get_db),
) -> Merchant:
    scheme, _, raw = authorization.partition(" ")
    if scheme.lower() != "bearer" or not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer API key")
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_key(raw), ApiKey.is_active))
    if key is None or not key.merchant.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return key.merchant
