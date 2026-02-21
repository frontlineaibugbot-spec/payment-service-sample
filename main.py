"""
payment-service-sample

A sample payment processing service for Bug Bot demo.
Logs are pushed to Grafana Loki on every API call (info on success, error on failure).
"""

import json
import subprocess
import time
import traceback
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────

LOKI_PUSH_URL = "http://localhost:3100/loki/api/v1/push"
SERVICE = "payment-service"
ENV = "local"
FIXED_FEE = 2.50  # processing fee in dollars

# ── Loki log pusher ───────────────────────────────────────────────────────────

def push_log(level: str, message: str, extra: dict | None = None) -> None:
    """Push a log line to Loki via curl, matching lokistaack/push-log.sh format."""
    ts_ns = str(int(time.time() * 1_000_000_000))
    line = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": SERVICE,
        "msg": message,
        **(extra or {}),
    })
    payload = json.dumps({
        "streams": [
            {
                "stream": {"app": SERVICE, "level": level, "env": ENV},
                "values": [[ts_ns, line]],
            }
        ]
    })
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                LOKI_PUSH_URL,
                "-H", "Content-Type: application/json",
                "-d", payload,
            ],
            timeout=3,
            check=False,
            capture_output=True,
        )
        print(result)
        if result.returncode == 0:
            print(f"Pushed: {message}")
        else:
            print(f"Loki push failed (exit {result.returncode}): {result.stderr.decode().strip()}")
    except Exception as e:
        print(f"Loki push error: {e}")


# ── The Bug ───────────────────────────────────────────────────────────────────

def calculate_payment_fee(amount: float) -> float:
    """Calculate the processing fee.

    BUG: Raises ZeroDivisionError when amount=0.
    Fix: guard with `if amount <= 0: return FIXED_FEE`
    """
    fee = FIXED_FEE / amount  # ZeroDivisionError when amount == 0
    return round(fee, 4)


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="payment-service-sample")


class PaymentRequest(BaseModel):
    payment_id: str
    amount: float
    currency: str = "USD"


@app.get("/health")
def health():
    push_log("info", "Health check OK")
    return {"status": "ok", "service": SERVICE}


@app.post("/process-payment")
def process_payment(req: PaymentRequest):
    """Process a payment. Raises 500 when amount=0 due to ZeroDivisionError in fee calculation."""
    push_log("info", f"Processing payment {req.payment_id}", {
        "payment_id": req.payment_id,
        "amount": req.amount,
        "currency": req.currency,
    })
    try:
        fee = calculate_payment_fee(req.amount)
        push_log("info", f"Payment {req.payment_id} processed successfully", {
            "payment_id": req.payment_id,
            "fee": fee,
            "total": round(req.amount + fee, 2),
        })
        return {
            "payment_id": req.payment_id,
            "amount": req.amount,
            "fee": fee,
            "total": round(req.amount + fee, 2),
            "status": "processed",
        }
    except ZeroDivisionError as exc:
        tb = traceback.format_exc()
        push_log("error", f"ZeroDivisionError processing payment {req.payment_id}: {exc}", {
            "payment_id": req.payment_id,
            "amount": req.amount,
            "error": "ZeroDivisionError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "ZeroDivisionError",
            "message": "division by zero",
            "payment_id": req.payment_id,
        })


@app.on_event("startup")
async def startup():
    pass


# ── Refund API ────────────────────────────────────────────────────────────────

REFUND_REASON_CODES = {
    "duplicate": "RF001",
    "defective": "RF002",
    "not_received": "RF003",
}


class RefundRequest(BaseModel):
    payment_id: str
    amount: float
    reason: str  # expected: duplicate | defective | not_received


