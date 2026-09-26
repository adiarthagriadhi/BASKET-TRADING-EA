from ..config import get_settings
from ..models import PaymentMethod
from .base import ChargeResult, PaymentProvider, ProviderError
from .shopeepay import ShopeePayProvider
from .simulator import SimulatorProvider

_PROVIDERS: dict[str, PaymentProvider] = {
    "simulator": SimulatorProvider(),
    "shopeepay": ShopeePayProvider(),
}


def get_provider(name: str = "simulator") -> PaymentProvider:
    return _PROVIDERS[name]


def register_provider(provider: PaymentProvider) -> None:
    _PROVIDERS[provider.name] = provider


def select_provider(method: PaymentMethod, channel: str | None) -> PaymentProvider:
    """Pilih acquirer untuk sebuah pembayaran (routing)."""
    settings = get_settings()
    if method == PaymentMethod.EWALLET and (channel or "").upper() == "SHOPEEPAY" and settings.shopeepay_enabled:
        return _PROVIDERS["shopeepay"]
    if settings.environment == "production":
        raise ValueError(f"No live acquirer configured for {method.value}/{channel}")
    return _PROVIDERS["simulator"]


__all__ = [
    "ChargeResult", "PaymentProvider", "ProviderError",
    "get_provider", "register_provider", "select_provider",
]
