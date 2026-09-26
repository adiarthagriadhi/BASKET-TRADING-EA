from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./gateway.db"
    admin_token: str = "change-me"
    environment: str = "sandbox"  # sandbox | production
    public_base_url: str = "http://localhost:8000"
    payment_expiry_minutes: int = 60
    webhook_timeout_seconds: float = 10.0
    webhook_max_attempts: int = 5

    # ShopeePay (kredensial dari ShopeePay saat onboarding merchant/partner)
    shopeepay_client_id: str | None = None
    shopeepay_secret_key: str | None = None
    shopeepay_merchant_ext_id: str | None = None
    shopeepay_store_ext_id: str | None = None
    shopeepay_base_url: str = "https://api.uat.wallet.airpay.co.id"  # prod: https://api.wallet.airpay.co.id
    shopeepay_return_url: str | None = None  # default: halaman checkout gateway
    shopeepay_platform_type: str = "mweb"  # app | pc | mweb

    @property
    def shopeepay_enabled(self) -> bool:
        return all(
            (self.shopeepay_client_id, self.shopeepay_secret_key,
             self.shopeepay_merchant_ext_id, self.shopeepay_store_ext_id)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
