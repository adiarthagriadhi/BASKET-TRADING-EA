from .base import ChargeResult, PaymentProvider
from .simulator import SimulatorProvider

_PROVIDERS: dict[str, PaymentProvider] = {"simulator": SimulatorProvider()}


def get_provider(name: str = "simulator") -> PaymentProvider:
    return _PROVIDERS[name]


def register_provider(provider: PaymentProvider) -> None:
    _PROVIDERS[provider.name] = provider


__all__ = ["ChargeResult", "PaymentProvider", "get_provider", "register_provider"]
