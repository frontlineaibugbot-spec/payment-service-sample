"""
Flow 2 – Account-gated Batch Refund
=====================================
Steps
  1. Fetch account and validate it exists (account metadata may be corrupted)
  2. For each refund item:
       a. Look up the original transaction
       b. Guard that refund_amount does not exceed transaction amount
       c. Resolve the refund reason code
       d. Approve and record the refund
  3. Return per-item results with a summary

Known edge cases (all trigger real failures or silent data corruption):

  EC-1  JSONDecodeError – same as checkout: ACC-003 / ACC-005 have bad JSON
        stored in the metadata column. fetch_account() blows up before we can
        even check whether the account exists.
        Trigger: account_id = "ACC-003" or "ACC-005"

  EC-2  ValueError from non-numeric transaction_id – lookup_transaction() calls
        int(transaction_id). IDs like "TXN-1001" or "abc" raise ValueError,
        which is caught and surfaced as HTTP 500.
        Trigger: transaction_id = "TXN-1001" (any non-numeric string)

  EC-3  Float comparison trap (silent wrong approval) – the over-refund guard
        uses `refund_amount > txn["amount"]`. Due to IEEE-754:
          • 99.9899999 is NOT > 99.99  → passes the guard (should fail)
          • 99.990001  IS  > 99.99     → blocked correctly
          • 99.99      is NOT > 99.99  → passes (full refund looks valid but
                                          a second call also passes → double-refund)
        There is no idempotency key or lock, so concurrent calls with the same
        transaction_id can both pass the guard and double-refund.
        Trigger: refund_amount=99.9899999 against transaction 1001 (amount=99.99)

  EC-4  KeyError from unknown refund reason – get_reason_code() subscripts a
        dict directly. Any reason outside {duplicate, defective, not_received}
        raises KeyError, surfaced as HTTP 500.
        Trigger: reason = "fraud" or any unlisted string

  EC-5  Transaction not found (404 per item) – lookup_transaction returns
        (id, None) when the numeric id is not in MOCK_TRANSACTIONS.
        The item is skipped with an error entry; processing continues.
        Trigger: transaction_id = "9999" (numeric but absent)

  EC-6  Partial failure non-atomicity – there is no database transaction or
        rollback. If item 1 is approved and item 2 raises KeyError, item 1's
        refund is already "issued" with no compensation path.
        Trigger: mix a valid refund item with an item using reason="fraud"

  EC-7  Empty refunds list → misleading HTTP 200 – an empty list passes
        validation, produces an empty results array, and returns 200 OK with
        processed=0. No error is raised.
        Trigger: refunds = []
"""

import time
import traceback

from fastapi import APIRouter, HTTPException

from app.logger import push_log
from app.models.schemas import BatchRefundRequest
from app.services.account_service import fetch_account
from app.services.refund_service import get_reason_code
from app.services.transaction_service import lookup_transaction

router = APIRouter()


@router.post("/refund-batch")
def batch_refund(req: BatchRefundRequest):
    """
    Validate account, then process each refund item independently.

    Buggy edge cases: EC-1 through EC-7 (see module docstring).
    """
    push_log("info", f"Batch refund requested for account {req.account_id}", {
        "account_id": req.account_id,
        "refund_count": len(req.refunds),
    })

    # ── Step 1: fetch account ─────────────────────────────────────────────────
    # EC-1: JSONDecodeError for ACC-003 / ACC-005 (corrupted metadata column)
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
        raise HTTPException(status_code=404, detail={
            "error": "not_found",
            "account_id": req.account_id,
        })

    # EC-7: empty list silently returns 200 with processed=0
    results = []
    errors = []

    # ── Step 2: process each refund item ─────────────────────────────────────
    for item in req.refunds:

        # (a) Look up original transaction
        # EC-2: ValueError when transaction_id is non-numeric ("TXN-1001")
        try:
            txn_int_id, txn = lookup_transaction(item.transaction_id)
        except ValueError as exc:
            tb = traceback.format_exc()
            push_log("error", f"ValueError: non-numeric transaction_id '{item.transaction_id}'", {
                "transaction_id": item.transaction_id,
                "account_id": req.account_id,
                "error": "ValueError",
                "traceback": tb,
                "http_status": 500,
            })
            raise HTTPException(status_code=500, detail={
                "error": "ValueError",
                "message": f"invalid transaction_id '{item.transaction_id}': must be numeric",
                "transaction_id": item.transaction_id,
            })

        # EC-5: transaction not found — record error and continue
        if txn is None:
            push_log("warn", f"Transaction {item.transaction_id} not found; skipping refund", {
                "transaction_id": item.transaction_id,
                "account_id": req.account_id,
            })
            errors.append({
                "transaction_id": item.transaction_id,
                "error": "not_found",
                "message": f"transaction {item.transaction_id} does not exist",
            })
            continue

        # (b) Guard: refund must not exceed original amount
        # EC-3: float comparison trap
        #   99.9899999 > 99.99  → False  (passes guard — should be blocked)
        #   99.990001  > 99.99  → True   (blocked correctly)
        #   Second call with same item: still passes (no idempotency / locking)
        if item.refund_amount > txn["amount"]:
            push_log("warn", f"Refund amount {item.refund_amount} exceeds transaction {txn_int_id} amount {txn['amount']}", {
                "transaction_id": item.transaction_id,
                "refund_amount": item.refund_amount,
                "original_amount": txn["amount"],
            })
            errors.append({
                "transaction_id": item.transaction_id,
                "error": "amount_exceeded",
                "message": (
                    f"refund_amount {item.refund_amount} exceeds "
                    f"original transaction amount {txn['amount']}"
                ),
            })
            continue

        # (c) Resolve reason code
        # EC-4: KeyError for any reason not in {duplicate, defective, not_received}
        # EC-6: if a previous item already succeeded, it is NOT rolled back
        try:
            reason_code = get_reason_code(item.reason)
        except KeyError as exc:
            tb = traceback.format_exc()
            push_log("error", f"Unknown refund reason '{item.reason}' for transaction {item.transaction_id}", {
                "transaction_id": item.transaction_id,
                "reason": item.reason,
                "error": "KeyError",
                "traceback": tb,
                "http_status": 500,
            })
            raise HTTPException(status_code=500, detail={
                "error": "KeyError",
                "message": f"unknown refund reason: '{item.reason}'",
                "transaction_id": item.transaction_id,
                # EC-6: refunds processed so far are NOT reversed
                "already_processed": [r["refund_id"] for r in results],
            })

        # (d) Approve refund
        refund_id = f"REF-{txn_int_id}-{int(time.time())}"
        push_log("info", f"Refund {refund_id} approved for transaction {txn_int_id}", {
            "refund_id": refund_id,
            "transaction_id": item.transaction_id,
            "account_id": req.account_id,
            "refund_amount": item.refund_amount,
            "reason_code": reason_code,
        })
        results.append({
            "refund_id": refund_id,
            "transaction_id": item.transaction_id,
            "original_amount": txn["amount"],
            "refund_amount": item.refund_amount,
            "reason_code": reason_code,
            "status": "approved",
        })

    push_log("info", f"Batch refund complete for account {req.account_id}", {
        "account_id": req.account_id,
        "processed": len(results),
        "failed": len(errors),
    })

    return {
        "account_id": req.account_id,
        "processed": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }
