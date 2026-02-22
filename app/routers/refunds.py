import time
import traceback

from fastapi import APIRouter, HTTPException

from app.logger import push_log
from app.models.schemas import RefundRequest
from app.services.refund_service import get_reason_code

router = APIRouter()


@router.post("/refund")
def refund_payment(req: RefundRequest):
    """Refund a payment. Raises 500 when reason is not a known refund code."""
    push_log("info", f"Refund requested for payment {req.payment_id}", {
        "payment_id": req.payment_id,
        "amount": req.amount,
        "reason": req.reason,
    })
    try:
        reason_code = get_reason_code(req.reason)
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
