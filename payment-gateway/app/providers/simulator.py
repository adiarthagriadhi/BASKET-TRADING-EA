import secrets

from ..models import Payment, PaymentMethod
from .base import ChargeResult, PaymentProvider

VA_BANK_CODES = {"BCA": "39358", "BNI": "8808", "BRI": "26215", "MANDIRI": "88908", "PERMATA": "8528"}
EWALLETS = {"OVO", "DANA", "GOPAY", "SHOPEEPAY", "LINKAJA"}


class SimulatorProvider(PaymentProvider):
    """Acquirer tiruan untuk sandbox. Pembayaran diselesaikan lewat
    endpoint /v1/simulate/payments/{id}/pay."""

    name = "simulator"

    def create_charge(self, payment: Payment) -> ChargeResult:
        ref = f"SIM-{secrets.token_hex(8).upper()}"
        if payment.method == PaymentMethod.QRIS:
            instructions = {"qr_string": f"00020101021226SIMULATOR{ref}5303360540{payment.amount}6304"}
        elif payment.method == PaymentMethod.VIRTUAL_ACCOUNT:
            bank = (payment.channel or "").upper()
            if bank not in VA_BANK_CODES:
                raise ValueError(f"Unsupported VA bank: {payment.channel}")
            number = VA_BANK_CODES[bank] + "".join(secrets.choice("0123456789") for _ in range(11))
            instructions = {"bank": bank, "va_number": number}
        elif payment.method == PaymentMethod.EWALLET:
            wallet = (payment.channel or "").upper()
            if wallet not in EWALLETS:
                raise ValueError(f"Unsupported e-wallet: {payment.channel}")
            instructions = {"wallet": wallet, "checkout_url": f"https://sandbox.example/ewallet/{ref}"}
        else:  # pragma: no cover
            raise ValueError(f"Unsupported method: {payment.method}")
        return ChargeResult(provider_reference=ref, instructions=instructions)

    def refund(self, payment: Payment, amount: int) -> bool:
        return True
