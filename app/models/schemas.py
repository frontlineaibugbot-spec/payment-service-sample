from pydantic import BaseModel


class PaymentRequest(BaseModel):
    payment_id: str
    amount: float
    currency: str = "USD"


class RefundRequest(BaseModel):
    payment_id: str
    amount: float
    reason: str  # expected: duplicate | defective | not_received


class BatchPaymentRequest(BaseModel):
    batch_id: str
    payments: list[PaymentRequest]


class TaxRequest(BaseModel):
    amount: float
    country_code: str   # expected: US | GB | DE
    tax_type: str = "standard"  # standard | reduced


class AccountSummary(BaseModel):
    account_id: str
    owner: str
    balance: float
    currency: str
    metadata: dict
    status: str
