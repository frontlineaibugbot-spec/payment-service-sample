"""
payment-service-sample

A sample payment processing service for Bug Bot demo.

Deliberately buggy: calculate_payment_fee() raises ZeroDivisionError when amount=0.
A background task triggers this bug every 30 seconds.
All logs are pushed directly to Grafana Loki via HTTP.
"""

import asyncio
import json
import random
import time
import traceback
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────

LOKI_PUSH_URL = "http://localhost:3100/loki/api/v1/push"
SERVICE = "payment-service"
ENV = "local"
FIXED_FEE = 2.50  # processing fee in dollars

# ── Loki log pusher ───────────────────────────────────────────────────────────

def push_log(level: str, message: str, extra: dict | None = None) -> None:
    """Push a log line to Loki using the same format as lokistaack/push-log.sh."""
    ts_ns = str(int(time.time() * 1_000_000_000))
    line = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": SERVICE,
        "msg": message,
        **(extra or {}),
    })
    payload = {
        "streams": [
            {
                "stream": {"service": SERVICE, "env": ENV, "level": level},
                "values": [[ts_ns, line]],
            }
        ]
    }
    try:
        with httpx.Client(timeout=3.0) as client:
            client.post(LOKI_PUSH_URL, json=payload)
    except Exception:
        pass  # never crash on log failures


# ── The Bug ───────────────────────────────────────────────────────────────────

def calculate_payment_fee(amount: float) -> float:
    """Calculate the processing fee.

    BUG: Raises ZeroDivisionError when amount=0.
    Fix: guard with `if amount <= 0: return FIXED_FEE`
    """
    if amount <= 0:
        return FIXED_FEE
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


# ── Background log generator ──────────────────────────────────────────────────

async def background_log_generator():
    """Continuously generates payment logs — 5 successful + 1 zero-amount (bug) every 30s."""
    await asyncio.sleep(3)  # wait for Loki to be reachable
    push_log("info", "Background log generator started", {"version": "1.0.0"})

    counter = 0
    while True:
        # 5 successful payments
        for i in range(5):
            amount = round(random.uniform(10.0, 500.0), 2)
            pid = f"pay_{counter:06d}_{i}"
            push_log("info", f"Processing payment {pid}", {"payment_id": pid, "amount": amount})
            try:
                fee = calculate_payment_fee(amount)
                push_log("info", f"Payment {pid} processed successfully", {
                    "payment_id": pid, "fee": fee,
                })
            except Exception as exc:
                push_log("error", f"Unexpected error for {pid}: {exc}", {"payment_id": pid})

        # 1 zero-amount payment — triggers the bug
        bad_pid = f"pay_{counter:06d}_zero"
        push_log("info", f"Processing payment {bad_pid}", {"payment_id": bad_pid, "amount": 0})
        try:
            calculate_payment_fee(0)
        except ZeroDivisionError as exc:
            tb = traceback.format_exc()
            push_log("error",
                f"ZeroDivisionError processing payment {bad_pid}: {exc}",
                {
                    "payment_id": bad_pid,
                    "amount": 0,
                    "error": "ZeroDivisionError",
                    "traceback": tb,
                    "http_status": 500,
                },
            )

        counter += 1
        await asyncio.sleep(30)


@app.on_event("startup")
async def startup():
    asyncio.create_task(background_log_generator())
