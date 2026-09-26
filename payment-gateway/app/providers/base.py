"""Adapter ke acquirer / bank / penyedia e-wallet.

Gateway Anda menerima pembayaran dari merchant lalu meneruskannya ke acquirer
(bank mitra, switching QRIS, penerbit e-wallet). Setiap acquirer punya API
berbeda, jadi dibungkus lewat interface ini agar mudah ditambah/diganti.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..models import Payment


@dataclass
class ChargeResult:
    provider_reference: str
    instructions: dict = field(default_factory=dict)


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    def create_charge(self, payment: Payment) -> ChargeResult:
        """Buat tagihan di sisi acquirer dan kembalikan instruksi bayar."""

    @abstractmethod
    def refund(self, payment: Payment, amount: int) -> bool:
        """Kembalikan dana ke pelanggan. True jika berhasil."""
