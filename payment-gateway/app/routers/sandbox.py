"""Endpoint sandbox untuk mensimulasikan pelanggan membayar.

Di produksi, konfirmasi datang dari callback acquirer (bank/switching) yang
harus diverifikasi tanda tangannya sebelum memanggil svc.mark_paid.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Merchant
from ..schemas import PaymentOut
from ..security import get_current_merchant
from ..services import payments as svc
from ..services.webhooks import deliver

router = APIRouter(prefix="/v1/simulate", tags=["sandbox"])


def _sandbox_only() -> None:
    if get_settings().environment == "production":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


@router.post("/payments/{payment_id}/pay", response_model=PaymentOut, dependencies=[Depends(_sandbox_only)])
def simulate_pay(
    payment_id: str,
    background: BackgroundTasks,
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    payment = svc.get_payment_for_update(db, payment_id, merchant.id)
    delivery = svc.mark_paid(db, payment)
    db.commit()
    if delivery:
        background.add_task(deliver, delivery.id)
    return svc.to_out(payment)
