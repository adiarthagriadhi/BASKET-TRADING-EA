from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..fees import calculate_fee
from ..models import (
    LedgerEntry,
    Merchant,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Refund,
    RefundStatus,
    WebhookDelivery,
)
from ..providers import get_provider
from ..schemas import PaymentCreate, PaymentOut, RefundOut
from .webhooks import enqueue_event

QRIS_MAX_AMOUNT = 10_000_000  # batas transaksi QRIS per transaksi (ketentuan BI)
MIN_AMOUNT = 1_000


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_out(payment: Payment) -> PaymentOut:
    return PaymentOut.model_validate(
        {
            **{c: getattr(payment, c) for c in (
                "id", "reference_id", "amount", "currency", "method", "channel", "status", "fee",
                "refunded_amount", "description", "customer", "metadata_", "instructions",
                "paid_at", "created_at",
            )},
            "expires_at": _aware(payment.expires_at),
            "net_amount": payment.amount - payment.fee,
            "checkout_url": f"{get_settings().public_base_url}/checkout/{payment.id}",
        }
    )


def expire_if_due(db: Session, payment: Payment) -> tuple[bool, WebhookDelivery | None]:
    """Tandai EXPIRED bila lewat batas waktu. Kembalikan (expired, webhook)."""
    if payment.status == PaymentStatus.PENDING and _aware(payment.expires_at) <= datetime.now(timezone.utc):
        payment.status = PaymentStatus.EXPIRED
        merchant = db.get(Merchant, payment.merchant_id)
        return True, enqueue_event(db, merchant, "payment.expired", to_out(payment).model_dump(mode="json"))
    return False, None


def create_payment(
    db: Session, merchant: Merchant, data: PaymentCreate, idempotency_key: str | None
) -> tuple[Payment, bool, WebhookDelivery | None]:
    """Kembalikan (payment, created, webhook). created=False bila hasil idempotency replay."""
    if idempotency_key:
        existing = db.scalar(
            select(Payment).where(Payment.merchant_id == merchant.id, Payment.idempotency_key == idempotency_key)
        )
        if existing:
            if existing.reference_id != data.reference_id or existing.amount != data.amount:
                raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key reused with different parameters")
            return existing, False, None

    if data.amount < MIN_AMOUNT:
        raise HTTPException(422, f"Minimum amount is {MIN_AMOUNT}")
    if data.method == PaymentMethod.QRIS and data.amount > QRIS_MAX_AMOUNT:
        raise HTTPException(422, f"QRIS maximum amount is {QRIS_MAX_AMOUNT}")
    dup = db.scalar(
        select(Payment.id).where(Payment.merchant_id == merchant.id, Payment.reference_id == data.reference_id)
    )
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, f"reference_id already used by {dup}")

    provider = get_provider()
    payment = Payment(
        merchant_id=merchant.id,
        reference_id=data.reference_id,
        idempotency_key=idempotency_key,
        amount=data.amount,
        currency=data.currency,
        method=data.method,
        channel=data.channel.upper() if data.channel else None,
        fee=calculate_fee(data.method, data.amount),
        description=data.description,
        customer=data.customer.model_dump(exclude_none=True) if data.customer else None,
        metadata_=data.metadata,
        provider=provider.name,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=get_settings().payment_expiry_minutes),
    )
    if payment.fee >= payment.amount:
        raise HTTPException(422, "Amount too small to cover fees")
    try:
        result = provider.create_charge(payment)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    payment.provider_reference = result.provider_reference
    payment.instructions = result.instructions
    db.add(payment)
    db.flush()
    delivery = enqueue_event(db, merchant, "payment.created", to_out(payment).model_dump(mode="json"))
    return payment, True, delivery


def get_payment_for_update(db: Session, payment_id: str, merchant_id: str | None = None) -> Payment:
    stmt = select(Payment).where(Payment.id == payment_id).with_for_update()
    if merchant_id:
        stmt = stmt.where(Payment.merchant_id == merchant_id)
    payment = db.scalar(stmt)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment


def mark_paid(db: Session, payment: Payment) -> WebhookDelivery | None:
    """Dipanggil saat acquirer mengonfirmasi dana diterima."""
    if expire_if_due(db, payment)[0]:
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment has expired")
    if payment.status != PaymentStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Payment is {payment.status.value}")
    payment.status = PaymentStatus.PAID
    payment.paid_at = datetime.now(timezone.utc)
    db.add_all(
        [
            LedgerEntry(merchant_id=payment.merchant_id, payment_id=payment.id, entry_type="PAYMENT", amount=payment.amount),
            LedgerEntry(merchant_id=payment.merchant_id, payment_id=payment.id, entry_type="FEE", amount=-payment.fee),
        ]
    )
    merchant = db.get(Merchant, payment.merchant_id)
    return enqueue_event(db, merchant, "payment.paid", to_out(payment).model_dump(mode="json"))


def refund_payment(
    db: Session, payment: Payment, amount: int | None, reason: str | None
) -> tuple[Refund, WebhookDelivery | None]:
    if payment.status not in (PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot refund a {payment.status.value} payment")
    refundable = payment.amount - payment.refunded_amount
    amount = amount or refundable
    if amount > refundable:
        raise HTTPException(422, f"Refundable amount is {refundable}")
    if balance_of(db, payment.merchant_id) < amount:
        raise HTTPException(status.HTTP_409_CONFLICT, "Insufficient merchant balance for refund")

    ok = get_provider(payment.provider).refund(payment, amount)
    refund = Refund(
        payment_id=payment.id,
        amount=amount,
        reason=reason,
        status=RefundStatus.SUCCEEDED if ok else RefundStatus.FAILED,
    )
    db.add(refund)
    if ok:
        payment.refunded_amount += amount
        payment.status = (
            PaymentStatus.REFUNDED if payment.refunded_amount == payment.amount else PaymentStatus.PARTIALLY_REFUNDED
        )
        db.add(LedgerEntry(merchant_id=payment.merchant_id, payment_id=payment.id, entry_type="REFUND", amount=-amount))
    db.flush()
    merchant = db.get(Merchant, payment.merchant_id)
    event = "refund.succeeded" if ok else "refund.failed"
    delivery = enqueue_event(db, merchant, event, RefundOut.model_validate(refund).model_dump(mode="json"))
    return refund, delivery


def balance_of(db: Session, merchant_id: str) -> int:
    return db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(LedgerEntry.merchant_id == merchant_id))


def ledger_summary(db: Session, merchant_id: str) -> dict[str, int]:
    rows = db.execute(
        select(LedgerEntry.entry_type, func.sum(LedgerEntry.amount))
        .where(LedgerEntry.merchant_id == merchant_id)
        .group_by(LedgerEntry.entry_type)
    ).all()
    return {k: int(v) for k, v in rows}


def expire_overdue(db: Session) -> list[str]:
    now = datetime.now(timezone.utc)
    pending = db.scalars(select(Payment).where(Payment.status == PaymentStatus.PENDING)).all()
    deliveries = []
    for p in pending:
        if _aware(p.expires_at) <= now:
            _, d = expire_if_due(db, p)
            if d:
                deliveries.append(d.id)
    return deliveries
