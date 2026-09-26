"""Endpoint operator gateway (Anda sebagai pemilik usaha)."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import ApiKey, Merchant, WebhookDelivery
from ..schemas import ApiKeyCreated, BalanceOut, MerchantCreate, MerchantCreated, MerchantOut
from ..security import generate_api_key, generate_webhook_secret, hash_key, require_admin
from ..services import payments as svc
from ..services.webhooks import deliver
from .merchant import build_balance

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _issue_key(db: Session, merchant: Merchant) -> tuple[ApiKey, str]:
    raw = generate_api_key()
    key = ApiKey(merchant_id=merchant.id, prefix=raw[:12], key_hash=hash_key(raw))
    db.add(key)
    return key, raw


def _get_merchant(db: Session, merchant_id: str) -> Merchant:
    merchant = db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Merchant not found")
    return merchant


@router.post("/merchants", response_model=MerchantCreated, status_code=201)
def create_merchant(data: MerchantCreate, db: Session = Depends(get_db)):
    merchant = Merchant(
        name=data.name,
        email=data.email,
        webhook_url=str(data.webhook_url) if data.webhook_url else None,
        webhook_secret=generate_webhook_secret(),
    )
    db.add(merchant)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    _, raw = _issue_key(db, merchant)
    db.commit()
    return MerchantCreated(
        **MerchantOut.model_validate(merchant).model_dump(), api_key=raw, webhook_secret=merchant.webhook_secret
    )


@router.get("/merchants", response_model=list[MerchantOut])
def list_merchants(db: Session = Depends(get_db)):
    return db.scalars(select(Merchant).order_by(Merchant.created_at)).all()


@router.post("/merchants/{merchant_id}/api-keys", response_model=ApiKeyCreated, status_code=201)
def rotate_api_key(merchant_id: str, revoke_existing: bool = True, db: Session = Depends(get_db)):
    merchant = _get_merchant(db, merchant_id)
    if revoke_existing:
        for k in merchant.api_keys:
            k.is_active = False
    key, raw = _issue_key(db, merchant)
    db.commit()
    return ApiKeyCreated(id=key.id, api_key=raw)


@router.post("/merchants/{merchant_id}/deactivate", response_model=MerchantOut)
def deactivate_merchant(merchant_id: str, db: Session = Depends(get_db)):
    merchant = _get_merchant(db, merchant_id)
    merchant.is_active = False
    db.commit()
    return merchant


@router.get("/merchants/{merchant_id}/balance", response_model=BalanceOut)
def merchant_balance(merchant_id: str, db: Session = Depends(get_db)):
    return build_balance(db, _get_merchant(db, merchant_id).id)


@router.post("/jobs/expire-payments")
def run_expire_job(background: BackgroundTasks, db: Session = Depends(get_db)):
    """Panggil berkala (cron) untuk menandai pembayaran kedaluwarsa."""
    ids = svc.expire_overdue(db)
    db.commit()
    for d in ids:
        background.add_task(deliver, d)
    return {"expired_events": len(ids)}


@router.post("/jobs/retry-webhooks")
def run_retry_job(background: BackgroundTasks, db: Session = Depends(get_db)):
    """Panggil berkala (cron) untuk mengirim ulang webhook yang gagal."""
    ids = db.scalars(
        select(WebhookDelivery.id).where(
            WebhookDelivery.delivered.is_(False),
            WebhookDelivery.attempts < get_settings().webhook_max_attempts,
        )
    ).all()
    for d in ids:
        background.add_task(deliver, d)
    return {"queued": len(ids)}
