"""
Flow 3 – International Payment Pipeline
=========================================
Steps
  1. Convert amount from source currency to destination currency
  2. Calculate tax on the converted amount for the given country
  3. Calculate the processing fee on the taxed subtotal
  4. Return full cost breakdown

This pipeline chains three services whose individual bugs compose into
a richer set of failure modes than any single service exhibits alone.

Known edge cases:

  EC-1  Same-currency KeyError – EXCHANGE_RATES stores only cross-currency
        pairs. EXCHANGE_RATES["USD"] = {"EUR": …, "GBP": …, "INR": …};
        there is no "USD" entry inside that dict. When from_currency equals
        to_currency the lookup EXCHANGE_RATES[c][c] always raises KeyError.
        Trigger: from_currency="USD", to_currency="USD"

  EC-2  INR-as-source KeyError – INR appears only as a *target* value inside
        USD/EUR/GBP sub-dicts. EXCHANGE_RATES["INR"] does not exist, so using
        INR as the source raises KeyError at the top-level subscript.
        Trigger: from_currency="INR", to_currency="USD"

  EC-3  ZeroDivisionError on zero amount – calculate_payment_fee does
        FIXED_FEE / amount. A zero-amount payment passes Step 1 (0 × rate = 0)
        and Step 2 (0 × tax_rate = 0), but Step 3 blows up when it tries to
        compute FIXED_FEE / 0.
        Trigger: amount=0.0

  EC-4  Negative amount → garbage totals – the pipeline applies no sign
        validation. A negative amount produces:
          converted_amount  = negative × positive_rate = negative
          tax_amount        = negative × tax_rate       = negative (a tax credit?)
          taxed_subtotal    = negative + negative       = more negative
          fee               = FIXED_FEE / negative      = negative fee
          grand_total       = negative                  (customer gets paid?)
        No exception is raised; the caller receives a structurally valid 200
        response with nonsensical negative values.
        Trigger: amount=-100.0

  EC-5  Unknown country TypeError – same as in the individual tax endpoint.
        TAX_RATES.get("FR") returns None; None["standard"] raises TypeError.
        Trigger: country_code="FR" (any unsupported country)

  EC-6  Fee-exceeds-principal on micro-payments – FIXED_FEE=2.50 is a flat
        fee. For very small amounts the fee (2.50 / amount, not a percentage)
        is actually *larger than* the converted principal. Example:
          amount=1.00 USD → EUR (rate 0.92) → converted=0.92
          tax (DE standard 19%) → tax=0.1748 → taxed_subtotal=1.0948
          fee = 2.50 / 1.0948 ≈ 2.28   (fee is 2× the original amount!)
          grand_total = 1.0948 + 2.28 ≈ 3.37  for a 1-dollar payment
        This is a business-logic bug in calculate_payment_fee, not a crash.
        Trigger: amount=1.0 (any micro-payment)

  EC-7  Floating-point compounding across steps – each step rounds independently,
        but the rounding in Step 1 feeds into Step 2, and Step 2 into Step 3.
        Three successive round() calls accumulate a larger total error than a
        single end-to-end calculation would produce. For currency conversion
        chains (e.g. USD→GBP→EUR via two calls) the drift is even larger.
        Trigger: amount=33.333 (any amount whose binary representation is
                  not exact after successive multiplications and rounding)
"""

import traceback

from fastapi import APIRouter, HTTPException

from app.logger import push_log
from app.models.schemas import InternationalPaymentRequest
from app.services.exchange_service import get_rate
from app.services.payment_service import calculate_payment_fee
from app.services.tax_service import get_tax_rate

router = APIRouter()