@app.post("/refund")
def refund_payment(req: RefundRequest):
    """Refund a previously processed payment.

    BUG: KeyError raised when `reason` is not one of the known codes
         (e.g. passing "fraud" or "chargeback").
    Fix: use REFUND_REASON_CODES.get(req.reason) and handle None.
    """
    push_log("info", f"Refund requested for payment {req.payment_id}", {
        "payment_id": req.payment_id,
        "amount": req.amount,
        "reason": req.reason,
    })
    try:
        reason_code = REFUND_REASON_CODES[req.reason]  # KeyError if reason unknown
        refund_id = f"REF-{req.payment_id}-{int(time.time())}"
        push_log("info", f"Refund {refund_id} approved for payment {req.payment_id}", {
            "payment_id": req.payment_id,
            "refund_id": refund_id,
            "reason_code": reason_code,
            "amount": req.amount,
        })
        return {
            "refund_id": refund_id,
            "payment_id": req.payment_id,
            "amount": req.amount,
            "reason_code": reason_code,
            "status": "approved",
        }
    except KeyError as exc:
        tb = traceback.format_exc()
        push_log("error", f"KeyError processing refund for {req.payment_id}: unknown reason '{req.reason}'", {
            "payment_id": req.payment_id,
            "reason": req.reason,
            "error": "KeyError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "KeyError",
            "message": f"unknown refund reason: {req.reason}",
            "payment_id": req.payment_id,
        })


# ── Transaction Lookup API ────────────────────────────────────────────────────

MOCK_TRANSACTIONS: dict[int, dict] = {
    1001: {"payment_id": "PAY-001", "amount": 99.99, "currency": "USD", "status": "completed"},
    1002: {"payment_id": "PAY-002", "amount": 250.00, "currency": "EUR", "status": "pending"},
    1003: {"payment_id": "PAY-003", "amount": 45.50, "currency": "GBP", "status": "failed"},
}


@app.get("/transaction/{transaction_id}")
def get_transaction(transaction_id: str):
    """Look up a transaction by its numeric ID.

    BUG: ValueError raised when transaction_id contains non-numeric characters
         (e.g. "TXN-001" or "abc").
    Fix: wrap int() in a try/except ValueError or declare the path param as int.
    """
    push_log("info", f"Looking up transaction {transaction_id}", {
        "transaction_id": transaction_id,
    })
    try:
        txn_int_id = int(transaction_id)  # ValueError if non-numeric
        txn = MOCK_TRANSACTIONS.get(txn_int_id)
        if not txn:
            push_log("warn", f"Transaction {transaction_id} not found", {
                "transaction_id": transaction_id,
                "http_status": 404,
            })
            raise HTTPException(status_code=404, detail={
                "error": "not_found",
                "transaction_id": transaction_id,
            })
        push_log("info", f"Transaction {transaction_id} fetched successfully", {
            "transaction_id": transaction_id,
            "status": txn["status"],
            "amount": txn["amount"],
        })
        return {"transaction_id": txn_int_id, **txn}
    except ValueError as exc:
        tb = traceback.format_exc()
        push_log("error", f"ValueError fetching transaction '{transaction_id}': non-numeric ID", {
            "transaction_id": transaction_id,
            "error": "ValueError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "ValueError",
            "message": f"invalid transaction_id '{transaction_id}': must be a numeric value",
        })


# ── Batch Payment API ─────────────────────────────────────────────────────────

class BatchPaymentRequest(BaseModel):
    batch_id: str
    payments: list[PaymentRequest]


@app.post("/batch-payment")
def batch_payment(req: BatchPaymentRequest):
    """Process a list of payments in a single batch request.

    BUG: IndexError when `payments` list is empty — `req.payments[0]` is
         accessed unconditionally to record the first payment in the log.
    Fix: guard with `if not req.payments: raise HTTPException(400, ...)`.
    """
    push_log("info", f"Batch {req.batch_id} received with {len(req.payments)} payments", {
        "batch_id": req.batch_id,
        "payment_count": len(req.payments),
    })
    try:
        first = req.payments[0]  # IndexError when list is empty
        results = []
        total_amount = 0.0
        for payment in req.payments:
            fee = calculate_payment_fee(payment.amount)
            total_amount += payment.amount
            results.append({
                "payment_id": payment.payment_id,
                "amount": payment.amount,
                "fee": fee,
                "total": round(payment.amount + fee, 2),
                "status": "processed",
            })
        push_log("info", f"Batch {req.batch_id} completed: {len(results)} payments processed", {
            "batch_id": req.batch_id,
            "payment_count": len(results),
            "total_amount": round(total_amount, 2),
            "first_payment_id": first.payment_id,
        })
        return {
            "batch_id": req.batch_id,
            "processed": len(results),
            "total_amount": round(total_amount, 2),
            "results": results,
        }
    except IndexError as exc:
        tb = traceback.format_exc()
        push_log("error", f"IndexError in batch {req.batch_id}: payments list is empty", {
            "batch_id": req.batch_id,
            "error": "IndexError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "IndexError",
            "message": "payments list must not be empty",
            "batch_id": req.batch_id,
        })


