import traceback
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.logger import push_log
from app.services.exchange_service import get_rate

router = APIRouter()


@router.get("/exchange-rate")
def get_exchange_rate(from_currency: str, to_currency: str):
    """Return the exchange rate between two currencies. Raises 500 for unsupported pairs."""
    push_log("info", f"Exchange rate requested: {from_currency} -> {to_currency}", {
        "from_currency": from_currency,
        "to_currency": to_currency,
    })
    try:
        rate = get_rate(from_currency, to_currency)
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
    except KeyError as exc:
        tb = traceback.format_exc()
        push_log("error", f"KeyError fetching exchange rate {from_currency}->{to_currency}: unsupported currency", {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "error": "KeyError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "KeyError",
            "message": f"unsupported currency pair: {from_currency} -> {to_currency}",
        })
