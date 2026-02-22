MOCK_TRANSACTIONS: dict[int, dict] = {
    1001: {"payment_id": "PAY-001", "amount": 99.99,  "currency": "USD", "status": "completed"},
    1002: {"payment_id": "PAY-002", "amount": 250.00, "currency": "EUR", "status": "pending"},
    1003: {"payment_id": "PAY-003", "amount": 45.50,  "currency": "GBP", "status": "failed"},
}


def lookup_transaction(transaction_id: str) -> tuple[int, dict | None]:
    """Look up a transaction by its string ID.

    BUG: ValueError raised when transaction_id contains non-numeric characters.
    Fix: wrap int() in a try/except ValueError.
    """
    txn_int_id = int(transaction_id)  # ValueError if non-numeric
    return txn_int_id, MOCK_TRANSACTIONS.get(txn_int_id)
