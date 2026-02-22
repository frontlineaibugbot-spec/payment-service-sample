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


# ── Flow 1: Checkout ─────────────────────────────────────────────────────────

class LineItem(BaseModel):
    description: str
    amount: float
    currency: str  # USD | EUR | GBP


class CheckoutRequest(BaseModel):
    account_id: str
    payment_id: str
    items: list[LineItem]
    destination_country: str   # US | GB | DE
    base_currency: str         # USD | EUR | GBP  (all items converted to this)


# ── Flow 2: Batch Refund ─────────────────────────────────────────────────────

class ScheduledRefundItem(BaseModel):
    transaction_id: str   # must be numeric string e.g. "1001"
    refund_amount: float
    reason: str           # duplicate | defective | not_received


class BatchRefundRequest(BaseModel):
    account_id: str
    refunds: list[ScheduledRefundItem]


# ── Flow 3: International Payment ────────────────────────────────────────────

class InternationalPaymentRequest(BaseModel):
    payment_id: str
    amount: float
    from_currency: str   # USD | EUR | GBP
    to_currency: str     # USD | EUR | GBP  (INR only supported as target)
    country_code: str    # US | GB | DE
    tax_type: str = "standard"  # standard | reduced
