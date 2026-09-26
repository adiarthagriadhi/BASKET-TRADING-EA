"""Integrasi langsung ke ShopeePay (API "merchant-host").

Autentikasi setiap request/notifikasi:
  X-Airpay-ClientId: <client_id>
  X-Airpay-Req-H:    base64(HMAC-SHA256(secret_key, raw_body))

Nominal dikirim dalam satuan x100 (Rp10.000 -> 1000000).

Catatan: cocokkan path & kode status dengan dokumentasi resmi yang Anda terima
saat onboarding ShopeePay; semua nilai tersebut dikumpulkan di konstanta di bawah.
"""

import base64
import hashlib
import hmac
import json
import time
import uuid

import httpx

from ..config import Settings, get_settings
from ..models import Payment, PaymentMethod
from .base import ChargeResult, PaymentProvider, ProviderError

PATH_CREATE_ORDER = "/v3/merchant-host/order/create"
PATH_CHECK_TRANSACTION = "/v3/merchant-host/transaction/check"
PATH_REFUND = "/v3/merchant-host/transaction/refund/create"

TRANSACTION_TYPE_PAYMENT = 13
# status transaksi pada respons transaction/check
TX_STATUS = {2: "PENDING", 3: "PAID", 4: "FAILED"}
AMOUNT_MULTIPLIER = 100


def sign(secret: str, body: bytes) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def verify(secret: str, body: bytes, signature: str | None) -> bool:
    return bool(signature) and hmac.compare_digest(sign(secret, body), signature)


class ShopeePayProvider(PaymentProvider):
    name = "shopeepay"

    def __init__(self, settings: Settings | None = None, http_client_factory=None):
        self._settings = settings
        self.http_client_factory = http_client_factory or (lambda: httpx.Client(timeout=15))

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    def _post(self, path: str, payload: dict) -> dict:
        s = self.settings
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = {
            "Content-Type": "application/json",
            "X-Airpay-ClientId": s.shopeepay_client_id,
            "X-Airpay-Req-H": sign(s.shopeepay_secret_key, body),
        }
        try:
            with self.http_client_factory() as client:
                resp = client.post(s.shopeepay_base_url + path, content=body, headers=headers)
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"ShopeePay unreachable: {exc}") from exc
        if resp.status_code != 200 or data.get("errcode") != 0:
            raise ProviderError(f"ShopeePay error {data.get('errcode')}: {data.get('debug_msg', resp.text)[:200]}")
        return data

    def _base(self) -> dict:
        s = self.settings
        return {
            "request_id": uuid.uuid4().hex,
            "merchant_ext_id": s.shopeepay_merchant_ext_id,
            "store_ext_id": s.shopeepay_store_ext_id,
        }

    def create_charge(self, payment: Payment) -> ChargeResult:
        if payment.method != PaymentMethod.EWALLET or (payment.channel or "").upper() != "SHOPEEPAY":
            raise ValueError("ShopeePay provider only handles EWALLET/SHOPEEPAY")
        validity = max(60, int(payment.expires_at.timestamp() - time.time()))
        data = self._post(
            PATH_CREATE_ORDER,
            {
                **self._base(),
                "payment_reference_id": payment.id,
                "amount": payment.amount * AMOUNT_MULTIPLIER,
                "currency": payment.currency,
                "return_url": self.settings.shopeepay_return_url
                or f"{self.settings.public_base_url}/checkout/{payment.id}",
                "platform_type": self.settings.shopeepay_platform_type,
                "validity_period": validity,
            },
        )
        return ChargeResult(
            provider_reference=payment.id,
            instructions={
                "wallet": "SHOPEEPAY",
                "checkout_url": data.get("redirect_url_http"),
                "deeplink_url": data.get("redirect_url_app"),
            },
        )

    def check_status(self, payment: Payment) -> str | None:
        data = self._post(
            PATH_CHECK_TRANSACTION,
            {**self._base(), "reference_id": payment.id, "transaction_type": TRANSACTION_TYPE_PAYMENT},
        )
        tx = data.get("transaction") or {}
        status = TX_STATUS.get(tx.get("status"), "PENDING")
        if status == "PAID" and tx.get("amount") != payment.amount * AMOUNT_MULTIPLIER:
            raise ProviderError(f"Amount mismatch for {payment.id}: {tx.get('amount')}")
        return status

    def refund(self, payment: Payment, amount: int) -> bool:
        try:
            self._post(
                PATH_REFUND,
                {
                    **self._base(),
                    "payment_reference_id": payment.id,
                    "refund_reference_id": f"{payment.id}-r{uuid.uuid4().hex[:8]}",
                    "amount": amount * AMOUNT_MULTIPLIER,
                },
            )
        except ProviderError:
            return False
        return True
