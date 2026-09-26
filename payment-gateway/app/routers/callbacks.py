"""Notifikasi dari acquirer ke gateway."""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..providers import shopeepay
from ..services import payments as svc
from ..services.webhooks import deliver

router = APIRouter(prefix="/callbacks", tags=["acquirer callbacks"])
log = logging.getLogger(__name__)


@router.post("/shopeepay")
async def shopeepay_notification(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    """URL ini didaftarkan ke ShopeePay sebagai notify URL.

    Isi notifikasi tidak dipercaya begitu saja: setelah tanda tangan valid,
    status dikonfirmasi ulang lewat API transaction/check sebelum ditandai PAID.
    """
    settings = get_settings()
    if not settings.shopeepay_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    body = await request.body()
    if not shopeepay.verify(settings.shopeepay_secret_key, body, request.headers.get("X-Airpay-Req-H")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    try:
        payment_id = json.loads(body)["payment_reference_id"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed notification")

    payment = svc.get_payment_for_update(db, payment_id)
    if payment.provider != shopeepay.ShopeePayProvider.name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    delivery = svc.sync_with_provider(db, payment)
    db.commit()
    if delivery:
        background.add_task(deliver, delivery.id)
    log.info("ShopeePay notification for %s -> %s", payment.id, payment.status.value)
    return {"errcode": 0, "debug_msg": "success"}
