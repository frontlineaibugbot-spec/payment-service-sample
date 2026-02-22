import traceback

from fastapi import APIRouter, HTTPException

from app.logger import push_log
from app.models.schemas import TaxRequest
from app.services.tax_service import get_tax_rate

router = APIRouter()


@router.post("/calculate-tax")
def calculate_tax(req: TaxRequest):
    """Calculate applicable tax. Raises 500 for unsupported country codes."""
    push_log("info", f"Tax calculation requested for country={req.country_code}, type={req.tax_type}", {
        "country_code": req.country_code,
        "tax_type": req.tax_type,
        "amount": req.amount,
    })
    try:
        tax_rate = get_tax_rate(req.country_code, req.tax_type)
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
