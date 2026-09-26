from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from .models import PaymentMethod, PaymentStatus, RefundStatus


class MerchantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    webhook_url: HttpUrl | None = None


class MerchantUpdate(BaseModel):
    webhook_url: HttpUrl | None = None


class MerchantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    webhook_url: str | None
    is_active: bool
    created_at: datetime


class MerchantCreated(MerchantOut):
    api_key: str = Field(description="Hanya ditampilkan sekali. Simpan dengan aman.")
    webhook_secret: str


class ApiKeyCreated(BaseModel):
    id: str
    api_key: str


class Customer(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class PaymentCreate(BaseModel):
    reference_id: str = Field(min_length=1, max_length=100, description="ID order di sistem merchant")
    amount: int = Field(gt=0, description="Nominal dalam rupiah")
    currency: str = Field(default="IDR", pattern="^IDR$")
    method: PaymentMethod
    channel: str | None = Field(default=None, description="Bank VA (BCA, BNI, ...) atau e-wallet (OVO, DANA, ...)")
    description: str | None = Field(default=None, max_length=500)
    customer: Customer | None = None
    metadata: dict | None = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference_id: str
    amount: int
    currency: str
    method: PaymentMethod
    channel: str | None
    status: PaymentStatus
    fee: int
    net_amount: int
    refunded_amount: int
    description: str | None
    customer: dict | None
    metadata: dict | None = Field(validation_alias="metadata_")
    instructions: dict | None
    checkout_url: str
    expires_at: datetime
    paid_at: datetime | None
    created_at: datetime


class RefundCreate(BaseModel):
    amount: int | None = Field(default=None, gt=0, description="Kosongkan untuk refund penuh")
    reason: str | None = Field(default=None, max_length=500)


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    payment_id: str
    amount: int
    reason: str | None
    status: RefundStatus
    created_at: datetime


class BalanceOut(BaseModel):
    merchant_id: str
    currency: str = "IDR"
    balance: int
    gross_volume: int
    total_fees: int
    total_refunds: int


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    attempts: int
    delivered: bool
    last_status_code: int | None
    last_error: str | None
    created_at: datetime
