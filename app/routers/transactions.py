import traceback

from fastapi import APIRouter, HTTPException

from app.logger import push_log
from app.services.transaction_service import lookup_transaction

router = APIRouter()


@router.get("/transaction/{transaction_id}")
def get_transaction(transaction_id: str):
    """Look up a transaction. Raises 500 when transaction_id is non-numeric."""
    push_log("info", f"Looking up transaction {transaction_id}", {
        "transaction_id": transaction_id,
    })
    try:
        txn_int_id, txn = lookup_transaction(transaction_id)
        if txn is None:
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
