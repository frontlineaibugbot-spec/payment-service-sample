import traceback

from fastapi import APIRouter, HTTPException

from app.logger import push_log
from app.models.schemas import BatchPaymentRequest, PaymentRequest
from app.services.payment_service import calculate_payment_fee

router = APIRouter()


@router.post("/process-payment")
def process_payment(req: PaymentRequest):
    """Process a payment. Raises 500 when amount=0 due to ZeroDivisionError."""
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


@router.post("/batch-payment")
def batch_payment(req: BatchPaymentRequest):
    """Process a batch of payments. Raises 500 when payments list is empty."""
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
