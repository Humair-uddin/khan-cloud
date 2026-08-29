from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


Currency = Literal["PKR", "USD"]


class FinanceDepositCreate(BaseModel):
    organization_id: UUID
    currency: Currency
    amount_minor: int = Field(gt=0)
    provider: str = Field(min_length=2, max_length=60)
    provider_event_id: str = Field(min_length=1, max_length=180)
    provider_reference: str = Field(default="", max_length=180)


class FinanceWalletRead(BaseModel):
    wallet_id: UUID
    organization_id: UUID
    currency: Currency
    available_minor: int
    reserved_minor: int


class LedgerTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_type: str
    currency: Currency
    status: str
    idempotency_key: str
    external_reference: str
    description: str
    posted_at: datetime


class FinanceReservationCreate(BaseModel):
    wallet_id: UUID
    amount_minor: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=180)
    reference_type: str = Field(default="", max_length=80)
    reference_id: str = Field(default="", max_length=180)


class RefundCreate(BaseModel):
    wallet_id: UUID
    amount_minor: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=180)
    external_reference: str = Field(default="", max_length=180)


class FinancialAdjustmentCreate(BaseModel):
    debit_account_id: UUID
    credit_account_id: UUID
    amount_minor: int = Field(gt=0)
    adjustment_type: str = Field(min_length=2, max_length=50)
    reason: str = Field(min_length=3, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=180)


class TreasurySettlementCreate(BaseModel):
    provider: str = Field(min_length=2, max_length=60)
    currency: Currency
    amount_minor: int = Field(gt=0)
    external_reference: str = Field(min_length=1, max_length=180)
    idempotency_key: str = Field(min_length=8, max_length=180)
