import json
import traceback

from fastapi import APIRouter, HTTPException

from app.logger import push_log
from app.models.schemas import AccountSummary
from app.services.account_service import fetch_account

router = APIRouter()


@router.get("/account/{account_id}", response_model=AccountSummary)
def get_account(account_id: str):
    """Return full account details including parsed metadata.

    CODE IS CORRECT — all accounts are fetched and processed identically.
    ACC-003 and ACC-005 have corrupted metadata written by a previous
    incident, so json.loads raises JSONDecodeError for those rows while
    every other account is served without error.

    Trigger the bug:
        GET /account/ACC-003   →  500 JSONDecodeError (unquoted-key corruption)
        GET /account/ACC-005   →  500 JSONDecodeError (truncated-write corruption)
    Healthy accounts:
        GET /account/ACC-001   →  200 OK
        GET /account/ACC-002   →  200 OK
        GET /account/ACC-004   →  200 OK
    """
    push_log("info", f"Account lookup: {account_id}", {"account_id": account_id})
    try:
        account = fetch_account(account_id)
        if account is None:
            push_log("warn", f"Account {account_id} not found", {
                "account_id": account_id,
                "http_status": 404,
            })
            raise HTTPException(status_code=404, detail={
                "error": "not_found",
                "account_id": account_id,
            })
        push_log("info", f"Account {account_id} fetched successfully", {
            "account_id": account_id,
            "owner": account["owner"],
            "status": account["status"],
        })
        return AccountSummary(**account)
    except json.JSONDecodeError as exc:
        tb = traceback.format_exc()
        push_log("error", f"JSONDecodeError for account {account_id}: metadata corrupted in DB", {
            "account_id": account_id,
            "error": "JSONDecodeError",
            "detail": str(exc),
            "traceback": tb,
            "http_status": 500,
        })
        raise HTTPException(status_code=500, detail={
            "error": "JSONDecodeError",
            "message": f"account metadata is corrupted in the database: {exc}",
            "account_id": account_id,
        })