@router.post("/pay-international")
def pay_international(req: InternationalPaymentRequest):
    """
    Convert → tax → fee pipeline for cross-border payments.

    Buggy edge cases: EC-1 through EC-7 (see module docstring).
    """
    push_log("info", f"International payment {req.payment_id}: "
             f"{req.amount} {req.from_currency} -> {req.to_currency} / {req.country_code}", {
        "payment_id": req.payment_id,
        "amount": req.amount,
        "from_currency": req.from_currency,
        "to_currency": req.to_currency,
        "country_code": req.country_code,
        "tax_type": req.tax_type,
    })

    # ── Step 1: currency conversion ───────────────────────────────────────────
    # EC-1: from_currency == to_currency  → EXCHANGE_RATES["USD"]["USD"] → KeyError
    # EC-2: from_currency == "INR"        → EXCHANGE_RATES["INR"]        → KeyError
    # EC-4: amount < 0 passes silently; result is a valid but negative number
    try:
        rate = get_rate(req.from_currency, req.to_currency)
        converted_amount = round(req.amount * rate, 4)
    except KeyError as exc:
        tb = traceback.format_exc()
        push_log("error", f"KeyError: unsupported currency pair {req.from_currency}->{req.to_currency}", {
            "payment_id": req.payment_id,
            "from_currency": req.from_currency,
            "to_currency": req.to_currency,
            "error": "KeyError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "KeyError",
            "message": f"unsupported currency pair: {req.from_currency} -> {req.to_currency}",
            "payment_id": req.payment_id,
        })

    # ── Step 2: tax on converted amount ──────────────────────────────────────
    # EC-5: unknown country_code → get_tax_rate returns None → TypeError
    # EC-7: round(converted_amount × tax_rate) compounds rounding from Step 1
    try:
        tax_rate = get_tax_rate(req.country_code, req.tax_type)
        tax_amount = round(converted_amount * tax_rate, 4)
        taxed_subtotal = round(converted_amount + tax_amount, 4)
    except TypeError as exc:
        tb = traceback.format_exc()
        push_log("error", f"TypeError: unsupported country '{req.country_code}'", {
            "payment_id": req.payment_id,
            "country_code": req.country_code,
            "tax_type": req.tax_type,
            "error": "TypeError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "TypeError",
            "message": f"unsupported country code: {req.country_code}",
            "payment_id": req.payment_id,
        })

    # ── Step 3: processing fee on taxed subtotal ──────────────────────────────
    # EC-3: taxed_subtotal == 0 when amount=0 → FIXED_FEE / 0 → ZeroDivisionError
    # EC-4: taxed_subtotal < 0 when amount<0 → fee is negative (no crash, bad data)
    # EC-6: fee = FIXED_FEE / taxed_subtotal is NOT a percentage — for micro-
    #        payments the flat fee can be many times the converted principal
    try:
        fee = calculate_payment_fee(taxed_subtotal)
        grand_total = round(taxed_subtotal + fee, 4)
    except ZeroDivisionError as exc:
        tb = traceback.format_exc()
        push_log("error", f"ZeroDivisionError: taxed subtotal is zero for payment {req.payment_id}", {
            "payment_id": req.payment_id,
            "amount": req.amount,
            "taxed_subtotal": taxed_subtotal,
            "error": "ZeroDivisionError",
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "ZeroDivisionError",
            "message": "payment amount must be greater than zero",
            "payment_id": req.payment_id,
        })

    push_log("info", f"International payment {req.payment_id} computed successfully", {
        "payment_id": req.payment_id,
        "exchange_rate": rate,
        "converted_amount": converted_amount,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "taxed_subtotal": taxed_subtotal,
        "fee": fee,
        "grand_total": grand_total,
        "to_currency": req.to_currency,
    })

    return {
        "payment_id": req.payment_id,
        # Step 1 output
        "original_amount": req.amount,
        "from_currency": req.from_currency,
        "exchange_rate": rate,
        "converted_amount": converted_amount,
        "to_currency": req.to_currency,
        # Step 2 output
        "country_code": req.country_code,
        "tax_type": req.tax_type,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "taxed_subtotal": taxed_subtotal,
        # Step 3 output
        "processing_fee": fee,
        "grand_total": grand_total,
        "status": "approved",
    }
