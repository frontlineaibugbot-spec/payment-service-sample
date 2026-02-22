REFUND_REASON_CODES: dict[str, str] = {
    "duplicate": "RF001",
    "defective": "RF002",
    "not_received": "RF003",
}


def get_reason_code(reason: str) -> str:
    """Return the internal code for a refund reason.

    BUG: KeyError raised when reason is not one of the known codes.
    Fix: use REFUND_REASON_CODES.get(reason) and handle None.
    """
    return REFUND_REASON_CODES[reason]
