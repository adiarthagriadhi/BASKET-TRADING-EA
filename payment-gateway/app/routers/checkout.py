"""Halaman checkout sederhana yang bisa dibuka pelanggan akhir."""

from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Merchant, Payment
from ..services import payments as svc

router = APIRouter(tags=["checkout"])


def _rupiah(n: int) -> str:
    return "Rp " + f"{n:,}".replace(",", ".")


@router.get("/checkout/{payment_id}", response_class=HTMLResponse, include_in_schema=False)
def checkout_page(payment_id: str, db: Session = Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(404, "Payment not found")
    if svc.expire_if_due(db, payment)[0]:
        db.commit()
    merchant = db.get(Merchant, payment.merchant_id)
    rows = "".join(
        f"<tr><th>{escape(str(k)).replace('_', ' ').title()}</th><td><code>{escape(str(v))}</code></td></tr>"
        for k, v in (payment.instructions or {}).items()
    )
    return f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Pembayaran</title>
<style>body{{font-family:system-ui,sans-serif;max-width:480px;margin:40px auto;padding:0 16px;color:#1a1a1a}}
.card{{border:1px solid #ddd;border-radius:12px;padding:24px}}th{{text-align:left;padding-right:12px;color:#666;font-weight:500}}
td code{{word-break:break-all}}.amount{{font-size:28px;font-weight:700}}.status{{display:inline-block;padding:2px 10px;border-radius:99px;background:#eee}}</style>
</head><body><div class="card">
<p>{escape(merchant.name)}</p>
<p class="amount">{_rupiah(payment.amount)}</p>
<p>{escape(payment.description or payment.reference_id)}</p>
<p>Status: <span class="status">{payment.status.value}</span></p>
<p>Metode: {payment.method.value}{' · ' + escape(payment.channel) if payment.channel else ''}</p>
<table>{rows}</table>
<p><small>Bayar sebelum {payment.expires_at:%d-%m-%Y %H:%M} UTC</small></p>
</div></body></html>"""