# ── Exchange Rate API ─────────────────────────────────────────────────────────

EXCHANGE_RATES: dict[str, dict[str, float]] = {
    "USD": {"EUR": 0.92, "GBP": 0.79, "INR": 83.12},
    "EUR": {"USD": 1.09, "GBP": 0.86, "INR": 90.45},
    "GBP": {"USD": 1.27, "EUR": 1.16, "INR": 105.23},
}


@app.get("/exchange-rate")
def get_exchange_rate(from_currency: str, to_currency: str):
    """Return the live exchange rate between two supported currencies."""
    push_log("info", f"Exchange rate requested: {from_currency} -> {to_currency}", {
        "from_currency": from_currency,
        "to_currency": to_currency,
    })
    
    # Validate currencies before accessing dictionary
    supported_currencies = list(EXCHANGE_RATES.keys())
    if from_currency not in EXCHANGE_RATES:
        push_log("warn", f"Unsupported from_currency: {from_currency}", {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "supported": supported_currencies,
            "http_status": 400,
        })
        raise HTTPException(status_code=400, detail={
            "error": "invalid_currency",
            "message": f"Unsupported from_currency: {from_currency}",
            "supported_currencies": supported_currencies,
        })
    
    if to_currency not in EXCHANGE_RATES[from_currency]:
        push_log("warn", f"Unsupported to_currency: {to_currency} for {from_currency}", {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "supported": list(EXCHANGE_RATES[from_currency].keys()),
            "http_status": 400,
        })
        raise HTTPException(status_code=400, detail={
            "error": "invalid_currency",
            "message": f"Unsupported currency pair: {from_currency} -> {to_currency}",
            "supported_currencies": supported_currencies,
        })
    
    rate = EXCHANGE_RATES[from_currency][to_currency]
    push_log("info", f"Exchange rate {from_currency}->{to_currency} = {rate}", {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate": rate,
    })
    return {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate": rate,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Tax Calculation API ───────────────────────────────────────────────────────

TAX_RATES: dict[str, dict[str, float]] = {
    "US": {"standard": 0.08, "reduced": 0.04},
    "GB": {"standard": 0.20, "reduced": 0.05},
    "DE": {"standard": 0.19, "reduced": 0.07},
}


class TaxRequest(BaseModel):
    amount: float
    country_code: str   # expected: US | GB | DE
    tax_type: str = "standard"  # standard | reduced


@app.post("/calculate-tax")
def calculate_tax(req: TaxRequest):
    """Calculate applicable tax for a payment amount given country and tax type.

    BUG: TypeError raised when country_code is not in TAX_RATES.
         TAX_RATES.get(req.country_code) returns None for unknown countries,
         and then None[req.tax_type] raises TypeError: 'NoneType' is not subscriptable.
    Fix: check that country_rates is not None before subscripting.
    """
    push_log("info", f"Tax calculation requested for country={req.country_code}, type={req.tax_type}", {
        "country_code": req.country_code,
        "tax_type": req.tax_type,
        "amount": req.amount,
    })
    try:
        country_rates = TAX_RATES.get(req.country_code)   # None for unknown country
        tax_rate = country_rates[req.tax_type]             # TypeError: NoneType not subscriptable
        tax_amount = round(req.amount * tax_rate, 2)
        total = round(req.amount + tax_amount, 2)
        push_log("info", f"Tax calculated: country={req.country_code}, rate={tax_rate}, tax={tax_amount}", {
            "country_code": req.country_code,
            "tax_type": req.tax_type,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "total": total,
        })
        return {
            "country_code": req.country_code,
            "tax_type": req.tax_type,
            "amount": req.amount,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "total": total,
        }
    except TypeError as exc:
        tb = traceback.format_exc()
        push_log("error", f"TypeError calculating tax for country '{req.country_code}': unsupported country code", {
            "country_code": req.country_code,
            "tax_type": req.tax_type,
            "error": "TypeError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "TypeError",
            "message": f"unsupported country code: {req.country_code}",
            "country_code": req.country_code,
        })
