"""Model bisnis: biaya MDR (Merchant Discount Rate) per metode pembayaran.

Sesuaikan dengan biaya dari acquirer + margin Anda. Nilai di bawah hanya contoh.
"""

from .models import PaymentMethod

# (persentase, biaya tetap dalam rupiah)
FEE_SCHEDULE: dict[PaymentMethod, tuple[float, int]] = {
    PaymentMethod.QRIS: (0.007, 0),  # 0,7% (batas MDR QRIS dari BI)
    PaymentMethod.VIRTUAL_ACCOUNT: (0.0, 4_000),
    PaymentMethod.EWALLET: (0.015, 0),
}


def calculate_fee(method: PaymentMethod, amount: int) -> int:
    pct, flat = FEE_SCHEDULE[method]
    return round(amount * pct) + flat
