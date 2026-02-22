"""
Flow 1 – Multi-currency Checkout
=================================
Steps
  1. Fetch & validate account (status must be "active")
  2. Convert every line-item to base_currency via exchange rates
  3. Calculate tax for the destination country on the converted subtotal
  4. Calculate the processing fee on the taxed total
  5. Return full breakdown

Known edge cases (all trigger unhandled exceptions in the underlying services):

  EC-1  JSONDecodeError – ACC-003 / ACC-005 have corrupted metadata in the DB.
        fetch_account() calls json.loads() on the stored TEXT column; rows
        with bad JSON raise JSONDecodeError before the account dict is returned.
        Trigger: account_id = "ACC-003" or "ACC-005"

  EC-2  Suspended account (HTTP 403) – ACC-004 has status="suspended".
        The guard checks account["status"] == "active" and rejects early.
        This is intentional business logic, NOT a bug, but must be exercised.
        Trigger: account_id = "ACC-004"

  EC-3  Same-currency KeyError – EXCHANGE_RATES["USD"] contains only EUR/GBP/INR;
        there is no "USD" sub-key. When item.currency == base_currency the code
        still calls get_rate() instead of short-circuiting with rate=1.0, so
        EXCHANGE_RATES["USD"]["USD"] raises KeyError.
        Trigger: any item with currency="USD" and base_currency="USD"

  EC-4  Unknown currency pair KeyError – any (from, to) pair not in EXCHANGE_RATES.
        INR is only a *target* currency; EXCHANGE_RATES["INR"] does not exist.
        Trigger: item.currency = "INR"

  EC-5  Unknown country TypeError – get_tax_rate() does TAX_RATES.get(code)[type],
        returning None for unknown codes. None["standard"] raises TypeError.
        Trigger: destination_country = "FR" (or any code not in US|GB|DE)

  EC-6  ZeroDivisionError – calculate_payment_fee does FIXED_FEE / amount.
        If every line-item has amount=0 the taxed total is 0 → fee blows up.
        Trigger: all items with amount=0.0

  EC-7  Float accumulation drift – IEEE-754 addition of many small floats
        (e.g., ten items of 0.10 USD) produces 0.9999999999999999, not 1.00.
        The subtotal and tax amounts will be off by a tiny fraction that
        only surfaces when totals are compared against ledger entries.
        Trigger: many items whose sum is not exactly representable in binary.
"""

import traceback

from fastapi import APIRouter, HTTPException

from app.logger import push_log
from app.models.schemas import CheckoutRequest
from app.services.account_service import fetch_account
from app.services.exchange_service import get_rate
from app.services.payment_service import calculate_payment_fee
from app.services.tax_service import get_tax_rate

router = APIRouter()


