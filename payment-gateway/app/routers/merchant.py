"""API publik untuk merchant (autentikasi: Authorization: Bearer sk_...)."""

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Merchant, Payment, PaymentStatus, Refund, WebhookDelivery
from ..schemas import (
    BalanceOut,
    MerchantOut,
    MerchantUpdate,
    PaymentCreate,
    PaymentOut,
    RefundCreate,
    RefundOut,
    WebhookDeliveryOut,
)
from ..security import get_current_merchant
from ..services import payments as svc
from ..services.webhooks import deliver

router = APIRouter(prefix="/v1", tags=["merchant"])


def build_balance(db: Session, merchant_id: str) -> BalanceOut:
    s = svc.ledger_summary(db, merchant_id)
    return BalanceOut(
        merchant_id=merchant_id,
        balance=sum(s.values()),
        gross_volume=s.get("PAYMENT", 0),
        total_fees=-s.get("FEE", 0),
        total_refunds=-s.get("REFUND", 0),
    )


@router.get("/me", response_model=MerchantOut)
def me(merchant: Merchant = Depends(get_current_merchant)):
    return merchant


@router.patch("/me", response_model=MerchantOut)
def update_me(data: MerchantUpdate, merchant: Merchant = Depends(get_current_merchant), db: Session = Depends(get_db)):
    merchant.webhook_url = str(data.webhook_url) if data.webhook_url else None
    db.commit()
    return merchant


@router.post("/payments", response_model=PaymentOut, status_code=201)
def create_payment(
    data: PaymentCreate,
    response: Response,
    background: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, max_length=100),
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    payment, created, delivery = svc.create_payment(db, merchant, data, idempotency_key)
    db.commit()
    if delivery:
        background.add_task(deliver, delivery.id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return svc.to_out(payment)


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(
    status_: PaymentStatus | None = Query(default=None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    stmt = select(Payment).where(Payment.merchant_id == merchant.id)
    if status_:
        stmt = stmt.where(Payment.status == status_)
    stmt = stmt.order_by(Payment.created_at.desc()).limit(min(limit, 200)).offset(offset)
    return [svc.to_out(p) for p in db.scalars(stmt).all()]


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: str,
    background: BackgroundTasks,
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    payment = svc.get_payment_for_update(db, payment_id, merchant.id)
    _, delivery = svc.expire_if_due(db, payment)
    db.commit()
    if delivery:
        background.add_task(deliver, delivery.id)
    return svc.to_out(payment)


@router.post("/payments/{payment_id}/refunds", response_model=RefundOut, status_code=201)
def create_refund(
    payment_id: str,
    data: RefundCreate,
    background: BackgroundTasks,
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    payment = svc.get_payment_for_update(db, payment_id, merchant.id)
    refund, delivery = svc.refund_payment(db, payment, data.amount, data.reason)
    db.commit()
    if delivery:
        background.add_task(deliver, delivery.id)
    return refund


@router.get("/payments/{payment_id}/refunds", response_model=list[RefundOut])
def list_refunds(payment_id: str, merchant: Merchant = Depends(get_current_merchant), db: Session = Depends(get_db)):
    payment = db.scalar(select(Payment).where(Payment.id == payment_id, Payment.merchant_id == merchant.id))
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return db.scalars(select(Refund).where(Refund.payment_id == payment_id).order_by(Refund.created_at)).all()


@router.get("/balance", response_model=BalanceOut)
def balance(merchant: Merchant = Depends(get_current_merchant), db: Session = Depends(get_db)):
    return build_balance(db, merchant.id)


@router.get("/webhooks", response_model=list[WebhookDeliveryOut])
def list_webhooks(limit: int = 50, merchant: Merchant = Depends(get_current_merchant), db: Session = Depends(get_db)):
    stmt = (
        select(WebhookDelivery)
        .where(WebhookDelivery.merchant_id == merchant.id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(min(limit, 200))
    )
    return db.scalars(stmt).all()
