from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


PaymentEventType = Literal[
    "deposit.succeeded",
    "refund.processing",
    "refund.succeeded",
    "refund.failed",
    "chargeback.created",
    "payout.processing",
    "payout.paid",
    "payout.failed",
    "treasury.settled",
]


class NormalizedPaymentEvent(BaseModel):
    provider: str = Field(min_length=1, max_length=60)
    event_id: str = Field(min_length=1, max_length=180)
    event_type: PaymentEventType

    provider_timestamp: int = Field(gt=0)

    organization_id: UUID | None = None
    user_id: UUID | None = None
    wallet_id: UUID | None = None
    payout_id: UUID | None = None
    refund_id: UUID | None = None

    provider_reference: str = Field(
        default="",
        max_length=180,
    )
    dispute_id: str = Field(
        default="",
        max_length=180,
    )

    amount_minor: int | None = Field(
        default=None,
        gt=0,
    )
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )

    presentment_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )
    settlement_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )

    reason: str = Field(
        default="",
        max_length=500,
    )

    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "currency",
        "presentment_currency",
        "settlement_currency",
    )
    @classmethod
    def normalize_currency(cls, value):
        if value is None:
            return None
        return value.upper()

    @field_validator("provider", "event_id")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank.")
        return value

    @field_validator(
        "provider_reference",
        "dispute_id",
        "reason",
    )
    @classmethod
    def strip_optional(cls, value: str) -> str:
        return value.strip()


class PaymentProviderCreate(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    display_name: str = Field(min_length=1, max_length=120)
    adapter_type: str = Field(min_length=1, max_length=80)
    environment: Literal["sandbox", "production"] = "sandbox"
    enabled: bool = False
    capabilities: dict[str, bool] = Field(default_factory=dict)
    supported_currencies: list[str] = Field(default_factory=list)
    credential_reference: str = Field(default="", max_length=240)
    webhook_secret_reference: str = Field(default="", max_length=240)
    webhook_tolerance_seconds: int = Field(default=300, gt=0, le=3600)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("Provider code cannot be blank.")
        return value

    @field_validator("supported_currencies")
    @classmethod
    def normalize_currencies(cls, values: list[str]) -> list[str]:
        result = []
        for value in values:
            currency = value.strip().upper()
            if len(currency) != 3:
                raise ValueError("Currency codes must contain 3 characters.")
            if currency not in result:
                result.append(currency)
        return result


class PaymentProviderRead(BaseModel):
    id: UUID
    code: str
    display_name: str
    adapter_type: str
    environment: str
    enabled: bool
    capabilities: dict[str, Any]
    supported_currencies: list[str]
    status: str
    webhook_tolerance_seconds: int


class PaymentWebhookResult(BaseModel):
    receipt_id: UUID
    provider: str
    event_id: str
    event_type: str
    status: str
    replay: bool = False
    resource_type: str = ""
    resource_id: UUID | None = None