@router.post("/checkout")
def checkout(req: CheckoutRequest):
    """
    Checkout: account validation → currency conversion → tax → fee.

    Buggy edge cases: EC-1 through EC-7 (see module docstring).
    """
    push_log("info", f"Checkout started: payment={req.payment_id} account={req.account_id}", {
        "payment_id": req.payment_id,
        "account_id": req.account_id,
        "item_count": len(req.items),
        "destination_country": req.destination_country,
        "base_currency": req.base_currency,
    })

    # ── Step 1: fetch & validate account ─────────────────────────────────────
    # EC-1: fetch_account raises JSONDecodeError for ACC-003 / ACC-005
    try:
        account = fetch_account(req.account_id)
    except Exception as exc:
        tb = traceback.format_exc()
        push_log("error", f"Failed to fetch account {req.account_id}: {type(exc).__name__}", {
            "account_id": req.account_id,
            "error": type(exc).__name__,
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": type(exc).__name__,
            "message": str(exc),
            "account_id": req.account_id,
        })

    if account is None:
        push_log("warn", f"Account {req.account_id} not found", {"account_id": req.account_id, "http_status": 404})
        raise HTTPException(status_code=404, detail={
            "error": "not_found",
            "account_id": req.account_id,
        })

    # EC-2: suspended / inactive accounts are blocked before any money moves
    if account["status"] != "active":
        push_log("warn", f"Checkout rejected: account {req.account_id} is {account['status']}", {
            "account_id": req.account_id,
            "status": account["status"],
            "http_status": 403,
        })
        raise HTTPException(status_code=403, detail={
            "error": "account_not_active",
            "message": f"account is '{account['status']}' and cannot process payments",
            "account_id": req.account_id,
        })

    # ── Step 2: convert each line-item to base_currency ──────────────────────
    # EC-3: item.currency == base_currency → get_rate("USD","USD") → KeyError
    # EC-4: item.currency not in EXCHANGE_RATES at all (e.g. "INR") → KeyError
    converted_items = []
    for item in req.items:
        try:
            # BUG: no short-circuit for same-currency items.
            # When item.currency == req.base_currency the correct rate is 1.0,
            # but the code blindly calls get_rate() which subscripts
            # EXCHANGE_RATES[same][same] — a key that does not exist.
            rate = get_rate(item.currency, req.base_currency)
            converted_amount = round(item.amount * rate, 2)
        except KeyError as exc:
            tb = traceback.format_exc()
            push_log("error", f"Currency conversion failed: {item.currency} -> {req.base_currency}", {
                "from_currency": item.currency,
                "to_currency": req.base_currency,
                "item_description": item.description,
                "error": "KeyError",
                "traceback": tb,
                "http_status": 500,
            })
            raise HTTPException(status_code=500, detail={
                "error": "KeyError",
                "message": f"unsupported currency pair: {item.currency} -> {req.base_currency}",
                "item_description": item.description,
            })

        converted_items.append({
            "description": item.description,
            "original_amount": item.amount,
            "original_currency": item.currency,
            "converted_amount": converted_amount,
            "exchange_rate": rate,
        })

    # EC-7: float accumulation drift — sum of many binary-inexact floats
    # e.g. 10 × 0.10 = 0.9999999999999999 instead of 1.00
    subtotal = sum(i["converted_amount"] for i in converted_items)

    # ── Step 3: calculate tax ─────────────────────────────────────────────────
    # EC-5: unknown country_code → get_tax_rate returns None → None["standard"]
    #        raises TypeError: 'NoneType' object is not subscriptable
    try:
        tax_rate = get_tax_rate(req.destination_country, "standard")
        tax_amount = round(subtotal * tax_rate, 2)
        total_with_tax = round(subtotal + tax_amount, 2)
    except TypeError as exc:
        tb = traceback.format_exc()
        push_log("error", f"Tax calculation failed for country '{req.destination_country}'", {
            "country_code": req.destination_country,
            "subtotal": subtotal,
            "error": "TypeError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "TypeError",
            "message": f"unsupported destination country: {req.destination_country}",
            "country_code": req.destination_country,
        })

    # ── Step 4: processing fee ────────────────────────────────────────────────
    # EC-6: total_with_tax == 0 when every item.amount == 0
    #        calculate_payment_fee does FIXED_FEE / amount → ZeroDivisionError
    try:
        fee = calculate_payment_fee(total_with_tax)
        grand_total = round(total_with_tax + fee, 2)
    except ZeroDivisionError as exc:
        tb = traceback.format_exc()
        push_log("error", f"ZeroDivisionError: checkout total is zero for payment {req.payment_id}", {
            "payment_id": req.payment_id,
            "total_with_tax": total_with_tax,
            "error": "ZeroDivisionError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "ZeroDivisionError",
            "message": "checkout total must be greater than zero",
            "payment_id": req.payment_id,
        })

    push_log("info", f"Checkout {req.payment_id} approved for account {req.account_id}", {
        "payment_id": req.payment_id,
        "account_id": req.account_id,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "fee": fee,
        "grand_total": grand_total,
        "currency": req.base_currency,
    })

    return {
        "payment_id": req.payment_id,
        "account_id": req.account_id,
        "items": converted_items,
        "subtotal": subtotal,
        "destination_country": req.destination_country,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total_with_tax": total_with_tax,
        "processing_fee": fee,
        "grand_total": grand_total,
        "currency": req.base_currency,
        "status": "approved",
    }
